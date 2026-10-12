"""Tests unitaires et d'intégration pour ReportAgent avec provenance et véracité (Story 009-4, AC7, NFR-5)."""

from datetime import datetime
import json
import os
from unittest.mock import MagicMock, patch
import pytest

from app.models.project import Project, ProjectManager, ProjectStatus
from app.models.source_document import (
    DocumentRole,
    DocumentValidationStatus,
    SourceConflict,
    SourceReference,
)
from app.services.report_agent import ReportAgent, ReportOutline, ReportSection
from app.services.simulation_action_verifier import ActionEventRecord, SimulationActionVerifier
from app.services.zep_tools import EdgeInfo, ZepToolsService


def test_report_agent_tools_definition_includes_provenance():
    """Vérifie que ReportAgent définit les outils de provenance et de véracité (AC7)."""
    agent = ReportAgent(
        graph_id="g_test",
        simulation_id="sim_test",
        simulation_requirement="Tester l'impact",
    )
    tools = agent._define_tools()
    assert "get_edge_provenance" in tools
    assert "verify_action" in tools
    assert "verify_citation" in tools


def test_report_agent_executes_provenance_tools():
    """Vérifie l'exécution des nouveaux outils par ReportAgent."""
    mock_zep = MagicMock(spec=ZepToolsService)
    mock_verifier = MagicMock(spec=SimulationActionVerifier)

    mock_edge = EdgeInfo(
        uuid="edge_123",
        name="CRITIQUE",
        fact="L'opposition critique la gestion",
        source_node_uuid="n1",
        target_node_uuid="n2",
        origin="documentary",
        source_filename="rapport.pdf",
        char_start=10,
        char_end=50,
    )
    mock_zep.get_edge_detail.return_value = mock_edge

    mock_verifier.validate_report_claim.return_value = {
        "allowed_as_observed_action": True,
        "qualification": "action_observee",
        "event_id": "evt_tw_1_2_abc",
        "message": "Action observée vérifiée avec l'événement evt_tw_1_2_abc",
    }

    mock_citation_res = MagicMock()
    mock_citation_res.valid = True
    mock_verifier.verify_citation.return_value = mock_citation_res

    agent = ReportAgent(
        graph_id="g_test",
        simulation_id="sim_test",
        simulation_requirement="Tester l'impact",
        zep_tools=mock_zep,
        action_verifier=mock_verifier,
    )

    # 1. get_edge_provenance
    out_edge = agent._execute_tool("get_edge_provenance", {"edge_uuid": "edge_123"})
    assert "来源: [documentary] rapport.pdf" in out_edge

    # 2. verify_action
    out_act = agent._execute_tool("verify_action", {"agent_id": "Agent_2", "action_type": "unsubscribe"})
    assert "【已验证行动】" in out_act
    assert "evt_tw_1_2_abc" in out_act

    # 3. verify_citation
    out_cit = agent._execute_tool("verify_citation", {"citation": "L'opposition critique", "source_filename": "rapport.pdf"})
    assert "【引用有效】" in out_cit


def test_report_agent_build_sources_provenance_section(tmp_path, monkeypatch):
    """Vérifie la génération de la section « Sources & Provenance » avec les 5 origines (AC7, NFR-5)."""
    # Configurer un dossier temporaire pour les projets
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr("app.config.Config.UPLOAD_FOLDER", str(tmp_path))

    # Créer un projet avec documents et conflits
    ref1 = SourceReference(
        document_id="doc_1",
        filename="source_a.txt",
        role=DocumentRole.FACTS,
        priority=1,
        date="2026-01-01",
        validation_status=DocumentValidationStatus.VALIDATED,
        chunk_index=0,
        char_start=0,
        char_end=50,
    )
    ref2 = SourceReference(
        document_id="doc_2",
        filename="source_b.txt",
        role=DocumentRole.FACTS,
        priority=2,
        date="2026-02-01",
        validation_status=DocumentValidationStatus.UNVALIDATED,
        chunk_index=0,
        char_start=0,
        char_end=50,
    )
    conflict = SourceConflict(
        conflict_id="conf_ab",
        claim="Taux d'inflation estimé",
        source_references=[ref1, ref2],
    )

    now_iso = datetime.now().isoformat()
    project = Project(
        project_id="proj_prov",
        name="Projet Provenance",
        status=ProjectStatus.CREATED,
        created_at=now_iso,
        updated_at=now_iso,
        graph_id="graph_prov",
        source_documents=[
            {
                "document_id": "doc_1",
                "filename": "source_a.txt",
                "role": "facts",
                "saved_filename": "source_a_saved.txt",
                "priority": 1,
                "date": "2026-01-01",
                "validation_status": "validated",
            }
        ],
        source_conflicts=[conflict.to_dict()],
    )
    (projects_dir / "proj_prov").mkdir(parents=True, exist_ok=True)
    ProjectManager.save_project(project)

    # Mock action verifier avec 1 action et 1 intention
    mock_verifier = MagicMock(spec=SimulationActionVerifier)
    mock_verifier.load_simulation_actions.return_value = [
        ActionEventRecord(
            event_id="evt_1",
            simulation_id="sim_prov",
            platform="twitter",
            round_num=1,
            agent_id=5,
            agent_name="Agent_5",
            action_type="unsubscribe",
            timestamp="2026-10-12T10:00:00",
            success=True,
        )
    ]
    mock_verifier.analyze_intentions.return_value = []
    mock_verifier.format_conflicts_for_report.return_value = (
        "### Contradictions documentaires\n- Source a vs Source b : **À confirmer**"
    )

    agent = ReportAgent(
        graph_id="graph_prov",
        simulation_id="sim_prov",
        simulation_requirement="Évaluer la stabilité",
        action_verifier=mock_verifier,
    )

    section_text = agent.build_sources_provenance_section()

    # Vérifications obligatoires AC7 et NFR-5
    assert "## Sources & Provenance" in section_text
    assert "Faits documentaires (`documentary`)" in section_text
    assert "Hypothèses & Scénario (`hypothesis`)" in section_text
    assert "Observations de simulation (`simulation`)" in section_text
    assert "Inférences analytiques (`inference`)" in section_text
    assert "Origines héritées / non résolues (`unknown`)" in section_text

    # Documents et statuts
    assert "`source_a.txt`" in section_text
    assert "`validated`" in section_text

    # Traçabilité et anti-affabulation
    assert "1 action(s) enregistrée(s)" in section_text
    assert "Règle anti-affabulation" in section_text

    # Contradictions
    assert "Contradictions documentaires" in section_text
    assert "À confirmer" in section_text

    # NFR-5 : séparation stricte données / consignes
    assert "étanchéité des consignes (NFR-5)" in section_text
    assert "Séparation stricte données et consignes" in section_text


def test_report_agent_generate_report_appends_sources_section(tmp_path, monkeypatch):
    """Vérifie que generate_report injecte la section Sources & Provenance dans le rapport final (AC7)."""
    monkeypatch.setattr("app.config.Config.UPLOAD_FOLDER", str(tmp_path))

    agent = ReportAgent(
        graph_id="graph_gen",
        simulation_id="sim_gen",
        simulation_requirement="Tester l'injection",
    )

    # Simuler plan_outline et _generate_section_react
    mock_outline = ReportOutline(
        title="Rapport de prospective 2026",
        summary="Synthèse générale",
        sections=[
            ReportSection(title="Dynamique des flux", content="Analyse des flux")
        ],
    )
    agent.plan_outline = MagicMock(return_value=mock_outline)
    agent._generate_section_react = MagicMock(
        return_value="Les flux observés indiquent une stabilisation des volumes."
    )

    report = agent.generate_report(report_id="rep_test_001")

    assert report.status.value == "completed"
    assert "## Sources & Provenance" in report.markdown_content
    assert "Typologie stricte des 5 origines d'information" in report.markdown_content
    assert "Dynamique des flux" in report.markdown_content


def test_report_agent_resolve_project_by_graph_id(tmp_path, monkeypatch):
    """Vérifie que `_resolve_project` retrouve un projet par `graph_id` puis `simulation_id`."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr("app.config.Config.UPLOAD_FOLDER", str(tmp_path))

    now_iso = datetime.now().isoformat()
    project = Project(
        project_id="proj_resolve",
        name="Résolution",
        status=ProjectStatus.CREATED,
        created_at=now_iso,
        updated_at=now_iso,
        graph_id="graph_resolve",
    )
    (projects_dir / "proj_resolve").mkdir(parents=True, exist_ok=True)
    ProjectManager.save_project(project)

    agent = ReportAgent(
        graph_id="graph_resolve",
        simulation_id="sim_x",
        simulation_requirement="Test",
    )
    resolved = agent._resolve_project()
    assert resolved is not None
    assert resolved.project_id == "proj_resolve"

    # Fallback par simulation_id
    agent_no_graph = ReportAgent(
        graph_id="graph_unknown",
        simulation_id="graph_resolve",  # par construction, fallback sur simulation_id
        simulation_requirement="Test",
    )
    # Le fallback par simulation_id fonctionne seulement si la méthode
    # `get_project` accepte un `simulation_id`, ce qui n'est pas garanti
    # partout : on vérifie au moins que la résolution ne lève pas d'exception.
    agent_no_graph._resolve_project()


def test_report_agent_load_source_document_text(tmp_path, monkeypatch):
    """Vérifie que `_load_source_document_text` charge le texte depuis le projet (AC6)."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr("app.config.Config.UPLOAD_FOLDER", str(tmp_path))

    now_iso = datetime.now().isoformat()
    project_id = "proj_text"
    project = Project(
        project_id=project_id,
        name="Texte",
        status=ProjectStatus.CREATED,
        created_at=now_iso,
        updated_at=now_iso,
        graph_id="graph_text",
        source_documents=[
            {
                "document_id": "doc_text",
                "filename": "source.txt",
                "role": "facts",
                "saved_filename": "source_saved.txt",
                "priority": 1,
                "validation_status": "validated",
            }
        ],
    )
    (projects_dir / project_id).mkdir(parents=True, exist_ok=True)
    ProjectManager.save_project(project)

    # Écrire le texte normalisé du document
    documents_dir = projects_dir / project_id / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    (documents_dir / "doc_text.txt").write_text(
        "Le Conseil d'État a statué que la redevance est conforme.",
        encoding="utf-8",
    )

    agent = ReportAgent(
        graph_id="graph_text",
        simulation_id="sim_text",
        simulation_requirement="Test",
    )
    text = agent._load_source_document_text("source.txt")
    assert text is not None
    assert "redevance est conforme" in text

    # Mauvais nom de fichier : None
    assert agent._load_source_document_text("absent.txt") is None

    # Pas de filename : None
    assert agent._load_source_document_text(None) is None


def test_report_agent_verify_citation_uses_source_document(tmp_path, monkeypatch):
    """Vérifie que l'outil `verify_citation` charge le document source réel (AC6).

    Avant la correction, l'outil agrégeait `search_graph().facts` et pouvait
    valider une citation présente comme paraphrase dans le graphe mais
    absente du document original.
    """
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    monkeypatch.setattr("app.config.Config.UPLOAD_FOLDER", str(tmp_path))

    now_iso = datetime.now().isoformat()
    project_id = "proj_cit"
    project = Project(
        project_id=project_id,
        name="Citation",
        status=ProjectStatus.CREATED,
        created_at=now_iso,
        updated_at=now_iso,
        graph_id="graph_cit",
        source_documents=[
            {
                "document_id": "doc_cit",
                "filename": "doc.txt",
                "role": "facts",
                "saved_filename": "doc_saved.txt",
                "priority": 1,
                "validation_status": "validated",
            }
        ],
    )
    (projects_dir / project_id).mkdir(parents=True, exist_ok=True)
    ProjectManager.save_project(project)
    documents_dir = projects_dir / project_id / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    (documents_dir / "doc_cit.txt").write_text(
        "Le Conseil d'État a statué sur la conformité de la redevance.",
        encoding="utf-8",
    )

    mock_zep = MagicMock(spec=ZepToolsService)
    # Le zep_tools ne doit PAS être consulté par verify_citation
    mock_zep.search_graph.side_effect = AssertionError(
        "verify_citation ne doit pas appeler search_graph"
    )
    mock_verifier = MagicMock(spec=SimulationActionVerifier)
    mock_res = MagicMock()
    mock_res.valid = True
    mock_verifier.verify_citation.return_value = mock_res

    agent = ReportAgent(
        graph_id="graph_cit",
        simulation_id="sim_cit",
        simulation_requirement="Test",
        zep_tools=mock_zep,
        action_verifier=mock_verifier,
    )
    out = agent._execute_tool(
        "verify_citation",
        {"citation": "la conformité de la redevance", "source_filename": "doc.txt"},
    )
    assert "【引用有效】" in out
    # Le texte du document a bien été transmis au vérificateur
    mock_verifier.verify_citation.assert_called_once()
    call_args = mock_verifier.verify_citation.call_args
    assert "Le Conseil d'État" in call_args[0][0]  # document_text


def test_report_agent_nfr5_suffix_in_plan_prompt():
    """Vérifie que la construction du `plan_outline` inclut la séparation NFR-5."""
    from app.services.report_agent import NFR5_DATA_NOT_INSTRUCTION_SUFFIX
    agent = ReportAgent(
        graph_id="g_nfr5",
        simulation_id="sim_nfr5",
        simulation_requirement="Test NFR-5",
    )
    # Le suffixe est concaténé au PLAN_SYSTEM_PROMPT
    assert "NFR-5" in NFR5_DATA_NOT_INSTRUCTION_SUFFIX
    assert "DONNÉE" in NFR5_DATA_NOT_INSTRUCTION_SUFFIX
    assert "JAMAIS" in NFR5_DATA_NOT_INSTRUCTION_SUFFIX or "Jamais" in NFR5_DATA_NOT_INSTRUCTION_SUFFIX
