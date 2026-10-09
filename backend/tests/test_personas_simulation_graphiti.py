import csv
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import simulation as simulation_api
from app.config import Config
from app.models.project import Project, ProjectManager
from app.services.oasis_profile_generator import (
    OasisAgentProfile,
    OasisProfileGenerator,
)
from app.services.simulation_config_generator import (
    AgentActivityConfig,
    EventConfig,
    PlatformConfig,
    SimulationConfigGenerator,
    SimulationParameters,
    TimeSimulationConfig,
)
from app.services.simulation_manager import (
    SimulationManager,
    SimulationState,
    SimulationStatus,
)
from app.services.zep_entity_reader import EntityNode, FilteredEntities, ZepEntityReader
from app.utils.graph_store.base import (
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphSearchResult,
    GraphStore,
)


class InMemoryMockStore(GraphStore):
    """Store en mémoire léger pour les tests hermétiques."""

    def __init__(self, nodes=None, edges=None):
        self._nodes = nodes or []
        self._edges = edges or []

    def create_graph(self, name: str, graph_id: str | None = None) -> str:
        return graph_id or "graph-test"

    def delete_graph(self, graph_id: str) -> None:
        pass

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        return GraphInfo(
            graph_id=graph_id,
            name="Mock Graph",
            node_count=len(self._nodes),
            edge_count=len(self._edges),
            entity_types=["Person", "Organization", "Location"],
        )

    def get_all_nodes(self, graph_id: str) -> list[GraphNode]:
        return self._nodes

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> list[GraphEdge]:
        return self._edges

    def get_node(self, graph_id: str, node_uuid: str) -> GraphNode | None:
        for n in self._nodes:
            if n.uuid == node_uuid:
                return n
        return None

    def get_node_edges(self, graph_id: str, node_uuid: str) -> list[GraphEdge]:
        return [
            e for e in self._edges
            if e.source_node_uuid == node_uuid or e.target_node_uuid == node_uuid
        ]

    def add_node(self, graph_id: str, name: str, labels: list[str] | None = None, summary: str = "", attributes: dict | None = None) -> str:
        return "node-id"

    def add_edge(self, graph_id: str, source_node_uuid: str, target_node_uuid: str, name: str = "", fact: str = "", attributes: dict | None = None, valid_at=None, invalid_at=None) -> str:
        return "edge-id"

    def add_episode(self, graph_id: str, name: str, episode_body: str, source_description: str = "", reference_time=None) -> str:
        return "episode-id"

    def set_ontology(self, graph_id: str, ontology: dict) -> None:
        pass

    def get_graph_data(self, graph_id: str) -> dict:
        return {
            "nodes": [n.to_dict() if hasattr(n, "to_dict") else n for n in self._nodes],
            "edges": [e.to_dict() if hasattr(e, "to_dict") else e for e in self._edges],
            "statistics": {"node_count": len(self._nodes), "edge_count": len(self._edges)},
        }

    def add_text_batch(self, graph_id: str, texts: list[str], batch_size: int = 10, group_id: str | None = None):
        return None

    def wait_for_batch(self, batch_submission, timeout: float = 300.0) -> list:
        return []

    def wait_for_episodes(self, graph_id: str, episode_uuids: list[str], timeout: float = 300.0) -> list:
        return []

    def search(self, graph_id: str, query: str, limit: int = 10, scope: str = "hybrid", reranker: str = "rrf") -> GraphSearchResult:
        facts = [e.fact for e in self._edges if e.fact]
        return GraphSearchResult(
            facts=facts,
            nodes=self._nodes,
            edges=self._edges,
            query=query,
            total_count=len(facts) + len(self._nodes),
        )

    def close(self) -> None:
        pass


@pytest.fixture
def sample_graph_data():
    nodes = [
        GraphNode(
            uuid="node-1",
            name="Alice Martin",
            labels=["Entity", "Person"],
            summary="Directrice de recherche et ingénieure en chef.",
            attributes={"entity_type": "Person", "occupation": "Ingénieure"},
        ),
        GraphNode(
            uuid="node-2",
            name="Thalès Défense",
            labels=["Entity", "Organization"],
            summary="Entreprise industrielle leader des technologies de défense.",
            attributes={"entity_type": "Organization", "sector": "Défense"},
        ),
        GraphNode(
            uuid="node-3",
            name="Brest Port",
            labels=["Entity", "Location"],
            summary="Port militaire et base stratégique maritime.",
            attributes={"entity_type": "Location"},
        ),
    ]
    edges = [
        GraphEdge(
            uuid="edge-1",
            name="DIRIGE",
            fact="Alice Martin dirige les programmes industriels chez Thalès Défense.",
            source_node_uuid="node-1",
            target_node_uuid="node-2",
            attributes={},
        ),
        GraphEdge(
            uuid="edge-2",
            name="IMPLANTE_A",
            fact="Thalès Défense est implanté sur le site de Brest Port.",
            source_node_uuid="node-2",
            target_node_uuid="node-3",
            attributes={},
        ),
    ]
    return nodes, edges


def test_zep_entity_reader_extracts_typed_entities_without_zep_key(sample_graph_data, monkeypatch):
    nodes, edges = sample_graph_data
    store = InMemoryMockStore(nodes=nodes, edges=edges)

    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    reader = ZepEntityReader(store=store)
    filtered = reader.filter_defined_entities(graph_id="test-graph", enrich_with_edges=True)

    assert filtered.filtered_count == 3
    assert filtered.total_count == 3
    assert "Person" in filtered.entity_types
    assert "Organization" in filtered.entity_types
    assert "Location" in filtered.entity_types

    alice = next(e for e in filtered.entities if e.name == "Alice Martin")
    assert alice.get_entity_type() == "Person"
    assert len(alice.related_edges) == 1
    assert alice.related_edges[0]["edge_name"] == "DIRIGE"
    assert len(alice.related_nodes) == 1
    assert alice.related_nodes[0]["name"] == "Thalès Défense"


def test_oasis_profile_generator_rule_based_and_formats(sample_graph_data, tmp_path, monkeypatch):
    nodes, edges = sample_graph_data
    store = InMemoryMockStore(nodes=nodes, edges=edges)

    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)
    monkeypatch.setattr(Config, "LLM_API_KEY", "test-key")

    reader = ZepEntityReader(store=store)
    filtered = reader.filter_defined_entities(graph_id="test-graph", enrich_with_edges=True)

    generator = OasisProfileGenerator(store=store, graph_id="test-graph")

    # Génération sans LLM (rule-based)
    profiles = generator.generate_profiles_from_entities(
        entities=filtered.entities,
        use_llm=False,
        parallel_count=2,
    )

    assert len(profiles) == 3
    for idx, p in enumerate(profiles):
        assert p.user_id == idx
        assert len(p.user_name) > 0
        assert len(p.bio) > 0
        assert len(p.persona) > 0
        assert p.gender in ("male", "female", "other")
        assert p.mbti is not None

    # Sauvegarde Reddit JSON
    reddit_path = str(tmp_path / "reddit_profiles.json")
    generator.save_profiles(profiles, reddit_path, platform="reddit")
    with open(reddit_path, "r", encoding="utf-8") as f:
        reddit_data = json.load(f)
    assert len(reddit_data) == 3
    assert "username" in reddit_data[0]
    assert "user_id" in reddit_data[0]

    # Sauvegarde Twitter CSV
    twitter_path = str(tmp_path / "twitter_profiles.csv")
    generator.save_profiles(profiles, twitter_path, platform="twitter")
    with open(twitter_path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert set(rows[0].keys()) == {"user_id", "name", "username", "user_char", "description"}


def test_simulation_config_generator_creates_valid_parameters(sample_graph_data, monkeypatch):
    nodes, edges = sample_graph_data
    store = InMemoryMockStore(nodes=nodes, edges=edges)

    monkeypatch.setattr(Config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(Config, "LLM_MODEL_NAME", "space-bunny-free")
    monkeypatch.setattr(Config, "LLM_BASE_URL", "https://opencode.ai/zen/go/v1")

    reader = ZepEntityReader(store=store)
    filtered = reader.filter_defined_entities(graph_id="test-graph", enrich_with_edges=True)

    config_gen = SimulationConfigGenerator()

    # Mock de l'appel LLM interne pour éviter tout appel réseau externe
    mock_time = {
        "total_simulation_hours": 48,
        "minutes_per_round": 60,
        "agents_per_hour_min": 2,
        "agents_per_hour_max": 3,
        "peak_hours": [19, 20, 21],
        "off_peak_hours": [0, 1, 2, 3, 4],
        "morning_hours": [6, 7, 8],
        "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
        "reasoning": "Configuration temps simulée",
    }
    mock_event = {
        "hot_topics": ["Défense", "Surveillance"],
        "narrative_direction": "Débat sur la sécurité maritime",
        "initial_posts": [
            {"content": "Communiqué officiel sur les radars", "poster_type": "Organization"},
            {"content": "Retour d'expérience technique", "poster_type": "Person"},
        ],
        "reasoning": "Configuration événements simulée",
    }
    mock_agents = {
        "agent_configs": [
            {
                "agent_id": 0,
                "activity_level": 0.8,
                "posts_per_hour": 1.0,
                "comments_per_hour": 2.0,
                "active_hours": [9, 10, 11, 12, 18, 19, 20],
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.2,
                "stance": "supportive",
                "influence_weight": 1.5,
            },
            {
                "agent_id": 1,
                "activity_level": 0.3,
                "posts_per_hour": 0.1,
                "comments_per_hour": 0.2,
                "active_hours": [9, 10, 11, 12, 14, 15, 16],
                "response_delay_min": 60,
                "response_delay_max": 180,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 3.0,
            },
            {
                "agent_id": 2,
                "activity_level": 0.5,
                "posts_per_hour": 0.5,
                "comments_per_hour": 1.0,
                "active_hours": [8, 9, 10, 18, 19],
                "response_delay_min": 10,
                "response_delay_max": 45,
                "sentiment_bias": 0.1,
                "stance": "observer",
                "influence_weight": 1.0,
            },
        ]
    }

    def fake_call(prompt, system_prompt):
        if "时间模拟配置" in prompt:
            return mock_time
        elif "事件配置" in prompt:
            return mock_event
        elif "活动配置" in prompt:
            return mock_agents
        return {}

    monkeypatch.setattr(config_gen, "_call_llm_with_retry", fake_call)

    params = config_gen.generate_config(
        simulation_id="sim-123",
        project_id="proj-456",
        graph_id="test-graph",
        simulation_requirement="Simuler le débat maritime",
        document_text="Texte source du rapport",
        entities=filtered.entities,
        enable_twitter=True,
        enable_reddit=True,
    )

    assert isinstance(params, SimulationParameters)
    assert params.simulation_id == "sim-123"
    assert params.time_config.total_simulation_hours == 48
    assert len(params.agent_configs) == 3
    assert len(params.event_config.initial_posts) == 2
    # Vérification de l'attribution des poster_agent_id
    assert params.event_config.initial_posts[0]["poster_agent_id"] == 1  # Organization -> agent_id 1
    assert params.event_config.initial_posts[1]["poster_agent_id"] == 0  # Person -> agent_id 0
    assert params.twitter_config is not None
    assert params.reddit_config is not None

    # Conversion JSON
    json_str = params.to_json()
    parsed = json.loads(json_str)
    assert parsed["simulation_id"] == "sim-123"
    assert len(parsed["agent_configs"]) == 3


def test_simulation_manager_prepare_e2e_mocked(sample_graph_data, tmp_path, monkeypatch):
    nodes, edges = sample_graph_data
    store = InMemoryMockStore(nodes=nodes, edges=edges)

    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)
    monkeypatch.setattr(Config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))

    manager = SimulationManager()
    state = manager.create_simulation(
        project_id="proj-test",
        graph_id="test-graph",
        enable_twitter=True,
        enable_reddit=True,
    )

    assert state.status == SimulationStatus.CREATED
    assert state.simulation_id.startswith("sim_")

    # Injection du store via le gestionnaire officiel de factory override_graph_store
    from app.utils.graph_store.factory import override_graph_store

    with override_graph_store(store):
        prepared = manager.prepare_simulation(
            simulation_id=state.simulation_id,
            simulation_requirement="Exigence de test",
            document_text="Document de test",
            use_llm_for_profiles=False,
            parallel_profile_count=2,
        )

    assert prepared.status == SimulationStatus.READY
    assert prepared.profiles_count == 3
    assert prepared.entities_count == 3
    assert prepared.config_generated is True

    # Vérification des fichiers créés sur disque
    sim_dir = tmp_path / state.simulation_id
    assert (sim_dir / "reddit_profiles.json").exists()
    assert (sim_dir / "twitter_profiles.csv").exists()
    assert (sim_dir / "simulation_config.json").exists()
    assert (sim_dir / "state.json").exists()


def test_api_simulation_create_without_zep_key(monkeypatch):
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    fake_project = SimpleNamespace(
        project_id="proj-abc",
        graph_id="graph-abc",
    )
    monkeypatch.setattr(
        ProjectManager,
        "get_project",
        classmethod(lambda _cls, pid: fake_project if pid == "proj-abc" else None),
    )

    app = Flask(__name__)
    with app.test_request_context(
        "/api/simulation/create",
        method="POST",
        json={"project_id": "proj-abc"},
    ):
        response = simulation_api.create_simulation()

    assert response.status_code == 200
    res_data = response.get_json()
    assert res_data["success"] is True
    assert res_data["data"]["project_id"] == "proj-abc"
    assert res_data["data"]["graph_id"] == "graph-abc"
    assert res_data["data"]["status"] == "created"


def test_api_simulation_create_error_cases(monkeypatch):
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", None)

    monkeypatch.setattr(
        ProjectManager,
        "get_project",
        classmethod(lambda _cls, pid: None),
    )

    def status_code(res):
        return res[1] if isinstance(res, tuple) else res.status_code

    app = Flask(__name__)

    # 1. Missing project_id (400)
    with app.test_request_context(
        "/api/simulation/create",
        method="POST",
        json={},
    ):
        resp = simulation_api.create_simulation()
    assert status_code(resp) == 400

    # 2. Project not found (404)
    with app.test_request_context(
        "/api/simulation/create",
        method="POST",
        json={"project_id": "proj-missing"},
    ):
        resp = simulation_api.create_simulation()
    assert status_code(resp) == 404

    # 3. Project without graph_id (400)
    no_graph_project = SimpleNamespace(project_id="proj-no-graph", graph_id=None)
    monkeypatch.setattr(
        ProjectManager,
        "get_project",
        classmethod(lambda _cls, pid: no_graph_project if pid == "proj-no-graph" else None),
    )
    with app.test_request_context(
        "/api/simulation/create",
        method="POST",
        json={"project_id": "proj-no-graph"},
    ):
        resp = simulation_api.create_simulation()
    assert status_code(resp) == 400

