"""Tests unitaires et d'API validant la levée des gardes ZEP_API_KEY (Story 004-2).

Couvre :
1. Config.requires_zep_api_key() et Config.validate()
2. Routes API backend/app/api/graph.py (/build, /data/<id>, /delete/<id>)
3. Routes API backend/app/api/simulation.py (/entities/<id>, /entities/<id>/<uuid>, /entities/<id>/by-type/<type>)
4. Services métiers (GraphBuilderService, ZepEntityReader, OasisProfileGenerator, ZepGraphMemoryUpdater, ZepToolsService)
"""

from typing import Any, Dict, List, Optional
from flask import Flask
import pytest

from app.api import graph as graph_api
from app.api import simulation as simulation_api
from app.config import Config
from app.models.project import Project, ProjectStatus
from app.services.graph_builder import GraphBuilderService
from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.zep_entity_reader import ZepEntityReader
from app.services.zep_graph_memory_updater import ZepGraphMemoryUpdater
from app.services.zep_tools import ZepToolsService
from app.utils.graph_store.base import (
    BatchSubmissionRecord,
    EpisodeRecord,
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphSearchResult,
    GraphStore,
)
from app.utils.graph_store.errors import GraphValidationError
from app.utils.graph_store.factory import override_graph_store


class DummyStore(GraphStore):
    """Store factice pour tester les routes sans accès réseau."""

    def __init__(self):
        self.deleted_graphs: List[str] = []
        self.node = GraphNode(
            uuid="node-1",
            name="Alice",
            labels=["Entity", "Person"],
            attributes={"summary": "Chercheuse", "role": "Scientifique"},
            created_at="2026-10-09T12:00:00Z",
        )
        self.edge = GraphEdge(
            uuid="edge-1",
            name="COLLABORATES_WITH",
            fact="Alice collabore avec Bob",
            source_node_uuid="node-1",
            target_node_uuid="node-2",
            source_node_name="Alice",
            target_node_name="Bob",
            created_at="2026-10-09T12:00:00Z",
        )

    def create_graph(self, name: str, graph_id: Optional[str] = None) -> str:
        return graph_id or "dummy-graph"

    def delete_graph(self, graph_id: str) -> None:
        self.deleted_graphs.append(graph_id)

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        pass

    def add_episode(self, graph_id: str, content: str, source_description: str = "") -> EpisodeRecord:
        return EpisodeRecord(episode_uuid="ep-1", graph_id=graph_id, content=content)

    def add_text_batch(
        self, graph_id: str, chunks: List[str], batch_size: int = 350
    ) -> BatchSubmissionRecord:
        return BatchSubmissionRecord(batch_id="b-1", item_count=len(chunks))

    def wait_for_batch(
        self, batch: BatchSubmissionRecord, progress_callback=None, timeout: float = 600.0
    ) -> bool:
        return True

    def wait_for_episodes(
        self, graph_id: str, episode_uuids: List[str], progress_callback=None, timeout: float = 600.0
    ) -> bool:
        return True

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        return GraphInfo(graph_id=graph_id, node_count=1, edge_count=1)

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        return {
            "graph_id": graph_id,
            "nodes": [self.node.to_dict()],
            "edges": [self.edge.to_dict()],
            "node_count": 1,
            "edge_count": 1,
        }

    def get_all_nodes(self, graph_id: str) -> List[GraphNode]:
        return [self.node]

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[GraphEdge]:
        return [self.edge]

    def get_node(self, graph_id: str, node_uuid: str) -> Optional[GraphNode]:
        if node_uuid == self.node.uuid:
            return self.node
        return None

    def get_node_edges(self, graph_id: str, node_uuid: str, include_temporal: bool = True) -> List[GraphEdge]:
        if node_uuid == self.node.uuid:
            return [self.edge]
        return []

    def search(
        self, graph_id: str, query: str, limit: int = 10, scope: str = "hybrid"
    ) -> List[GraphSearchResult]:
        return []


def _json_result(result):
    if isinstance(result, tuple):
        response, status = result
    else:
        response, status = result, result.status_code
    return response.get_json(), status


def _dummy_project(project_id="proj-1", graph_id="graph-1"):
    return Project(
        project_id=project_id,
        name="Test Project",
        status=ProjectStatus.ONTOLOGY_GENERATED,
        created_at="2026-10-09T12:00:00Z",
        updated_at="2026-10-09T12:00:00Z",
        ontology={"entity_types": [], "edge_types": []},
        graph_id=graph_id,
    )


# ==============================================================================
# 1. Tests de Config.requires_zep_api_key() et Config.validate()
# ==============================================================================

def test_requires_zep_api_key_defaults_to_cloud(monkeypatch):
    """Par défaut ou en mode cloud, la clé Zep est exigée (avec tolérance casse/espaces et fail-closed)."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    assert Config.requires_zep_api_key() is True

    monkeypatch.setattr(Config, "ZEP_BACKEND", "  CLOUD  ")
    assert Config.requires_zep_api_key() is True

    monkeypatch.setattr(Config, "ZEP_BACKEND", "Cloud")
    assert Config.requires_zep_api_key() is True

    monkeypatch.setattr(Config, "ZEP_BACKEND", None)
    assert Config.requires_zep_api_key() is True

    # Comportement fail-closed sur chaîne vide, espaces ou backend non supporté
    monkeypatch.setattr(Config, "ZEP_BACKEND", "")
    assert Config.requires_zep_api_key() is True

    monkeypatch.setattr(Config, "ZEP_BACKEND", "   ")
    assert Config.requires_zep_api_key() is True

    monkeypatch.setattr(Config, "ZEP_BACKEND", "unsupported_backend")
    assert Config.requires_zep_api_key() is True


def test_requires_zep_api_key_returns_false_for_graphiti(monkeypatch):
    """En mode graphiti, la clé Zep n'est pas requise."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    assert Config.requires_zep_api_key() is False

    monkeypatch.setattr(Config, "ZEP_BACKEND", "  GRAPHITI  ")
    assert Config.requires_zep_api_key() is False


def test_config_validate_checks_key_only_when_required(monkeypatch):
    """validate() ne vérifie ZEP_API_KEY que si requires_zep_api_key() est vrai."""
    monkeypatch.setattr(Config, "LLM_API_KEY", "mock-llm-key")
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    errors = Config.validate()
    assert any("ZEP_API_KEY" in err for err in errors)

    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    errors_graphiti = Config.validate()
    assert not any("ZEP_API_KEY" in err for err in errors_graphiti)


# ==============================================================================
# 2. Tests des routes API graph.py (/build, /data, /delete)
# ==============================================================================

def test_api_graph_build_rejects_missing_key_in_cloud_mode(monkeypatch):
    """En mode cloud, /api/graph/build refuse la requête si ZEP_API_KEY manque."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    app = Flask(__name__)
    with app.test_request_context("/api/graph/build", method="POST", json={"project_id": "proj-1"}):
        body, status = _json_result(graph_api.build_graph())

    assert status == 500
    assert body["success"] is False
    assert "ZEP_API_KEY" in body["error"] or "zep" in body["error"].lower()


def test_api_graph_build_accepts_missing_key_in_graphiti_mode(monkeypatch):
    """En mode graphiti, /api/graph/build ne bloque pas si ZEP_API_KEY est absent."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_project",
        classmethod(lambda _cls, _pid: _dummy_project()),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "get_extracted_text",
        classmethod(lambda _cls, _pid: "Texte de test"),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "save_project",
        classmethod(lambda _cls, _p: None),
    )

    app = Flask(__name__)
    with app.test_request_context("/api/graph/build", method="POST", json={"project_id": "proj-1"}):
        # On mocke le thread asynchrone pour ne pas démarrer de tâche de fond
        monkeypatch.setattr(
            graph_api.threading.Thread,
            "start",
            lambda self: None,
        )
        body, status = _json_result(graph_api.build_graph())

    # La route a passé le garde de clé et a créé la tâche
    assert status == 200
    assert body["success"] is True
    assert "task_id" in body["data"]


def test_api_graph_data_rejects_missing_key_in_cloud_mode(monkeypatch):
    """En mode cloud, /api/graph/data/<id> renvoie une erreur si ZEP_API_KEY manque."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    app = Flask(__name__)
    with app.test_request_context("/api/graph/data/graph-1", method="GET"):
        body, status = _json_result(graph_api.get_graph_data("graph-1"))

    assert status == 500
    assert body["success"] is False


def test_api_graph_data_succeeds_without_key_in_graphiti_mode(monkeypatch):
    """En mode graphiti, /api/graph/data/<id> fonctionne sans ZEP_API_KEY."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    dummy_store = DummyStore()
    with override_graph_store(dummy_store):
        app = Flask(__name__)
        with app.test_request_context("/api/graph/data/graph-1", method="GET"):
            body, status = _json_result(graph_api.get_graph_data("graph-1"))

    assert status == 200
    assert body["success"] is True
    assert body["data"]["graph_id"] == "graph-1"
    assert len(body["data"]["nodes"]) == 1


def test_api_graph_delete_rejects_missing_key_in_cloud_mode(monkeypatch):
    """En mode cloud, /api/graph/delete/<id> renvoie 500 si ZEP_API_KEY manque."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    app = Flask(__name__)
    with app.test_request_context("/api/graph/delete/graph-1", method="DELETE"):
        body, status = _json_result(graph_api.delete_graph("graph-1"))

    assert status == 500
    assert body["success"] is False


def test_api_graph_delete_succeeds_without_key_in_graphiti_mode(monkeypatch):
    """En mode graphiti, /api/graph/delete/<id> fonctionne sans ZEP_API_KEY."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "find_projects_by_graph_id",
        classmethod(lambda _cls, _gid: [_dummy_project()]),
    )
    monkeypatch.setattr(
        graph_api.ProjectManager,
        "save_project",
        classmethod(lambda _cls, _p: None),
    )

    dummy_store = DummyStore()
    with override_graph_store(dummy_store):
        app = Flask(__name__)
        with app.test_request_context("/api/graph/delete/graph-1", method="DELETE"):
            body, status = _json_result(graph_api.delete_graph("graph-1"))

    assert status == 200
    assert body["success"] is True
    assert "graph-1" in dummy_store.deleted_graphs


# ==============================================================================
# 3. Tests des routes API simulation.py (/entities)
# ==============================================================================

def test_api_simulation_entities_rejects_missing_key_in_cloud_mode(monkeypatch):
    """En mode cloud, GET /entities/<graph_id> bloque si ZEP_API_KEY manque."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    app = Flask(__name__)
    with app.test_request_context("/api/simulation/entities/graph-1", method="GET"):
        body, status = _json_result(simulation_api.get_graph_entities("graph-1"))

    assert status == 500
    assert body["success"] is False


def test_api_simulation_entities_succeeds_without_key_in_graphiti_mode(monkeypatch):
    """En mode graphiti, GET /entities/<graph_id> fonctionne sans ZEP_API_KEY."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    dummy_store = DummyStore()
    with override_graph_store(dummy_store):
        app = Flask(__name__)
        with app.test_request_context("/api/simulation/entities/graph-1", method="GET"):
            body, status = _json_result(simulation_api.get_graph_entities("graph-1"))

    assert status == 200
    assert body["success"] is True
    assert body["data"]["total_count"] == 1
    assert body["data"]["filtered_count"] == 1


def test_api_simulation_entity_detail_rejects_missing_key_in_cloud_mode(monkeypatch):
    """En mode cloud, GET /entities/<graph_id>/<uuid> bloque si ZEP_API_KEY manque."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    app = Flask(__name__)
    with app.test_request_context("/api/simulation/entities/graph-1/node-1", method="GET"):
        body, status = _json_result(simulation_api.get_entity_detail("graph-1", "node-1"))

    assert status == 500
    assert body["success"] is False


def test_api_simulation_entity_detail_succeeds_without_key_in_graphiti_mode(monkeypatch):
    """En mode graphiti, GET /entities/<graph_id>/<uuid> fonctionne sans ZEP_API_KEY."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    dummy_store = DummyStore()
    with override_graph_store(dummy_store):
        app = Flask(__name__)
        with app.test_request_context("/api/simulation/entities/graph-1/node-1", method="GET"):
            body, status = _json_result(simulation_api.get_entity_detail("graph-1", "node-1"))

    assert status == 200
    assert body["success"] is True
    assert body["data"]["name"] == "Alice"


def test_api_simulation_entities_by_type_rejects_missing_key_in_cloud_mode(monkeypatch):
    """En mode cloud, GET /entities/<graph_id>/by-type/<type> bloque si ZEP_API_KEY manque."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    app = Flask(__name__)
    with app.test_request_context("/api/simulation/entities/graph-1/by-type/Person", method="GET"):
        body, status = _json_result(simulation_api.get_entities_by_type("graph-1", "Person"))

    assert status == 500
    assert body["success"] is False


def test_api_simulation_entities_by_type_succeeds_without_key_in_graphiti_mode(monkeypatch):
    """En mode graphiti, GET /entities/<graph_id>/by-type/<type> fonctionne sans ZEP_API_KEY."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    dummy_store = DummyStore()
    with override_graph_store(dummy_store):
        app = Flask(__name__)
        with app.test_request_context("/api/simulation/entities/graph-1/by-type/Person", method="GET"):
            body, status = _json_result(simulation_api.get_entities_by_type("graph-1", "Person"))

    assert status == 200
    assert body["success"] is True
    assert body["data"]["count"] == 1


# ==============================================================================
# 4. Tests des services métiers sans ZEP_API_KEY en mode graphiti
# ==============================================================================

def test_graph_builder_service_instantiation_without_zep_key_graphiti(monkeypatch):
    """GraphBuilderService(api_key=None) s'instancie sans erreur en mode graphiti."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    dummy_store = DummyStore()
    with override_graph_store(dummy_store):
        builder = GraphBuilderService(api_key=None)
        assert builder.store is dummy_store


def test_graph_builder_service_instantiation_without_zep_key_cloud_fails(monkeypatch):
    """GraphBuilderService(api_key=None) échoue en mode cloud si ZEP_API_KEY est absent."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    with pytest.raises(GraphValidationError) as exc_info:
        GraphBuilderService(api_key=None)

    assert "ZEP_API_KEY" in str(exc_info.value)


def test_zep_entity_reader_without_zep_key_graphiti(monkeypatch):
    """ZepEntityReader(api_key=None) s'instancie sans erreur en mode graphiti."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    dummy_store = DummyStore()
    with override_graph_store(dummy_store):
        reader = ZepEntityReader(api_key=None)
        assert reader.store is dummy_store
        result = reader.filter_defined_entities("graph-1")
        assert result.total_count == 1
        assert result.filtered_count == 1


def test_oasis_profile_generator_store_resolution_without_zep_key_graphiti(monkeypatch):
    """OasisProfileGenerator(zep_api_key=None) résout son store en mode graphiti sans clé."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)
    monkeypatch.setattr(Config, "LLM_API_KEY", "mock-llm-key")

    dummy_store = DummyStore()
    with override_graph_store(dummy_store):
        generator = OasisProfileGenerator(zep_api_key=None)
        assert generator.store is dummy_store


def test_zep_graph_memory_updater_without_zep_key_graphiti(monkeypatch):
    """ZepGraphMemoryUpdater(api_key=None) résout son store en mode graphiti sans clé."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    dummy_store = DummyStore()
    with override_graph_store(dummy_store):
        updater = ZepGraphMemoryUpdater("graph-1", api_key=None)
        assert updater.store is dummy_store


def test_zep_tools_service_without_zep_key_graphiti(monkeypatch):
    """ZepToolsService(api_key=None) résout son store en mode graphiti sans clé."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    dummy_store = DummyStore()
    with override_graph_store(dummy_store):
        tools = ZepToolsService(api_key=None)
        assert tools.store is dummy_store


def test_zep_entity_reader_without_zep_key_cloud_fails(monkeypatch):
    """ZepEntityReader(api_key=None) échoue en mode cloud si ZEP_API_KEY est absent."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    with pytest.raises(GraphValidationError) as exc_info:
        ZepEntityReader(api_key=None)

    assert "ZEP_API_KEY" in str(exc_info.value)


def test_zep_graph_memory_updater_without_zep_key_cloud_fails(monkeypatch):
    """ZepGraphMemoryUpdater(api_key=None) échoue en mode cloud si ZEP_API_KEY est absent."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    with pytest.raises(GraphValidationError) as exc_info:
        ZepGraphMemoryUpdater("graph-1", api_key=None)

    assert "ZEP_API_KEY" in str(exc_info.value)


def test_zep_tools_service_without_zep_key_cloud_fails(monkeypatch):
    """ZepToolsService(api_key=None) échoue en mode cloud si ZEP_API_KEY est absent."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    with pytest.raises(GraphValidationError) as exc_info:
        ZepToolsService(api_key=None)

    assert "ZEP_API_KEY" in str(exc_info.value)
