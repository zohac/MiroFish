"""
Report API路由
提供模拟报告生成、获取、对话等接口
"""

import json
import os
import traceback
import threading
from flask import request, jsonify, send_file

from . import report_bp
from ..config import Config
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.simulation_manager import SimulationManager
from ..services.simulation_runner import SimulationRunner, RunnerStatus
from ..services.zep_graph_memory_updater import ZepGraphMemoryManager
from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger
from ..utils.locale import t, use_locale
from ..utils.zep_lifecycle import (
    graph_lifecycle_lock,
    register_graph_reader,
    unregister_graph_reader,
)

logger = get_logger('mirofish.api.report')


# ============== 报告生成接口 ==============

@report_bp.route('/generate', methods=['POST'])
def generate_report():
    """
    生成模拟分析报告（异步任务）
    
    这是一个耗时操作，接口会立即返回task_id，
    使用 GET /api/report/generate/status 查询进度
    
    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",    // 必填，模拟ID
            "force_regenerate": false        // 可选，强制重新生成
        }
    
    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",
                "status": "generating",
                "message": "报告生成任务已启动"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t('api.requireSimulationId')
            }), 400

        force_regenerate = data.get('force_regenerate', False)
        if not isinstance(force_regenerate, bool):
            return jsonify({
                "success": False,
                "error": "force_regenerate must be a JSON boolean",
            }), 400

        replay_mode = str(data.get('replay_mode', 'live')).strip().lower()
        if replay_mode not in ('live', 'replay_frozen'):
            return jsonify({
                "success": False,
                "error": "replay_mode must be either 'live' or 'replay_frozen'",
            }), 400
        
        # Résolution du profil LLM optionnel (Story 013-1)
        profile_id = data.get('profile_id') or data.get('report_profile_id')
        profile_data = data.get('llm_profile')
        profile = None
        if profile_id:
            from ..models.report_llm_profile import ReportLLMProfile
            profile = ReportLLMProfile.get_standard_profile(str(profile_id))
            if not profile:
                # Rejet explicite : un repli silencieux sur le modèle global
                # ferait croire à un benchmark sur un modèle qui n'a jamais
                # été exécuté (Story 013-5, AC2). Le garde-fou ne s'efface
                # pas devant un corps `llm_profile` concurrent.
                return jsonify({
                    "success": False,
                    "error": (
                        f"Unknown report profile '{profile_id}'. "
                        f"Available profiles: "
                        f"{', '.join(ReportLLMProfile.standard_profile_ids())}"
                    ),
                }), 400
            if profile_data:
                # Les deux voies sont exclusives : le choix doit être univoque,
                # sinon le client ne sait plus quel profil il a demandé.
                return jsonify({
                    "success": False,
                    "error": (
                        "Fournir soit 'profile_id', soit 'llm_profile' — "
                        "pas les deux à la fois."
                    ),
                }), 400
        elif profile_data and isinstance(profile_data, dict):
            from ..models.report_llm_profile import ReportLLMProfile
            try:
                # Profil client aligné sur le catalogue : le navigateur choisit
                # le modèle et l'effort, jamais la destination ni la clé
                # (Story 013-5, décision du 20 octobre 2026).
                profile = ReportLLMProfile.from_client(profile_data)
            except Exception as e:
                return jsonify({"success": False, "error": f"Invalid llm_profile: {e}"}), 400

        # 获取模拟信息
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": t('api.simulationNotFound', id=simulation_id)
            }), 404

        run_state = SimulationRunner.get_run_state(simulation_id)
        updater = ZepGraphMemoryManager.get_updater(simulation_id)
        active_statuses = {
            RunnerStatus.STARTING,
            RunnerStatus.RUNNING,
            RunnerStatus.PAUSED,
            RunnerStatus.STOPPING,
        }
        if updater is not None or (
            run_state is not None and run_state.runner_status in active_statuses
        ):
            return jsonify({
                "success": False,
                "error": (
                    "Simulation or Zep graph ingestion is still active; "
                    "wait for a terminal run status before generating a report"
                ),
                "ingestion_pending": updater is not None,
            }), 409
        successful_terminal_statuses = {
            RunnerStatus.COMPLETED,
            RunnerStatus.STOPPED,
        }
        if (
            run_state is None
            or run_state.runner_status not in successful_terminal_statuses
        ):
            return jsonify({
                "success": False,
                "error": (
                    "A successfully completed or stopped simulation is required "
                    "before generating a report"
                ),
            }), 409

        # 获取项目信息
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": t('api.projectNotFound', id=state.project_id)
            }), 404
        
        if project.status != ProjectStatus.GRAPH_COMPLETED:
            return jsonify({
                "success": False,
                "error": "The project graph must be completely built before reporting",
            }), 409

        graph_id = project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": t('api.missingGraphIdEnsure')
            }), 400
        if state.graph_id and state.graph_id != graph_id:
            return jsonify({
                "success": False,
                "error": (
                    "The simulation references an older graph; prepare it "
                    "again before generating a report"
                ),
            }), 409
        
        simulation_requirement = project.simulation_requirement
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": t('api.missingSimRequirement')
            }), 400
        
        # 提前生成 report_id，以便立即返回给前端
        import uuid
        report_id = f"report_{uuid.uuid4().hex[:12]}"
        
        # Register the background report as a graph reader under the same lock
        # used by graph deletion and updater startup. A lock itself cannot be
        # acquired in this request thread and released by the worker, so the
        # durable reader registration is the cross-thread lease.
        with graph_lifecycle_lock(graph_id):
            refreshed_state = manager.get_simulation(simulation_id)
            refreshed_project = (
                ProjectManager.get_project(refreshed_state.project_id)
                if refreshed_state
                else None
            )
            refreshed_run_state = SimulationRunner.get_run_state(simulation_id)
            refreshed_updater = ZepGraphMemoryManager.get_updater(simulation_id)
            if (
                refreshed_state is None
                or refreshed_project is None
                or refreshed_project.graph_id != graph_id
                or refreshed_project.status != ProjectStatus.GRAPH_COMPLETED
                or (
                    refreshed_state.graph_id
                    and refreshed_state.graph_id != graph_id
                )
            ):
                return jsonify({
                    "success": False,
                    "error": "The project graph changed while reporting was starting",
                }), 409
            if refreshed_updater is not None or (
                refreshed_run_state is not None
                and refreshed_run_state.runner_status in active_statuses
            ):
                return jsonify({
                    "success": False,
                    "error": (
                        "Simulation or Zep graph ingestion became active; "
                        "retry after it reaches a terminal state"
                    ),
                    "ingestion_pending": refreshed_updater is not None,
                }), 409
            if (
                refreshed_run_state is None
                or refreshed_run_state.runner_status
                not in successful_terminal_statuses
            ):
                return jsonify({
                    "success": False,
                    "error": (
                        "A successfully completed or stopped simulation is "
                        "required before generating a report"
                    ),
                }), 409

            # Cached-report reuse is now part of the same atomic barrier, so a
            # concurrent rerun cannot make the returned report stale between
            # the status check and response.
            if not force_regenerate:
                existing_report = ReportManager.get_report_by_simulation(
                    simulation_id
                )
                if (
                    existing_report
                    and existing_report.status == ReportStatus.COMPLETED
                ):
                    return jsonify({
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "report_id": existing_report.report_id,
                            "status": "completed",
                            "message": t('api.reportAlreadyExists'),
                            "already_generated": True
                        }
                    })

            task_manager = TaskManager()
            task_id = task_manager.create_task(
                task_type="report_generate",
                metadata={
                    "simulation_id": simulation_id,
                    "graph_id": graph_id,
                    "report_id": report_id
                }
            )
            current_locale = state.locale
            register_graph_reader(graph_id, report_id)

            def run_generate():
                with use_locale(current_locale):
                    generate_in_locale()

            def generate_in_locale():
                try:
                    task_manager.update_task(
                        task_id,
                        status=TaskStatus.PROCESSING,
                        progress=0,
                        message=t('api.initReportAgent')
                    )

                    agent = ReportAgent(
                        graph_id=graph_id,
                        simulation_id=simulation_id,
                        simulation_requirement=simulation_requirement,
                        locale=current_locale,
                        profile=profile,
                        replay_mode=replay_mode,
                    )

                    def progress_callback(stage, progress, message):
                        task_manager.update_task(
                            task_id,
                            progress=progress,
                            message=f"[{stage}] {message}"
                        )

                    report = agent.generate_report(
                        progress_callback=progress_callback,
                        report_id=report_id
                    )
                    ReportManager.save_report(report)

                    if report.status == ReportStatus.COMPLETED:
                        task_manager.complete_task(
                            task_id,
                            result={
                                "report_id": report.report_id,
                                "simulation_id": simulation_id,
                                "status": "completed",
                                "replay_mode": replay_mode,
                            }
                        )
                    else:
                        task_manager.fail_task(
                            task_id,
                            report.error or t('api.reportGenerateFailed')
                        )
                except Exception as e:
                    logger.error(f"报告生成失败: {str(e)}")
                    task_manager.fail_task(task_id, str(e))
                finally:
                    unregister_graph_reader(graph_id, report_id)
                    if replay_mode != "replay_frozen":
                        try:
                            from ..services.simulation_runner import SimulationRunner
                            SimulationRunner.close_simulation_environment(simulation_id)
                        except Exception as env_err:
                            logger.warning(f"Clôture environnement différée dans report.py ({simulation_id}): {env_err}")

            try:
                thread = threading.Thread(target=run_generate, daemon=True)
                thread.start()
            except Exception:
                unregister_graph_reader(graph_id, report_id)
                raise
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "report_id": report_id,
                "task_id": task_id,
                "profile_id": getattr(profile, "profile_id", None),
                "replay_mode": replay_mode,
                "status": "generating",
                "message": t('api.reportGenerateStarted'),
                "already_generated": False
            }
        })
        
    except Exception as e:
        logger.error(f"启动报告生成任务失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/generate/status', methods=['POST'])
def get_generate_status():
    """
    查询报告生成任务进度
    
    请求（JSON）：
        {
            "task_id": "task_xxxx",         // 可选，generate返回的task_id
            "simulation_id": "sim_xxxx"     // 可选，模拟ID
        }
    
    返回：
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|failed",
                "progress": 45,
                "message": "..."
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')
        
        # 如果提供了simulation_id，先检查是否已有完成的报告
        if simulation_id:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": existing_report.report_id,
                        "status": "completed",
                        "progress": 100,
                        "message": t('api.reportGenerated'),
                        "already_completed": True
                    }
                })
        
        if not task_id:
            return jsonify({
                "success": False,
                "error": t('api.requireTaskOrSimId')
            }), 400
        
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        
        if not task:
            return jsonify({
                "success": False,
                "error": t('api.taskNotFound', id=task_id)
            }), 404
        
        return jsonify({
            "success": True,
            "data": task.to_dict()
        })
        
    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============== 报告获取接口 ==============

@report_bp.route('/<report_id>', methods=['GET'])
def get_report(report_id: str):
    """
    获取报告详情
    
    返回：
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                "simulation_id": "sim_xxxx",
                "status": "completed",
                "outline": {...},
                "markdown_content": "...",
                "created_at": "...",
                "completed_at": "..."
            }
        }
    """
    try:
        report = ReportManager.get_report(report_id)
        
        if not report:
            return jsonify({
                "success": False,
                "error": t('api.reportNotFound', id=report_id)
            }), 404
        
        return jsonify({
            "success": True,
            "data": report.to_dict()
        })
        
    except Exception as e:
        logger.error(f"获取报告失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/by-simulation/<simulation_id>', methods=['GET'])
def get_report_by_simulation(simulation_id: str):
    """
    根据模拟ID获取报告
    
    返回：
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                ...
            }
        }
    """
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)
        
        if not report:
            return jsonify({
                "success": False,
                "error": t('api.noReportForSim', id=simulation_id),
                "has_report": False
            }), 404
        
        return jsonify({
            "success": True,
            "data": report.to_dict(),
            "has_report": True
        })
        
    except Exception as e:
        logger.error(f"获取报告失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/list', methods=['GET'])
def list_reports():
    """
    列出所有报告
    
    Query参数：
        simulation_id: 按模拟ID过滤（可选）
        limit: 返回数量限制（默认50）
    
    返回：
        {
            "success": true,
            "data": [...],
            "count": 10
        }
    """
    try:
        simulation_id = request.args.get('simulation_id')
        limit = request.args.get('limit', 50, type=int)
        
        reports = ReportManager.list_reports(
            simulation_id=simulation_id,
            limit=limit
        )
        
        return jsonify({
            "success": True,
            "data": [r.to_dict() for r in reports],
            "count": len(reports)
        })
        
    except Exception as e:
        logger.error(f"列出报告失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/download', methods=['GET'])
def download_report(report_id: str):
    """
    下载报告（Markdown格式）
    
    返回Markdown文件
    """
    try:
        report = ReportManager.get_report(report_id)
        
        if not report:
            return jsonify({
                "success": False,
                "error": t('api.reportNotFound', id=report_id)
            }), 404
        
        md_path = ReportManager._get_report_markdown_path(report_id)
        
        if not os.path.exists(md_path):
            # 如果MD文件不存在，生成一个临时文件
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(report.markdown_content)
                temp_path = f.name
            
            return send_file(
                temp_path,
                as_attachment=True,
                download_name=f"{report_id}.md"
            )
        
        return send_file(
            md_path,
            as_attachment=True,
            download_name=f"{report_id}.md"
        )
        
    except Exception as e:
        logger.error(f"下载报告失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>', methods=['DELETE'])
def delete_report(report_id: str):
    """删除报告"""
    try:
        success = ReportManager.delete_report(report_id)
        
        if not success:
            return jsonify({
                "success": False,
                "error": t('api.reportNotFound', id=report_id)
            }), 404
        
        return jsonify({
            "success": True,
            "message": t('api.reportDeleted', id=report_id)
        })
        
    except Exception as e:
        logger.error(f"删除报告失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Report Agent对话接口 ==============

@report_bp.route('/chat', methods=['POST'])
def chat_with_report_agent():
    """
    与Report Agent对话
    
    Report Agent可以在对话中自主调用检索工具来回答问题
    
    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",        // 必填，模拟ID
            "message": "请解释一下舆情走向",    // 必填，用户消息
            "chat_history": [                   // 可选，对话历史
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."}
            ]
        }
    
    返回：
        {
            "success": true,
            "data": {
                "response": "Agent回复...",
                "tool_calls": [调用的工具列表],
                "sources": [信息来源]
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        message = data.get('message')
        chat_history = data.get('chat_history', [])
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t('api.requireSimulationId')
            }), 400

        if not message:
            return jsonify({
                "success": False,
                "error": t('api.requireMessage')
            }), 400
        
        # 获取模拟和项目信息
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": t('api.simulationNotFound', id=simulation_id)
            }), 404

        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": t('api.projectNotFound', id=state.project_id)
            }), 404
        
        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": t('api.missingGraphId')
            }), 400
        
        simulation_requirement = project.simulation_requirement or ""
        
        # 创建Agent并进行对话
        agent = ReportAgent(
            graph_id=graph_id,
            simulation_id=simulation_id,
            simulation_requirement=simulation_requirement,
            locale=state.locale,
        )
        
        with use_locale(state.locale):
            result = agent.chat(message=message, chat_history=chat_history)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"对话失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 报告进度与分章节接口 ==============

@report_bp.route('/<report_id>/progress', methods=['GET'])
def get_report_progress(report_id: str):
    """
    获取报告生成进度（实时）
    
    返回：
        {
            "success": true,
            "data": {
                "status": "generating",
                "progress": 45,
                "message": "正在生成章节: 关键发现",
                "current_section": "关键发现",
                "completed_sections": ["执行摘要", "模拟背景"],
                "updated_at": "2025-12-09T..."
            }
        }
    """
    try:
        progress = ReportManager.get_progress(report_id)
        
        if not progress:
            return jsonify({
                "success": False,
                "error": t('api.reportProgressNotAvail', id=report_id)
            }), 404
        
        return jsonify({
            "success": True,
            "data": progress
        })
        
    except Exception as e:
        logger.error(f"获取报告进度失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/sections', methods=['GET'])
def get_report_sections(report_id: str):
    """
    获取已生成的章节列表（分章节输出）
    
    前端可以轮询此接口获取已生成的章节内容，无需等待整个报告完成
    
    返回：
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                "sections": [
                    {
                        "filename": "section_01.md",
                        "section_index": 1,
                        "content": "## 执行摘要\\n\\n..."
                    },
                    ...
                ],
                "total_sections": 3,
                "is_complete": false
            }
        }
    """
    try:
        sections = ReportManager.get_generated_sections(report_id)
        
        # 获取报告状态
        report = ReportManager.get_report(report_id)
        is_complete = report is not None and report.status == ReportStatus.COMPLETED
        
        return jsonify({
            "success": True,
            "data": {
                "report_id": report_id,
                "sections": sections,
                "total_sections": len(sections),
                "is_complete": is_complete
            }
        })
        
    except Exception as e:
        logger.error(f"获取章节列表失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/section/<int:section_index>', methods=['GET'])
def get_single_section(report_id: str, section_index: int):
    """
    获取单个章节内容
    
    返回：
        {
            "success": true,
            "data": {
                "filename": "section_01.md",
                "content": "## 执行摘要\\n\\n..."
            }
        }
    """
    try:
        section_path = ReportManager._get_section_path(report_id, section_index)
        
        if not os.path.exists(section_path):
            return jsonify({
                "success": False,
                "error": t('api.sectionNotFound', index=f"{section_index:02d}")
            }), 404
        
        with open(section_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return jsonify({
            "success": True,
            "data": {
                "filename": f"section_{section_index:02d}.md",
                "section_index": section_index,
                "content": content
            }
        })
        
    except Exception as e:
        logger.error(f"获取章节内容失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 报告状态检查接口 ==============

@report_bp.route('/check/<simulation_id>', methods=['GET'])
def check_report_status(simulation_id: str):
    """
    检查模拟是否有报告，以及报告状态
    
    用于前端判断是否解锁Interview功能
    
    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "has_report": true,
                "report_status": "completed",
                "report_id": "report_xxxx",
                "interview_unlocked": true
            }
        }
    """
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)
        
        has_report = report is not None
        report_status = report.status.value if report else None
        report_id = report.report_id if report else None
        
        # 只有报告完成后才解锁interview
        interview_unlocked = has_report and report.status == ReportStatus.COMPLETED
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "has_report": has_report,
                "report_status": report_status,
                "report_id": report_id,
                "interview_unlocked": interview_unlocked
            }
        })
        
    except Exception as e:
        logger.error(f"检查报告状态失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Agent 日志接口 ==============

@report_bp.route('/<report_id>/agent-log', methods=['GET'])
def get_agent_log(report_id: str):
    """
    获取 Report Agent 的详细执行日志
    
    实时获取报告生成过程中的每一步动作，包括：
    - 报告开始、规划开始/完成
    - 每个章节的开始、工具调用、LLM响应、完成
    - 报告完成或失败
    
    Query参数：
        from_line: 从第几行开始读取（可选，默认0，用于增量获取）
    
    返回：
        {
            "success": true,
            "data": {
                "logs": [
                    {
                        "timestamp": "2025-12-13T...",
                        "elapsed_seconds": 12.5,
                        "report_id": "report_xxxx",
                        "action": "tool_call",
                        "stage": "generating",
                        "section_title": "执行摘要",
                        "section_index": 1,
                        "details": {
                            "tool_name": "insight_forge",
                            "parameters": {...},
                            ...
                        }
                    },
                    ...
                ],
                "total_lines": 25,
                "from_line": 0,
                "has_more": false
            }
        }
    """
    try:
        from_line = request.args.get('from_line', 0, type=int)
        
        log_data = ReportManager.get_agent_log(report_id, from_line=from_line)
        
        return jsonify({
            "success": True,
            "data": log_data
        })
        
    except Exception as e:
        logger.error(f"获取Agent日志失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/agent-log/stream', methods=['GET'])
def stream_agent_log(report_id: str):
    """
    获取完整的 Agent 日志（一次性获取全部）
    
    返回：
        {
            "success": true,
            "data": {
                "logs": [...],
                "count": 25
            }
        }
    """
    try:
        logs = ReportManager.get_agent_log_stream(report_id)
        
        return jsonify({
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        })
        
    except Exception as e:
        logger.error(f"获取Agent日志失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 控制台日志接口 ==============

@report_bp.route('/<report_id>/console-log', methods=['GET'])
def get_console_log(report_id: str):
    """
    获取 Report Agent 的控制台输出日志
    
    实时获取报告生成过程中的控制台输出（INFO、WARNING等），
    这与 agent-log 接口返回的结构化 JSON 日志不同，
    是纯文本格式的控制台风格日志。
    
    Query参数：
        from_line: 从第几行开始读取（可选，默认0，用于增量获取）
    
    返回：
        {
            "success": true,
            "data": {
                "logs": [
                    "[19:46:14] INFO: 搜索完成: 找到 15 条相关事实",
                    "[19:46:14] INFO: 图谱搜索: graph_id=xxx, query=...",
                    ...
                ],
                "total_lines": 100,
                "from_line": 0,
                "has_more": false
            }
        }
    """
    try:
        from_line = request.args.get('from_line', 0, type=int)
        
        log_data = ReportManager.get_console_log(report_id, from_line=from_line)
        
        return jsonify({
            "success": True,
            "data": log_data
        })
        
    except Exception as e:
        logger.error(f"获取控制台日志失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/console-log/stream', methods=['GET'])
def stream_console_log(report_id: str):
    """
    获取完整的控制台日志（一次性获取全部）
    
    返回：
        {
            "success": true,
            "data": {
                "logs": [...],
                "count": 100
            }
        }
    """
    try:
        logs = ReportManager.get_console_log_stream(report_id)
        
        return jsonify({
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        })
        
    except Exception as e:
        logger.error(f"获取控制台日志失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 工具调用接口（供调试使用）==============

@report_bp.route('/tools/search', methods=['POST'])
def search_graph_tool():
    """
    图谱搜索工具接口（供调试使用）
    
    请求（JSON）：
        {
            "graph_id": "mirofish_xxxx",
            "query": "搜索查询",
            "limit": 10
        }
    """
    try:
        data = request.get_json() or {}
        
        graph_id = data.get('graph_id')
        query = data.get('query')
        limit = data.get('limit', 10)
        
        if not graph_id or not query:
            return jsonify({
                "success": False,
                "error": t('api.requireGraphIdAndQuery')
            }), 400
        
        from ..services.zep_tools import ZepToolsService
        
        tools = ZepToolsService()
        result = tools.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit
        )
        
        return jsonify({
            "success": True,
            "data": result.to_dict()
        })
        
    except Exception as e:
        logger.error(f"图谱搜索失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/tools/statistics', methods=['POST'])
def get_graph_statistics_tool():
    """
    图谱统计工具接口（供调试使用）
    
    请求（JSON）：
        {
            "graph_id": "mirofish_xxxx"
        }
    """
    try:
        data = request.get_json() or {}
        
        graph_id = data.get('graph_id')
        
        if not graph_id:
            return jsonify({
                "success": False,
                "error": t('api.requireGraphId')
            }), 400
        
        from ..services.zep_tools import ZepToolsService
        
        tools = ZepToolsService()
        result = tools.get_graph_statistics(graph_id)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"获取图谱统计失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Endpoints Qualité & Dossier d'Audit (Story 011-5, FR-09, FR-10, C9, C10) ==============

@report_bp.route('/<report_id>/quality', methods=['GET'])
def get_report_quality(report_id: str):
    """
    Consulte le rapport de validation de la barrière ReportQualityGate.
    
    Retourne le contenu de quality_checks.json contenant la liste des 5 contrôles,
    le résumé des diagnostics et le booléen is_publishable.
    """
    try:
        report = ReportManager.get_report(report_id)
        quality_file = ReportManager._get_quality_path(report_id)
        
        if not os.path.exists(quality_file):
            # Tenter de charger depuis la simulation si présente
            sim_quality_path = ""
            if report and report.simulation_id:
                sim_quality_path = os.path.join(Config.UPLOAD_FOLDER, "simulations", report.simulation_id, "quality_checks.json")
            if sim_quality_path and os.path.exists(sim_quality_path):
                quality_file = sim_quality_path
            else:
                return jsonify({
                    "success": False,
                    "error": f"Résultats de qualité non trouvés pour le rapport {report_id}",
                }), 404
        
        from ..models.report_quality import QualityGateResult
        result = QualityGateResult.load_from_file(quality_file)
        
        return jsonify({
            "success": True,
            "data": result.to_dict()
        })
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du statut qualité du rapport {report_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/audit/download', methods=['GET'])
def download_report_audit(report_id: str):
    """
    Télécharge l'archive ZIP autonome du dossier d'audit complet (FR-10, C10).
    
    L'archive simulation_audit_<sim_id>.zip réunit les 8 artefacts de preuve canoniques
    avec leurs empreintes cryptographiques checksums.sha256.
    """
    try:
        report = ReportManager.get_report(report_id)
        if not report:
            return jsonify({
                "success": False,
                "error": f"Rapport {report_id} introuvable",
            }), 404
            
        if report.status == ReportStatus.GENERATING:
            return jsonify({
                "success": False,
                "error": f"Rapport {report_id} en cours de génération. Dossier d'audit non finalisé.",
            }), 409

        simulation_id = report.simulation_id
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Identifiant de simulation introuvable dans le rapport",
            }), 400
            
        from ..services.simulation_audit_service import SimulationAuditService
        audit_service = SimulationAuditService(simulation_id=simulation_id, report_id=report_id)
        zip_path = audit_service.get_audit_package_path()
        
        # Conserver simulation_audit_<sim_id>.zip comme nom de téléchargement canonique pour le client
        # tout en servant le binaire du zip isolé per-report résolu par audit_service
        download_name = f"simulation_audit_{simulation_id}.zip"
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=download_name,
            mimetype="application/zip",
        )
    except Exception as e:
        logger.error(f"Erreur lors du téléchargement de l'audit pour le rapport {report_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/simulation/<simulation_id>/audit/download', methods=['GET'])
def download_simulation_audit(simulation_id: str):
    """
    Télécharge l'archive ZIP autonome d'audit directement via l'identifiant de simulation (FR-10, C10).
    """
    try:
        from ..services.simulation_manager import SimulationManager
        sim_manager = SimulationManager()
        sim_state = sim_manager.get_simulation(simulation_id)
        sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", simulation_id)
        if not sim_state and not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": f"Simulation {simulation_id} introuvable",
            }), 404

        # Garde 409 si la simulation est activement en cours d'exécution
        if sim_state and hasattr(sim_state, "status"):
            st_val = sim_state.status.value if hasattr(sim_state.status, "value") else str(sim_state.status)
            if st_val.lower() in ("running", "generating"):
                return jsonify({
                    "success": False,
                    "error": f"Simulation {simulation_id} en cours d'exécution. Dossier d'audit non finalisé.",
                }), 409

        # Identifier le report_id via le helper canonique
        report = ReportManager.get_report_by_simulation(simulation_id)
        report_id = report.report_id if report else None

        if report and report.status == ReportStatus.GENERATING:
            return jsonify({
                "success": False,
                "error": f"Rapport {report_id} en cours de génération pour la simulation {simulation_id}.",
            }), 409

        from ..services.simulation_audit_service import SimulationAuditService
        audit_service = SimulationAuditService(simulation_id=simulation_id, report_id=report_id)
        zip_path = audit_service.get_audit_package_path()

        download_name = f"simulation_audit_{simulation_id}.zip"
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=download_name,
            mimetype="application/zip",
        )
    except Exception as e:
        logger.error(f"Erreur lors du téléchargement direct de l'audit pour la simulation {simulation_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Endpoints Multi-rapports et Historique (Story 013-3, FR-06) ==============

@report_bp.route('/profiles', methods=['GET'])
def list_report_profiles():
    """Expose le catalogue des profils LLM de rapport (Story 013-5, FR-08, AC2).

    Le catalogue est une liste fermée et ordonnée côté serveur : le navigateur
    ne reçoit que des métadonnées de modèle (identifiant, modèle, passerelle,
    effort, mode de facturation, plafonds). Aucune URL de passerelle, aucune
    clé d'API, aucun secret ne quitte le serveur (NFR-4).

    ``provider_id`` désigne la **passerelle qui a servi** (alias dérivé du
    ``base_url`` configuré), pas l'éditeur du modèle : les cinq profils
    partagent la même passerelle.

    Retour :
        {
            "success": true,
            "data": {
                "profiles": [
                    {
                        "profile_id": "flash-high",
                        "model": "gemini-3.8-flash",
                        "provider_id": "antigravity-local",
                        "reasoning_effort": "high",
                        "temperature": null,
                        "max_tokens": null,
                        "billing_mode": "metered",
                        "max_total_cost_usd": 2.0,
                        "max_wall_seconds": 900,
                        "base_url_configured": true
                    },
                    ...
                ],
                "count": 5
            }
        }
    """
    try:
        from ..models.report_llm_profile import ReportLLMProfile

        # Liste blanche stricte : même si la structure du profil évoluait, un
        # champ non listé ici ne pourrait pas être exposé au navigateur.
        public_fields = (
            "profile_id",
            "model",
            "provider_id",
            "reasoning_effort",
            "temperature",
            "max_tokens",
            "max_total_cost_usd",
            "max_wall_seconds",
            "billing_mode",
        )

        profiles = []
        for profile_id in ReportLLMProfile.standard_profile_ids():
            profile = ReportLLMProfile.get_standard_profile(profile_id)
            if profile is None:
                continue
            raw = profile.to_dict()
            entry = {field: raw.get(field) for field in public_fields}
            entry["base_url_configured"] = bool(raw.get("base_url_configured"))
            profiles.append(entry)

        # Ordre déterministe par identifiant : deux appels rendent la même
        # liste, dans le même ordre, quelle que soit la configuration.
        profiles.sort(key=lambda item: str(item.get("profile_id") or ""))

        return jsonify({
            "success": True,
            "data": {
                "profiles": profiles,
                "count": len(profiles),
            },
        })
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du catalogue de profils LLM: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Impossible de restituer le catalogue de profils LLM",
        }), 500


@report_bp.route('/simulation/<simulation_id>/history', methods=['GET'])
def get_simulation_report_history(simulation_id: str):
    """
    Retourne l'historique chronologique complet des rapports générés pour une simulation (Story 013-3, FR-06, AC4).
    
    Retour :
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "latest_report_id": "report_yyyy",
                "reports": [
                    {
                        "report_id": "report_1",
                        "created_at": "...",
                        "completed_at": "...",
                        "status": "completed",
                        "profile_id": "flash-medium",
                        "replay_mode": "replay_frozen",
                        "evidence_snapshot_id": "snap_...",
                        "publication_status": "verified_publishable",
                        "is_publishable": true,
                        "total_claims": 24,
                        "supported_claims": 22,
                        "unsupported_claims": 2,
                        "adoption_rate": 0.35
                    },
                    ...
                ],
                "count": 2
            }
        }
    """
    try:
        from ..services.simulation_manager import SimulationManager
        sim_manager = SimulationManager()
        sim_state = sim_manager.get_simulation(simulation_id)
        sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", simulation_id)
        if not sim_state and not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": f"Simulation {simulation_id} introuvable",
            }), 404

        history_list = ReportManager.list_reports_by_simulation(simulation_id)
        history_raw = ReportManager._load_history(simulation_id)
        latest_report_id = history_raw.get("latest_report_id")

        if not latest_report_id and history_list:
            latest_report_id = history_list[-1].get("report_id")

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "latest_report_id": latest_report_id,
                "reports": history_list,
                "count": len(history_list),
            }
        })
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'historique des rapports ({simulation_id}): {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@report_bp.route('/<report_id>/claims', methods=['GET'])
def get_report_claims(report_id: str):
    """
    Retourne le registre des assertions et vérifications propre au rapport spécifié (Story 013-3, FR-06, AC4).
    """
    try:
        report = ReportManager.get_report(report_id)
        if not report:
            return jsonify({
                "success": False,
                "error": f"Rapport {report_id} introuvable",
            }), 404

        rep_claims_path = ReportManager._get_report_claims_path(report_id)
        claims_data = None
        if os.path.exists(rep_claims_path):
            with open(rep_claims_path, "r", encoding="utf-8") as f:
                claims_data = json.load(f)
        else:
            # Repli sur simulation si copie miroir disponible UNIQUEMENT pour simulation legacy
            # ou si ce rapport est le seul / le plus récent (évite d'attribuer les claims du run N au run N-1)
            history_raw = ReportManager._load_history(report.simulation_id)
            reports_in_hist = history_raw.get("reports", [])
            latest_id = history_raw.get("latest_report_id")
            is_eligible_for_fallback = (
                not reports_in_hist
                or len(reports_in_hist) <= 1
                or latest_id == report_id
            )
            if is_eligible_for_fallback:
                sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", report.simulation_id)
                sim_claims_path = os.path.join(sim_dir, "report_claims.json")
                if os.path.exists(sim_claims_path):
                    with open(sim_claims_path, "r", encoding="utf-8") as f:
                        claims_data = json.load(f)

        if claims_data is None:
            return jsonify({
                "success": False,
                "error": f"Registre de claims introuvable pour le rapport {report_id}",
            }), 404

        return jsonify({
            "success": True,
            "data": claims_data,
        })
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des claims du rapport {report_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@report_bp.route('/<report_id>/cohort', methods=['GET'])
def get_report_cohort(report_id: str):
    """
    Retourne le tableau de couverture de cohorte propre au rapport spécifié (Story 013-3, FR-06, AC4).
    """
    try:
        report = ReportManager.get_report(report_id)
        if not report:
            return jsonify({
                "success": False,
                "error": f"Rapport {report_id} introuvable",
            }), 404

        rep_cohort_path = ReportManager._get_cohort_coverage_path(report_id)
        cohort_data = None
        if os.path.exists(rep_cohort_path):
            with open(rep_cohort_path, "r", encoding="utf-8") as f:
                cohort_data = json.load(f)
        else:
            # Repli sur simulation si copie miroir disponible UNIQUEMENT pour simulation legacy
            # ou si ce rapport est le seul / le plus récent (évite d'attribuer la cohorte du run N au run N-1)
            history_raw = ReportManager._load_history(report.simulation_id)
            reports_in_hist = history_raw.get("reports", [])
            latest_id = history_raw.get("latest_report_id")
            is_eligible_for_fallback = (
                not reports_in_hist
                or len(reports_in_hist) <= 1
                or latest_id == report_id
            )
            if is_eligible_for_fallback:
                sim_dir = os.path.join(Config.UPLOAD_FOLDER, "simulations", report.simulation_id)
                sim_cohort_path = os.path.join(sim_dir, "cohort_coverage.json")
                if os.path.exists(sim_cohort_path):
                    with open(sim_cohort_path, "r", encoding="utf-8") as f:
                        cohort_data = json.load(f)

        if cohort_data is None:
            return jsonify({
                "success": False,
                "error": f"Tableau de couverture de cohorte introuvable pour le rapport {report_id}",
            }), 404

        return jsonify({
            "success": True,
            "data": cohort_data,
        })
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la cohorte du rapport {report_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@report_bp.route('/<report_id>/usage', methods=['GET'])
def get_report_usage(report_id: str):
    """Retourne la télémétrie d'usage LLM propre au rapport (Story 013-4, FR-08, C5).

    Expose les tokens (prompt, complétion, réflexion), la durée, le nombre
    d'appels et le coût estimé. Le payload est reconstruit depuis le modèle
    (liste blanche de champs) : aucune clé d'API, URL privée, prompt ou message
    brut ne peut être restitué (NFR-4).
    """
    try:
        report = ReportManager.get_report(report_id)
        if not report:
            return jsonify({
                "success": False,
                "error": f"Rapport {report_id} introuvable",
            }), 404

        usage_path = ReportManager._get_usage_path(report_id)
        usage_exists = os.path.exists(usage_path)
        metrics = ReportManager.load_usage_metrics(report_id)
        if metrics is not None:
            usage_data = metrics.to_dict()
        elif usage_exists:
            return jsonify({
                "success": False,
                "error": (
                    f"Métriques d'usage illisibles ou corrompues pour le rapport "
                    f"{report_id}"
                ),
            }), 500
        elif isinstance(report.usage_metrics, dict):
            # Reconstruction par le modèle : les clés inconnues d'un meta.json
            # altéré ne traversent pas la réponse (liste blanche de champs).
            from ..models.report_usage import ReportUsageMetrics

            try:
                usage_data = ReportUsageMetrics.from_dict(report.usage_metrics).to_dict()
            except (TypeError, ValueError, OverflowError):
                return jsonify({
                    "success": False,
                    "error": (
                        f"Métriques d'usage illisibles pour le rapport {report_id}"
                    ),
                }), 500
        else:
            return jsonify({
                "success": False,
                "error": f"Métriques d'usage introuvables pour le rapport {report_id}",
            }), 404

        from ..models.report_usage import sanitize_usage_payload
        return jsonify({
            "success": True,
            "data": sanitize_usage_payload(usage_data),
        })
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'usage du rapport {report_id}: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"Impossible de restituer la télémétrie d'usage du rapport {report_id}",
        }), 500


