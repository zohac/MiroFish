"""
OASIS模拟管理器
管理Twitter和Reddit双平台并行模拟
使用预设脚本 + LLM智能生成配置参数
"""

import os
import json
import shutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import ZepEntityReader, FilteredEntities
from .oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
from .simulation_config_generator import SimulationConfigGenerator, SimulationParameters
from ..utils.locale import t, normalize_locale
from ..models.actor_eligibility import (
    ACTOR_ELIGIBILITY_POLICY_VERSION,
    ActorEligibility,
    ActorRole,
    EligibilityStatus,
)
from ..models.simulation_brief import SimulationBrief, build_minimal_brief
from ..models.project import ProjectManager
from ..models.source_document import ConflictStatus
from ..models.actor_selection import (
    ACTOR_SELECTION_FILENAME,
    ActorItem,
    ActorSelection,
    OptimisticLockError,
    SelectionValidationError,
)
from .actor_classifier import (
    ActorClassifierService,
    ActorClassificationResult,
    fingerprint_qualification_inputs,
)

logger = get_logger('mirofish.simulation')


class SimulationStatus(str, Enum):
    """模拟状态"""
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    PAUSED = "paused"
    STOPPED = "stopped"      # 模拟被手动停止
    COMPLETED = "completed"  # 模拟自然完成
    FAILED = "failed"


class PlatformType(str, Enum):
    """平台类型"""
    TWITTER = "twitter"
    REDDIT = "reddit"


# Nom du fichier de preuve de qualification dans le dossier d'une simulation.
QUALIFICATION_PROOF_FILENAME = "actor_qualifications.json"


class QualificationProofError(ValueError):
    """Preuve de qualification illisible (fichier corrompu ou tronqué)."""


def build_qualification_proof(
    *,
    state: "SimulationState",
    entities: List[Any],
    simulation_requirement: str,
    classification: ActorClassificationResult,
    policy_version: str,
    simulation_brief: Optional[SimulationBrief] = None,
    actor_selection_revision: Optional[int] = None,
) -> Dict[str, Any]:
    """Construit la preuve automatique du verrou de qualification (AC10).

    Elle lie la préparation au projet/graphe, à la version de politique et à une
    empreinte déterministe des entrées. Les UUID des acteurs retenus doivent
    correspondre aux profils et à la configuration produits.
    """

    proof = {
        "schema_version": 1,
        "policy_version": policy_version,
        "simulation_id": state.simulation_id,
        "project_id": state.project_id,
        "graph_id": state.graph_id,
        "simulation_requirement": simulation_requirement or "",
        "input_fingerprint": fingerprint_qualification_inputs(
            entities, simulation_requirement, policy_version, simulation_brief
        ),
        "qualified_actor_uuids": [q.entity_uuid for q in classification.eligible],
        "counts": classification.summary(),
        "qualifications": [q.to_dict() for q in classification.qualifications],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if actor_selection_revision is not None:
        proof["actor_selection_revision"] = actor_selection_revision
    return proof


def write_qualification_proof(sim_dir: str, proof: Dict[str, Any]) -> str:
    """Écrit la preuve de façon atomique : le démarrage en dépend."""

    path = os.path.join(sim_dir, QUALIFICATION_PROOF_FILENAME)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(proof, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, path)
    return path


def read_qualification_proof(sim_dir: str) -> Optional[Dict[str, Any]]:
    """Lit la preuve de qualification.

    Retourne `None` si le fichier est absent ; lève `QualificationProofError`
    s'il est présent mais illisible, pour que l'absence et la corruption ne
    produisent pas le même diagnostic.
    """

    path = os.path.join(sim_dir, QUALIFICATION_PROOF_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as error:
        raise QualificationProofError(
            f"preuve de qualification illisible: {error}"
        ) from error


@dataclass
class SimulationState:
    """模拟状态"""
    simulation_id: str
    project_id: str
    graph_id: str
    locale: str = "zh"  # Langue canonique fixée à la création.
    
    # 平台启用状态
    enable_twitter: bool = True
    enable_reddit: bool = True
    
    # 状态
    status: SimulationStatus = SimulationStatus.CREATED
    
    # 准备阶段数据
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: List[str] = field(default_factory=list)

    # Barrière d'éligibilité (story 009-1) : préserve la distinction entre
    # connaissances lues, acteurs retenus et candidats en review.
    actors_count: int = 0
    review_count: int = 0
    ineligible_count: int = 0
    policy_version: str = ""
    qualified_actor_uuids: List[str] = field(default_factory=list)

    # Référence ontologique appliquée du projet (Story 007-5, AC1, C5)
    applied_ontology_id: Optional[str] = None
    
    # 配置生成信息
    profiles_generated: bool = False
    config_generated: bool = False
    config_reasoning: str = ""
    
    # 运行时数据
    current_round: int = 0
    twitter_status: str = "not_started"
    reddit_status: str = "not_started"
    
    # 时间戳
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 错误信息
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """完整状态字典（内部使用）"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "locale": normalize_locale(self.locale),
            "enable_twitter": self.enable_twitter,
            "enable_reddit": self.enable_reddit,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "actors_count": self.actors_count,
            "review_count": self.review_count,
            "ineligible_count": self.ineligible_count,
            "policy_version": self.policy_version,
            "qualified_actor_uuids": self.qualified_actor_uuids,
            "applied_ontology_id": self.applied_ontology_id,
            "profiles_generated": self.profiles_generated,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "current_round": self.current_round,
            "twitter_status": self.twitter_status,
            "reddit_status": self.reddit_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }
    
    def get_default_platform(self) -> str:
        """根据启用状态返回默认平台"""
        if self.enable_twitter and self.enable_reddit:
            return "reddit"  # 两者都启用时保持原默认
        elif self.enable_twitter:
            return "twitter"
        else:
            return "reddit"

    def to_simple_dict(self) -> Dict[str, Any]:
        """简化状态字典（API返回使用）"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "locale": normalize_locale(self.locale),
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "actors_count": self.actors_count,
            "review_count": self.review_count,
            "ineligible_count": self.ineligible_count,
            "policy_version": self.policy_version,
            "applied_ontology_id": self.applied_ontology_id,
            "profiles_generated": self.profiles_generated,
            "config_generated": self.config_generated,
            "error": self.error,
        }


class SimulationManager:
    """
    模拟管理器
    
    核心功能：
    1. 从Zep图谱读取实体并过滤
    2. 生成OASIS Agent Profile
    3. 使用LLM智能生成模拟配置参数
    4. 准备预设脚本所需的所有文件
    """
    
    # 模拟数据存储目录
    SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__), 
        '../../uploads/simulations'
    )
    
    def __init__(self):
        # 确保目录存在
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)
        
        # 内存中的模拟状态缓存
        self._simulations: Dict[str, SimulationState] = {}
    
    def _get_simulation_dir(self, simulation_id: str) -> str:
        """获取模拟数据目录"""
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir
    
    def _save_simulation_state(self, state: SimulationState):
        """保存模拟状态到文件"""
        sim_dir = self._get_simulation_dir(state.simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        state.updated_at = datetime.now().isoformat()
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        
        self._simulations[state.simulation_id] = state
    
    def _load_simulation_state(self, simulation_id: str) -> Optional[SimulationState]:
        """从文件加载模拟状态"""
        if simulation_id in self._simulations:
            return self._simulations[simulation_id]
        
        sim_dir = self._get_simulation_dir(simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        if not os.path.exists(state_file):
            return None
        
        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            locale=normalize_locale(data.get("locale")),
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
            status=SimulationStatus(data.get("status", "created")),
            entities_count=data.get("entities_count", 0),
            profiles_count=data.get("profiles_count", 0),
            entity_types=data.get("entity_types", []),
            actors_count=data.get("actors_count", 0),
            review_count=data.get("review_count", 0),
            ineligible_count=data.get("ineligible_count", 0),
            policy_version=data.get("policy_version", ""),
            qualified_actor_uuids=data.get("qualified_actor_uuids", []),
            applied_ontology_id=data.get("applied_ontology_id"),
            profiles_generated=data.get("profiles_generated", False),
            config_generated=data.get("config_generated", False),
            config_reasoning=data.get("config_reasoning", ""),
            current_round=data.get("current_round", 0),
            twitter_status=data.get("twitter_status", "not_started"),
            reddit_status=data.get("reddit_status", "not_started"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
        )
        
        self._simulations[simulation_id] = state
        return state
    
    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        locale: str = "zh",
    ) -> SimulationState:
        """
        创建新的模拟
        
        Args:
            project_id: 项目ID
            graph_id: Zep图谱ID
            enable_twitter: 是否启用Twitter模拟
            enable_reddit: 是否启用Reddit模拟
            
        Returns:
            SimulationState
        """
        import uuid
        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            locale=normalize_locale(locale),
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
            status=SimulationStatus.CREATED,
        )
        
        self._save_simulation_state(state)
        logger.info(f"创建模拟: {simulation_id}, project={project_id}, graph={graph_id}")
        
        return state
    
    def get_actor_selection(self, simulation_id: str) -> Optional[ActorSelection]:
        """Lit la sélection persistée `actors.json` rattachée à la simulation."""
        sim_dir = self._get_simulation_dir(simulation_id)
        selection_file = os.path.join(sim_dir, ACTOR_SELECTION_FILENAME)
        return ActorSelection.load(selection_file)

    def save_actor_selection(self, selection: ActorSelection) -> str:
        """Sauvegarde atomique de la sélection `actors.json`."""
        sim_dir = self._get_simulation_dir(selection.simulation_id)
        selection_file = os.path.join(sim_dir, ACTOR_SELECTION_FILENAME)
        return selection.save_atomic(selection_file)

    def preview_actors(
        self,
        simulation_id: str,
        force_refresh: bool = False,
        classifier: Optional[ActorClassifierService] = None,
    ) -> tuple[ActorSelection, Dict[str, Any]]:
        """Prévisualise et persiste la sélection des acteurs pour une simulation (AC2).

        Si `actors.json` existe déjà et que ses entrées sont inchangées (sans
        force_refresh), la sélection existante est renvoyée sans recalcul LLM,
        préservant ainsi les arbitrages humains existants.
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation inexistante: {simulation_id}")

        project = ProjectManager.get_project(state.project_id)
        simulation_requirement = (project.simulation_requirement or "") if project else ""
        brief = project.get_brief() if project else None
        if brief is None:
            brief = build_minimal_brief(goal=simulation_requirement)

        reader = ZepEntityReader()
        filtered = reader.filter_defined_entities(
            graph_id=state.graph_id,
            defined_entity_types=state.entity_types or None,
            enrich_with_edges=True,
        )

        current_fingerprint = fingerprint_qualification_inputs(
            filtered.entities,
            simulation_requirement,
            ACTOR_ELIGIBILITY_POLICY_VERSION,
            brief,
        )

        existing = self.get_actor_selection(simulation_id)
        if (
            existing is not None
            and not force_refresh
            and existing.input_fingerprint == current_fingerprint
        ):
            logger.info(
                f"Réutilisation de la sélection persistée actors.json pour {simulation_id} "
                f"(révision {existing.revision})"
            )
            return existing, {"reused": True, "diagnostics": {}}

        # Recalcul ou première exécution
        classifier = classifier or ActorClassifierService()
        classification = classifier.classify_entities(
            filtered.entities, simulation_requirement, brief
        )

        actor_items = [
            ActorItem(
                entity_uuid=q.entity_uuid,
                entity_name=q.entity_name,
                original_type=q.original_type,
                qualified_role=q.role,
                eligibility_status=q.status,
                confidence=q.confidence,
                reasoning=q.rationale,
                is_human_modified=False,
                last_modified_at=None,
                justification=None,
            )
            for q in classification.qualifications
        ]

        selection = ActorSelection(
            simulation_id=state.simulation_id,
            project_id=state.project_id,
            graph_id=state.graph_id,
            input_fingerprint=current_fingerprint,
            revision=1,
            actors=actor_items,
        )
        self.save_actor_selection(selection)

        # Synchroniser l'état
        state.entities_count = filtered.filtered_count
        state.actors_count = selection.counts["eligible"]
        state.review_count = selection.counts["review"]
        state.ineligible_count = selection.counts["ineligible"]
        state.policy_version = selection.policy_version
        state.qualified_actor_uuids = [a.entity_uuid for a in selection.eligible_actors]
        self._save_simulation_state(state)

        return selection, {"reused": False, "diagnostics": classification.diagnostics}

    def review_actors(
        self,
        simulation_id: str,
        expected_revision: int,
        modifications: List[Dict[str, Any]],
    ) -> ActorSelection:
        """Applique des arbitrages motivés sur la sélection d'acteurs (AC3).

        Vérifie le verrouillage d'état, la concurrence optimiste et les règles
        d'admissibilité des rôles.
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation inexistante: {simulation_id}")

        if state.status in {
            SimulationStatus.PREPARING,
            SimulationStatus.RUNNING,
            SimulationStatus.COMPLETED,
        }:
            raise SelectionValidationError(
                f"Mutations interdites : la simulation {simulation_id} est en statut "
                f"'{state.status.value}'"
            )

        selection = self.get_actor_selection(simulation_id)
        if not selection:
            raise SelectionValidationError(
                f"Aucune sélection d'acteurs trouvée pour {simulation_id}. "
                "Veuillez d'abord exécuter une prévisualisation."
            )

        selection.apply_review(expected_revision, modifications)
        self.save_actor_selection(selection)

        # Synchroniser l'état de simulation
        state.actors_count = selection.counts["eligible"]
        state.review_count = selection.counts["review"]
        state.ineligible_count = selection.counts["ineligible"]
        state.qualified_actor_uuids = [a.entity_uuid for a in selection.eligible_actors]
        self._save_simulation_state(state)

        return selection

    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: Optional[List[str]] = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Optional[callable] = None,
        parallel_profile_count: int = 3,
        classifier: Optional[ActorClassifierService] = None,
        simulation_brief: Optional[SimulationBrief] = None,
        document_sections: Optional[List[Dict[str, Any]]] = None,
        block_on_review: bool = False,
        block_on_conflict: bool = False,
    ) -> SimulationState:
        """
        准备模拟环境（全程自动化）
        
        步骤：
        1. 从Zep图谱读取并过滤实体
        2. 为每个实体生成OASIS Agent Profile（可选LLM增强，支持并行）
        3. 使用LLM智能生成模拟配置参数（时间、活跃度、发言频率等）
        4. 保存配置文件和Profile文件
        5. 复制预设脚本到模拟目录
        
        Args:
            simulation_id: 模拟ID
            simulation_requirement: 模拟需求描述（用于LLM生成配置）
            document_text: 原始文档内容（用于LLM理解背景）
            defined_entity_types: 预定义的实体类型（可选）
            use_llm_for_profiles: 是否使用LLM生成详细人设
            progress_callback: 进度回调函数 (stage, progress, message)
            parallel_profile_count: 并行生成人设的数量，默认3
            simulation_brief: 完整brief（story 009-2）。为 None 时回退到
                simulation_requirement 构造一个最小 brief，因此旧调用不受影响。
            block_on_review: interruption volontaire si des entités restent en REVIEW (AC6)
            block_on_conflict: interruption volontaire si des conflits restent OPEN (AC6)
            
        Returns:
            SimulationState
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"模拟不存在: {simulation_id}")

        project = ProjectManager.get_project(state.project_id)
        if simulation_brief is None and project:
            simulation_brief = project.get_brief()
        if simulation_brief is None:
            simulation_brief = build_minimal_brief(goal=simulation_requirement)
        
        # Récupération de l'ontologie projet appliquée (Événement E5, AC1, C5)
        applied_ontology_id = getattr(project, "applied_ontology_id", None) if project else None

        try:
            state.status = SimulationStatus.PREPARING
            state.error = None
            state.profiles_generated = False
            state.config_generated = False
            state.config_reasoning = ""
            state.applied_ontology_id = applied_ontology_id
            self._save_simulation_state(state)
            
            sim_dir = self._get_simulation_dir(simulation_id)
            
            # ========== 阶段1: 读取并过滤实体 ==========
            if progress_callback:
                progress_callback("reading", 0, t('progress.connectingZepGraph'))
            
            reader = ZepEntityReader()
            
            if progress_callback:
                progress_callback("reading", 30, t('progress.readingNodeData'))
            
            filtered = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=True
            )
            
            state.entities_count = filtered.filtered_count
            state.entity_types = list(filtered.entity_types)

            # ========== Barrière d'éligibilité & Sélection (stories 009-1 / 009-3) ==========
            current_fingerprint = fingerprint_qualification_inputs(
                filtered.entities,
                simulation_requirement,
                ACTOR_ELIGIBILITY_POLICY_VERSION,
                simulation_brief,
            )
            existing_selection = self.get_actor_selection(simulation_id)

            if (
                existing_selection is not None
                and existing_selection.input_fingerprint == current_fingerprint
            ):
                # Consomme la sélection existante avec les arbitrages humains appliqués (AC4)
                logger.info(
                    f"Consommation de la sélection actors.json existante (révision {existing_selection.revision}) "
                    f"pour {simulation_id}"
                )
                selection = existing_selection
            else:
                # Parcours simple direct ou sélection invalidée sur divergence d'empreinte (AC4 / AC5)
                classifier = classifier or ActorClassifierService()
                classification = classifier.classify_entities(
                    filtered.entities, simulation_requirement, simulation_brief
                )
                actor_items = [
                    ActorItem(
                        entity_uuid=q.entity_uuid,
                        entity_name=q.entity_name,
                        original_type=q.original_type,
                        qualified_role=q.role,
                        eligibility_status=q.status,
                        confidence=q.confidence,
                        reasoning=q.rationale,
                        is_human_modified=False,
                        last_modified_at=None,
                        justification=None,
                    )
                    for q in classification.qualifications
                ]
                selection = ActorSelection(
                    simulation_id=state.simulation_id,
                    project_id=state.project_id,
                    graph_id=state.graph_id,
                    input_fingerprint=current_fingerprint,
                    revision=1,
                    actors=actor_items,
                )
                self.save_actor_selection(selection)

            # Blocage volontaire préventif (AC6)
            if block_on_review and selection.counts.get("review", 0) > 0:
                review_names = [a.entity_name or a.entity_uuid for a in selection.review_actors]
                error_msg = (
                    f"Blocage préventif activé : {len(review_names)} entité(s) non tranchée(s) "
                    f"en statut REVIEW : {', '.join(review_names[:5])}"
                )
                state.status = SimulationStatus.FAILED
                state.error = error_msg
                self._save_simulation_state(state)
                raise ValueError(error_msg)

            if block_on_conflict and project:
                open_conflicts = [
                    c
                    for c in project.get_source_conflicts()
                    if getattr(c, "status", None) == ConflictStatus.OPEN
                ]
                if open_conflicts:
                    claims = [c.claim for c in open_conflicts]
                    error_msg = (
                        f"Blocage préventif activé : {len(open_conflicts)} conflit(s) documentaire(s) "
                        f"non résolu(s) : {', '.join(claims[:5])}"
                    )
                    state.status = SimulationStatus.FAILED
                    state.error = error_msg
                    self._save_simulation_state(state)
                    raise ValueError(error_msg)

            eligible_uuids = {a.entity_uuid for a in selection.eligible_actors}
            eligible_entities = [
                entity for entity in filtered.entities if entity.uuid in eligible_uuids
            ]
            state.actors_count = len(eligible_entities)
            state.review_count = selection.counts.get("review", 0)
            state.ineligible_count = selection.counts.get("ineligible", 0)
            state.policy_version = selection.policy_version
            state.qualified_actor_uuids = list(eligible_uuids)

            if progress_callback:
                progress_callback(
                    "reading", 100,
                    t('progress.readingComplete', count=filtered.filtered_count),
                    current=filtered.filtered_count,
                    total=filtered.filtered_count
                )
            
            if filtered.filtered_count == 0:
                state.status = SimulationStatus.FAILED
                state.error = "没有找到符合条件的实体，请检查图谱是否正确构建"
                self._save_simulation_state(state)
                raise ValueError(state.error)

            if not eligible_entities:
                state.status = SimulationStatus.FAILED
                state.error = t(
                    'api.noEligibleActor',
                    eligible=selection.counts.get('eligible', 0),
                    review=selection.counts.get('review', 0),
                    ineligible=selection.counts.get('ineligible', 0),
                )
                self._save_simulation_state(state)
                raise ValueError(state.error)
            
            # ========== 阶段2: 生成Agent Profile ==========
            total_entities = len(eligible_entities)
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 0,
                    t('progress.startGenerating'),
                    current=0,
                    total=total_entities
                )
            
            # 传入graph_id以启用检索功能，获取更丰富的上下文
            generator = OasisProfileGenerator(graph_id=state.graph_id)
            
            def profile_progress(current, total, msg):
                if progress_callback:
                    progress_callback(
                        "generating_profiles", 
                        int(current / total * 100), 
                        msg,
                        current=current,
                        total=total,
                        item_name=msg
                    )
            
            # 设置实时保存的文件路径（优先使用 Reddit JSON 格式）
            realtime_output_path = None
            realtime_platform = "reddit"
            if state.enable_reddit:
                realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
                realtime_platform = "reddit"
            elif state.enable_twitter:
                realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
                realtime_platform = "twitter"
            
            # Qualifications avec rôles qualifiés humains ou automatiques (AC4)
            qualifications_for_profiles = {
                a.entity_uuid: ActorEligibility(
                    entity_uuid=a.entity_uuid,
                    entity_name=a.entity_name,
                    role=a.qualified_role,
                    status=a.eligibility_status,
                    rationale=(
                        a.justification
                        if (a.is_human_modified and a.justification)
                        else (a.reasoning or "")
                    ),
                    confidence=a.confidence,
                    original_type=a.original_type,
                )
                for a in selection.actors
            }

            profiles = generator.generate_profiles_from_entities(
                entities=eligible_entities,
                use_llm=use_llm_for_profiles,
                progress_callback=profile_progress,
                graph_id=state.graph_id,  # 传入graph_id用于检索
                parallel_count=parallel_profile_count,  # 并行生成数量
                realtime_output_path=realtime_output_path,  # 实时保存路径
                output_platform=realtime_platform,  # 输出格式
                qualifications={
                    uuid: qualifications_for_profiles[uuid]
                    for uuid in state.qualified_actor_uuids
                    if uuid in qualifications_for_profiles
                },
                classifier=classifier,
                simulation_requirement=simulation_requirement,
                simulation_brief=simulation_brief,
            )
            
            state.profiles_count = len(profiles)
            state.profiles_generated = len(profiles) > 0
            self._save_simulation_state(state)
            
            # 保存Profile文件（注意：Twitter使用CSV格式，Reddit使用JSON格式）
            # Reddit 已经在生成过程中实时保存了，这里再保存一次确保完整性
            if progress_callback:
                progress_callback(
                    "generating_profiles", 95,
                    t('progress.savingProfiles'),
                    current=total_entities,
                    total=total_entities
                )
            
            if state.enable_reddit:
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "reddit_profiles.json"),
                    platform="reddit"
                )
            
            if state.enable_twitter:
                # Twitter使用CSV格式！这是OASIS的要求
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
                    platform="twitter"
                )
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 100,
                    t('progress.profilesComplete', count=len(profiles)),
                    current=len(profiles),
                    total=len(profiles)
                )
            
            # ========== 阶段3: LLM智能生成模拟配置 ==========
            if progress_callback:
                progress_callback(
                    "generating_config", 0,
                    t('progress.analyzingRequirements'),
                    current=0,
                    total=3
                )
            
            config_generator = SimulationConfigGenerator()
            
            if progress_callback:
                progress_callback(
                    "generating_config", 30,
                    t('progress.callingLLMConfig'),
                    current=1,
                    total=3
                )
            
            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=eligible_entities,
                enable_twitter=state.enable_twitter,
                enable_reddit=state.enable_reddit,
                simulation_brief=simulation_brief,
                document_sections=document_sections,
                applied_ontology_id=applied_ontology_id,
            )
            
            if progress_callback:
                progress_callback(
                    "generating_config", 70,
                    t('progress.savingConfigFiles'),
                    current=2,
                    total=3
                )
            
            # 保存配置文件
            config_path = os.path.join(sim_dir, "simulation_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(sim_params.to_json())
            
            state.config_generated = True
            state.config_reasoning = sim_params.generation_reasoning
            
            if progress_callback:
                progress_callback(
                    "generating_config", 100,
                    t('progress.configComplete'),
                    current=3,
                    total=3
                )
            
            # 注意：运行脚本保留在 backend/scripts/ 目录，不再复制到模拟目录
            # 启动模拟时，simulation_runner 会从 scripts/ 目录运行脚本

            # Preuve automatique du verrou de qualification (AC10 / AC4). Écrite
            # seulement quand profils et configuration sont produits : une
            # préparation sans preuve n'est jamais réutilisée comme fraîche.
            classification_for_proof = ActorClassificationResult(
                qualifications=[
                    ActorEligibility(
                        entity_uuid=a.entity_uuid,
                        entity_name=a.entity_name,
                        role=a.qualified_role,
                        status=a.eligibility_status,
                        rationale=(
                            a.justification
                            if (a.is_human_modified and a.justification)
                            else (a.reasoning or "")
                        ),
                        confidence=a.confidence,
                        original_type=a.original_type,
                    )
                    for a in selection.actors
                ]
            )
            proof = build_qualification_proof(
                state=state,
                entities=filtered.entities,
                simulation_requirement=simulation_requirement,
                classification=classification_for_proof,
                policy_version=selection.policy_version,
                simulation_brief=simulation_brief,
                actor_selection_revision=selection.revision,
            )
            write_qualification_proof(sim_dir, proof)

            # 更新状态
            state.status = SimulationStatus.READY
            self._save_simulation_state(state)
            
            logger.info(f"模拟准备完成: {simulation_id}, "
                       f"entities={state.entities_count}, profiles={state.profiles_count}")
            
            return state
            
        except Exception as e:
            logger.error(f"模拟准备失败: {simulation_id}, error={str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            state.status = SimulationStatus.FAILED
            state.error = str(e)
            self._save_simulation_state(state)
            raise
    
    def get_simulation(self, simulation_id: str) -> Optional[SimulationState]:
        """获取模拟状态"""
        return self._load_simulation_state(simulation_id)

    @staticmethod
    def no_actor_diagnostic(classification: ActorClassificationResult) -> str:
        """Diagnostic exploitable quand aucun acteur n'est retenu (AC9).

        Le gabarit est localisé ; les motifs par entité restent des données
        (raisons produites par le classifieur).
        """

        counts = classification.summary()
        details = []
        for qualification in classification.review[:10]:
            reason = qualification.diagnostic or qualification.rationale
            details.append(f"{qualification.entity_name or qualification.entity_uuid}: {reason}")
        suffix = (" | " + " ; ".join(details)) if details else ""
        return t(
            'api.noEligibleActor',
            eligible=counts['eligible'],
            review=counts['review'],
            ineligible=counts['ineligible'],
        ) + suffix
    
    def list_simulations(self, project_id: Optional[str] = None) -> List[SimulationState]:
        """列出所有模拟"""
        simulations = []
        
        if os.path.exists(self.SIMULATION_DATA_DIR):
            for sim_id in os.listdir(self.SIMULATION_DATA_DIR):
                # 跳过隐藏文件（如 .DS_Store）和非目录文件
                sim_path = os.path.join(self.SIMULATION_DATA_DIR, sim_id)
                if sim_id.startswith('.') or not os.path.isdir(sim_path):
                    continue
                
                state = self._load_simulation_state(sim_id)
                if state:
                    if project_id is None or state.project_id == project_id:
                        simulations.append(state)
        
        # Tri déterministe antéchronologique (plus récent en premier)
        def _get_sort_key(s: SimulationState) -> str:
            if s.created_at:
                return s.created_at
            if s.updated_at:
                return s.updated_at
            try:
                sim_path = os.path.join(self.SIMULATION_DATA_DIR, s.simulation_id)
                mtime = os.path.getmtime(sim_path)
                return datetime.fromtimestamp(mtime).isoformat()
            except Exception:
                return ""

        simulations.sort(key=_get_sort_key, reverse=True)
        return simulations
    
    def get_profiles(self, simulation_id: str, platform: str = None) -> List[Dict[str, Any]]:
        """获取模拟的Agent Profile"""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"模拟不存在: {simulation_id}")

        if platform is None:
            platform = state.get_default_platform()

        if platform not in {"twitter", "reddit"}:
            raise ValueError(f"不支持的平台: {platform}")

        sim_dir = self._get_simulation_dir(simulation_id)
        profile_path = os.path.join(
            sim_dir,
            "twitter_profiles.csv" if platform == "twitter" else "reddit_profiles.json",
        )
        
        if not os.path.exists(profile_path):
            return []

        if platform == "twitter":
            import csv

            with open(profile_path, 'r', encoding='utf-8', newline='') as f:
                return list(csv.DictReader(f))

        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_simulation_config(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        """获取模拟配置"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_run_instructions(self, simulation_id: str) -> Dict[str, str]:
        """获取运行说明"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "twitter": f"python {scripts_dir}/run_twitter_simulation.py --config {config_path}",
                "reddit": f"python {scripts_dir}/run_reddit_simulation.py --config {config_path}",
                "parallel": f"python {scripts_dir}/run_parallel_simulation.py --config {config_path}",
            },
            "instructions": (
                f"1. 激活conda环境: conda activate MiroFish\n"
                f"2. 运行模拟 (脚本位于 {scripts_dir}):\n"
                f"   - 单独运行Twitter: python {scripts_dir}/run_twitter_simulation.py --config {config_path}\n"
                f"   - 单独运行Reddit: python {scripts_dir}/run_reddit_simulation.py --config {config_path}\n"
                f"   - 并行运行双平台: python {scripts_dir}/run_parallel_simulation.py --config {config_path}"
            )
        }
