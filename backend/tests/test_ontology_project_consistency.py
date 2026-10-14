"""Tests hermétiques pour la cohérence projet C5, événement E5 et isolation inter-projets (Story 007-5, AC1, AC2)."""

import json
from pathlib import Path
import pytest

from app.config import Config
from app.models.actor_eligibility import ActorEligibility, ActorRole, EligibilityStatus
from app.models.ontology_version import OntologyVersion, OntologyVersionStore
from app.models.project import Project, ProjectManager, ProjectStatus
from app.services.actor_classifier import ActorClassificationResult
from app.services.simulation_config_generator import SimulationParameters
from app.services.simulation_manager import SimulationManager
from app.services.zep_entity_reader import EntityNode
from app.utils.graph_store.base import GraphStore
from app.utils.graph_store.factory import override_graph_store


class MemoryGraphStore(GraphStore):
    """Store factice en mémoire sans réseau."""

    def __init__(self, nodes=None, edges=None):
        self._nodes = nodes or []
        self._edges = edges or []

    def create_graph(self, name, graph_id=None):
        return graph_id or "mem-graph"

    def delete_graph(self, graph_id):
        pass

    def get_graph_info(self, graph_id):
        from app.utils.graph_store.base import GraphInfo
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
        from app.utils.graph_store.base import GraphSearchResult
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

    def set_ontology(self, graph_id, entity_types, edge_types, strict=False):
        pass

    def add_episode(self, graph_id, name, content="", source="text", source_description="", episode_type="text", metadata=None, created_at=None, ontology=None):
        return "ep-uuid"

    def add_text_batch(self, graph_id, episodes_data):
        return None

    def wait_for_batch(self, graph_id, batch_id, timeout=30.0, poll_interval=0.5):
        return None

    def wait_for_episodes(self, graph_id, episode_uuids, timeout=30.0, poll_interval=0.5):
        return None


class FakeClassifier:
    """Classifieur factice renvoyant une qualification déterministe."""

    def __init__(self, mapping):
        self.mapping = mapping

    def classify_entities(self, entities, *args, **kwargs):
        qualifications = []
        for ent in entities:
            role, status, rationale = self.mapping.get(
                ent.uuid, (ActorRole.PERSON, EligibilityStatus.ELIGIBLE, "ok")
            )
            qualifications.append(
                ActorEligibility(
                    entity_uuid=ent.uuid,
                    entity_name=ent.name,
                    role=role,
                    status=status,
                    rationale=rationale,
                    confidence=1.0,
                    original_type=getattr(ent, "labels", ["Entity"])[-1],
                )
            )
        return ActorClassificationResult(qualifications=qualifications, diagnostics={})


class StubSimulationConfigGenerator:
    """Générateur factice de configuration en mémoire hors réseau (Story 007-5, AC1, C5)."""

    def generate_config(self, **kwargs):
        return SimulationParameters(
            simulation_id=kwargs.get("simulation_id", "sim-stub"),
            project_id=kwargs.get("project_id", "proj-stub"),
            graph_id=kwargs.get("graph_id", "graph-stub"),
            simulation_requirement=kwargs.get("simulation_requirement", ""),
            applied_ontology_id=kwargs.get("applied_ontology_id"),
            generation_reasoning="stub hermétique sans appel LLM",
        )


# ==============================================================================
# AC1 : Cohérence projet (C5) et événement E5
# ==============================================================================


def test_simulation_parameters_serialization_contains_applied_ontology_id():
    """AC1 : SimulationParameters sérialise et désérialise applied_ontology_id."""
    params = SimulationParameters(
        simulation_id="sim-test-1",
        project_id="proj-1",
        graph_id="graph-1",
        simulation_requirement="Tester l'adoption",
        applied_ontology_id="ont_abc123456789",
    )
    d = params.to_dict()
    assert d["applied_ontology_id"] == "ont_abc123456789"

    js = params.to_json()
    parsed = json.loads(js)
    assert parsed["applied_ontology_id"] == "ont_abc123456789"


def test_prepare_simulation_attaches_project_applied_ontology_id(tmp_path, monkeypatch):
    """AC1 & E5 : prepare_simulation lie de façon stable project.applied_ontology_id à la simulation."""
    import app.services.simulation_manager as sim_manager_module
    monkeypatch.setattr(sim_manager_module, "SimulationConfigGenerator", StubSimulationConfigGenerator)

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    simulations_dir = tmp_path / "simulations"
    simulations_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(simulations_dir))

    project = ProjectManager.create_project(name="Projet Cohérence")
    project_id = project.project_id
    applied_onto_id = "ont_stable12345"
    project.simulation_requirement = "Consigne stable"
    project.graph_id = "graph-ac1"
    project.status = ProjectStatus.GRAPH_COMPLETED
    project.applied_ontology_id = applied_onto_id
    project.applied_ontology_version = 1
    ProjectManager.save_project(project)

    nodes = [
        EntityNode(
            uuid="u-1",
            name="Alice",
            labels=["Entity", "PersonEntity"],
            summary="Citoyenne",
            attributes={},
        ),
        EntityNode(
            uuid="u-2",
            name="Bob",
            labels=["Entity", "Citizen"],
            summary="Citoyen",
            attributes={},
        ),
    ]
    store = MemoryGraphStore(nodes=nodes)

    classifier = FakeClassifier({
        "u-1": (ActorRole.PERSON, EligibilityStatus.ELIGIBLE, "Alice ok"),
        "u-2": (ActorRole.PERSON, EligibilityStatus.ELIGIBLE, "Bob ok"),
    })

    manager = SimulationManager()

    with override_graph_store(store):
        # Première simulation
        sim_state_1 = manager.create_simulation(project_id=project_id, graph_id="graph-ac1")
        prep_1 = manager.prepare_simulation(
            simulation_id=sim_state_1.simulation_id,
            simulation_requirement="Consigne stable",
            document_text="Contenu texte",
            use_llm_for_profiles=False,
            classifier=classifier,
        )

        # Deuxième simulation (sans aucun événement modificateur E1/E2/E3)
        sim_state_2 = manager.create_simulation(project_id=project_id, graph_id="graph-ac1")
        prep_2 = manager.prepare_simulation(
            simulation_id=sim_state_2.simulation_id,
            simulation_requirement="Consigne stable",
            document_text="Contenu texte",
            use_llm_for_profiles=False,
            classifier=classifier,
        )

    # Vérification AC1 / E5 : Les 2 simulations partagent exactement le même applied_ontology_id
    assert prep_1.applied_ontology_id == applied_onto_id
    assert prep_2.applied_ontology_id == applied_onto_id
    assert prep_1.applied_ontology_id == prep_2.applied_ontology_id

    # Vérification que le fichier de config simulation_config.json porte applied_ontology_id
    sim_dir_1 = simulations_dir / prep_1.simulation_id
    sim_dir_2 = simulations_dir / prep_2.simulation_id

    cfg_1 = json.loads((sim_dir_1 / "simulation_config.json").read_text(encoding="utf-8"))
    cfg_2 = json.loads((sim_dir_2 / "simulation_config.json").read_text(encoding="utf-8"))

    assert cfg_1["applied_ontology_id"] == applied_onto_id
    assert cfg_2["applied_ontology_id"] == applied_onto_id
    assert cfg_1["applied_ontology_id"] == cfg_2["applied_ontology_id"]


# ==============================================================================
# AC2 : Isolation stricte inter-projets (C5)
# ==============================================================================


def test_inter_project_ontology_isolation(tmp_path, monkeypatch):
    """AC2 : Deux projets distincts possèdent des ontologies indépendantes avec applied_ontology_id hermétiques."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    simulations_dir = tmp_path / "simulations"
    simulations_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(simulations_dir))
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

    # Projet A (Santé)
    proj_a = ProjectManager.create_project(name="Projet Santé")
    proj_a_id = proj_a.project_id
    ver_a = OntologyVersionStore.create(
        project_id=proj_a_id,
        ontology_dict={
            "entity_types": [{"name": "Doctor", "description": "Médecin"}],
            "edge_types": [{"name": "TREATS", "description": "Soigne"}],
        },
        source_summary="E4_project_created",
    )
    proj_a.status = ProjectStatus.GRAPH_COMPLETED
    proj_a.simulation_requirement = "Étudier l'accès aux soins"
    proj_a.graph_id = "graph-sante"
    proj_a.applied_ontology_id = ver_a.version_id
    proj_a.applied_ontology_version = 1
    ProjectManager.save_project(proj_a)

    # Projet B (Énergie)
    proj_b = ProjectManager.create_project(name="Projet Énergie")
    proj_b_id = proj_b.project_id
    ver_b = OntologyVersionStore.create(
        project_id=proj_b_id,
        ontology_dict={
            "entity_types": [{"name": "PowerPlant", "description": "Centrale électrique"}],
            "edge_types": [{"name": "SUPPLIES", "description": "Alimente"}],
        },
        source_summary="E4_project_created",
    )
    proj_b.status = ProjectStatus.GRAPH_COMPLETED
    proj_b.simulation_requirement = "Transition énergétique"
    proj_b.graph_id = "graph-energie"
    proj_b.applied_ontology_id = ver_b.version_id
    proj_b.applied_ontology_version = 1
    ProjectManager.save_project(proj_b)

    # Vérification de l'étanchéité des versions
    assert ver_a.version_id != ver_b.version_id
    assert proj_a.applied_ontology_id != proj_b.applied_ontology_id

    # Une modification sur projet A (ex: nouvelle version d'ontologie A) n'affecte pas B
    ver_a2 = OntologyVersionStore.create(
        project_id=proj_a_id,
        ontology_dict={
            "entity_types": [
                {"name": "Doctor", "description": "Médecin"},
                {"name": "Patient", "description": "Patient"},
            ],
            "edge_types": [{"name": "TREATS", "description": "Soigne"}],
        },
        parent_version_id=ver_a.version_id,
        source_summary="E1_document_added",
    )
    proj_a.applied_ontology_id = ver_a2.version_id
    proj_a.applied_ontology_version = 2
    ProjectManager.save_project(proj_a)

    # Recharger les projets depuis le disque
    reloaded_a = ProjectManager.get_project(proj_a_id)
    reloaded_b = ProjectManager.get_project(proj_b_id)

    assert reloaded_a.applied_ontology_id == ver_a2.version_id
    assert reloaded_a.applied_ontology_version == 2
    # Projet B est rigoureusement intact
    assert reloaded_b.applied_ontology_id == ver_b.version_id
    assert reloaded_b.applied_ontology_version == 1

    # Les magasins de versions sont strictement séparés
    versions_a = OntologyVersionStore.list_for_project(proj_a_id)
    versions_b = OntologyVersionStore.list_for_project(proj_b_id)
    assert len(versions_a) == 2
    assert len(versions_b) == 1
    assert [v.version_id for v in versions_b] == [ver_b.version_id]
