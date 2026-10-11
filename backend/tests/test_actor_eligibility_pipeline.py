"""Tests de pipeline de la barrière d'éligibilité (story 009-1, AC6–AC11)."""

import csv
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import create_app
from app.api import simulation as simulation_api
from app.config import Config
from app.models.actor_eligibility import (
    ActorEligibility,
    ActorRole,
    EligibilityStatus,
)
from app.models.project import ProjectManager
from app.models import task as task_module
from app.services import simulation_manager as sim_manager_module
from app.services import oasis_profile_generator as oasis_module
from app.services.actor_classifier import ActorClassifierService, ActorClassificationResult
from app.services.oasis_profile_generator import (
    ActorNotEligibleError,
    OasisProfileGenerator,
)
from app.services.simulation_manager import SimulationManager, SimulationStatus
from app.services.zep_entity_reader import EntityNode
from app.utils.graph_store.base import (
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphSearchResult,
    GraphStore,
)
from app.utils.graph_store.factory import override_graph_store


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "actor_eligibility"
DATASETS = ("logiciel_gestion", "evenement_culturel")


def load_dataset(name):
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Doubles de test
# ---------------------------------------------------------------------------


class FixtureStore(GraphStore):
    """Store en mémoire qui compte les mutations pour prouver la non-écriture."""

    def __init__(self, nodes=None, edges=None):
        self._nodes = nodes or []
        self._edges = edges or []
        self.add_node_calls = 0
        self.add_edge_calls = 0
        self.delete_calls = 0
        self.add_episode_calls = 0

    def create_graph(self, name, graph_id=None):
        return graph_id or "graph"

    def delete_graph(self, graph_id):
        self.delete_calls += 1

    def get_graph_info(self, graph_id):
        return GraphInfo(
            graph_id=graph_id, node_count=len(self._nodes), edge_count=len(self._edges)
        )

    def get_all_nodes(self, graph_id):
        return list(self._nodes)

    def get_all_edges(self, graph_id, include_temporal=True):
        return list(self._edges)

    def get_node(self, graph_id, node_uuid):
        for node in self._nodes:
            if node.uuid == node_uuid:
                return node
        return None

    def get_node_edges(self, graph_id, node_uuid):
        return [
            edge
            for edge in self._edges
            if edge.source_node_uuid == node_uuid or edge.target_node_uuid == node_uuid
        ]



    def get_edge_provenance(self, graph_id: str, edge_uuid: str):
        """Aucune provenance : doublure de test, graphe en mémoire."""
        return []
    def add_node(self, *args, **kwargs):
        self.add_node_calls += 1
        return "node"

    def add_edge(self, *args, **kwargs):
        self.add_edge_calls += 1
        return "edge"

    def add_episode(self, *args, **kwargs):
        self.add_episode_calls += 1
        return "episode"

    def set_ontology(self, graph_id, ontology):
        pass

    def get_graph_data(self, graph_id):
        return {"nodes": [], "edges": [], "statistics": {}}

    def add_text_batch(self, *args, **kwargs):
        return None

    def wait_for_batch(self, batch_submission, timeout=300.0):
        return []

    def wait_for_episodes(self, graph_id, episode_uuids, timeout=300.0):
        return []

    def search(self, graph_id, query, limit=10, scope="hybrid", reranker="rrf"):
        return GraphSearchResult(facts=[], nodes=[], edges=[], query=query, total_count=0)

    def close(self):
        pass


class FixtureLLM:
    """Oracle : reproduit la qualification attendue des fixtures.

    Ce n'est pas une mesure du modèle réel (voir la sonde dédiée à AC12) ; il
    sert à vérifier la barrière en aval sur des données annotées.
    """

    def __init__(self, dataset):
        self.by_key = {
            (case["entity"]["name"], case["entity"]["summary"]): case["expected"]
            for case in dataset["cases"]
        }
        self.calls = []

    def chat_json(self, messages, **kwargs):
        self.calls.append(messages)
        payload = json.loads(messages[1]["content"].split("\n", 1)[1])
        entity = payload["entite"]
        expected = self.by_key.get((entity["nom"], entity["resume"]))
        if expected is None:
            return {"role": "unknown", "status": "review", "rationale": "inconnu", "confidence": 0.0}
        return {
            "role": expected["role"],
            "status": expected["status"],
            "rationale": expected["rationale"],
            "confidence": 0.95,
        }


class AllReviewLLM:
    def chat_json(self, messages, **kwargs):
        return {"role": "unknown", "status": "review", "rationale": "doute", "confidence": 0.4}


class StubConfigGenerator:
    """Remplace la génération LLM de configuration, hors réseau."""

    def generate_config(self, **kwargs):
        return SimpleNamespace(
            to_json=lambda: json.dumps({"simulation_id": kwargs.get("simulation_id")}),
            generation_reasoning="stub",
        )


def build_fixture_store(dataset):
    nodes = []
    edges = []
    seen_edges = set()
    for case in dataset["cases"]:
        raw = case["entity"]
        nodes.append(GraphNode(
            uuid=raw["uuid"],
            name=raw["name"],
            labels=list(raw["labels"]),
            summary=raw["summary"],
            attributes=dict(raw["attributes"]),
        ))
        for edge in raw["related_edges"]:
            if edge["direction"] == "outgoing":
                source, target = raw["uuid"], edge["target_node_uuid"]
            else:
                source, target = edge["source_node_uuid"], raw["uuid"]
            key = (source, target, edge["fact"])
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append(GraphEdge(
                uuid=f"e-{len(edges)}",
                name=edge["edge_name"],
                fact=edge["fact"],
                source_node_uuid=source,
                target_node_uuid=target,
                attributes={},
            ))
    return FixtureStore(nodes=nodes, edges=edges)


def fixture_entities(dataset):
    return [EntityNode(**case["entity"]) for case in dataset["cases"]]


def _prepare(dataset, tmp_path, monkeypatch, use_llm):
    store = build_fixture_store(dataset)
    classifier = ActorClassifierService(llm_client=FixtureLLM(dataset))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sim_manager_module, "SimulationConfigGenerator", StubConfigGenerator)
    if use_llm:
        monkeypatch.setattr(
            OasisProfileGenerator,
            "_generate_profile_with_llm",
            lambda self, **kwargs: {"bio": "bio", "persona": "persona"},
        )
    manager = SimulationManager()
    state = manager.create_simulation(project_id="proj", graph_id="graph")
    with override_graph_store(store):
        prepared = manager.prepare_simulation(
            simulation_id=state.simulation_id,
            simulation_requirement=dataset["simulation_requirement"],
            document_text="document",
            use_llm_for_profiles=use_llm,
            classifier=classifier,
        )
    return manager, store, prepared


# ---------------------------------------------------------------------------
# AC11 — garanties multi-domaines avec et sans LLM de personas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dataset_name", DATASETS)
@pytest.mark.parametrize("use_llm", [False, True])
def test_pipeline_keeps_only_qualified_actors(dataset_name, use_llm, tmp_path, monkeypatch):
    dataset = load_dataset(dataset_name)
    expected_actors = [
        case["entity"] for case in dataset["cases"]
        if case["expected"]["status"] == "eligible"
    ]
    expected_actor_ids = {entity["uuid"] for entity in expected_actors}
    passive_ids = {
        case["entity"]["uuid"] for case in dataset["cases"]
        if case["expected"]["status"] == "ineligible"
    }
    actor_names = {entity["name"] for entity in expected_actors}

    manager, store, prepared = _prepare(dataset, tmp_path, monkeypatch, use_llm)

    assert prepared.status == SimulationStatus.READY
    assert prepared.profiles_count == len(expected_actors)
    assert prepared.actors_count == len(expected_actors)
    assert prepared.review_count == 3
    assert prepared.ineligible_count == 12

    assert store.add_node_calls == 0
    assert store.add_edge_calls == 0
    assert store.delete_calls == 0
    assert store.add_episode_calls == 0

    sim_dir = tmp_path / prepared.simulation_id
    reddit = json.loads((sim_dir / "reddit_profiles.json").read_text(encoding="utf-8"))
    assert len(reddit) == len(expected_actors)
    with (sim_dir / "twitter_profiles.csv").open(encoding="utf-8", newline="") as handle:
        twitter = list(csv.DictReader(handle))
    assert len(twitter) == len(expected_actors)

    exported_names = {profile["name"] for profile in reddit}
    assert exported_names == actor_names

    proof = json.loads((sim_dir / "actor_qualifications.json").read_text(encoding="utf-8"))
    assert set(proof["qualified_actor_uuids"]) == expected_actor_ids
    assert set(proof["qualified_actor_uuids"]).isdisjoint(passive_ids)
    assert proof["policy_version"] == "009-1-v1"


# ---------------------------------------------------------------------------
# AC9 — zéro acteur : échec explicite sans artefact
# ---------------------------------------------------------------------------


def test_zero_qualified_actor_fails_without_artifacts(tmp_path, monkeypatch):
    store = FixtureStore(nodes=[
        GraphNode(uuid="p-1", name="Élodie", labels=["Entity"], summary="personne"),
        GraphNode(uuid="p-2", name="Malik", labels=["Entity"], summary="personne"),
        GraphNode(uuid="d-1", name="https://example.test", labels=["Entity"], summary="url"),
    ])
    classifier = ActorClassifierService(llm_client=AllReviewLLM())
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))

    manager = SimulationManager()
    state = manager.create_simulation(project_id="proj", graph_id="graph")
    with override_graph_store(store):
        with pytest.raises(ValueError, match="eligible=0"):
            manager.prepare_simulation(
                simulation_id=state.simulation_id,
                simulation_requirement="consigne",
                document_text="document",
                use_llm_for_profiles=False,
                classifier=classifier,
            )

    sim_dir = tmp_path / state.simulation_id
    assert not (sim_dir / "simulation_config.json").exists()
    assert not (sim_dir / "reddit_profiles.json").exists()
    assert not (sim_dir / "actor_qualifications.json").exists()
    failed = json.loads((sim_dir / "state.json").read_text(encoding="utf-8"))
    assert failed["status"] == "failed"
    assert "eligible=0" in failed["error"]
    assert failed["actors_count"] == 0


# ---------------------------------------------------------------------------
# AC6 — barrière du générateur unitaire et par lots
# ---------------------------------------------------------------------------


def _qual(entity, role, status):
    return ActorEligibility(
        entity_uuid=entity.uuid,
        entity_name=entity.name,
        role=role,
        status=status,
        rationale="test",
        confidence=0.9,
        original_type=entity.get_entity_type() or "Entity",
        attributes=dict(entity.attributes),
    )


def test_unit_generator_refuses_unqualified_entity():
    generator = OasisProfileGenerator(api_key="fake")
    entity = EntityNode(uuid="u-1", name="Sillage", labels=["Entity"], summary="logiciel", attributes={})
    qualification = _qual(entity, ActorRole.PRODUCT, EligibilityStatus.INELIGIBLE)
    with pytest.raises(ActorNotEligibleError):
        generator.generate_profile_from_entity(entity, 0, use_llm=False, qualification=qualification)


def test_batch_generator_excludes_refusals_without_fallback():
    generator = OasisProfileGenerator(api_key="fake")
    person = EntityNode(uuid="u-1", name="Élodie", labels=["Entity"], summary="personne", attributes={})
    product = EntityNode(uuid="u-2", name="Sillage", labels=["Entity"], summary="logiciel", attributes={})
    qualifications = {
        "u-1": _qual(person, ActorRole.PERSON, EligibilityStatus.ELIGIBLE),
        "u-2": _qual(product, ActorRole.PRODUCT, EligibilityStatus.INELIGIBLE),
    }
    profiles = generator.generate_profiles_from_entities(
        entities=[person, product], use_llm=False, qualifications=qualifications
    )
    assert [p.name for p in profiles] == ["Élodie"]


def test_batch_with_no_eligible_actor_returns_empty():
    generator = OasisProfileGenerator(api_key="fake")
    product = EntityNode(uuid="u-2", name="Sillage", labels=["Entity"], summary="logiciel", attributes={})
    qualifications = {"u-2": _qual(product, ActorRole.PRODUCT, EligibilityStatus.INELIGIBLE)}
    profiles = generator.generate_profiles_from_entities(
        entities=[product], use_llm=False, qualifications=qualifications
    )
    assert profiles == []


# ---------------------------------------------------------------------------
# AC7 — prompt choisi par rôle qualifié, traçabilité d'origine préservée
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, content):
        self.content = content
        self.choices = [SimpleNamespace(finish_reason="stop")]


def test_prompt_selected_by_qualified_role(monkeypatch):
    generator = OasisProfileGenerator(api_key="fake")
    captured = {}
    monkeypatch.setattr(
        generator,
        "_build_group_persona_prompt",
        lambda *args, **kwargs: captured.setdefault("group", True) or "G",
    )
    monkeypatch.setattr(
        generator,
        "_build_individual_persona_prompt",
        lambda *args, **kwargs: captured.setdefault("individual", True) or "I",
    )
    monkeypatch.setattr(
        oasis_module,
        "create_chat_completion",
        lambda *args, **kwargs: _FakeResponse('{"bio": "b", "persona": "p"}'),
    )
    monkeypatch.setattr(oasis_module, "extract_chat_completion_text", lambda response: response.content)

    entity = EntityNode(uuid="u-1", name="Atelier Sillage", labels=["Entity"], summary="société", attributes={})
    qualification = _qual(entity, ActorRole.ORGANIZATION, EligibilityStatus.ELIGIBLE)
    profile = generator.generate_profile_from_entity(
        entity, 0, use_llm=True, qualification=qualification
    )
    assert captured.get("group") is True
    assert "individual" not in captured
    assert profile.source_entity_type == "Entity"
    assert profile.source_entity_uuid == "u-1"


# ---------------------------------------------------------------------------
# AC10 — réutilisation, invalidation et démarrage (routes)
# ---------------------------------------------------------------------------


def _configure_app(monkeypatch, tmp_path, project):
    monkeypatch.setattr(Config, "OASIS_SIMULATION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        ProjectManager, "get_project", classmethod(lambda cls, pid: project)
    )
    monkeypatch.setattr(
        ProjectManager, "get_extracted_text", classmethod(lambda cls, pid: "")
    )
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _write_legacy_preparation(manager, tmp_path):
    """Prépare un dossier complet mais sans preuve de qualification."""

    state = manager.create_simulation(project_id="proj", graph_id="graph")
    state.status = SimulationStatus.READY
    state.profiles_generated = True
    state.config_generated = True
    manager._save_simulation_state(state)
    sim_dir = tmp_path / state.simulation_id
    (sim_dir / "simulation_config.json").write_text("{}", encoding="utf-8")
    (sim_dir / "reddit_profiles.json").write_text("[]", encoding="utf-8")
    (sim_dir / "twitter_profiles.csv").write_text("user_id\n", encoding="utf-8")
    return state


class _ParkedThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


class _StubTaskManager:
    def create_task(self, **kwargs):
        return "task-test"

    def update_task(self, *args, **kwargs):
        pass

    def fail_task(self, *args, **kwargs):
        pass

    def complete_task(self, *args, **kwargs):
        pass

    def get_task(self, *args, **kwargs):
        return None


def _park_background(monkeypatch):
    monkeypatch.setattr(threading, "Thread", _ParkedThread)
    monkeypatch.setattr(task_module, "TaskManager", _StubTaskManager)


def test_prepare_status_does_not_declare_historical_preparation_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))
    manager = SimulationManager()
    state = _write_legacy_preparation(manager, tmp_path)
    client = _configure_app(monkeypatch, tmp_path, SimpleNamespace(project_id="proj"))

    response = client.post(
        "/api/simulation/prepare/status", json={"simulation_id": state.simulation_id}
    )
    data = response.get_json()["data"]
    assert data["already_prepared"] is False
    assert data["status"] != "ready"
    assert data["reason"] == "preuve de qualification absente"


def test_start_refuses_preparation_without_qualification_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))
    manager = SimulationManager()
    state = _write_legacy_preparation(manager, tmp_path)
    client = _configure_app(monkeypatch, tmp_path, SimpleNamespace(project_id="proj"))

    response = client.post(
        "/api/simulation/start", json={"simulation_id": state.simulation_id}
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["reason"] == "preuve de qualification absente"


def test_prepare_reuses_fresh_qualification(tmp_path, monkeypatch):
    dataset = load_dataset("logiciel_gestion")
    manager, store, prepared = _prepare(dataset, tmp_path, monkeypatch, use_llm=False)
    project = SimpleNamespace(
        project_id=prepared.project_id,
        graph_id=prepared.graph_id,
        simulation_requirement=dataset["simulation_requirement"],
    )
    with override_graph_store(store):
        client = _configure_app(monkeypatch, tmp_path, project)
        response = client.post(
            "/api/simulation/prepare", json={"simulation_id": prepared.simulation_id}
        )
    assert response.status_code == 200
    assert response.get_json()["data"]["already_prepared"] is True


def _fresh_context(tmp_path, monkeypatch):
    dataset = load_dataset("logiciel_gestion")
    manager, store, prepared = _prepare(dataset, tmp_path, monkeypatch, use_llm=False)
    project = SimpleNamespace(
        project_id=prepared.project_id,
        graph_id=prepared.graph_id,
        simulation_requirement=dataset["simulation_requirement"],
    )
    return manager, store, prepared, project


def test_prepare_status_invalidates_on_policy_change(tmp_path, monkeypatch):
    manager, store, prepared, project = _fresh_context(tmp_path, monkeypatch)
    monkeypatch.setattr(
        simulation_api, "ACTOR_ELIGIBILITY_POLICY_VERSION", "009-1-v2"
    )
    with override_graph_store(store):
        client = _configure_app(monkeypatch, tmp_path, project)
        response = client.post(
            "/api/simulation/prepare/status", json={"simulation_id": prepared.simulation_id}
        )
    assert response.get_json()["data"]["already_prepared"] is False


def test_prepare_invalidates_on_requirement_change(tmp_path, monkeypatch):
    manager, store, prepared, project = _fresh_context(tmp_path, monkeypatch)
    _park_background(monkeypatch)
    project.simulation_requirement = "Consigne différente"
    with override_graph_store(store):
        client = _configure_app(monkeypatch, tmp_path, project)
        response = client.post(
            "/api/simulation/prepare", json={"simulation_id": prepared.simulation_id}
        )
    assert response.get_json()["data"]["already_prepared"] is False


def test_prepare_invalidates_on_entity_change(tmp_path, monkeypatch):
    manager, store, prepared, project = _fresh_context(tmp_path, monkeypatch)
    _park_background(monkeypatch)
    store._nodes.append(
        GraphNode(uuid="new-node", name="Nouvelle entité", labels=["Entity"], summary="apparue")
    )
    with override_graph_store(store):
        client = _configure_app(monkeypatch, tmp_path, project)
        response = client.post(
            "/api/simulation/prepare", json={"simulation_id": prepared.simulation_id}
        )
    assert response.get_json()["data"]["already_prepared"] is False


# ---------------------------------------------------------------------------
# Revue de code du 11 octobre 2026 — patches du triage
# ---------------------------------------------------------------------------


def test_qualification_inputs_fresh_for_untouched_preparation(tmp_path, monkeypatch):
    manager, store, prepared, project = _fresh_context(tmp_path, monkeypatch)
    monkeypatch.setattr(Config, "OASIS_SIMULATION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ProjectManager, "get_project", classmethod(lambda cls, pid: project))
    with override_graph_store(store):
        fresh, reason = simulation_api._qualification_inputs_are_fresh(
            prepared, prepared.entity_types or None
        )
    assert fresh is True
    assert reason == ""


def test_start_refuses_stale_qualification_inputs(tmp_path, monkeypatch):
    manager, store, prepared, project = _fresh_context(tmp_path, monkeypatch)
    store._nodes.append(
        GraphNode(uuid="new-node", name="Nouvelle entité", labels=["Entity"], summary="apparue")
    )
    with override_graph_store(store):
        client = _configure_app(monkeypatch, tmp_path, project)
        response = client.post(
            "/api/simulation/start", json={"simulation_id": prepared.simulation_id}
        )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["reason"] == "entrées de qualification modifiées"


def _mutate_proof(tmp_path, prepared_id, **changes):
    proof_path = tmp_path / prepared_id / "actor_qualifications.json"
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    proof.update(changes)
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")


def test_prepare_status_refuses_proof_from_other_graph(tmp_path, monkeypatch):
    manager, store, prepared, project = _fresh_context(tmp_path, monkeypatch)
    _mutate_proof(tmp_path, prepared.simulation_id, graph_id="un-autre-graphe")
    client = _configure_app(monkeypatch, tmp_path, project)
    response = client.post(
        "/api/simulation/prepare/status", json={"simulation_id": prepared.simulation_id}
    )
    data = response.get_json()["data"]
    assert data["already_prepared"] is False
    assert data["reason"] == "préparation liée à un autre graphe"


def test_prepare_status_refuses_proof_from_other_project(tmp_path, monkeypatch):
    manager, store, prepared, project = _fresh_context(tmp_path, monkeypatch)
    _mutate_proof(tmp_path, prepared.simulation_id, project_id="un-autre-projet")
    client = _configure_app(monkeypatch, tmp_path, project)
    response = client.post(
        "/api/simulation/prepare/status", json={"simulation_id": prepared.simulation_id}
    )
    data = response.get_json()["data"]
    assert data["already_prepared"] is False
    assert data["reason"] == "préparation liée à un autre projet"


def test_prepare_status_refuses_proof_from_other_simulation(tmp_path, monkeypatch):
    manager, store, prepared, project = _fresh_context(tmp_path, monkeypatch)
    _mutate_proof(tmp_path, prepared.simulation_id, simulation_id="sim-inconnue")
    client = _configure_app(monkeypatch, tmp_path, project)
    response = client.post(
        "/api/simulation/prepare/status", json={"simulation_id": prepared.simulation_id}
    )
    data = response.get_json()["data"]
    assert data["already_prepared"] is False
    assert data["reason"] == "preuve liée à une autre simulation"


def test_start_refuses_proof_from_other_graph(tmp_path, monkeypatch):
    manager, store, prepared, project = _fresh_context(tmp_path, monkeypatch)
    _mutate_proof(tmp_path, prepared.simulation_id, graph_id="un-autre-graphe")
    client = _configure_app(monkeypatch, tmp_path, project)
    response = client.post(
        "/api/simulation/start", json={"simulation_id": prepared.simulation_id}
    )
    assert response.status_code == 400
    assert response.get_json()["reason"] == "préparation liée à un autre graphe"


def test_realtime_total_expected_prefers_actors_count(tmp_path, monkeypatch):
    client = _configure_app(monkeypatch, tmp_path, SimpleNamespace(project_id="proj"))
    sim_dir = tmp_path / "sim-realtime"
    sim_dir.mkdir()
    (sim_dir / "state.json").write_text(json.dumps({
        "status": "preparing",
        "actors_count": 8,
        "entities_count": 23,
        "enable_twitter": True,
        "enable_reddit": True,
    }), encoding="utf-8")
    response = client.get("/api/simulation/sim-realtime/profiles/realtime")
    data = response.get_json()["data"]
    assert data["total_expected"] == 8


def test_realtime_total_expected_falls_back_to_entities_count(tmp_path, monkeypatch):
    client = _configure_app(monkeypatch, tmp_path, SimpleNamespace(project_id="proj"))
    sim_dir = tmp_path / "sim-realtime-2"
    sim_dir.mkdir()
    (sim_dir / "state.json").write_text(json.dumps({
        "status": "preparing",
        "entities_count": 23,
        "enable_twitter": True,
        "enable_reddit": True,
    }), encoding="utf-8")
    response = client.get("/api/simulation/sim-realtime-2/profiles/realtime")
    data = response.get_json()["data"]
    assert data["total_expected"] == 23


class _StubClassifier:
    """Classifieur de route : décisions fixées par UUID, sans LLM."""

    def __init__(self, decisions):
        self._decisions = decisions

    def classify_entities(self, entities, simulation_requirement=""):
        qualifications = []
        for entity in entities:
            role, status = self._decisions.get(
                entity.uuid, (ActorRole.UNKNOWN, EligibilityStatus.REVIEW)
            )
            qualifications.append(_qual(entity, role, status))
        return ActorClassificationResult(qualifications=qualifications)


def test_generate_profiles_route_applies_barrier(tmp_path, monkeypatch):
    store = FixtureStore(nodes=[
        GraphNode(uuid="p-1", name="Élodie", labels=["Entity"], summary="personne"),
        GraphNode(uuid="c-1", name="Sillage", labels=["Entity"], summary="logiciel"),
    ])
    client = _configure_app(monkeypatch, tmp_path, SimpleNamespace(project_id="proj"))
    stub = _StubClassifier({
        "p-1": (ActorRole.PERSON, EligibilityStatus.ELIGIBLE),
        "c-1": (ActorRole.PRODUCT, EligibilityStatus.INELIGIBLE),
    })
    monkeypatch.setattr(simulation_api, "ActorClassifierService", lambda *a, **k: stub)
    with override_graph_store(store):
        response = client.post(
            "/api/simulation/generate-profiles",
            json={"graph_id": "graph", "use_llm": False},
        )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["count"] == 1
    assert data["actors_count"] == 1
    assert data["ineligible_count"] == 1


def test_generate_profiles_route_refuses_when_no_actor(tmp_path, monkeypatch):
    store = FixtureStore(nodes=[
        GraphNode(uuid="c-1", name="Sillage", labels=["Entity"], summary="logiciel"),
    ])
    client = _configure_app(monkeypatch, tmp_path, SimpleNamespace(project_id="proj"))
    monkeypatch.setattr(
        simulation_api, "ActorClassifierService", lambda *a, **k: _StubClassifier({})
    )
    with override_graph_store(store):
        response = client.post(
            "/api/simulation/generate-profiles",
            json={"graph_id": "graph", "use_llm": False},
        )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["counts"]["eligible"] == 0
    assert payload["counts"]["review"] == 1
    assert payload["error"]


def test_rule_based_persona_keeps_student_template():
    generator = OasisProfileGenerator(api_key="fake")
    data = generator._generate_profile_rule_based(
        "Élodie", "Student", "étudiante", {}, role=ActorRole.PERSON
    )
    assert data["profession"] == "Student"
    assert "thought leader" not in data["bio"]


def test_rule_based_persona_keeps_media_template_for_organization():
    generator = OasisProfileGenerator(api_key="fake")
    data = generator._generate_profile_rule_based(
        "Le Quotidien", "MediaOutlet", "journal local", {}, role=ActorRole.ORGANIZATION
    )
    assert data["profession"] == "Media"


def test_keyless_generator_degrades_with_counter(monkeypatch):
    monkeypatch.setattr(Config, "LLM_API_KEY", None)
    monkeypatch.setattr(OasisProfileGenerator, "_build_entity_context", lambda self, entity: "")
    generator = OasisProfileGenerator()
    assert generator.client is None
    entity = EntityNode(uuid="u-1", name="Élodie", labels=["Entity"], summary="personne", attributes={})
    qualification = _qual(entity, ActorRole.PERSON, EligibilityStatus.ELIGIBLE)
    profile = generator.generate_profile_from_entity(
        entity, 0, use_llm=True, qualification=qualification
    )
    assert profile.name == "Élodie"
    assert generator.degraded_generations == 1
