"""Tests hermétiques pour la Story 015-5 : télémétrie vivante et ergonomie IHM.

Vérifie :
1. La persistance incrémentale de usage.json (final=False) sans sceller _usage_persisted.
2. L'actualisation des métriques aux étapes intermédiaires puis le scellement définitif (final=True)
   et l'identité octet pour octet avec l'archive d'audit ZIP (AC3).
3. L'exécution réelle de ReportAgent._generate_report_internal prouvant l'ordre strict des opérations de clôture
   (persistance des artefacts sur disque avant log_report_complete et log_error, AC4).
4. La persistance incrémentale déclenchée dans _execute_tool pour les outils d'entretien.
5. La présence des règles CSS anti-débordement dans Step3Simulation.vue et des jalons dans Step4Report.vue.
"""

from datetime import datetime
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import zipfile

from app.config import Config
from app.models.report_usage import ReportUsageMetrics
from app.services.report_agent import Report, ReportAgent, ReportManager, ReportStatus
from app.services.report_usage_tracker import ReportUsageTracker
from app.services.simulation_audit_service import SimulationAuditService


def test_incremental_usage_metrics_persistence_without_premature_sealing(tmp_path: Path):
    """AC3 : final=False écrit usage.json sans sceller _usage_persisted."""
    report_id = "report_test_inc_001"
    report_dir = tmp_path / "reports" / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    with patch.object(ReportManager, "_get_report_folder", return_value=str(report_dir)):
        agent = ReportAgent(
            graph_id="graph_test",
            simulation_id="sim_test",
            simulation_requirement="Test requirement",
            zep_tools=MagicMock(),
        )
        agent._current_report_id = report_id
        tracker = ReportUsageTracker(report_id=report_id, simulation_id="sim_test", model="deepseek-v4.1-flash")
        agent.usage_tracker = tracker

        # 1. Premier appel
        tracker.record_call(
            usage={"prompt_tokens": 100, "completion_tokens": 20, "thinking_tokens": 10, "total_tokens": 130},
            model="deepseek-v4.1-flash",
            duration_seconds=1.2,
        )
        metrics_step1 = agent._persist_usage_metrics(report_id, final=False)

        assert getattr(agent, "_usage_persisted", False) is False
        assert tracker._completed_at is None  # restauré pour permettre de continuer
        usage_file = report_dir / "usage.json"
        assert usage_file.exists()
        with open(usage_file, "r", encoding="utf-8") as f:
            data1 = json.load(f)
        assert data1["calls_count"] == 1
        assert data1["total_tokens"] == 130

        # 2. Deuxième appel incrémental
        tracker.record_call(
            usage={"prompt_tokens": 200, "completion_tokens": 20, "thinking_tokens": 10, "total_tokens": 230},
            model="deepseek-v4.1-flash",
            duration_seconds=1.2,
        )
        metrics_step2 = agent._persist_usage_metrics(report_id, final=False)

        assert getattr(agent, "_usage_persisted", False) is False
        with open(usage_file, "r", encoding="utf-8") as f:
            data2 = json.load(f)
        assert data2["calls_count"] == 2
        assert data2["total_tokens"] == 360

        # 3. Clôture finale (final=True)
        metrics_final = agent._persist_usage_metrics(report_id, final=True)
        assert getattr(agent, "_usage_persisted", False) is True
        with open(usage_file, "r", encoding="utf-8") as f:
            data3 = json.load(f)
        assert data3["calls_count"] == 2
        assert data3["completed_at"] is not None

        # 4. Appel ultérieur après scellement : retourne les métriques scellées sans réécrire
        tracker.record_call(
            usage={"prompt_tokens": 999, "completion_tokens": 20, "thinking_tokens": 10, "total_tokens": 1029},
            model="deepseek-v4.1-flash",
            duration_seconds=1.2,
        )
        metrics_cached = agent._persist_usage_metrics(report_id, final=True)
        with open(usage_file, "r", encoding="utf-8") as f:
            data4 = json.load(f)
        assert data4["calls_count"] == 2  # n'a pas été écrasé


def test_usage_metrics_sealed_matches_zip_audit_archive(tmp_path: Path):
    """AC3 §3 : L'artefact usage.json scellé sur disque et celui extrait du zip d'audit sont identiques octet pour octet."""
    sim_id = "sim_audit_015_5"
    report_id = "rep_audit_015_5"
    sim_dir = tmp_path / "simulations" / sim_id
    sim_dir.mkdir(parents=True, exist_ok=True)
    report_dir = tmp_path / "reports" / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    # Écrire les artefacts minimaux requis pour l'archive d'audit
    (report_dir / "full_report.md").write_text("# Test report\n", encoding="utf-8")
    (report_dir / "meta.json").write_text(json.dumps({"report_id": report_id}), encoding="utf-8")
    (sim_dir / "run_state.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    with patch.object(ReportManager, "_get_report_folder", return_value=str(report_dir)), \
         patch.object(Config, "UPLOAD_FOLDER", str(tmp_path)):

        agent = ReportAgent(graph_id="g1", simulation_id=sim_id, simulation_requirement="req", zep_tools=MagicMock())
        tracker = ReportUsageTracker(report_id=report_id, simulation_id=sim_id, model="gemini-3.8-flash")
        agent.usage_tracker = tracker

        tracker.record_call(
            usage={"prompt_tokens": 150, "completion_tokens": 50, "thinking_tokens": 0, "total_tokens": 200},
            model="gemini-3.8-flash",
            duration_seconds=2.0,
        )
        agent._persist_usage_metrics(report_id, final=True)

        usage_file = report_dir / "usage.json"
        assert usage_file.exists()
        disk_bytes = usage_file.read_bytes()

        audit_svc = SimulationAuditService(simulation_id=sim_id, report_id=report_id)
        zip_bytes = audit_svc.build_audit_package()
        assert isinstance(zip_bytes, bytes) and len(zip_bytes) > 0

        zip_path = report_dir / f"simulation_audit_{report_id}.zip"
        assert zip_path.exists()
        with zipfile.ZipFile(zip_path, "r") as zf:
            assert "usage.json" in zf.namelist()
            extracted_bytes = zf.read("usage.json")

        assert disk_bytes == extracted_bytes, "usage.json sur disque et celui extrait de l'archive ZIP doivent être strictement identiques octet pour octet"


def test_closure_sequence_persists_artifacts_before_logging_completion(tmp_path: Path):
    """AC4 : _generate_report_internal appelle save_report et persist_usage_metrics AVANT log_report_complete."""
    events = []
    report_id = "rep_order_complete"
    report_dir = tmp_path / "reports" / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    mock_logger = MagicMock()
    mock_logger.log_report_complete.side_effect = lambda **kwargs: events.append("log_report_complete")
    mock_logger.log_planning_complete.side_effect = lambda *args, **kwargs: events.append("log_planning_complete")
    mock_logger.log_start.side_effect = lambda **kwargs: events.append("log_start")
    mock_logger.log_planning_start.side_effect = lambda **kwargs: events.append("log_planning_start")

    agent = ReportAgent(
        graph_id="graph_order",
        simulation_id="sim_order",
        simulation_requirement="Order requirement",
        zep_tools=MagicMock(),
    )

    original_persist = agent._persist_usage_metrics

    def tracking_persist(rep_id, report=None, final=True):
        events.append(f"persist_usage_final_{final}")
        return original_persist(rep_id, report=report, final=final)

    agent._persist_usage_metrics = tracking_persist

    def tracking_save_report(rep):
        events.append("save_report")

    def tracking_update_progress(rep_id, status, progress, message="", **kwargs):
        events.append(f"update_progress_{status}")

    fake_outline = MagicMock()
    fake_outline.title = "Test Outline"
    fake_outline.summary = "Test summary"
    fake_outline.sections = []
    fake_outline.to_dict.return_value = {"title": "Test Outline", "summary": "Test summary", "sections": []}

    fake_quality = MagicMock()
    fake_quality.is_publishable = True
    fake_quality.publication_status = MagicMock(value="published")
    fake_quality.summary = "Quality OK"

    with patch.object(ReportManager, "_get_report_folder", return_value=str(report_dir)), \
         patch.object(ReportManager, "save_report", side_effect=tracking_save_report), \
         patch.object(ReportManager, "update_progress", side_effect=tracking_update_progress), \
         patch.object(ReportManager, "save_outline"), \
         patch.object(ReportManager, "_append_to_history", lambda *args, **kwargs: events.append("append_history")), \
         patch("app.services.report_agent.ReportLogger", return_value=mock_logger), \
         patch("app.services.report_agent.ReportConsoleLogger", return_value=MagicMock()), \
         patch.object(agent, "plan_outline", return_value=fake_outline), \
         patch("app.services.report_quality_gate.ReportQualityGate.evaluate_report", return_value=fake_quality), \
         patch.object(agent, "extract_claims_from_content", return_value=MagicMock(total_claims=0, verified_claims=0, unsupported_claims=0, contradicted_claims=0)), \
         patch("app.services.simulation_audit_service.SimulationAuditService.build_audit_package", lambda self: events.append("build_audit_package")):

        agent._generate_report_internal(report_id=report_id)

    assert "persist_usage_final_True" in events
    assert "save_report" in events
    assert "log_report_complete" in events

    idx_persist_final = events.index("persist_usage_final_True")
    idx_save = [i for i, e in enumerate(events) if e == "save_report"][-1]
    idx_complete = events.index("log_report_complete")

    assert idx_persist_final < idx_complete, "persist_usage_metrics(final=True) doit précéder log_report_complete"
    assert idx_save < idx_complete, "save_report doit précéder log_report_complete"


def test_closure_sequence_persists_artifacts_before_logging_error(tmp_path: Path):
    """AC4 : _generate_report_internal appelle save_report et persist_usage_metrics AVANT log_error sur échec."""
    events = []
    report_id = "rep_order_error"
    report_dir = tmp_path / "reports" / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    mock_logger = MagicMock()
    mock_logger.log_error.side_effect = lambda *args, **kwargs: events.append("log_error")
    mock_logger.log_start.side_effect = lambda **kwargs: events.append("log_start")
    mock_logger.log_planning_start.side_effect = lambda **kwargs: events.append("log_planning_start")

    agent = ReportAgent(
        graph_id="graph_err",
        simulation_id="sim_err",
        simulation_requirement="Error requirement",
        zep_tools=MagicMock(),
    )

    original_persist = agent._persist_usage_metrics

    def tracking_persist(rep_id, report=None, final=True):
        events.append(f"persist_usage_final_{final}")
        return original_persist(rep_id, report=report, final=final)

    agent._persist_usage_metrics = tracking_persist

    def tracking_save_report(rep):
        events.append("save_report")

    def tracking_update_progress(rep_id, status, progress, message="", **kwargs):
        events.append(f"update_progress_{status}")

    # Forcer une exception dans plan_outline
    with patch.object(ReportManager, "_get_report_folder", return_value=str(report_dir)), \
         patch.object(ReportManager, "save_report", side_effect=tracking_save_report), \
         patch.object(ReportManager, "update_progress", side_effect=tracking_update_progress), \
         patch.object(ReportManager, "_append_to_history", lambda *args, **kwargs: events.append("append_history")), \
         patch("app.services.report_agent.ReportLogger", return_value=mock_logger), \
         patch("app.services.report_agent.ReportConsoleLogger", return_value=MagicMock()), \
         patch.object(agent, "plan_outline", side_effect=RuntimeError("Erreur simulée de test")):

        agent._generate_report_internal(report_id=report_id)

    assert "persist_usage_final_True" in events
    assert "save_report" in events
    assert "log_error" in events

    idx_persist_final = events.index("persist_usage_final_True")
    idx_save = [i for i, e in enumerate(events) if e == "save_report"][-1]
    idx_error = events.index("log_error")

    assert idx_persist_final < idx_error, "persist_usage_metrics(final=True) doit précéder log_error"
    assert idx_save < idx_error, "save_report doit précéder log_error"


def test_execute_tool_persists_incremental_telemetry_on_interview():
    """Patch 5 : _execute_tool persiste la télémétrie incrémentale sur les outils d'entretien."""
    agent = ReportAgent(
        graph_id="graph_ivw",
        simulation_id="sim_ivw",
        simulation_requirement="Interview requirement",
        zep_tools=MagicMock(),
    )
    agent._current_report_id = "rep_ivw_test"

    calls = []
    agent._persist_usage_metrics = MagicMock(side_effect=lambda rep_id, final=True: calls.append((rep_id, final)))
    agent._execute_tool_impl = MagicMock(return_value="Interview result")

    res1 = agent._execute_tool("interview_agents", {"agent_id": "a1"})
    assert res1 == "Interview result"
    assert ("rep_ivw_test", False) in calls

    calls.clear()
    res2 = agent._execute_tool("interview_agents_batch", {"agent_ids": ["a1", "a2"]})
    assert res2 == "Interview result"
    assert ("rep_ivw_test", False) in calls

    # Sur un outil non-interview, _persist_usage_metrics n'est pas appelé
    calls.clear()
    res3 = agent._execute_tool("query_simulation_events", {})
    assert res3 == "Interview result"
    assert len(calls) == 0


def test_step3_control_bar_css_rules_present():
    """AC1, AC2 : Les règles CSS anti-débordement et d'espacement sont présentes dans Step3Simulation.vue."""
    step3_file = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "Step3Simulation.vue"
    assert step3_file.exists()
    content = step3_file.read_text(encoding="utf-8")

    # .control-bar
    assert "min-height: 64px;" in content
    assert "height: auto;" in content
    assert "flex-wrap: wrap;" in content
    assert "gap: 12px 16px;" in content

    # .status-group
    assert "flex: 1 1 auto;" in content
    assert "min-width: 0;" in content

    # .platform-status
    assert "overflow: visible;" in content
    assert "box-sizing: border-box;" in content

    # .stat
    assert "white-space: nowrap;" in content

    # .action-controls
    assert ".action-controls {" in content
    assert "margin-left: auto;" in content
    assert "flex-shrink: 0;" in content


def test_step4_live_telemetry_milestones_present():
    """AC5, AC6 : Step4Report.vue écoute les jalons de polling et gère l'état error."""
    step4_file = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "Step4Report.vue"
    assert step4_file.exists()
    content = step4_file.read_text(encoding="utf-8")

    assert "resolveLiveTelemetryDisplay" in content
    assert "step4.metricPending" in content
    assert "step4.metricUnpriced" in content
    assert "log.action === 'error'" in content
    assert "shouldRefreshTelemetry" in content
