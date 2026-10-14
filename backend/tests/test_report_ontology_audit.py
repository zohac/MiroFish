"""Tests unitaires et hermétiques pour l'audit d'ontologie appliquée dans le rapport et l'outil LLM (Story 007-6, AC1-AC8)."""

import json
from unittest.mock import MagicMock, patch
import pytest

from app import create_app
from app.models.ontology_version import (
    OntologyEdgeType,
    OntologyEntityType,
    OntologyVersion,
    OntologyVersionStore,
)
from app.models.project import Project, ProjectManager, ProjectStatus
from app.models.source_document import InformationOrigin
from app.services.ontology_events import OntologyEventService
from app.services.report_agent import ReportAgent
from app.utils.graph_store.base import (
    AppliedOntology,
    GraphEdge,
    GraphNode,
    GraphStore,
    GraphValidationWarning,
)


@pytest.fixture
def clean_env(tmp_path, monkeypatch):
    """Environnement isolé avec dossier temporaire pour uploads et projets."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    projects_dir = upload_dir / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    ontologies_dir = upload_dir / "ontologies"
    ontologies_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("app.config.Config.UPLOAD_FOLDER", str(upload_dir))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr(OntologyVersionStore, "get_storage_dir", classmethod(lambda cls: str(ontologies_dir)))
    return tmp_path


@pytest.fixture
def app(clean_env):
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _create_sample_version(project_id: str, version_id: str = "ont_a3f9c2d8e1b7") -> OntologyVersion:
    return OntologyVersion(
        version_id=version_id,
        project_id=project_id,
        entity_types=(
            OntologyEntityType(
                name="PersonEntity",
                description="Citoyen ou usager type du domaine",
                attributes=("name", "role"),
                source=InformationOrigin.DOCUMENTARY,
            ),
            OntologyEntityType(
                name="MediaOrganization",
                description="Organe de presse, régulateur",
                attributes=("name", "jurisdiction"),
                source=InformationOrigin.DOCUMENTARY,
            ),
            OntologyEntityType(
                name="RegulatoryDecision",
                description="Décision ou sanction d'un régulateur",
                attributes=("title", "severity"),
                source=InformationOrigin.HYPOTHESIS,
            ),
        ),
        edge_types=(
            OntologyEdgeType(
                name="REGULATES",
                source_types=("MediaOrganization",),
                target_types=("PersonEntity",),
                description="Encadrement ou régulation",
            ),
        ),
        created_at="2026-10-14T14:22:00Z",
        source_summary="brief + 2 documents",
    )


# --- AC1 : Sous-section « Ontologie appliquée » dans le rapport ---

def test_report_agent_build_sources_provenance_section_includes_ontology(clean_env):
    """AC1 (FR-6, C7) : Vérifie la présence et la structure exacte de la sous-section 6."""
    project = ProjectManager.create_project(name="Project Typé")
    project.graph_id = "graph_typed_1"
    project.strict_ontology = False
    
    version = _create_sample_version(project.project_id)
    OntologyVersionStore.save(version)
    project.applied_ontology_id = version.version_id
    project.applied_ontology_version = 1
    ProjectManager.save_project(project)

    mock_zep = MagicMock()
    # Mock des nœuds renvoyés par zep_tools
    node1 = MagicMock()
    node1.labels = ["Entity", "PersonEntity"]
    node2 = MagicMock()
    node2.labels = ["Entity", "MediaOrganization"]
    mock_zep.get_all_nodes.return_value = [node1, node2]

    # Mock des arêtes
    edge1 = MagicMock()
    edge1.name = "REGULATES"
    mock_zep.get_all_edges.return_value = [edge1]

    agent = ReportAgent(
        graph_id=project.graph_id,
        simulation_id="sim_typed_1",
        simulation_requirement="Tester l'impact",
        zep_tools=mock_zep,
    )

    section = agent.build_sources_provenance_section()

    assert "### 6. Ontologie appliquée (Epic 007, FR-6)" in section
    assert "| Type d'entité | Description | Origine | Compte |" in section
    assert "| `PersonEntity` | Citoyen ou usager type du domaine | documentary | 1 |" in section
    assert "| `MediaOrganization` | Organe de presse, régulateur | documentary | 1 |" in section
    assert "| `RegulatoryDecision` | Décision ou sanction d'un régulateur | hypothesis | 0 |" in section

    assert "| Type de relation | Source | Cible | Description | Compte |" in section
    assert "| `REGULATES` | `MediaOrganization` | `PersonEntity` | Encadrement ou régulation | 1 |" in section

    assert f"**Version d'ontologie appliquée** : `{version.version_id}` (créée le 2026-10-14T14:22:00Z, source : brief + 2 documents)." in section
    assert "**Politique de validation** : mode permissif (avertissement + rétrogradation). 0 avertissement(s) actif(s)." in section


def test_report_agent_build_sources_provenance_strict_policy(clean_env):
    """AC1 : Vérifie le libellé de la politique strict dans la sous-section 6."""
    project = ProjectManager.create_project(name="Project Strict")
    project.graph_id = "graph_strict_1"
    project.strict_ontology = True

    version = _create_sample_version(project.project_id)
    OntologyVersionStore.save(version)
    project.applied_ontology_id = version.version_id
    ProjectManager.save_project(project)

    mock_zep = MagicMock()
    mock_zep.get_all_nodes.return_value = []
    mock_zep.get_all_edges.return_value = []

    agent = ReportAgent(
        graph_id=project.graph_id,
        simulation_id="sim_strict_1",
        simulation_requirement="Tester l'impact",
        zep_tools=mock_zep,
    )

    section = agent.build_sources_provenance_section()
    assert "**Politique de validation** : mode strict (rejet des types non déclarés). 0 avertissement(s) actif(s)." in section


# --- AC2 : Absence conditionnelle stricte ---

def test_report_agent_omits_ontology_section_when_no_applied_ontology(clean_env):
    """AC2 (C7) : Vérifie que la sous-section 6 est strictement absente sans ontologie appliquée."""
    project = ProjectManager.create_project(name="Projet Ancien Sans Ontologie")
    project.graph_id = "graph_legacy_1"
    project.applied_ontology_id = None
    ProjectManager.save_project(project)

    agent = ReportAgent(
        graph_id=project.graph_id,
        simulation_id="sim_legacy_1",
        simulation_requirement="Tester sans ontologie",
    )

    section = agent.build_sources_provenance_section()

    # Sous-sections 1 à 5 présentes
    assert "### 1. Typologie stricte des 5 origines d'information" in section
    assert "### 2. Documents sources et statut de validation" in section
    assert "### 3. Traçabilité des actions observées et contrôle anti-affabulation (C7)" in section
    assert "### 4. Contradictions documentaires et statut de résolution" in section
    assert "### 5. Diagnostics de contexte et étanchéité des consignes (NFR-5)" in section

    # Sous-section 6 strictement absente
    assert "### 6. Ontologie appliquée" not in section
    assert "Version d'ontologie appliquée" not in section


def test_report_agent_omits_ontology_section_when_no_project(clean_env):
    """AC2 : Vérifie l'omission gracieuse si aucun projet n'est trouvé."""
    agent = ReportAgent(
        graph_id="graph_unknown_orphan",
        simulation_id="sim_orphan",
        simulation_requirement="Tester orphelin",
    )

    section = agent.build_sources_provenance_section()
    assert "### 6. Ontologie appliquée" not in section
    assert "### 1. Typologie stricte des 5 origines d'information" in section


# --- AC3 : Définition de l'outil LLM get_applied_ontology ---

def test_report_agent_tools_definition_includes_get_applied_ontology():
    """AC3 (FR-6) : Vérifie que ReportAgent._define_tools déclare l'outil get_applied_ontology."""
    agent = ReportAgent(
        graph_id="g_test",
        simulation_id="sim_test",
        simulation_requirement="Tester l'outil",
    )
    tools = agent._define_tools()
    assert "get_applied_ontology" in tools
    tool = tools["get_applied_ontology"]
    assert tool["name"] == "get_applied_ontology"
    assert "description" in tool and len(tool["description"]) > 10
    assert "parameters" in tool
    params = tool["parameters"]
    assert "include_counts" in params
    assert "since" in params


# --- AC4 : Exécution robuste de l'outil LLM dans _execute_tool ---

def test_execute_tool_get_applied_ontology_success(clean_env):
    """AC4 (FR-6) : Vérifie l'exécution nominale de get_applied_ontology avec format JSON attendu."""
    project = ProjectManager.create_project(name="Project Exec")
    project.graph_id = "graph_exec_1"
    version = _create_sample_version(project.project_id)
    OntologyVersionStore.save(version)
    project.applied_ontology_id = version.version_id
    ProjectManager.save_project(project)

    mock_zep = MagicMock()
    n1 = MagicMock()
    n1.labels = ["Entity", "PersonEntity"]
    mock_zep.get_all_nodes.return_value = [n1, n1]  # 2 PersonEntity
    mock_zep.get_all_edges.return_value = []

    agent = ReportAgent(
        graph_id=project.graph_id,
        simulation_id="sim_exec_1",
        simulation_requirement="Requirement",
        zep_tools=mock_zep,
    )

    res_raw = agent._execute_tool("get_applied_ontology", {"include_counts": True})
    data = json.loads(res_raw)

    assert data["status"] == "applied"
    assert data["version_id"] == version.version_id
    assert data["created_at"] == version.created_at
    assert data["source_summary"] == "brief + 2 documents"
    assert data["policy"]["strict_ontology"] is False
    assert data["policy"]["warnings_count"] == 0

    assert len(data["entity_types"]) == 3
    person_type = next(t for t in data["entity_types"] if t["name"] == "PersonEntity")
    assert person_type["count"] == 2
    assert person_type["source"] == "documentary"
    assert person_type["attributes"] == ["name", "role"]

    assert len(data["edge_types"]) == 1
    rel_type = data["edge_types"][0]
    assert rel_type["name"] == "REGULATES"
    assert rel_type["count"] == 0
    assert rel_type["source_types"] == ["MediaOrganization"]
    assert rel_type["target_types"] == ["PersonEntity"]


def test_execute_tool_get_applied_ontology_without_counts(clean_env):
    """AC4 : Vérifie que include_counts=False omet les champs 'count'."""
    project = ProjectManager.create_project(name="Project No Counts")
    project.graph_id = "graph_no_counts"
    version = _create_sample_version(project.project_id)
    OntologyVersionStore.save(version)
    project.applied_ontology_id = version.version_id
    ProjectManager.save_project(project)

    agent = ReportAgent(
        graph_id=project.graph_id,
        simulation_id="sim_no_counts",
        simulation_requirement="Requirement",
    )

    res_raw = agent._execute_tool("get_applied_ontology", {"include_counts": False})
    data = json.loads(res_raw)
    assert data["status"] == "applied"
    assert "count" not in data["entity_types"][0]
    assert "count" not in data["edge_types"][0]


def test_execute_tool_get_applied_ontology_no_ontology(clean_env):
    """AC4 : Vérifie la réponse gracieuse quand aucune ontologie n'est appliquée."""
    project = ProjectManager.create_project(name="Project Sans Onto")
    project.graph_id = "graph_empty_1"
    ProjectManager.save_project(project)

    agent = ReportAgent(
        graph_id=project.graph_id,
        simulation_id="sim_empty_1",
        simulation_requirement="Requirement",
    )

    res_raw = agent._execute_tool("get_applied_ontology", {})
    data = json.loads(res_raw)
    assert data["status"] == "no_ontology_applied"
    assert "message" in data


def test_execute_tool_get_applied_ontology_missing_version_file(clean_env):
    """AC4 : Vérifie la robustesse si l'identifiant pointe sur une version inexistante."""
    project = ProjectManager.create_project(name="Project Fichier Perdu")
    project.graph_id = "graph_lost_1"
    project.applied_ontology_id = "ont_inexistant12"
    ProjectManager.save_project(project)

    agent = ReportAgent(
        graph_id=project.graph_id,
        simulation_id="sim_lost_1",
        simulation_requirement="Requirement",
    )

    res_raw = agent._execute_tool("get_applied_ontology", {})
    data = json.loads(res_raw)
    assert data["status"] == "no_ontology_applied"
    assert "introuvable" in data["message"]


# --- AC5 : Comptage tolérant aux pannes ---

def test_ontology_instance_counts_resilience_on_store_exception(clean_env):
    """AC5 (NFR-4) : En cas d'erreur de requête ou store inaccessible, décompte retombe à 0 sans bloquer."""
    mock_zep = MagicMock()
    mock_zep.get_all_nodes.side_effect = RuntimeError("Neo4j database connection lost")
    mock_zep.get_all_edges.side_effect = ConnectionError("Connection refused")

    agent = ReportAgent(
        graph_id="g_fail",
        simulation_id="sim_fail",
        simulation_requirement="Req",
        zep_tools=mock_zep,
    )

    entity_counts, edge_counts = agent._get_ontology_instance_counts("g_fail")
    assert entity_counts == {}
    assert edge_counts == {}


def test_report_generation_proceeds_even_when_counts_fail(clean_env):
    """AC5 : Vérifie que build_sources_provenance_section n'échoue pas si le décompte échoue."""
    project = ProjectManager.create_project(name="Project Crash Store")
    project.graph_id = "graph_crash_1"
    version = _create_sample_version(project.project_id)
    OntologyVersionStore.save(version)
    project.applied_ontology_id = version.version_id
    ProjectManager.save_project(project)

    mock_zep = MagicMock()
    mock_zep.get_all_nodes.side_effect = Exception("Store unavailable")
    mock_zep.get_all_edges.side_effect = Exception("Store unavailable")

    agent = ReportAgent(
        graph_id=project.graph_id,
        simulation_id="sim_crash_1",
        simulation_requirement="Req",
        zep_tools=mock_zep,
    )

    section = agent.build_sources_provenance_section()
    assert "### 6. Ontologie appliquée (Epic 007, FR-6)" in section
    # Compte retombe à 0
    assert "| `PersonEntity` | Citoyen ou usager type du domaine | documentary | 0 |" in section


# --- AC6 : Étanchéité des consignes et séparation des données ---

def test_ontology_metadata_not_in_system_prompt():
    """AC6 (NFR-5) : Vérifie que les données d'ontologie ne s'échappent pas dans les consignes système."""
    agent = ReportAgent(
        graph_id="g_test",
        simulation_id="sim_test",
        simulation_requirement="Impact d'une régulation",
    )
    tools_desc = agent._get_tools_description()
    # get_applied_ontology est un outil, sa description est présente
    assert "get_applied_ontology" in tools_desc
    # Mais aucune donnée d'instance ni règle métier n'est injectée comme consigne
    assert "SYSTEM INSTRUCTION" not in tools_desc


# --- AC7 : Exposition API pour l'audit et l'IHM ---

def test_api_get_project_ontology_with_policy_and_stats(client, clean_env):
    """AC7 (PRD Q4) : Vérifie que l'endpoint GET /api/project/<id>/ontology expose version, politique et statistiques."""
    project = ProjectManager.create_project(name="Projet API Audit")
    project.graph_id = "graph_api_audit_1"
    project.strict_ontology = True

    version = _create_sample_version(project.project_id)
    OntologyVersionStore.save(version)
    project.applied_ontology_id = version.version_id
    ProjectManager.save_project(project)

    fake_store = MagicMock()
    n = MagicMock()
    n.labels = ["Entity", "PersonEntity"]
    fake_store.get_all_nodes.return_value = [n, n, n]
    e = MagicMock()
    e.name = "REGULATES"
    e.relation_type = "REGULATES"
    fake_store.get_all_edges.return_value = [e]

    with patch("app.api.project.get_graph_store", return_value=fake_store):
        # 1. Appel sans include_counts
        resp = client.get(f"/api/project/{project.project_id}/ontology")
        assert resp.status_code == 200
        res = resp.get_json()
        assert res["success"] is True
        data = res["data"]
        assert data["version_id"] == version.version_id
        assert data["policy"]["strict_ontology"] is True
        assert data["policy"]["warnings_count"] == 0

        # 2. Appel avec include_counts=true
        resp_counts = client.get(f"/api/project/{project.project_id}/ontology?include_counts=true")
        assert resp_counts.status_code == 200
        data_counts = resp_counts.get_json()["data"]
        assert "statistics" in data_counts
        assert data_counts["statistics"]["entity_counts"]["PersonEntity"] == 3
        assert data_counts["statistics"]["edge_counts"]["REGULATES"] == 1
        assert data_counts["statistics"]["total_nodes"] == 3
        assert data_counts["statistics"]["total_edges"] == 1


def test_api_get_project_ontology_404_not_found(client, clean_env):
    """AC7 : Vérifie la 404 sur projet inexistant."""
    resp = client.get("/api/project/proj_non_existent/ontology")
    assert resp.status_code == 404
    assert resp.get_json()["success"] is False


def test_api_get_project_ontology_404_when_no_ontology(client, clean_env):
    """AC7 : Vérifie la 404 sur projet existant mais sans ontologie appliquée."""
    project = ProjectManager.create_project(name="Projet Sans Onto")
    resp = client.get(f"/api/project/{project.project_id}/ontology")
    assert resp.status_code == 404
    assert "Aucune ontologie appliquée" in resp.get_json()["error"]


# --- Tests de régression issus de la revue BMAD contradictoire (Patches 1, 2, 3) ---

def test_parse_tool_calls_bare_json_get_applied_ontology():
    """BMAD Patch 1 : Vérifie que get_applied_ontology est reconnu en mode JSON brut par _parse_tool_calls."""
    agent = ReportAgent(
        graph_id="g_test",
        simulation_id="sim_test",
        simulation_requirement="Tester parse tool call",
    )
    raw_response = '{"name": "get_applied_ontology", "parameters": {"include_counts": true}}'
    tool_calls = agent._parse_tool_calls(raw_response)
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "get_applied_ontology"
    assert tool_calls[0]["parameters"]["include_counts"] is True


def test_api_get_project_ontology_include_counts_without_graph_id(client, clean_env):
    """BMAD Patch 2 : Vérifie que ?include_counts=true initialise statistics même si project.graph_id est None."""
    project = ProjectManager.create_project(name="Projet Sans GraphId")
    project.graph_id = None

    version = _create_sample_version(project.project_id)
    OntologyVersionStore.save(version)
    project.applied_ontology_id = version.version_id
    ProjectManager.save_project(project)

    resp = client.get(f"/api/project/{project.project_id}/ontology?include_counts=true")
    assert resp.status_code == 200
    res = resp.get_json()
    assert res["success"] is True
    data = res["data"]
    assert "statistics" in data
    assert data["statistics"]["total_nodes"] == 0
    assert data["statistics"]["total_edges"] == 0
    assert data["statistics"]["entity_counts"] == {}
    assert data["statistics"]["edge_counts"] == {}


def test_report_agent_table_description_pipe_and_newline_escaping(clean_env):
    """BMAD Patch 3 : Vérifie l'échappement des pipes et retours à la ligne dans les descriptions des tableaux."""
    project = ProjectManager.create_project(name="Projet Pipe Escape")
    project.graph_id = "graph_pipe_1"

    version = OntologyVersion(
        version_id="ont_pipe123456",
        project_id=project.project_id,
        entity_types=(
            OntologyEntityType(
                name="PipeEntity",
                description="Ligne 1\nLigne 2 | avec pipe",
                attributes=("attr1",),
                source=InformationOrigin.DOCUMENTARY,
            ),
        ),
        edge_types=(
            OntologyEdgeType(
                name="PIPE_REL",
                source_types=("PipeEntity",),
                target_types=("PipeEntity",),
                description="Relation | avec pipe\net saut",
            ),
        ),
        created_at="2026-10-14T14:30:00Z",
        source_summary="brief test",
    )
    OntologyVersionStore.save(version)
    project.applied_ontology_id = version.version_id
    ProjectManager.save_project(project)

    mock_zep = MagicMock()
    mock_zep.get_all_nodes.return_value = []
    mock_zep.get_all_edges.return_value = []

    agent = ReportAgent(
        graph_id=project.graph_id,
        simulation_id="sim_pipe_1",
        simulation_requirement="Tester échappement",
        zep_tools=mock_zep,
    )

    section = agent.build_sources_provenance_section()
    assert "### 6. Ontologie appliquée (Epic 007, FR-6)" in section
    # Vérifie que le pipe est échappé et le saut de ligne converti en espace
    assert "| `PipeEntity` | Ligne 1 Ligne 2 \\| avec pipe | documentary | 0 |" in section
    assert "| `PIPE_REL` | `PipeEntity` | `PipeEntity` | Relation \\| avec pipe et saut | 0 |" in section

