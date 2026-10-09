"""Tests unitaires et de flux de bout en bout pour la construction de graphe avec GraphitiGraphStore (Story 004-3).

Valide :
1. L'exécution de `GraphBuilderService._build_graph_worker` avec un GraphStore en mode local (Graphiti).
2. La route API `POST /api/graph/build` et son thread d'arrière-plan avec transitions d'état du projet et du TaskManager.
3. La consultation des données du graphe via `GET /api/graph/data/<graph_id>`.
4. La reconstruction de graphe avec purge et force=True.
5. La robustesse en cas d'erreur lors de la construction (passage à FAILED).
"""

from datetime import datetime
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from flask import Flask
import pytest

from app.api import graph as graph_api
from app.config import Config
from app.models.project import Project, ProjectManager, ProjectStatus
from app.models.task import TaskManager, TaskStatus
from app.services.graph_builder import GraphBuilderService
from app.utils.graph_store.base import (
    BatchSubmissionRecord,
    EpisodeRecord,
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphSearchResult,
    GraphStore,
)
from app.utils.graph_store.errors import GraphStoreError, GraphValidationError
from app.utils.graph_store.factory import override_graph_store


class MockE2EGraphitiStore(GraphStore):
    """Store factice simulant fidèlement le comportement de GraphitiGraphStore en local."""

    def __init__(self, should_fail: bool = False, fail_stage: Optional[str] = None):
        self.should_fail = should_fail
        self.fail_stage = fail_stage
        self.created_graphs: Dict[str, str] = {}
        self.deleted_graphs: List[str] = []
        self.ontologies: Dict[str, Dict[str, Any]] = {}
        self.episodes: List[Dict[str, Any]] = []
        self.progress_records: List[tuple[str, int, int]] = []
        self.wait_progress_records: List[tuple[str, float]] = []

        # Données de graphe synthétiques générées après ingestion
        self._nodes: Dict[str, List[GraphNode]] = {}
        self._edges: Dict[str, List[GraphEdge]] = {}

    def create_graph(self, name: str, graph_id: Optional[str] = None) -> str:
        if self.should_fail and self.fail_stage == "create_graph":
            raise GraphStoreError("Erreur simulée lors de create_graph")
        gid = graph_id or f"mirofish_{len(self.created_graphs) + 1}"
        self.created_graphs[gid] = name
        self._nodes[gid] = []
        self._edges[gid] = []
        return gid

    def delete_graph(self, graph_id: str) -> None:
        if self.should_fail and self.fail_stage == "delete_graph":
            raise GraphStoreError("Erreur simulée lors de delete_graph")
        self.deleted_graphs.append(graph_id)
        self.created_graphs.pop(graph_id, None)
        self._nodes.pop(graph_id, None)
        self._edges.pop(graph_id, None)

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        if self.should_fail and self.fail_stage == "set_ontology":
            raise GraphStoreError("Erreur simulée lors de set_ontology")
        self.ontologies[graph_id] = ontology

    def add_episode(
        self,
        graph_id: str,
        text: str,
        source_description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> EpisodeRecord:
        ep_uuid = f"ep-{len(self.episodes) + 1}"
        self.episodes.append({
            "uuid": ep_uuid,
            "graph_id": graph_id,
            "text": text,
            "source_description": source_description,
        })
        return EpisodeRecord(
            uuid=ep_uuid,
            graph_id=graph_id,
            processed=True,
            created_at=created_at or datetime.now().isoformat(),
        )

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> BatchSubmissionRecord:
        if self.should_fail and self.fail_stage == "add_text_batch":
            raise GraphStoreError("Erreur simulée lors de add_text_batch")

        total = len(chunks)
        for i, chunk in enumerate(chunks, 1):
            if progress_callback:
                progress_callback("processing", i, total)
                self.progress_records.append(("processing", i, total))
            self.add_episode(graph_id, chunk, source_description=f"chunk_{i}")

        # Populer des nœuds et arêtes de test
        self._nodes[graph_id] = [
            GraphNode(
                uuid="node-1",
                name="Thalès",
                labels=["Entity", "Organization"],
                summary="Groupe d'électronique et de défense.",
            ),
            GraphNode(
                uuid="node-2",
                name="Marine Nationale",
                labels=["Entity", "Organization"],
                summary="Force maritime des armées.",
            ),
            GraphNode(
                uuid="node-3",
                name="Alice Martin",
                labels=["Entity", "Person"],
                summary="Ingénieure directrice de programme.",
            ),
            GraphNode(
                uuid="node-4",
                name="Radar-2026",
                labels=["Entity", "Project"],
                summary="Système radar nouvelle génération.",
            ),
            GraphNode(
                uuid="node-5",
                name="Brest",
                labels=["Entity", "Location"],
                summary="Port militaire et base navale.",
            ),
        ]
        self._edges[graph_id] = [
            GraphEdge(
                uuid="edge-1",
                name="FOURNIT_EQUIPEMENT",
                fact="Thalès fournit des systèmes à la Marine Nationale.",
                source_node_uuid="node-1",
                target_node_uuid="node-2",
                source_node_name="Thalès",
                target_node_name="Marine Nationale",
                valid_at="2026-05-01T10:00:00Z",
            ),
            GraphEdge(
                uuid="edge-2",
                name="SUPERVISE",
                fact="Alice Martin supervise le projet Radar-2026.",
                source_node_uuid="node-3",
                target_node_uuid="node-4",
                source_node_name="Alice Martin",
                target_node_name="Radar-2026",
                valid_at="2026-06-01T12:00:00Z",
            ),
            GraphEdge(
                uuid="edge-3",
                name="DEPLOIE_A",
                fact="Le Radar-2026 est déployé à Brest.",
                source_node_uuid="node-4",
                target_node_uuid="node-5",
                source_node_name="Radar-2026",
                target_node_name="Brest",
                valid_at="2026-07-01T08:00:00Z",
            ),
        ]

        return BatchSubmissionRecord(
            batch_id=f"batch-{graph_id}",
            operation_id=f"op-{graph_id}",
            episode_uuids=[f"ep-{i+1}" for i in range(total)],
            item_count=total,
        )

    def wait_for_batch(
        self,
        batch: BatchSubmissionRecord,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        timeout: float = 600.0,
    ) -> bool:
        if self.should_fail and self.fail_stage == "wait_for_batch":
            raise GraphStoreError("Erreur simulée lors de wait_for_batch")
        if progress_callback:
            progress_callback("completed", 1.0)
            self.wait_progress_records.append(("completed", 1.0))
        return True

    def wait_for_episodes(
        self,
        graph_id: str,
        episode_uuids: List[str],
        timeout: float = 600.0,
    ) -> bool:
        return True

    def get_all_nodes(self, graph_id: str) -> List[GraphNode]:
        return list(self._nodes.get(graph_id, []))

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[GraphEdge]:
        return list(self._edges.get(graph_id, []))

    def get_node(self, graph_id: str, node_uuid: str) -> Optional[GraphNode]:
        for n in self._nodes.get(graph_id, []):
            if n.uuid == node_uuid:
                return n
        return None

    def get_node_edges(self, graph_id: str, node_uuid: str, include_temporal: bool = True) -> List[GraphEdge]:
        return [
            e for e in self._edges.get(graph_id, [])
            if e.source_node_uuid == node_uuid or e.target_node_uuid == node_uuid
        ]

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        return {
            "graph_id": graph_id,
            "nodes": [n.to_dict() for n in nodes],
            "edges": [e.to_dict() for e in edges],
            "node_count": len(nodes),
            "edge_count": len(edges),
            "statistics": {
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        }

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        entity_types = sorted(list({
            label for n in nodes for label in n.labels
            if label not in ["Entity", "Node"]
        }))
        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=entity_types,
        )

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "hybrid",
        reranker: Optional[str] = None,
    ) -> GraphSearchResult:
        return GraphSearchResult(facts=[], nodes=[], edges=[], query=query, total_count=0)


def _json_result(result):
    if isinstance(result, tuple):
        response, status = result
    else:
        response, status = result, result.status_code
    return response.get_json(), status


def _setup_test_project(
    project_id: str = "proj-e2e-1",
    name: str = "Projet Test Défense",
    status: ProjectStatus = ProjectStatus.ONTOLOGY_GENERATED,
    text: str = (
        "Thalès conçoit des radars haute fréquence pour la Marine Nationale. "
        "L'ingénieure Alice Martin supervise le programme Radar-2026 à Brest."
    ),
    ontology: Optional[Dict[str, Any]] = None,
) -> Project:
    now = datetime.now().isoformat()
    project = Project(
        project_id=project_id,
        name=name,
        status=status,
        created_at=now,
        updated_at=now,
        ontology=ontology or {
            "entity_types": [{"name": "Organization"}, {"name": "Person"}, {"name": "Project"}],
            "edge_types": [{"name": "FOURNIT_EQUIPEMENT"}, {"name": "SUPERVISE"}],
        },
        graph_id=None,
    )
    return project, text


# ==============================================================================
# 1. Tests GraphBuilderService avec Store Local
# ==============================================================================

def test_graph_builder_service_build_graph_worker_e2e(monkeypatch):
    """Vérifie le cycle complet de _build_graph_worker avec un store local sans clé Zep."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    store = MockE2EGraphitiStore()
    service = GraphBuilderService(store=store)
    task_id = service.task_manager.create_task("Tâche test e2e")

    sample_text = (
        "Thalès conçoit des radars haute fréquence pour la Marine Nationale. "
        "L'ingénieure Alice Martin supervise le programme Radar-2026 à Brest."
    )
    ontology = {
        "entity_types": [{"name": "Organization"}, {"name": "Person"}],
        "edge_types": [{"name": "SUPERVISE"}],
    }

    # Exécution synchrone du worker
    service._build_graph_worker(
        task_id=task_id,
        text=sample_text,
        ontology=ontology,
        graph_name="Graphe Local E2E",
        chunk_size=50,
        chunk_overlap=10,
        batch_size=5,
    )

    task = service.task_manager.get_task(task_id)
    assert task is not None
    assert task.status == TaskStatus.COMPLETED
    assert task.progress == 100
    assert task.result is not None
    assert task.result["graph_id"].startswith("mirofish_")
    assert task.result["chunks_processed"] > 0
    assert task.result["graph_info"]["node_count"] == 5
    assert task.result["graph_info"]["edge_count"] == 3


def test_graph_builder_service_handles_worker_exception(monkeypatch):
    """Vérifie que _build_graph_worker passe la tâche en FAILED si une erreur survient."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    store = MockE2EGraphitiStore(should_fail=True, fail_stage="add_text_batch")
    service = GraphBuilderService(store=store)
    task_id = service.task_manager.create_task("Tâche test failure")

    service._build_graph_worker(
        task_id=task_id,
        text="Texte d'essai.",
        ontology={"entity_types": []},
        graph_name="Graphe Fail",
        chunk_size=50,
        chunk_overlap=5,
        batch_size=2,
    )

    task = service.task_manager.get_task(task_id)
    assert task is not None
    assert task.status == TaskStatus.FAILED
    assert "Erreur simulée lors de add_text_batch" in task.error


def test_graph_builder_service_build_graph_async_e2e(monkeypatch):
    """Vérifie l'exécution asynchrone complète via build_graph_async()."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    store = MockE2EGraphitiStore()
    service = GraphBuilderService(store=store)

    sample_text = (
        "Thalès conçoit des radars haute fréquence pour la Marine Nationale. "
        "L'ingénieure Alice Martin supervise le programme Radar-2026 à Brest."
    )
    ontology = {
        "entity_types": [{"name": "Organization"}, {"name": "Person"}],
        "edge_types": [{"name": "SUPERVISE"}],
    }

    task_id = service.build_graph_async(
        text=sample_text,
        ontology=ontology,
        graph_name="Graphe Async Service E2E",
        chunk_size=50,
        chunk_overlap=10,
        batch_size=5,
    )

    assert task_id is not None

    start = time.time()
    while time.time() - start < 5.0:
        task = service.task_manager.get_task(task_id)
        if task and task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            break
        time.sleep(0.05)

    task = service.task_manager.get_task(task_id)
    assert task is not None
    assert task.status == TaskStatus.COMPLETED
    assert task.progress == 100
    assert task.result is not None
    assert task.result["graph_id"].startswith("mirofish_")
    assert task.result["graph_info"]["node_count"] == 5
    assert task.result["graph_info"]["edge_count"] == 3


# ==============================================================================
# 2. Tests API POST /api/graph/build et son thread de fond
# ==============================================================================

def test_api_graph_build_full_lifecycle_success(monkeypatch):
    """Vérifie l'enchaînement de /api/graph/build avec exécution complète du thread de fond."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    store = MockE2EGraphitiStore()
    project, text = _setup_test_project("proj-full-e2e")
    saved_projects: List[Project] = []

    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _pid: project),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_extracted_text",
        classmethod(lambda _cls, _pid: text),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "save_project",
        classmethod(lambda _cls, p: saved_projects.append(p)),
    )

    with override_graph_store(store):
        app = Flask(__name__)
        with app.test_request_context(
            "/api/graph/build",
            method="POST",
            json={"project_id": "proj-full-e2e", "chunk_size": 100, "chunk_overlap": 20},
        ):
            body, status = _json_result(graph_api.build_graph())

        assert status == 200
        assert body["success"] is True
        task_id = body["data"]["task_id"]
        assert task_id is not None

        # Attente que le thread de fond termine
        start = time.time()
        while time.time() - start < 5.0:
            task = TaskManager().get_task(task_id)
            if task and task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
                break
            time.sleep(0.05)

        task = TaskManager().get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert task.progress == 100
        assert task.result["node_count"] == 5
        assert task.result["edge_count"] == 3

        assert project.status == ProjectStatus.GRAPH_COMPLETED
        assert project.graph_id is not None
        assert project.error is None


def test_api_graph_build_failure_in_background_thread(monkeypatch):
    """Vérifie que l'échec dans le thread de fond positionne le projet et la tâche en FAILED."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    store = MockE2EGraphitiStore(should_fail=True, fail_stage="wait_for_batch")
    project, text = _setup_test_project("proj-fail-e2e")

    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _pid: project),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_extracted_text",
        classmethod(lambda _cls, _pid: text),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "save_project",
        classmethod(lambda _cls, p: None),
    )

    with override_graph_store(store):
        app = Flask(__name__)
        with app.test_request_context(
            "/api/graph/build",
            method="POST",
            json={"project_id": "proj-fail-e2e"},
        ):
            body, status = _json_result(graph_api.build_graph())

        assert status == 200
        task_id = body["data"]["task_id"]

        start = time.time()
        while time.time() - start < 5.0:
            task = TaskManager().get_task(task_id)
            if task and task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
                break
            time.sleep(0.05)

        task = TaskManager().get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert project.status == ProjectStatus.FAILED
        assert "Erreur simulée lors de wait_for_batch" in project.error


def test_api_graph_build_force_rebuild_purges_previous_graph(monkeypatch):
    """Vérifie que force=True purge le graphe existant avant de relancer l'ingestion."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    store = MockE2EGraphitiStore()
    project, text = _setup_test_project(
        "proj-rebuild",
        status=ProjectStatus.GRAPH_COMPLETED,
    )
    project.graph_id = "old-graph-123"

    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _pid: project),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_extracted_text",
        classmethod(lambda _cls, _pid: text),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "save_project",
        classmethod(lambda _cls, p: None),
    )

    with override_graph_store(store):
        app = Flask(__name__)
        with app.test_request_context(
            "/api/graph/build",
            method="POST",
            json={"project_id": "proj-rebuild", "force": True},
        ):
            body, status = _json_result(graph_api.build_graph())

        assert status == 200
        assert "old-graph-123" in store.deleted_graphs

        task_id = body["data"]["task_id"]
        start = time.time()
        while time.time() - start < 5.0:
            task = TaskManager().get_task(task_id)
            if task and task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
                break
            time.sleep(0.05)

        assert project.status == ProjectStatus.GRAPH_COMPLETED
        assert project.graph_id is not None
        assert project.graph_id != "old-graph-123"


# ==============================================================================
# 3. Tests de lecture des données via GET /api/graph/data/<graph_id>
# ==============================================================================

def test_api_graph_data_retrieval_e2e(monkeypatch):
    """Vérifie que GET /api/graph/data/<graph_id> restitue la structure complète du graphe."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    store = MockE2EGraphitiStore()
    gid = store.create_graph("Graphe Données E2E", graph_id="graph-data-e2e")
    store.add_text_batch(gid, ["Extrait de test pour les données."])

    with override_graph_store(store):
        app = Flask(__name__)
        with app.test_request_context(f"/api/graph/data/{gid}", method="GET"):
            body, status = _json_result(graph_api.get_graph_data(gid))

    assert status == 200
    assert body["success"] is True
    data = body["data"]
    assert data["graph_id"] == gid
    assert data["node_count"] == 5
    assert data["edge_count"] == 3
    assert len(data["nodes"]) == 5
    assert len(data["edges"]) == 3

    # Vérification des détails des nœuds et arêtes
    node_names = {n["name"] for n in data["nodes"]}
    assert "Thalès" in node_names
    assert "Marine Nationale" in node_names
    assert "Alice Martin" in node_names

    edge_facts = [e["fact"] for e in data["edges"]]
    assert any("Marine Nationale" in f for f in edge_facts)
