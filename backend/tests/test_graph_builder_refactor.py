"""Tests unitaires du refactoring de l'ingestion (Story 002-4)."""

import sys
from typing import Any, Callable, Dict, List, Optional
import pytest

from app.services.graph_builder import (
    BatchSubmission,
    GraphBuilderService,
)
from app.services.zep_graph_memory_updater import (
    AgentActivity,
    ZepGraphMemoryManager,
    ZepGraphMemoryUpdater,
)
from app.utils.graph_store.base import (
    BatchSubmissionRecord,
    EpisodeRecord,
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphSearchResult,
    GraphStore,
)
from app.utils.graph_store.errors import (
    GraphNotFoundError,
    GraphStoreError,
    GraphTimeoutError,
    GraphValidationError,
)


class MockIngestionStore(GraphStore):
    """Store factice enregistrant tous les appels d'ingestion pour les assertions."""

    def __init__(self):
        self.calls: List[tuple[str, Dict[str, Any]]] = []
        self.created_graphs: Dict[str, str] = {}
        self.ontologies: Dict[str, Dict[str, Any]] = {}
        self.episodes: List[Dict[str, Any]] = []

    def create_graph(self, name: str, graph_id: Optional[str] = None) -> str:
        gid = graph_id or f"mock_{len(self.created_graphs) + 1}"
        self.created_graphs[gid] = name
        self.calls.append(("create_graph", {"name": name, "graph_id": gid}))
        return gid

    def delete_graph(self, graph_id: str) -> None:
        self.calls.append(("delete_graph", {"graph_id": graph_id}))
        self.created_graphs.pop(graph_id, None)

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        self.calls.append(("get_graph_data", {"graph_id": graph_id}))
        return {
            "graph_id": graph_id,
            "nodes": [{"uuid": "n-1", "name": "TestNode"}],
            "edges": [{"uuid": "e-1", "name": "REL"}],
            "node_count": 1,
            "edge_count": 1,
            "statistics": {"node_count": 1, "edge_count": 1},
        }

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        self.calls.append(("get_graph_info", {"graph_id": graph_id}))
        return GraphInfo(graph_id=graph_id, node_count=1, edge_count=1, entity_types=["Test"])

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        self.ontologies[graph_id] = ontology
        self.calls.append(("set_ontology", {"graph_id": graph_id, "ontology": ontology}))

    def add_episode(
        self,
        graph_id: str,
        text: str,
        source_description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> EpisodeRecord:
        ep_uuid = f"ep-{len(self.episodes) + 1}"
        record = {
            "uuid": ep_uuid,
            "graph_id": graph_id,
            "text": text,
            "source_description": source_description,
            "metadata": metadata or {},
            "created_at": created_at,
        }
        self.episodes.append(record)
        self.calls.append(("add_episode", record))
        return EpisodeRecord(uuid=ep_uuid, graph_id=graph_id, processed=True, created_at=created_at)

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> BatchSubmissionRecord:
        self.calls.append(("add_text_batch", {"graph_id": graph_id, "chunks": chunks, "batch_size": batch_size}))
        if progress_callback:
            progress_callback("sending", len(chunks), len(chunks))
        return BatchSubmissionRecord(
            batch_id="mock-batch-1",
            operation_id="mock-op-1",
            episode_uuids=[f"ep-{i}" for i in range(len(chunks))],
            item_count=len(chunks),
        )

    def wait_for_batch(
        self,
        batch: BatchSubmissionRecord,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        timeout: float = 600.0,
    ) -> bool:
        self.calls.append(("wait_for_batch", {"batch_id": batch.batch_id, "timeout": timeout}))
        if progress_callback:
            progress_callback("completed", 1.0)
        return True

    def wait_for_episodes(
        self,
        graph_id: str,
        episode_uuids: List[str],
        timeout: float = 600.0,
    ) -> bool:
        self.calls.append(("wait_for_episodes", {"graph_id": graph_id, "episode_uuids": episode_uuids, "timeout": timeout}))
        return True

    def get_all_nodes(self, graph_id: str) -> List[GraphNode]:
        return []

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[GraphEdge]:
        return []

    def get_node(self, graph_id: str, node_uuid: str) -> Optional[GraphNode]:
        return None

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[GraphEdge]:
        return []

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
        reranker: Optional[str] = None,
    ) -> GraphSearchResult:
        return GraphSearchResult(facts=[], nodes=[], edges=[], query=query, total_count=0)


def test_graph_builder_imports_are_decoupled_from_zep_cloud():
    """Vérifie que graph_builder et zep_graph_memory_updater n'importent aucun symbole propriétaire au niveau module."""
    import app.services.graph_builder as gb_module

    assert "get_zep_client" not in gb_module.__dict__
    assert "call_zep_read_with_retry" not in gb_module.__dict__
    assert "is_retryable_zep_error" not in gb_module.__dict__
    assert "fetch_all_nodes" not in gb_module.__dict__
    assert "fetch_all_edges" not in gb_module.__dict__
    assert "ZepGraphStore" not in gb_module.__dict__


def test_zep_graph_memory_updater_imports_are_decoupled_from_utils_zep():
    """Vérifie que zep_graph_memory_updater n'importe ni utils.zep ni ZepGraphStore au niveau module."""
    import app.services.zep_graph_memory_updater as mu_module

    assert "get_zep_client" not in mu_module.__dict__
    assert "call_zep_read_with_retry" not in mu_module.__dict__
    assert "ZEP_INGESTION_WAIT_TIMEOUT_SECONDS" not in mu_module.__dict__
    assert "ZepGraphStore" not in mu_module.__dict__


def test_simulation_runner_imports_are_decoupled_from_utils_zep():
    """Vérifie que simulation_runner n'importe plus de constantes propriétaires de utils.zep."""
    import app.services.simulation_runner as sr_module

    assert "ZEP_HTTP_REQUEST_TIMEOUT_SECONDS" not in sr_module.__dict__
    assert "ZEP_INGESTION_WAIT_TIMEOUT_SECONDS" not in sr_module.__dict__


def test_client_setter_supports_direct_graph_store_injection():
    """Vérifie que client.setter affecte directement un GraphStore s'il en reçoit un."""
    store = MockIngestionStore()
    service = GraphBuilderService(store=store)

    new_store = MockIngestionStore()
    service.client = new_store
    assert service.store is new_store


def test_add_text_batches_adapts_two_argument_progress_callback():
    """Vérifie que add_text_batches adapte sans erreur un callback legacy à 2 arguments (msg, prog)."""
    store = MockIngestionStore()
    service = GraphBuilderService(store=store)

    calls = []

    def legacy_cb(msg: str, prog: float):
        calls.append((msg, prog))

    submission = service.add_text_batches(
        "graph-test",
        ["chunk 1", "chunk 2"],
        batch_size=10,
        progress_callback=legacy_cb,
    )
    assert submission.batch_id == "mock-batch-1"
    assert len(calls) == 1
    assert calls[0][0] == "sending"
    assert calls[0][1] == 1.0


def test_build_graph_worker_executes_full_lifecycle_with_progress():
    """Vérifie que _build_graph_worker s'exécute de bout en bout sans TypeError et met à jour le TaskManager."""
    store = MockIngestionStore()
    service = GraphBuilderService(store=store)
    task_id = service.task_manager.create_task(task_type="graph_build", metadata={})

    text = "MiroFish est un moteur de simulation sociale multi-agents local-first."
    service._build_graph_worker(
        task_id=task_id,
        text=text,
        ontology={"entity_types": [{"name": "Agent"}]},
        graph_name="Worker Graph",
        chunk_size=30,
        chunk_overlap=5,
        batch_size=2,
    )

    task = service.task_manager.get_task(task_id)
    assert task is not None
    assert task.status == "completed"
    assert task.progress == 100
    assert task.result is not None
    assert task.result["chunks_processed"] > 0
    assert task.result["graph_id"].startswith("mirofish_")
    assert task.result["graph_info"]["node_count"] == 1


def test_pending_episodes_wait_raises_immediately_if_deadline_past():
    """Vérifie que _wait_for_pending_episodes lève immédiatement GraphTimeoutError si le deadline est déjà dépassé."""
    store = MockIngestionStore()
    updater = ZepGraphMemoryUpdater(
        graph_id="graph-memory-timeout",
        simulation_id="sim-timeout",
        store=store,
    )
    updater._pending_episode_uuids = ["ep-1", "ep-2"]

    with pytest.raises(GraphTimeoutError, match="Délai d'attente d'ingestion"):
        updater._wait_for_pending_episodes(deadline=0.0)


def test_graph_builder_delegates_all_lifecycle_to_injected_store():
    """Vérifie que GraphBuilderService délègue création, ontologie, batch et lecture au GraphStore."""
    store = MockIngestionStore()
    service = GraphBuilderService(store=store)

    # 1. Création de graphe
    gid = service.create_graph("Mon Graphe", graph_id="graph-custom")
    assert gid == "graph-custom"
    assert ("create_graph", {"name": "Mon Graphe", "graph_id": "graph-custom"}) in store.calls

    # 2. Ontologie
    service.set_ontology(gid, {"entity_types": [{"name": "Person"}]})
    assert ("set_ontology", {"graph_id": "graph-custom", "ontology": {"entity_types": [{"name": "Person"}]}}) in store.calls

    # 3. Ingestion par lot
    progress_calls = []
    submission = service.add_text_batches(
        gid,
        ["fragment 1", "fragment 2"],
        batch_size=10,
        progress_callback=lambda st, cur, tot: progress_calls.append((st, cur, tot)),
    )
    assert submission.batch_id == "mock-batch-1"
    assert submission.item_count == 2
    assert ("add_text_batch", {"graph_id": "graph-custom", "chunks": ["fragment 1", "fragment 2"], "batch_size": 10}) in store.calls

    # 4. Attente de lot
    uuids = service._wait_for_batch(submission, timeout=30.0)
    assert uuids == ["ep-0", "ep-1"]
    assert ("wait_for_batch", {"batch_id": "mock-batch-1", "timeout": 30.0}) in store.calls

    # 5. Attente d'épisodes
    service._wait_for_episodes(["ep-0", "ep-1"], graph_id=gid, timeout=25.0)
    assert ("wait_for_episodes", {"graph_id": "graph-custom", "episode_uuids": ["ep-0", "ep-1"], "timeout": 25.0}) in store.calls

    # 6. Lecture des données et infos
    info = service.get_graph_info(gid)
    assert info.graph_id == "graph-custom"
    assert ("get_graph_info", {"graph_id": "graph-custom"}) in store.calls

    data = service.get_graph_data(gid)
    assert data["node_count"] == 1
    assert ("get_graph_data", {"graph_id": "graph-custom"}) in store.calls

    # 7. Suppression
    service.delete_graph(gid)
    assert ("delete_graph", {"graph_id": "graph-custom"}) in store.calls


def test_memory_updater_delegates_episodes_and_barrier_to_injected_store():
    """Vérifie que ZepGraphMemoryUpdater délègue les ajouts d'épisodes et la barrière au GraphStore."""
    store = MockIngestionStore()
    updater = ZepGraphMemoryUpdater(
        graph_id="graph-memory-1",
        simulation_id="sim-memory",
        store=store,
    )
    updater.SEND_INTERVAL = 0
    updater.start()

    activity = AgentActivity(
        platform="twitter",
        agent_id=42,
        agent_name="Alice",
        action_type="CREATE_POST",
        action_args={"content": "Analyse géopolitique"},
        round_num=1,
        timestamp="2026-10-06T12:00:00Z",
    )
    updater.add_activity(activity)
    updater.stop()

    # Vérification que l'épisode a été transmis au store
    assert len(store.episodes) == 1
    ep = store.episodes[0]
    assert ep["graph_id"] == "graph-memory-1"
    assert "Alice" in ep["text"]
    assert ep["metadata"]["simulation_id"] == "sim-memory"
    assert ep["metadata"]["platform"] == "twitter"

    # Vérification de l'appel de barrière d'attente
    assert any(c[0] == "wait_for_episodes" for c in store.calls)


def test_memory_manager_accepts_injected_store():
    """Vérifie que ZepGraphMemoryManager.create_updater propage le store injecté."""
    store = MockIngestionStore()
    sim_id = "sim-manager-test"

    try:
        updater = ZepGraphMemoryManager.create_updater(
            simulation_id=sim_id,
            graph_id="graph-manager",
            store=store,
        )
        assert updater.store is store
        assert ZepGraphMemoryManager.get_updater(sim_id) is updater
    finally:
        ZepGraphMemoryManager.stop_updater(sim_id)
