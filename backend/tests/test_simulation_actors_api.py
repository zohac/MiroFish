"""Tests d'intégration des routes `/actors/preview`, `/actors/review` et préparation (story 009-3).

Couvre :
  - AC2 : route `POST /api/simulation/actors/preview` (cache, recalcul, conflits, diagnostics)
  - AC3 : route `POST /api/simulation/actors/review` (409, 400 rôle passif eligible, 400 justification vide, 400 état)
  - AC4 : parcours simple préservé et consommation de `actors.json` révisé
  - AC5 : invalidation sur divergence d'empreinte
  - AC6 : blocage volontaire préventif (`block_on_review`, `block_on_conflict`)
"""

import json
from types import SimpleNamespace

import pytest

from app import create_app
from app.config import Config
from app.models.actor_eligibility import (
    ACTOR_ELIGIBILITY_POLICY_VERSION,
    ActorEligibility,
    ActorRole,
    EligibilityStatus,
)
from app.models.actor_selection import (
    ActorItem,
    ActorSelection,
)
from app.models.project import ProjectManager
from app.models.simulation_brief import SimulationBrief
from app.models.source_document import (
    ConflictResolutionRule,
    ConflictStatus,
    DocumentRole,
    DocumentValidationStatus,
    SourceConflict,
    SourceReference,
)
from app.services.actor_classifier import (
    ActorClassificationResult,
    ActorClassifierService,
)
from app.services.simulation_manager import (
    SimulationManager,
    SimulationStatus,
)
from app.utils.graph_store.base import (
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphSearchResult,
    GraphStore,
)
from app.utils.graph_store.factory import override_graph_store


class MemoryGraphStore(GraphStore):
    """Store en mémoire simple et hermétique."""

    def __init__(self, nodes=None, edges=None):
        self._nodes = nodes or []
        self._edges = edges or []

    def create_graph(self, name, graph_id=None):
        return graph_id or "mem-graph"

    def delete_graph(self, graph_id):
        pass

    def get_graph_info(self, graph_id):
        return GraphInfo(
            graph_id=graph_id,
            name=graph_id,
            node_count=len(self._nodes),
            edge_count=len(self._edges),
        )

    def get_all_nodes(self, graph_id):
        return list(self._nodes)

    def get_all_edges(self, graph_id, include_temporal=True):
        return list(self._edges)

    def get_node(self, graph_id, node_uuid):
        for n in self._nodes:
            if n.uuid == node_uuid:
                return n
        return None

    def get_node_edges(self, graph_id, node_uuid):
        return [
            e
            for e in self._edges
            if e.source_node_uuid == node_uuid or e.target_node_uuid == node_uuid
        ]

    def search(self, graph_id, query, limit=10, scope="edges", reranker=None):
        return GraphSearchResult(
            nodes=list(self._nodes[:limit]),
            edges=[],
            facts=[],
            query=query,
            total_count=len(self._nodes),
        )

    def get_graph_data(self, graph_id: str):
        return {
            "nodes": [n.to_dict() for n in self._nodes],
            "edges": [e.to_dict() for e in self._edges],
        }

    def get_edge_provenance(self, graph_id: str, edge_uuid: str):
        return []

    def add_node(self, graph_id, name, labels, attributes=None):
        return "n-uuid"

    def add_edge(self, graph_id, source_node_uuid, target_node_uuid, name, fact=None, valid_at=None, invalid_at=None):
        return "e-uuid"

    def set_ontology(self, graph_id, entity_types, edge_types):
        pass

    def add_episode(self, graph_id, name, content, source="text", source_description="", episode_type="text", metadata=None):
        return "ep-uuid"

    def add_text_batch(self, graph_id, episodes_data):
        return None

    def wait_for_batch(self, graph_id, batch_id, timeout=30.0, poll_interval=0.5):
        return None

    def wait_for_episodes(self, graph_id, episode_uuids, timeout=30.0, poll_interval=0.5):
        return None


class FakeClassifier(ActorClassifierService):
    """Classifieur déterministe simulant les résultats de classification."""

    def __init__(self, mapping=None):
        super().__init__(llm_client=None)
        self.mapping = mapping or {}

    def classify_entities(self, entities, simulation_requirement="", simulation_brief=None):
        qualifications = []
        for e in entities:
            if e.uuid in self.mapping:
                role, status, rationale = self.mapping[e.uuid]
            else:
                role = ActorRole.PERSON if "Person" in e.labels else ActorRole.PRODUCT
                status = (
                    EligibilityStatus.ELIGIBLE
                    if role == ActorRole.PERSON
                    else EligibilityStatus.INELIGIBLE
                )
                rationale = f"Heuristique pour {e.name}"
            qualifications.append(
                ActorEligibility(
                    entity_uuid=e.uuid,
                    entity_name=e.name,
                    role=role,
                    status=status,
                    rationale=rationale,
                    confidence=0.9,
                    original_type="Person" if role == ActorRole.PERSON else "Product",
                )
            )
        return ActorClassificationResult(qualifications=qualifications)


def _setup_env(tmp_path, monkeypatch, conflicts=None):
    monkeypatch.setattr(Config, "OASIS_SIMULATION_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path))

    store = MemoryGraphStore(
        nodes=[
            GraphNode(uuid="uuid-1", name="Jean Dupont", labels=["Entity", "Person"]),
            GraphNode(uuid="uuid-2", name="Société Beta", labels=["Entity", "Organization"]),
            GraphNode(uuid="uuid-3", name="Collectif Test", labels=["Entity", "Group"]),
            GraphNode(uuid="uuid-4", name="Offre Cloud 10€", labels=["Entity", "Product"]),
        ]
    )

    project = SimpleNamespace(
        project_id="proj-test",
        graph_id="graph-test",
        simulation_requirement="Tester l'adoption du produit",
        get_brief=lambda: SimulationBrief(
            goal="Tester l'adoption",
            initial_state="Lancement récent",
            target_audiences=["Professionnels"],
            excluded_actors=[],
            rules=[],
            hypotheses=[],
        ),
        get_source_conflicts=lambda: conflicts or [],
    )

    monkeypatch.setattr(
        ProjectManager, "get_project", classmethod(lambda cls, pid: project)
    )
    monkeypatch.setattr(
        ProjectManager, "get_extracted_text", classmethod(lambda cls, pid: "Texte documentaire")
    )

    app = create_app()
    app.config.update(TESTING=True)
    client = app.test_client()

    manager = SimulationManager()
    state = manager.create_simulation(project_id="proj-test", graph_id="graph-test")

    return client, manager, state, store


# ===========================================================================
# AC2 : POST /api/simulation/actors/preview
# ===========================================================================

def test_preview_actors_missing_simulation_id(tmp_path, monkeypatch):
    client, _, _, _ = _setup_env(tmp_path, monkeypatch)
    res = client.post("/api/simulation/actors/preview", json={})
    assert res.status_code == 400
    assert "simulation" in res.get_json()["error"].lower()


def test_preview_actors_not_found(tmp_path, monkeypatch):
    client, _, _, _ = _setup_env(tmp_path, monkeypatch)
    res = client.post(
        "/api/simulation/actors/preview", json={"simulation_id": "sim-inconnu"}
    )
    assert res.status_code == 404


def test_preview_actors_nominal_and_cache_reuse(tmp_path, monkeypatch):
    conflict = SourceConflict(
        conflict_id="conf-1",
        claim="Date de lancement contestée",
        status=ConflictStatus.OPEN,
        source_references=[
            SourceReference(
                document_id="doc-1",
                filename="doc1.md",
                role=DocumentRole.FACTS,
                priority=1,
                date="2026-01-01",
                validation_status=DocumentValidationStatus.UNVALIDATED,
            ),
            SourceReference(
                document_id="doc-2",
                filename="doc2.md",
                role=DocumentRole.FACTS,
                priority=2,
                date="2026-01-02",
                validation_status=DocumentValidationStatus.UNVALIDATED,
            ),
        ],
    )
    client, manager, state, store = _setup_env(tmp_path, monkeypatch, conflicts=[conflict])

    classifier = FakeClassifier({
        "uuid-1": (ActorRole.PERSON, EligibilityStatus.ELIGIBLE, "Directeur"),
        "uuid-2": (ActorRole.ORGANIZATION, EligibilityStatus.ELIGIBLE, "PME"),
        "uuid-3": (ActorRole.COLLECTIVE, EligibilityStatus.REVIEW, "Collectif citoyen"),
        "uuid-4": (ActorRole.PRODUCT, EligibilityStatus.INELIGIBLE, "Offre"),
    })
    orig_preview = SimulationManager.preview_actors
    monkeypatch.setattr(
        SimulationManager,
        "preview_actors",
        lambda self, simulation_id, force_refresh=False, **kwargs: orig_preview(
            self, simulation_id, force_refresh=force_refresh, classifier=classifier
        ),
    )

    with override_graph_store(store):
        # 1. Premier appel : création de la sélection
        res1 = client.post(
            "/api/simulation/actors/preview", json={"simulation_id": state.simulation_id}
        )
        assert res1.status_code == 200
        data1 = res1.get_json()["data"]
        assert data1["reused"] is False
        assert len(data1["conflicts"]) == 1
        assert data1["conflicts"][0]["claim"] == "Date de lancement contestée"

        sel1 = data1["selection"]
        assert sel1["revision"] == 1
        assert sel1["counts"] == {"total": 4, "eligible": 2, "review": 1, "ineligible": 1}

        # 2. Deuxième appel sans force_refresh : réutilisation du cache
        res2 = client.post(
            "/api/simulation/actors/preview", json={"simulation_id": state.simulation_id}
        )
        assert res2.status_code == 200
        data2 = res2.get_json()["data"]
        assert data2["reused"] is True
        assert data2["selection"]["revision"] == 1

        # 3. Troisième appel avec force_refresh=True : recalcul forcé
        res3 = client.post(
            "/api/simulation/actors/preview",
            json={"simulation_id": state.simulation_id, "force_refresh": True},
        )
        assert res3.status_code == 200
        data3 = res3.get_json()["data"]
        assert data3["reused"] is False


# ===========================================================================
# AC3 : POST /api/simulation/actors/review
# ===========================================================================

def test_review_actors_validations_and_rejections(tmp_path, monkeypatch):
    client, manager, state, store = _setup_env(tmp_path, monkeypatch)

    classifier = FakeClassifier()
    with override_graph_store(store):
        manager.preview_actors(state.simulation_id, classifier=classifier)

    # 1. Paramètres manquants
    res = client.post("/api/simulation/actors/review", json={"simulation_id": state.simulation_id})
    assert res.status_code == 400
    assert "expected_revision" in res.get_json()["error"]

    res = client.post(
        "/api/simulation/actors/review",
        json={"simulation_id": state.simulation_id, "expected_revision": 1, "modifications": []},
    )
    assert res.status_code == 400
    assert "modifications" in res.get_json()["error"]

    # 2. Conflit de révision (HTTP 409)
    res_409 = client.post(
        "/api/simulation/actors/review",
        json={
            "simulation_id": state.simulation_id,
            "expected_revision": 99,  # Désynchronisé !
            "modifications": [
                {
                    "entity_uuid": "uuid-3",
                    "role": "organization",
                    "status": "eligible",
                    "justification": "Statuts légaux déposés",
                }
            ],
        },
    )
    assert res_409.status_code == 409
    assert res_409.get_json()["code"] == "CONFLICT_REVISION"

    # 3. Rejet d'un rôle passif combiné à eligible (HTTP 400)
    res_passive = client.post(
        "/api/simulation/actors/review",
        json={
            "simulation_id": state.simulation_id,
            "expected_revision": 1,
            "modifications": [
                {
                    "entity_uuid": "uuid-4",
                    "role": "product",
                    "status": "eligible",
                    "justification": "Compte de support produit",
                }
            ],
        },
    )
    assert res_passive.status_code == 400
    assert "Interdiction stricte" in res_passive.get_json()["error"]

    # 4. Rejet sur justification vide (HTTP 400)
    res_empty_justif = client.post(
        "/api/simulation/actors/review",
        json={
            "simulation_id": state.simulation_id,
            "expected_revision": 1,
            "modifications": [
                {
                    "entity_uuid": "uuid-3",
                    "role": "organization",
                    "status": "eligible",
                    "justification": "   ",
                }
            ],
        },
    )
    assert res_empty_justif.status_code == 400
    assert "Justification obligatoire" in res_empty_justif.get_json()["error"]

    # 5. Rejet sur simulation active (HTTP 400)
    state.status = SimulationStatus.PREPARING
    manager._save_simulation_state(state)
    res_active = client.post(
        "/api/simulation/actors/review",
        json={
            "simulation_id": state.simulation_id,
            "expected_revision": 1,
            "modifications": [
                {
                    "entity_uuid": "uuid-3",
                    "role": "organization",
                    "status": "eligible",
                    "justification": "Valide",
                }
            ],
        },
    )
    assert res_active.status_code == 400
    assert "Mutations interdites" in res_active.get_json()["error"]


def test_review_actors_nominal_success(tmp_path, monkeypatch):
    client, manager, state, store = _setup_env(tmp_path, monkeypatch)

    classifier = FakeClassifier({
        "uuid-1": (ActorRole.PERSON, EligibilityStatus.ELIGIBLE, "Directeur"),
        "uuid-2": (ActorRole.ORGANIZATION, EligibilityStatus.ELIGIBLE, "PME"),
        "uuid-3": (ActorRole.COLLECTIVE, EligibilityStatus.REVIEW, "Collectif citoyen"),
        "uuid-4": (ActorRole.PRODUCT, EligibilityStatus.INELIGIBLE, "Offre"),
    })
    with override_graph_store(store):
        manager.preview_actors(state.simulation_id, classifier=classifier)

    # Révision réussie de uuid-3 vers Organization éligible
    res = client.post(
        "/api/simulation/actors/review",
        json={
            "simulation_id": state.simulation_id,
            "expected_revision": 1,
            "modifications": [
                {
                    "entity_uuid": "uuid-3",
                    "role": "organization",
                    "status": "eligible",
                    "justification": "Association loi 1901 confirmée",
                }
            ],
        },
    )
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["revision"] == 2
    selection = data["selection"]
    assert selection["counts"]["eligible"] == 3
    assert selection["counts"]["review"] == 0

    # L'acteur modifié porte bien les attributs d'arbitrage
    item_3 = next(a for a in selection["actors"] if a["entity_uuid"] == "uuid-3")
    assert item_3["is_human_modified"] is True
    assert item_3["qualified_role"] == "organization"
    assert item_3["justification"] == "Association loi 1901 confirmée"


# ===========================================================================
# AC4 / AC5 / AC6 : Intégration de prepare_simulation
# ===========================================================================

def test_prepare_simulation_simple_path_without_prior_preview(tmp_path, monkeypatch):
    _, manager, state, store = _setup_env(tmp_path, monkeypatch)
    classifier = FakeClassifier()

    with override_graph_store(store):
        result = manager.prepare_simulation(
            simulation_id=state.simulation_id,
            simulation_requirement="Consigne",
            document_text="Contenu",
            use_llm_for_profiles=False,
            classifier=classifier,
        )

    assert result.status == SimulationStatus.READY
    assert result.actors_count > 0

    # actors.json a été automatiquement généré en révision 1 (AC4)
    selection = manager.get_actor_selection(state.simulation_id)
    assert selection is not None
    assert selection.revision == 1
    assert selection.counts["eligible"] == result.actors_count


def test_prepare_simulation_consumes_human_reviewed_selection(tmp_path, monkeypatch):
    client, manager, state, store = _setup_env(tmp_path, monkeypatch)

    classifier = FakeClassifier({
        "uuid-1": (ActorRole.PERSON, EligibilityStatus.ELIGIBLE, "Directeur"),
        "uuid-2": (ActorRole.ORGANIZATION, EligibilityStatus.ELIGIBLE, "PME"),
        "uuid-3": (ActorRole.COLLECTIVE, EligibilityStatus.REVIEW, "Collectif citoyen"),
        "uuid-4": (ActorRole.PRODUCT, EligibilityStatus.INELIGIBLE, "Offre"),
    })

    with override_graph_store(store):
        # 1. Prévisualisation
        manager.preview_actors(state.simulation_id, classifier=classifier)

        # 2. Arbitrage humain : uuid-3 promu en organisation éligible
        client.post(
            "/api/simulation/actors/review",
            json={
                "simulation_id": state.simulation_id,
                "expected_revision": 1,
                "modifications": [
                    {
                        "entity_uuid": "uuid-3",
                        "role": "organization",
                        "status": "eligible",
                        "justification": "Structure formelle",
                    }
                ],
            },
        )

        # 3. Préparation : consomme la sélection révisée révision 2 (AC4)
        result = manager.prepare_simulation(
            simulation_id=state.simulation_id,
            simulation_requirement="Tester l'adoption du produit",
            document_text="Contenu",
            use_llm_for_profiles=False,
            classifier=classifier,
        )

    assert result.status == SimulationStatus.READY
    assert result.actors_count == 3  # uuid-1, uuid-2 et uuid-3
    assert "uuid-3" in result.qualified_actor_uuids

    # Vérification que le fichier profiles reddit contient bien 3 profils
    profiles = manager.get_profiles(state.simulation_id, platform="reddit")
    assert len(profiles) == 3

    # Vérification que la justification humaine est transmise dans la preuve de qualification (Patch 2)
    from app.services.simulation_manager import read_qualification_proof
    proof = read_qualification_proof(str(tmp_path / state.simulation_id))
    assert proof is not None
    q3 = next(q for q in proof["qualifications"] if q["entity_uuid"] == "uuid-3")
    assert q3["rationale"] == "Structure formelle"


def test_prepare_simulation_invalidates_obsolete_selection_on_fingerprint_divergence(
    tmp_path, monkeypatch
):
    _, manager, state, store = _setup_env(tmp_path, monkeypatch)

    # 1. Sélection initiale enregistrée avec une empreinte différente
    dummy_selection = ActorSelection(
        simulation_id=state.simulation_id,
        project_id=state.project_id,
        graph_id=state.graph_id,
        input_fingerprint="empreinte-obsolete-1234",
        revision=2,
        actors=[
            ActorItem(
                entity_uuid="uuid-1",
                entity_name="Jean Dupont",
                qualified_role=ActorRole.PERSON,
                eligibility_status=EligibilityStatus.ELIGIBLE,
            )
        ],
    )
    manager.save_actor_selection(dummy_selection)

    classifier = FakeClassifier()
    with override_graph_store(store):
        result = manager.prepare_simulation(
            simulation_id=state.simulation_id,
            simulation_requirement="Consigne actuelle",
            document_text="Contenu",
            use_llm_for_profiles=False,
            classifier=classifier,
        )

    # La sélection a été régénérée car l'empreinte divergait (AC5)
    new_selection = manager.get_actor_selection(state.simulation_id)
    assert new_selection.input_fingerprint != "empreinte-obsolete-1234"
    assert new_selection.revision == 1


def test_prepare_simulation_blocks_on_review(tmp_path, monkeypatch):
    _, manager, state, store = _setup_env(tmp_path, monkeypatch)

    classifier = FakeClassifier({
        "uuid-1": (ActorRole.PERSON, EligibilityStatus.ELIGIBLE, "Directeur"),
        "uuid-2": (ActorRole.ORGANIZATION, EligibilityStatus.ELIGIBLE, "PME"),
        "uuid-3": (ActorRole.COLLECTIVE, EligibilityStatus.REVIEW, "Collectif citoyen"),
        "uuid-4": (ActorRole.PRODUCT, EligibilityStatus.INELIGIBLE, "Offre"),
    })

    with override_graph_store(store):
        with pytest.raises(ValueError) as exc_info:
            manager.prepare_simulation(
                simulation_id=state.simulation_id,
                simulation_requirement="Consigne",
                document_text="Contenu",
                use_llm_for_profiles=False,
                classifier=classifier,
                block_on_review=True,  # Blocage préventif actif !
            )

    assert "Blocage préventif activé" in str(exc_info.value)
    assert "REVIEW" in str(exc_info.value)
    assert "Collectif Test" in str(exc_info.value)


def test_prepare_simulation_blocks_on_conflict(tmp_path, monkeypatch):
    open_conflict = SourceConflict(
        conflict_id="conf-open",
        claim="Contradiction sur la tarification officielle",
        status=ConflictStatus.OPEN,
        source_references=[
            SourceReference(
                document_id="doc-1",
                filename="doc1.md",
                role=DocumentRole.FACTS,
                priority=1,
                date="2026-01-01",
                validation_status=DocumentValidationStatus.UNVALIDATED,
            ),
            SourceReference(
                document_id="doc-2",
                filename="doc2.md",
                role=DocumentRole.FACTS,
                priority=2,
                date="2026-01-02",
                validation_status=DocumentValidationStatus.UNVALIDATED,
            ),
        ],
    )
    _, manager, state, store = _setup_env(tmp_path, monkeypatch, conflicts=[open_conflict])

    classifier = FakeClassifier({
        "uuid-1": (ActorRole.PERSON, EligibilityStatus.ELIGIBLE, "Directeur"),
        "uuid-2": (ActorRole.ORGANIZATION, EligibilityStatus.ELIGIBLE, "PME"),
        "uuid-3": (ActorRole.PERSON, EligibilityStatus.ELIGIBLE, "Associé"),
        "uuid-4": (ActorRole.PRODUCT, EligibilityStatus.INELIGIBLE, "Offre"),
    })

    with override_graph_store(store):
        with pytest.raises(ValueError) as exc_info:
            manager.prepare_simulation(
                simulation_id=state.simulation_id,
                simulation_requirement="Consigne",
                document_text="Contenu",
                use_llm_for_profiles=False,
                classifier=classifier,
                block_on_conflict=True,  # Blocage préventif actif !
            )

    assert "Blocage préventif activé" in str(exc_info.value)
    assert "conflit(s) documentaire(s) non résolu(s)" in str(exc_info.value)
    assert "Contradiction sur la tarification officielle" in str(exc_info.value)
