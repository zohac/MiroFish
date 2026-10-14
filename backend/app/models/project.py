"""
项目上下文管理
用于在服务端持久化项目状态，避免前端在接口间传递大量数据
"""

import os
import json
import re
import uuid
import shutil
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass, field, asdict
from ..config import Config


class ProjectStatus(str, Enum):
    """项目状态"""
    CREATED = "created"              # 刚创建，文件已上传
    ONTOLOGY_GENERATED = "ontology_generated"  # 本体已生成
    GRAPH_BUILDING = "graph_building"    # 图谱构建中
    GRAPH_COMPLETED = "graph_completed"  # 图谱构建完成
    FAILED = "failed"                # 失败


@dataclass
class Project:
    """项目数据模型"""
    project_id: str
    name: str
    status: ProjectStatus
    created_at: str
    updated_at: str
    
    # 文件信息
    files: List[Dict[str, str]] = field(default_factory=list)  # [{filename, path, size}]
    total_text_length: int = 0
    
    # 本体信息（接口1生成后填充）
    ontology: Optional[Dict[str, Any]] = None
    analysis_summary: Optional[str] = None
    
    # 图谱信息（接口2完成后填充）
    graph_id: Optional[str] = None
    graph_build_task_id: Optional[str] = None
    zep_batch_id: Optional[str] = None
    zep_batch_operation_id: Optional[str] = None
    
    # 配置
    simulation_requirement: Optional[str] = None
    chunk_size: int = 500
    chunk_overlap: int = 50
    strict_ontology: bool = False
    
    # --- Story 007-4 : ontologie dynamique appliquée et versionnée ---
    applied_ontology_id: Optional[str] = None
    applied_ontology_version: int = 0
    ontology_history: List[str] = field(default_factory=list)

    # 错误信息
    error: Optional[str] = None

    # --- Story 009-2 : documents sources typés, brief versionné ---
    # Champs strictement additifs : un ancien project.json se relit avec des
    # valeurs par défaut, et la lecture seule ne fabrique aucun document
    # (provenance « inconnue », jamais reconstruite).
    source_documents: List[Dict[str, Any]] = field(default_factory=list)
    simulation_brief: Optional[Dict[str, Any]] = None
    additional_context: Optional[str] = None
    #: Conflits de sources conservés (story 009-2, AC8). Les deux sources de
    #: chaque conflit restent attachées : aucune fusion silencieuse. C'est le
    #: point de stockage ; l'arbitrage humain appartient à 009-3.
    source_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "project_id": self.project_id,
            "name": self.name,
            "status": self.status.value if isinstance(self.status, ProjectStatus) else self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "files": self.files,
            "total_text_length": self.total_text_length,
            "ontology": self.ontology,
            "analysis_summary": self.analysis_summary,
            "graph_id": self.graph_id,
            "graph_build_task_id": self.graph_build_task_id,
            "zep_batch_id": self.zep_batch_id,
            "zep_batch_operation_id": self.zep_batch_operation_id,
            "simulation_requirement": self.simulation_requirement,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "strict_ontology": self.strict_ontology,
            "applied_ontology_id": self.applied_ontology_id,
            "applied_ontology_version": self.applied_ontology_version,
            "ontology_history": list(self.ontology_history),
            "error": self.error,
            "source_documents": self.source_documents,
            "simulation_brief": self.simulation_brief,
            "additional_context": self.additional_context,
            "source_conflicts": self.source_conflicts
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """从字典创建"""
        status = data.get('status', 'created')
        if isinstance(status, str):
            status = ProjectStatus(status)
        
        return cls(
            project_id=data['project_id'],
            name=data.get('name', 'Unnamed Project'),
            status=status,
            created_at=data.get('created_at', ''),
            updated_at=data.get('updated_at', ''),
            files=data.get('files', []),
            total_text_length=data.get('total_text_length', 0),
            ontology=data.get('ontology'),
            analysis_summary=data.get('analysis_summary'),
            graph_id=data.get('graph_id'),
            graph_build_task_id=data.get('graph_build_task_id'),
            zep_batch_id=data.get('zep_batch_id'),
            zep_batch_operation_id=data.get('zep_batch_operation_id'),
            simulation_requirement=data.get('simulation_requirement'),
            chunk_size=data.get('chunk_size', 500),
            chunk_overlap=data.get('chunk_overlap', 50),
            strict_ontology=(
                data.get('strict_ontology', False)
                if type(data.get('strict_ontology', False)) is bool
                else False
            ),
            applied_ontology_id=data.get('applied_ontology_id'),
            applied_ontology_version=int(data.get('applied_ontology_version', 0) or 0),
            ontology_history=list(data.get('ontology_history', []) or []),
            error=data.get('error'),
            source_documents=data.get('source_documents', []),
            simulation_brief=data.get('simulation_brief'),
            additional_context=data.get('additional_context'),
            source_conflicts=data.get('source_conflicts', [])
        )

    def get_brief(self):
        """Retourne le brief persisté, ou ``None`` pour un projet ancien.

        Un projet sans brief n'en reconstruit pas un : la fabrication d'un
        objectif à partir d'un autre champ masquerait l'absence de consigne
        structurée (AC6).
        """
        from .simulation_brief import SimulationBrief

        if not self.simulation_brief:
            return None
        return SimulationBrief.from_dict(self.simulation_brief)

    def get_source_documents(self):
        """Retourne les documents persistés, éventuellement vides.

        Un projet ancien n'a pas de document : la liste est vide, jamais peuplée
        d'une entrée inventée à partir de ``files``.
        """
        from .source_document import SourceDocument

        return [
            SourceDocument.from_dict(entry) for entry in (self.source_documents or [])
        ]

    def get_source_conflicts(self):
        """Retourne les conflits de sources persistés (AC8), éventuellement vides.

        Un conflit conserve **ses deux sources** : c'est le point de stockage de
        la story 009-2 ; l'arbitrage humain appartient à 009-3.
        """
        from .source_document import SourceConflict

        return [
            SourceConflict.from_dict(entry) for entry in (self.source_conflicts or [])
        ]

    def record_source_conflicts(self, conflicts) -> None:
        """Stoque une liste de conflits de sources dans le projet."""

        self.source_conflicts = [conflict.to_dict() for conflict in conflicts]

    def apply_ontology(self, version) -> None:
        """Applique une version d'ontologie de manière monotone (story 007-4, AC2).
        
        Incrémente le compteur appliqué, met à jour l'identifiant courant et
        alimente l'historique sans duplication immédiate.
        """
        version_id = getattr(version, "version_id", None) or str(version)
        if not version_id or not version_id.startswith("ont_"):
            raise ValueError(f"Identifiant de version d'ontologie invalide (doit commencer par 'ont_') : {version_id!r}")
        
        self.applied_ontology_id = version_id
        self.applied_ontology_version = (self.applied_ontology_version or 0) + 1
        if not self.ontology_history:
            self.ontology_history = []
        self.ontology_history.append(version_id)

    def get_applied_ontology(self):
        """Relit la version d'ontologie courante depuis OntologyVersionStore (AC2)."""
        if not self.applied_ontology_id:
            return None
        from .ontology_version import OntologyVersionStore
        return OntologyVersionStore.get(self.applied_ontology_id)


class ProjectManager:
    """项目管理器 - 负责项目的持久化存储和检索"""
    
    # 项目存储根目录
    PROJECTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'projects')

    @staticmethod
    def _safe_document_id(document_id: str) -> str:
        """Valide un identifiant de document avant de l'utiliser comme nom de fichier."""
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError("document_id is required")
        candidate = document_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", candidate):
            raise ValueError(f"document_id invalide : {document_id!r}")
        return candidate
    
    @classmethod
    def _ensure_projects_dir(cls):
        """确保项目目录存在"""
        os.makedirs(cls.PROJECTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_project_dir(cls, project_id: str) -> str:
        """获取项目目录路径"""
        return os.path.join(cls.PROJECTS_DIR, project_id)
    
    @classmethod
    def _get_project_meta_path(cls, project_id: str) -> str:
        """获取项目元数据文件路径"""
        return os.path.join(cls._get_project_dir(project_id), 'project.json')
    
    @classmethod
    def _get_project_files_dir(cls, project_id: str) -> str:
        """获取项目文件存储目录"""
        return os.path.join(cls._get_project_dir(project_id), 'files')
    
    @classmethod
    def _get_project_text_path(cls, project_id: str) -> str:
        """获取项目提取文本存储路径"""
        return os.path.join(cls._get_project_dir(project_id), 'extracted_text.txt')

    @classmethod
    def _get_project_documents_dir(cls, project_id: str) -> str:
        """文本按文档存储的目录（story 009-2）。

        Le texte normalisé de chaque document est conservé séparément : c'est ce
        qui permet de vérifier plus tard que
        ``document_text[char_start:char_end] == chunk_text`` (AC2).
        """
        return os.path.join(cls._get_project_dir(project_id), 'documents')
    
    @classmethod
    def create_project(cls, name: str = "Unnamed Project") -> Project:
        """
        创建新项目
        
        Args:
            name: 项目名称
            
        Returns:
            新创建的Project对象
        """
        cls._ensure_projects_dir()
        
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        
        project = Project(
            project_id=project_id,
            name=name,
            status=ProjectStatus.CREATED,
            created_at=now,
            updated_at=now
        )
        
        # 创建项目目录结构
        project_dir = cls._get_project_dir(project_id)
        files_dir = cls._get_project_files_dir(project_id)
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(files_dir, exist_ok=True)
        
        # 保存项目元数据
        cls.save_project(project)
        
        return project
    
    @classmethod
    def save_project(cls, project: Project) -> None:
        """保存项目元数据"""
        project.updated_at = datetime.now().isoformat()
        meta_path = cls._get_project_meta_path(project.project_id)
        
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(project.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_project(cls, project_id: str) -> Optional[Project]:
        """
        获取项目
        
        Args:
            project_id: 项目ID
            
        Returns:
            Project对象，如果不存在返回None
        """
        meta_path = cls._get_project_meta_path(project_id)
        
        if not os.path.exists(meta_path):
            return None
        
        with open(meta_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return Project.from_dict(data)
    
    @classmethod
    def list_projects(cls, limit: Optional[int] = 50) -> List[Project]:
        """
        列出所有项目
        
        Args:
            limit: 返回数量限制
            
        Returns:
            项目列表，按创建时间倒序
        """
        cls._ensure_projects_dir()
        
        projects = []
        for project_id in os.listdir(cls.PROJECTS_DIR):
            project = cls.get_project(project_id)
            if project:
                projects.append(project)
        
        # 按创建时间倒序排序
        projects.sort(key=lambda p: p.created_at, reverse=True)
        
        return projects if limit is None else projects[:limit]

    @classmethod
    def find_projects_by_graph_id(cls, graph_id: str) -> List[Project]:
        """Return every persisted project that references a Cloud graph."""

        return [
            project
            for project in cls.list_projects(limit=None)
            if project.graph_id == graph_id
        ]
    
    @classmethod
    def delete_project(cls, project_id: str) -> bool:
        """
        删除项目及其所有文件
        
        Args:
            project_id: 项目ID
            
        Returns:
            是否删除成功
        """
        project_dir = cls._get_project_dir(project_id)
        
        if not os.path.exists(project_dir):
            return False
        
        shutil.rmtree(project_dir)
        return True
    
    @classmethod
    def save_file_to_project(cls, project_id: str, file_storage, original_filename: str) -> Dict[str, str]:
        """
        保存上传的文件到项目目录
        
        Args:
            project_id: 项目ID
            file_storage: Flask的FileStorage对象
            original_filename: 原始文件名
            
        Returns:
            文件信息字典 {filename, path, size}
        """
        files_dir = cls._get_project_files_dir(project_id)
        os.makedirs(files_dir, exist_ok=True)
        
        # 生成安全的文件名
        ext = os.path.splitext(original_filename)[1].lower()
        safe_filename = f"{uuid.uuid4().hex[:8]}{ext}"
        file_path = os.path.join(files_dir, safe_filename)
        
        # 保存文件
        file_storage.save(file_path)
        
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        
        return {
            "original_filename": original_filename,
            "saved_filename": safe_filename,
            "path": file_path,
            "size": file_size
        }
    
    @classmethod
    def save_extracted_text(cls, project_id: str, text: str) -> None:
        """保存提取的文本"""
        text_path = cls._get_project_text_path(project_id)
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(text)
    
    @classmethod
    def get_extracted_text(cls, project_id: str) -> Optional[str]:
        """获取提取的文本"""
        text_path = cls._get_project_text_path(project_id)
        
        if not os.path.exists(text_path):
            return None
        
        with open(text_path, 'r', encoding='utf-8') as f:
            return f.read()

    @classmethod
    def save_document_text(cls, project_id: str, document_id: str, text: str) -> str:
        """按文档保存归一化文本（story 009-2, AC2）。

        返回写入的路径。``document_id`` est validé pour ne jamais s'échapper du
        répertoire du projet : un identifiantissu d'une requête ne doit pas
        pouvoir écrire ailleurs.
        """
        safe_id = cls._safe_document_id(document_id)
        documents_dir = cls._get_project_documents_dir(project_id)
        os.makedirs(documents_dir, exist_ok=True)
        path = os.path.join(documents_dir, f"{safe_id}.txt")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path

    @classmethod
    def get_document_text(cls, project_id: str, document_id: str) -> Optional[str]:
        """读取某个文档的归一化文本；不存在时返回 None 而非空串。"""
        safe_id = cls._safe_document_id(document_id)
        path = os.path.join(cls._get_project_documents_dir(project_id), f"{safe_id}.txt")
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    @classmethod
    def get_all_document_texts(cls, project_id: str) -> Dict[str, str]:
        """返回全部文档文本 {document_id: text}；项目 ancien 返回空字典。"""
        documents_dir = cls._get_project_documents_dir(project_id)
        if not os.path.isdir(documents_dir):
            return {}
        texts: Dict[str, str] = {}
        for entry in os.listdir(documents_dir):
            if not entry.endswith('.txt'):
                continue
            full_path = os.path.join(documents_dir, entry)
            if not os.path.isfile(full_path):
                continue
            with open(full_path, 'r', encoding='utf-8') as f:
                texts[entry[:-4]] = f.read()
        return texts
    
    @classmethod
    def get_project_files(cls, project_id: str) -> List[str]:
        """获取项目的所有文件路径"""
        files_dir = cls._get_project_files_dir(project_id)
        
        if not os.path.exists(files_dir):
            return []
        
        return [
            os.path.join(files_dir, f) 
            for f in os.listdir(files_dir) 
            if os.path.isfile(os.path.join(files_dir, f))
        ]
