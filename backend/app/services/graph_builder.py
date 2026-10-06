"""
图谱构建服务
使用 GraphStore 抽象构建与管理知识图谱
"""

from dataclasses import dataclass
import hashlib
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
    get_graph_store,
)
from ..utils.locale import get_locale, set_locale, t
from .text_processor import TextProcessor

DEFAULT_INGESTION_WAIT_TIMEOUT_SECONDS = 600.0

# Alias de compatibilité pour les appelants existants
BatchSubmission = BatchSubmissionRecord


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
    def build_operation_id(graph_id: str, chunks: List[str]) -> str:
        """Génère un identifiant déterministe d'opération d'ingestion."""
        payload_hash = hashlib.sha256("\0".join(chunks).encode("utf-8")).hexdigest()
        return hashlib.sha256(f"{graph_id}:{payload_hash}".encode("utf-8")).hexdigest()

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        """Définit l'ontologie du graphe via le GraphStore."""
        self.store.set_ontology(graph_id=graph_id, ontology=ontology)

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable] = None,
        batch_created_callback: Optional[Callable[[str | None, str], None]] = None,
    ) -> BatchSubmissionRecord:
        """Soumet des morceaux de documents par lot au GraphStore."""
        if not graph_id:
            raise ValueError("graph_id is required")
        self.validate_batch_chunks(chunks, batch_size=batch_size)

        operation_id = self.build_operation_id(graph_id, chunks)
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
