"""
图谱构建服务
使用 GraphStore 抽象构建与管理知识图谱
"""

from dataclasses import dataclass
import hashlib
import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.graph_store import (
    BatchSubmissionRecord,
    GraphInfo,
    GraphNotFoundError,
    GraphStore,
    GraphStoreError,
    GraphTimeoutError,
    GraphValidationError,
    get_graph_store,
)
from ..utils.locale import get_locale, set_locale, t
from .text_processor import TextProcessor

DEFAULT_INGESTION_WAIT_TIMEOUT_SECONDS = 600.0

# Alias de compatibilité pour les appelants existants
BatchSubmission = BatchSubmissionRecord


@dataclass(frozen=True)
class DocumentChunkPlan:
    """Découpage d'un ensemble de documents, prêt à être ingéré.

    Les fragments sont découpés **par document**, jamais sur la concaténation : un
    fragment qui chevauchant deux fichiers n'est attribuable à aucun (R04). La
    concaténation reste disponible comme contexte de prompt, via `context_text`.
    """

    chunks: List[str]
    chunk_metadata: List[Dict[str, Any]]
    context_text: str
    diagnostics: Dict[str, Any]

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)

    def per_document_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in self.chunk_metadata:
            document_id = entry["source_document_id"]
            counts[document_id] = counts.get(document_id, 0) + 1
        return counts


def plan_document_chunks(
    documents: List[Dict[str, Any]],
    document_texts: Dict[str, str],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> DocumentChunkPlan:
    """Découpe chaque document séparément et produit des métadonnées alignées.

    `documents` est une liste de dictionnaires ou d'objets `SourceDocument` ; le
    texte correspondant est cherché dans `document_texts` par `document_id`.

    Un document dont le texte est absent du projet est **signalé** dans les
    diagnostics et ne produit aucun fragment : il ne doit pas disparaître en
    silence. Un document dont le texte normalisé est vide est également signalé.
    """
    chunks: List[str] = []
    metadata: List[Dict[str, Any]] = []
    context_parts: List[str] = []
    omitted_documents: List[Dict[str, str]] = []

    for document in documents:
        try:
            source = to_source_document_dict(document)
        except ValueError as error:
            omitted_documents.append(
                {
                    "document_id": str(
                        document.get("document_id") if isinstance(document, dict) else ""
                    ),
                    "filename": "",
                    "reason": f"document source invalide : {error}",
                }
            )
            continue
        document_id = source["document_id"]
        filename = source["filename"]
        role = source["role"]

        normalized_text = document_texts.get(document_id)
        if normalized_text is None:
            omitted_documents.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "reason": "texte normalisé absent du projet",
                }
            )
            continue
        if not normalized_text.strip():
            omitted_documents.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "reason": "texte normalisé vide",
                }
            )
            continue

        context_parts.append(f"=== {filename} ===\n{normalized_text}")

        # Positions exactes issues du découpage lui-même (AC2) : jamais d'une
        # recherche de sous-chaîne, qui choisirait la première occurrence sur un
        # texte répétitif.
        spans = TextProcessor.split_text_with_offsets(
            normalized_text, chunk_size, chunk_overlap
        )
        if not spans:
            omitted_documents.append(
                {
                    "document_id": document_id,
                    "filename": filename,
                    "reason": "aucun fragment produit",
                }
            )
            continue

        for local_index, (chunk_text, char_start, char_end) in enumerate(spans):
            chunks.append(chunk_text)
            metadata.append(
                {
                    "source_document_id": document_id,
                    "source_filename": filename,
                    "chunk_index": local_index,
                    "char_start": char_start,
                    "char_end": char_end,
                    "source_role": role,
                }
            )

    # Diagnostics calculés **après** construction : un document dont tous les
    # fragments auraient été écartés ne doit pas être compté comme ingéré.
    per_document: Dict[str, int] = {}
    for entry in metadata:
        document_id = entry["source_document_id"]
        per_document[document_id] = per_document.get(document_id, 0) + 1

    diagnostics = {
        "documents_total": len(documents),
        "documents_ingested": len(per_document),
        "documents_omitted": omitted_documents,
        "chunks_total": len(chunks),
        "chunks_per_document": per_document,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
    }

    return DocumentChunkPlan(
        chunks=chunks,
        chunk_metadata=metadata,
        context_text="\n\n".join(context_parts),
        diagnostics=diagnostics,
    )


def to_source_document_dict(document: Any) -> Dict[str, Any]:
    """Accepte un `SourceDocument` ou son dictionnaire, sans en deviner le contenu."""

    if isinstance(document, dict):
        data = dict(document)
    elif hasattr(document, "to_dict"):
        data = document.to_dict()
    else:
        raise ValueError(
            "un document source doit être un SourceDocument ou un dictionnaire"
        )
    if not data.get("document_id"):
        raise ValueError("chaque document source doit porter un document_id")
    if not data.get("filename"):
        raise ValueError("un document source doit porter un filename")
    if not data.get("role"):
        raise ValueError("un document source doit porter un role")
    return data


class GraphBuilderService:
    """
    图谱构建服务
    负责通过 GraphStore 构建与管理知识图谱
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        store: Optional[GraphStore] = None,
    ):
        """Initialise le service de construction de graphe.

        Args:
            api_key: Clé d'API Zep Cloud optionnelle (si omise, utilise Config.ZEP_API_KEY).
                Strictement superflue lorsque ZEP_BACKEND='graphiti'.
            store: Instance explicite de GraphStore (injection pour tests ou overrides).
                Si None, résolue dynamiquement via get_graph_store(api_key=...).
        """
        self.api_key = api_key or Config.ZEP_API_KEY
        if store is not None:
            self.store = store
        else:
            self.store = get_graph_store(api_key=self.api_key)

        self.task_manager = TaskManager()

    @property
    def client(self) -> Any:
        """Accès de compatibilité au client sous-jacent (si présent)."""
        return getattr(self.store, "_client", None)

    @client.setter
    def client(self, value: Any) -> None:
        """Permet l'injection directe d'un client mocké en créant un ZepGraphStore."""
        if isinstance(value, GraphStore):
            self.store = value
            return
        from ..utils.graph_store.zep_store import ZepGraphStore

        self.store = ZepGraphStore(client=value)

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 350,
    ) -> str:
        """
        异步构建图谱

        Args:
            text: 输入文本
            ontology: 本体定义
            graph_name: 图谱名称
            chunk_size: 文本块大小
            chunk_overlap: 块重叠大小
            batch_size: 每批发送的块数量

        Returns:
            任务ID
        """
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            },
        )

        current_locale = get_locale()

        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(
                task_id,
                text,
                ontology,
                graph_name,
                chunk_size,
                chunk_overlap,
                batch_size,
                current_locale,
            ),
        )
        thread.daemon = True
        thread.start()

        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        locale: str = "zh",
    ):
        """图谱构建工作线程"""
        set_locale(locale)
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message=t("progress.startBuildingGraph"),
            )

            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            self.validate_batch_chunks(chunks, batch_size=batch_size)
            total_chunks = len(chunks)

            # 1. 创建图谱
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=t("progress.graphCreated", graphId=graph_id),
            )

            # 2. 设置本体
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message=t("progress.ontologySet"),
            )

            # 3. 文本分块
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=t("progress.textSplit", count=total_chunks),
            )

            # 4. 分批发送数据
            submission = self.add_text_batches(
                graph_id,
                chunks,
                batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 40),  # 20-60%
                    message=msg,
                ),
            )

            # 5. 等待处理完成
            self.task_manager.update_task(
                task_id,
                progress=60,
                message=t("progress.waitingZepProcess"),
            )

            self._wait_for_batch(
                submission,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=60 + int(prog * 30),  # 60-90%
                    message=msg,
                ),
            )

            # 6. 获取图谱信息
            self.task_manager.update_task(
                task_id,
                progress=90,
                message=t("progress.fetchingGraphInfo"),
            )

            graph_info = self._get_graph_info(graph_id)

            # 完成
            self.task_manager.complete_task(
                task_id,
                {
                    "graph_id": graph_id,
                    "graph_info": graph_info.to_dict(),
                    "chunks_processed": total_chunks,
                },
            )

        except Exception as e:
            import traceback

            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)

    def create_graph(
        self,
        name: str,
        *,
        graph_id: str | None = None,
        graph_id_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Crée un graphe via le GraphStore avec réconciliation."""
        target_graph_id = graph_id or f"mirofish_{uuid.uuid4().hex[:16]}"
        if graph_id_callback:
            graph_id_callback(target_graph_id)

        return self.store.create_graph(name=name, graph_id=target_graph_id)

    @staticmethod
    def build_operation_id(
        graph_id: str,
        chunks: List[str],
        chunk_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Génère un identifiant déterministe d'opération d'ingestion.

        Sans métadonnées, le hachage est strictement celui d'avant : un lot déjà
        persisté dans `project.json` et repris après redémarrage reste
        reconnaissable. Avec métadonnées, celles-ci entrent dans le hachage, pour
        que deux textes identiques de deux documents différents ne soient jamais
        confondus lors d'une réconciliation (ADR 0012 §1).
        """
        payload_hash = hashlib.sha256("\0".join(chunks).encode("utf-8")).hexdigest()
        if chunk_metadata:
            canonical = json.dumps(
                chunk_metadata, ensure_ascii=False, sort_keys=True
            ).encode("utf-8")
            payload_hash = hashlib.sha256(
                payload_hash.encode("ascii") + b"\0" + canonical
            ).hexdigest()
        return hashlib.sha256(f"{graph_id}:{payload_hash}".encode("utf-8")).hexdigest()

    def set_ontology(
        self,
        graph_id: str,
        ontology: Dict[str, Any],
        *,
        strict: bool = False,
    ) -> None:
        """Définit l'ontologie du graphe via le GraphStore.

        Depuis l'ADR 0014 l'ontologie est **effectivement posée** : le store la
        retient pour ce `graph_id`, et les écritures suivantes — y compris
        celles déclenchées par `add_text_batches` sur ce même `self.store` —
        consomment les types déclarés. L'ordre `set_ontology` puis ingestion est
        donc porteur, et c'est cet ordre que `_build_graph_worker` garantit.

        `strict` est propagé tel quel au store ; le wrapper ne le consomme
        pas. Le contrat v2 reste exposé aux appelants qui voudront poser la
        politique dès la 007-2.

        Returns:
            None. Aucun appelant aval ne consomme de retour ; l'ontologie
            appliquée se relit par `store.get_applied_ontology(graph_id)`.
        """
        if strict and not self.store.supports_pre_persistence_ontology_validation:
            raise GraphValidationError(
                "La politique strict_ontology exige une validation avant persistance "
                "que ce backend de graphe ne garantit pas"
            )
        self.store.set_ontology(graph_id=graph_id, ontology=ontology, strict=strict)

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable] = None,
        batch_created_callback: Optional[Callable[[str | None, str], None]] = None,
        chunk_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> BatchSubmissionRecord:
        """Soumet des morceaux de documents par lot au GraphStore.

        `chunk_metadata` est transmis tel quel au store, qui le valide avant
        toute écriture (ADR 0012 §1). Les métadonnées entrent aussi dans
        l'identité d'opération : deux textes identiques issus de deux documents
        différents sont deux opérations distinctes.
        """
        if not graph_id:
            raise ValueError("graph_id is required")
        self.validate_batch_chunks(chunks, batch_size=batch_size)

        operation_id = self.build_operation_id(graph_id, chunks, chunk_metadata)
        if batch_created_callback:
            batch_created_callback(None, operation_id)

        # Normalise le callback pour tolérer les signatures (msg, prog) ou (status, current, total)
        adapted_progress: Optional[Callable[[str, int, int], None]] = None
        if progress_callback:
            import inspect

            try:
                sig = inspect.signature(progress_callback)
                params = list(sig.parameters.values())
                varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)
                if varargs or len(params) >= 3:
                    adapted_progress = progress_callback
                elif len(params) == 2:
                    adapted_progress = lambda status, current, total: progress_callback(
                        status, current / total if total > 0 else 0.0
                    )
                else:
                    adapted_progress = lambda status, current, total: progress_callback(status)
            except Exception:
                adapted_progress = progress_callback

        submission = self.store.add_text_batch(
            graph_id=graph_id,
            chunks=chunks,
            batch_size=batch_size,
            progress_callback=adapted_progress,
            chunk_metadata=chunk_metadata,
        )

        if batch_created_callback:
            batch_created_callback(submission.batch_id, submission.operation_id)

        return submission

    @staticmethod
    def validate_batch_chunks(chunks: List[str], *, batch_size: int = 350) -> None:
        """Valide les limites des fragments avant ingestion."""
        if not chunks:
            raise ValueError("At least one text chunk is required")
        if not 1 <= batch_size <= 350:
            raise ValueError("batch_size must be between 1 and 350")
        if len(chunks) > 50_000:
            raise ValueError("A batch cannot contain more than 50,000 items")
        oversized = [index for index, chunk in enumerate(chunks) if len(chunk) > 10_000]
        if oversized:
            raise ValueError(
                f"Batch item exceeds 10,000 characters at chunk {oversized[0]}"
            )

    def _wait_for_batch(
        self,
        submission: BatchSubmissionRecord,
        progress_callback: Optional[Callable] = None,
        timeout: int | float | None = None,
    ) -> List[str]:
        """Attend la fin du traitement asynchrone du lot."""
        timeout_val = (
            float(timeout)
            if timeout is not None
            else DEFAULT_INGESTION_WAIT_TIMEOUT_SECONDS
        )
        self.store.wait_for_batch(
            batch=submission,
            progress_callback=progress_callback,
            timeout=timeout_val,
        )
        return list(submission.episode_uuids)

    def _wait_for_episodes(
        self,
        episode_uuids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int | float | None = None,
        graph_id: str = "graph_default",
    ) -> None:
        """Attend le traitement d'une liste d'épisodes."""
        if not episode_uuids:
            if progress_callback:
                progress_callback(t("progress.noEpisodesWait"), 1.0)
            return

        timeout_val = (
            float(timeout)
            if timeout is not None
            else DEFAULT_INGESTION_WAIT_TIMEOUT_SECONDS
        )
        self.store.wait_for_episodes(
            graph_id=graph_id or "graph_default",
            episode_uuids=episode_uuids,
            timeout=timeout_val,
        )
        if progress_callback:
            progress_callback(
                t("progress.processingComplete", completed=len(episode_uuids), total=len(episode_uuids)),
                1.0,
            )

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """Récupère les informations résumées du graphe."""
        return self.store.get_graph_info(graph_id)

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        """Récupère les informations résumées du graphe (méthode publique)."""
        return self.store.get_graph_info(graph_id)

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """Récupère les données complètes du graphe (nœuds, arêtes, statistiques)."""
        return self.store.get_graph_data(graph_id)

    def delete_graph(self, graph_id: str) -> None:
        """Supprime un graphe."""
        self.store.delete_graph(graph_id)
