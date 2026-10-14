"""Tests hermétiques pour les événements ontologiques E1, E2, E3, E4 et les routes API (story 007-4)."""

import json
import pytest
from unittest.mock import MagicMock

from app.config import Config
from app import create_app
from app.models.ontology_version import OntologyVersionStore
from app.models.project import Project, ProjectManager, ProjectStatus
from app.models.source_document import InformationOrigin
from app.services.ontology_events import (
    BRIEF_SIMILARITY_THRESHOLD,
    OntologyEventService,
    calculate_brief_similarity,
    should_regenerate_on_brief_change,
)
from app.utils.graph_store.base import (
    AppliedOntology,
    GraphNode,
    GraphStore,
    GraphValidationWarning,
)
from app.utils.graph_store.errors import GraphNotFoundError, GraphValidationError


class FakeOntologyGraphStore(GraphStore):
    """Store factice conservant nœuds et ontologie pour vérifier l'intégrité C4."""

    def __init__(self):
        self.ontologies = {}
        self.nodes = {}  # graph_id -> list[GraphNode]
        self.policies = {}
        self.warnings = {}

    def set_ontology(self, graph_id: str, ontology: dict, *, strict: bool = False) -> None:
        self.ontologies[graph_id] = ontology
        self.policies[graph_id] = strict

    def get_applied_ontology(self, graph_id: str):
        if graph_id not in self.ontologies:
            return None
        onto = self.ontologies[graph_id]
        entity_names = tuple(t["name"] if isinstance(t, dict) else getattr(t, "name", str(t)) for t in onto.get("entity_types", []))
        edge_names = tuple(t["name"] if isinstance(t, dict) else getattr(t, "name", str(t)) for t in onto.get("edge_types", []))
        return AppliedOntology(entity_type_names=entity_names, edge_type_names=edge_names, strict=self.policies.get(graph_id, False))

    def update_ontology_policy(self, graph_id: str, strict: bool) -> None:
        self.policies[graph_id] = strict

    def get_ontology_warnings(self, graph_id: str, since=None):
        return self.warnings.get(graph_id, [])

    def get_edge_provenance(self, graph_id: str, edge_uuid: str):
        return []

    def get_edges_provenance(self, graph_id: str, edge_uuids):
        return {uid: [] for uid in edge_uuids}

    def add_episode(self, graph_id: str, text: str, source_description: str = "", metadata=None, created_at=None, *, ontology=None):
        # Stub
        pass

    # Stubs des méthodes obligatoires de GraphStore
    def create_graph(self, graph_id: str) -> None: pass
    def delete_graph(self, graph_id: str) -> None: pass
    def add_text_batch(self, graph_id: str, episodes): pass
    def wait_for_batch(self, batch_id: str, max_wait: float = 300.0, poll_interval: float = 2.0): pass
    def wait_for_episodes(self, graph_id: str, episode_ids, max_wait: float = 300.0, poll_interval: float = 2.0): pass
    def get_all_nodes(self, graph_id: str): return self.nodes.get(graph_id, [])
    def get_all_edges(self, graph_id: str): return []
    def get_node(self, graph_id: str, node_id: str): return None
    def get_node_edges(self, graph_id: str, node_id: str): return []
    def get_graph_data(self, graph_id: str): return {"nodes": [], "edges": []}
    def get_graph_info(self, graph_id: str): return None
    def search(self, graph_id: str, query: str, limit: int = 10, scope: str = "hybrid", center_node_uuid=None): return None


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_dir))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_dir / "projects"))
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
    monkeypatch.setattr(Config, "ZEP_API_KEY", "")
    yield upload_dir


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestSequenceMatcherBrief:
    def test_brief_similarity_ratio_exact_match(self):
        b1 = "Simulation d'une crise énergétique avec blackout."
        b2 = "Simulation d'une crise énergétique avec blackout."
        assert calculate_brief_similarity(b1, b2) == 1.0
        assert not should_regenerate_on_brief_change(b1, b2)

    def test_brief_similarity_minor_edit_ge_95(self):
        b1 = "Simulation d'une crise energetique majeure avec coupure de courant générale."
        b2 = "Simulation d'une crise énergétique majeure avec coupure de courant générale."
        ratio = calculate_brief_similarity(b1, b2)
        assert ratio >= BRIEF_SIMILARITY_THRESHOLD
        assert not should_regenerate_on_brief_change(b1, b2)

    def test_brief_similarity_substantial_change_lt_95(self):
        b1 = "Simulation d'une crise énergétique."
        b2 = "Simulation d'une cyberattaque visant le système bancaire international."
        ratio = calculate_brief_similarity(b1, b2)
        assert ratio < BRIEF_SIMILARITY_THRESHOLD
        assert should_regenerate_on_brief_change(b1, b2)


class TestOntologyEventsCore:
    def test_e4_initialization_at_creation(self):
        project = ProjectManager.create_project(name="Project E4")
        onto_dict = {
            "entity_types": [{"name": "PersonEntity", "description": "Personne"}],
            "edge_types": [],
        }

        fake_store = FakeOntologyGraphStore()
        version = OntologyEventService.initialize_ontology(
            project_id=project.project_id,
            ontology_dict=onto_dict,
            store=fake_store,
        )

        assert version.version_id.startswith("ont_")
        assert version.parent_version_id is None

        # Vérification sur le projet persisté
        reloaded = ProjectManager.get_project(project.project_id)
        assert reloaded.applied_ontology_id == version.version_id
        assert reloaded.applied_ontology_version == 1
        assert reloaded.ontology_history == [version.version_id]
        assert reloaded.get_applied_ontology().version_id == version.version_id

    def test_e2_brief_change_event(self):
        project = ProjectManager.create_project(name="Project E2")
        project.simulation_requirement = "Étude des transports urbains à Paris."
        ProjectManager.save_project(project)

        onto_v1 = {
            "entity_types": [{"name": "TransportOperator"}],
            "edge_types": [],
        }
        fake_store = FakeOntologyGraphStore()
        OntologyEventService.initialize_ontology(project.project_id, onto_v1, store=fake_store)

        mock_gen = MagicMock()
        mock_gen.generate.return_value = {
            "entity_types": [{"name": "Hospital"}, {"name": "Doctor"}],
            "edge_types": [],
        }

        # 1. Retouche mineure (ratio >= 0.95) -> Pas de régénération
        minor_brief = "Etude des transports urbains à Paris."
        regen, v = OntologyEventService.on_brief_changed(
            project_id=project.project_id,
            new_brief_text=minor_brief,
            generator=mock_gen,
            store=fake_store,
        )
        assert regen is False
        assert v is None
        mock_gen.generate.assert_not_called()

        reloaded = ProjectManager.get_project(project.project_id)
        assert reloaded.applied_ontology_version == 1

        # 2. Changement substantiel (ratio < 0.95) -> Régénération E2
        new_brief = "Pandémie mondiale et gestion des urgences hospitalières."
        regen, v2 = OntologyEventService.on_brief_changed(
            project_id=project.project_id,
            new_brief_text=new_brief,
            generator=mock_gen,
            store=fake_store,
        )
        assert regen is True
        assert v2 is not None
        assert v2.parent_version_id == reloaded.applied_ontology_id
        mock_gen.generate.assert_called_once()

        reloaded2 = ProjectManager.get_project(project.project_id)
        assert reloaded2.applied_ontology_version == 2
        assert reloaded2.applied_ontology_id == v2.version_id
        assert len(reloaded2.ontology_history) == 2

    def test_e1_document_added_and_c4_label_preservation(self):
        """Vérifie AC3 et critère C4 : les nœuds existants conservent leur label, les nouveaux portent les nouveaux types."""
        project = ProjectManager.create_project(name="Project E1 C4")
        project.graph_id = "graph_e1_c4"
        ProjectManager.save_project(project)

        fake_store = FakeOntologyGraphStore()
        fake_store.nodes[project.graph_id] = [
            GraphNode(uuid="node_1", name="Alice", labels=["Entity", "PersonEntity"]),
            GraphNode(uuid="node_2", name="Bob", labels=["Entity", "PersonEntity"]),
        ]

        onto_v1 = {
            "entity_types": [{"name": "PersonEntity"}],
            "edge_types": [],
        }
        v1 = OntologyEventService.initialize_ontology(project.project_id, onto_v1, store=fake_store)

        # Ajout d'un second document déclenchant E1
        mock_gen = MagicMock()
        mock_gen.generate.return_value = {
            "entity_types": [{"name": "PersonEntity"}, {"name": "MediaOrganization"}],
            "edge_types": [],
        }

        v2 = OntologyEventService.on_document_added(
            project_id=project.project_id,
            document_id="doc_2",
            document_text="Le journal Le Monde a publié un rapport d'enquête.",
            filename="article.txt",
            generator=mock_gen,
            store=fake_store,
        )

        assert v2.version_id != v1.version_id
        assert v2.parent_version_id == v1.version_id
        assert len(v2.entity_types) == 2

        # Vérification sur le store
        applied = fake_store.get_applied_ontology(project.graph_id)
        assert applied is not None
        applied_names = set(applied.entity_type_names)
        assert "MediaOrganization" in applied_names
        assert "PersonEntity" in applied_names

        # C4 : Les anciens nœuds ont conservé leur label sans écrasement
        existing_nodes = fake_store.get_all_nodes(project.graph_id)
        assert len(existing_nodes) == 2
        assert existing_nodes[0].labels == ["Entity", "PersonEntity"]
        assert existing_nodes[1].labels == ["Entity", "PersonEntity"]

    def test_e3_regenerate_on_demand(self):
        project = ProjectManager.create_project(name="Project E3")
        ProjectManager.save_extracted_text(project.project_id, "Corpus de base.")
        project.simulation_requirement = "Scénario E3."
        ProjectManager.save_project(project)

        onto_v1 = {"entity_types": [{"name": "OldType"}], "edge_types": []}
        fake_store = FakeOntologyGraphStore()
        OntologyEventService.initialize_ontology(project.project_id, onto_v1, store=fake_store)

        mock_gen = MagicMock()
        mock_gen.generate.return_value = {
            "entity_types": [{"name": "NewType"}],
            "edge_types": [],
        }

        v_new = OntologyEventService.regenerate_on_demand(
            project_id=project.project_id,
            generator=mock_gen,
            store=fake_store,
        )

        assert v_new.entity_types[0].name == "NewType"
        reloaded = ProjectManager.get_project(project.project_id)
        assert reloaded.applied_ontology_version == 2
        assert reloaded.applied_ontology_id == v_new.version_id

    def test_e3_reject_when_graph_building_409(self):
        project = ProjectManager.create_project(name="Building Project")
        project.status = ProjectStatus.GRAPH_BUILDING
        ProjectManager.save_project(project)

        with pytest.raises(GraphValidationError, match="déjà en cours"):
            OntologyEventService.regenerate_on_demand(project_id=project.project_id)


class TestProjectOntologyApi:
    def test_get_project_ontology_404_not_found(self, client):
        resp = client.get("/api/project/proj_missing/ontology")
        assert resp.status_code == 404

    def test_get_project_ontology_404_when_no_ontology(self, client):
        project = ProjectManager.create_project(name="Empty")
        resp = client.get(f"/api/project/{project.project_id}/ontology")
        assert resp.status_code == 404
        assert "Aucune ontologie appliquée" in resp.get_json()["error"]

    def test_get_project_ontology_200_success(self, client):
        project = ProjectManager.create_project(name="With Onto")
        onto = {"entity_types": [{"name": "Citizen"}], "edge_types": []}
        v = OntologyEventService.initialize_ontology(project.project_id, onto)

        resp = client.get(f"/api/project/{project.project_id}/ontology")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["version_id"] == v.version_id
        assert data["entity_types"][0]["name"] == "Citizen"

    def test_post_regenerate_ontology_api_flow(self, client, monkeypatch):
        project = ProjectManager.create_project(name="Regen API")
        ProjectManager.save_extracted_text(project.project_id, "Texte du projet")
        project.simulation_requirement = "Brief initial"
        ProjectManager.save_project(project)

        OntologyEventService.initialize_ontology(
            project.project_id, {"entity_types": [{"name": "Type1"}], "edge_types": []}
        )

        # Mock generator
        from app.services.ontology_generator import OntologyGenerator
        monkeypatch.setattr(
            OntologyGenerator,
            "generate",
            lambda self, document_texts, simulation_requirement, additional_context=None: {
                "entity_types": [{"name": "RegeneratedType"}],
                "edge_types": [],
            },
        )

        resp = client.post(f"/api/project/{project.project_id}/ontology/regenerate")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["entity_types"][0]["name"] == "RegeneratedType"
        assert data["version_id"].startswith("ont_")

    def test_post_documents_triggers_e1_api(self, client, monkeypatch):
        project = ProjectManager.create_project(name="Doc API")
        OntologyEventService.initialize_ontology(
            project.project_id, {"entity_types": [{"name": "Type1"}], "edge_types": []}
        )

        from app.services.ontology_generator import OntologyGenerator
        monkeypatch.setattr(
            OntologyGenerator,
            "generate",
            lambda self, document_texts, simulation_requirement, additional_context=None: {
                "entity_types": [{"name": "Type1"}, {"name": "TypeDoc"}],
                "edge_types": [],
            },
        )

        resp = client.post(
            f"/api/project/{project.project_id}/documents",
            json={"text": "Nouveau contenu documentaire", "filename": "doc2.txt"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["filename"] == "doc2.txt"
        assert len(data["ontology_version"]["entity_types"]) == 2

    def test_patch_brief_api_ge_95_no_regen(self, client):
        project = ProjectManager.create_project(name="Brief API")
        project.simulation_requirement = "Brief text exact 12345"
        ProjectManager.save_project(project)
        OntologyEventService.initialize_ontology(
            project.project_id, {"entity_types": [{"name": "T1"}], "edge_types": []}
        )

        resp = client.patch(
            f"/api/project/{project.project_id}/brief",
            json={"simulation_requirement": "Brief text exact 12345"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["regenerated"] is False
        assert data["ontology_version"] is None

    def test_warnings_api_includes_applied_ontology_id(self, client, monkeypatch):
        project = ProjectManager.create_project(name="Warnings API")
        project.graph_id = "graph_warn"
        ProjectManager.save_project(project)

        onto_v1 = {"entity_types": [{"name": "DeclaredType"}], "edge_types": []}
        fake_store = FakeOntologyGraphStore()
        v = OntologyEventService.initialize_ontology(project.project_id, onto_v1, store=fake_store)

        fake_store.warnings[project.graph_id] = [
            GraphValidationWarning(
                graph_id=project.graph_id,
                attempted_type="UnknownType",
                node_uuid="node_123",
                source_call="add_episode",
                message="Type inconnu",
                timestamp="2026-10-14T10:00:00Z",
                policy="downgrade",
                applied_ontology_id=None,
            )
        ]

        import app.api.project as api_proj
        import app.services.ontology_policy as svc_policy
        monkeypatch.setattr(api_proj, "get_graph_store", lambda: fake_store)
        monkeypatch.setattr(svc_policy, "get_graph_store", lambda: fake_store)

        resp = client.get(f"/api/project/{project.project_id}/ontology/warnings")
        assert resp.status_code == 200
        warnings = resp.get_json()["data"]
        assert len(warnings) == 1
        assert warnings[0]["attempted_type"] == "UnknownType"
        # AC6 : applied_ontology_id rattaché
        assert warnings[0]["applied_ontology_id"] == v.version_id
