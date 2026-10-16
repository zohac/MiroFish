import io
import json
import os
import tempfile
import zipfile
import pytest

from app import create_app
from app.models.report_quality import (
    QualityCategory,
    QualityCheckItem,
    QualityGateResult,
    QualityStatus,
)
from app.services.report_quality_gate import (
    SectionCompletionGuard,
    ReportQualityGate,
)
from app.services.simulation_audit_service import SimulationAuditService
from app.models.report_claim import (
    ReportClaim,
    ReportClaimRegistry,
    ClaimKind,
    VerificationStatus,
)
from app.models.cohort_coverage import (
    CohortCoverageTable,
    CohortMemberStatus,
    ScenarioRole,
    DecisionStatus,
)
from app.models.source_document import InformationOrigin
from app.services.report_agent import ReportStatus


@pytest.fixture
def app(tmp_path, monkeypatch):
    from app.config import Config
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# =====================================================================
# 1. Tests des modèles de qualité (T1)
# =====================================================================

def test_quality_check_item_serialization():
    item = QualityCheckItem(
        category=QualityCategory.COMPLETION_GUARD,
        title="Test truncation",
        status=QualityStatus.PASSED,
        message="Section complète.",
        details={"retries": 1},
    )
    d = item.to_dict()
    assert d["category"] == "completion_guard"
    assert d["status"] == "passed"
    assert d["details"]["retries"] == 1

    restored = QualityCheckItem.from_dict(d)
    assert restored.category == QualityCategory.COMPLETION_GUARD
    assert restored.status == QualityStatus.PASSED
    assert restored.title == "Test truncation"


def test_quality_gate_result_recompute_and_persistence(tmp_path):
    result = QualityGateResult(
        simulation_id="sim_test_001",
        report_id="rep_test_001",
        is_publishable=False,
        final_status=QualityStatus.FAILED,
        summary="Évaluation initiale",
    )

    # 1. Ajout d'un item réussi
    result.add_check(
        QualityCheckItem(
            category=QualityCategory.STRUCTURAL_INTEGRITY,
            title="Structure",
            status=QualityStatus.PASSED,
            message="OK",
        )
    )
    assert result.is_publishable is True
    assert result.final_status == QualityStatus.PASSED

    # 2. Ajout d'un avertissement
    result.add_check(
        QualityCheckItem(
            category=QualityCategory.LANGUAGE_COMPLIANCE,
            title="Langue",
            status=QualityStatus.WARNING,
            message="Attention titre en anglais",
        )
    )
    assert result.is_publishable is True
    assert result.final_status == QualityStatus.WARNING

    # 3. Ajout d'un échec bloquant
    result.add_check(
        QualityCheckItem(
            category=QualityCategory.COMPLETION_GUARD,
            title="Troncature",
            status=QualityStatus.FAILED,
            message="Phrase coupée",
        )
    )
    assert result.is_publishable is False
    assert result.final_status == QualityStatus.FAILED

    # 4. Sauvegarde et relecture
    target_json = str(tmp_path / "quality_checks.json")
    result.save_to_file(target_json)
    assert os.path.exists(target_json)

    loaded = QualityGateResult.load_from_file(target_json)
    assert loaded.simulation_id == "sim_test_001"
    assert loaded.report_id == "rep_test_001"
    assert loaded.is_publishable is False
    assert loaded.final_status == QualityStatus.FAILED
    assert len(loaded.checks) == 3


def test_report_status_enum_extension():
    assert ReportStatus.FAILED_VALIDATION.value == "failed_validation"


# =====================================================================
# 2. Tests de SectionCompletionGuard (T2)
# =====================================================================

def test_section_completion_guard_detection():
    # Complète avec point
    truncated, reason = SectionCompletionGuard.is_text_truncated("Ceci est une analyse rigoureuse.")
    assert truncated is False

    # Complète avec point d'exclamation
    truncated, _ = SectionCompletionGuard.is_text_truncated("Le taux d'adoption est remarquable !")
    assert truncated is False

    # Complète avec guillemet fermant
    truncated, _ = SectionCompletionGuard.is_text_truncated("Elle a déclaré : « Je refuse cette offre. »")
    assert truncated is False

    # Complète avec tableau markdown
    table_text = "| Col1 | Col2 |\n|---|---|\n| Val1 | Val2 |"
    truncated, _ = SectionCompletionGuard.is_text_truncated(table_text)
    assert truncated is False

    # Complète avec bloc de code clôturé
    code_text = "```python\nprint('hello')\n```"
    truncated, _ = SectionCompletionGuard.is_text_truncated(code_text)
    assert truncated is False

    # Tronquée : sans ponctuation finale
    truncated, reason = SectionCompletionGuard.is_text_truncated("Pour les indépendants le surcoût de l'offre")
    assert truncated is True
    assert "Absence de ponctuation terminale" in reason

    # Tronquée : mot suspensif
    truncated, reason = SectionCompletionGuard.is_text_truncated("La décision de Florence est négative car")
    assert truncated is True
    assert "mot de liaison suspensif" in reason

    # Tronquée : bloc de code non clôturé
    unclosed_code = "Voici l'extrait :\n```python\nx = 1\n"
    truncated, reason = SectionCompletionGuard.is_text_truncated(unclosed_code)
    assert truncated is True
    assert "non clôturé" in reason


def test_section_completion_guard_assemble_continuation():
    orig = "Pour les indépendants le surcoût représente un frein majeur car"
    cont = "car le budget mensuel de 149 euros est trop élevé pour leur trésorerie."
    merged = SectionCompletionGuard.assemble_continuation(orig, cont)
    # Vérifier l'élimination du doublon du mot 'car'
    assert "car car" not in merged
    assert merged.endswith("leur trésorerie.")
    assert merged.startswith("Pour les indépendants")


def test_section_completion_guard_complete_section_mock_llm():
    class MockLLM:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, temperature=0.3, max_tokens=2048):
            self.calls += 1
            return "le coût mensuel est excessif par rapport aux bénéfices attendus."

    mock_llm = MockLLM()
    orig = "Florence a refusé l'offre car"

    final_text, retries, is_complete = SectionCompletionGuard.complete_section(
        llm_client=mock_llm,
        section_title="Analyse de Florence",
        current_content=orig,
        locale="fr",
    )

    assert is_complete is True
    assert retries == 1
    assert mock_llm.calls == 1
    assert "Florence a refusé l'offre car" in final_text
    assert final_text.endswith("attendus.")


def test_section_completion_guard_max_retries():
    class StubbornTruncatedLLM:
        def chat(self, messages, temperature=0.3, max_tokens=2048):
            # Renvoie toujours une suite tronquée sans ponctuation
            return "et elle a encore hésité parce"

    mock_llm = StubbornTruncatedLLM()
    orig = "Florence est indécise car"

    final_text, retries, is_complete = SectionCompletionGuard.complete_section(
        llm_client=mock_llm,
        section_title="Analyse",
        current_content=orig,
        locale="fr",
        max_retries=2,
    )

    assert retries == 2
def test_section_completion_guard_empty_continuation():
    class EmptyLLM:
        def chat(self, messages, temperature=0.3, max_tokens=2048):
            return ""

    mock_llm = EmptyLLM()
    orig = "Florence hésite encore car"
    final_text, retries, is_complete = SectionCompletionGuard.complete_section(
        llm_client=mock_llm,
        section_title="Analyse",
        current_content=orig,
        locale="fr",
    )
    assert retries == 1
    assert is_complete is False
    assert final_text == orig


# =====================================================================
# 3. Tests de ReportQualityGate (T3, T4)
# =====================================================================

class DummyOutline:
    def __init__(self, titles):
        self.sections = [type("Sec", (), {"title": t})() for t in titles]


def test_report_quality_gate_all_passed():
    gate = ReportQualityGate("sim_001", "rep_001", locale="fr")
    outline = DummyOutline(["Introduction", "Analyse détaillée", "Objections non levées, contradictions et limites"])
    report_md = (
        "## Introduction\n\nVoici une introduction complète sur le cas réel étudié ici avec une argumentation substantielle et fouillée.\n\n"
        "## Analyse détaillée\n\nVoici une analyse très détaillée de la simulation avec tous les personas et données observées.\n\n"
        "## Objections non levées, contradictions et limites\n\nVoici les objections observées détaillées de manière tout à fait exhaustive et rigoureuse.\n"
    )

    result = gate.evaluate_report(outline, report_md)
    assert result.is_publishable is True
    assert result.final_status == QualityStatus.PASSED
    assert result.failed_checks == 0


def test_report_quality_gate_missing_section():
    gate = ReportQualityGate("sim_001", "rep_001", locale="fr")
    outline = DummyOutline(["Introduction", "Section Absente"])
    report_md = "## Introduction\n\nContenu suffisant pour l'introduction ici.\n"

    result = gate.evaluate_report(outline, report_md)
    assert result.is_publishable is False
    assert result.final_status == QualityStatus.FAILED
    struct_check = next(c for c in result.checks if c.category == QualityCategory.STRUCTURAL_INTEGRITY)
    assert struct_check.status == QualityStatus.FAILED
    assert "Section Absente" in struct_check.message


def test_report_quality_gate_truncated_report():
    gate = ReportQualityGate("sim_001", "rep_001", locale="fr")
    outline = DummyOutline(["Introduction"])
    report_md = "## Introduction\n\nL'analyse s'interrompt abruptement sur le mot car"

    result = gate.evaluate_report(outline, report_md)
    assert result.is_publishable is False
    assert result.final_status == QualityStatus.FAILED
    trunc_check = next(c for c in result.checks if c.category == QualityCategory.COMPLETION_GUARD)
    assert trunc_check.status == QualityStatus.FAILED


def test_report_quality_gate_missing_limitations_section_when_objections_exist():
    gate = ReportQualityGate("sim_001", "rep_001", locale="fr")
    outline = DummyOutline(["Introduction", "Synthèse"])
    report_md = "## Introduction\n\nContenu intro substantiel dépassant cinquante caractères.\n\n## Synthèse\n\nContenu synthèse substantiel dépassant cinquante caractères.\n"

    # Création d'une table avec un membre ayant rejeté
    table = CohortCoverageTable(
        simulation_id="sim_001",
        members=[
            CohortMemberStatus(
                persona_name="Florence",
                scenario_role=ScenarioRole.PROSPECT,
                decision_status=DecisionStatus.REJECTED,
                objections=["Prix trop élevé"],
            )
        ],
    )

    result = gate.evaluate_report(outline, report_md, cohort_table=table)
    assert result.is_publishable is False
    assert result.final_status == QualityStatus.FAILED
    lim_check = next(c for c in result.checks if c.category == QualityCategory.LIMITATIONS_SECTION)
    assert lim_check.status == QualityStatus.FAILED


def test_report_quality_gate_contradicted_claims():
    gate = ReportQualityGate("sim_001", "rep_001", locale="fr")
    outline = DummyOutline(["Introduction"])
    report_md = "## Introduction\n\nContenu introductif très rigoureux et complet dépassant cinquante caractères largement.\n"

    registry = ReportClaimRegistry(simulation_id="sim_001")
    registry.add_claim(
        ReportClaim(
            claim_id="clm_01",
            text="Florence a souscrit l'offre au round 2",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            verification_status=VerificationStatus.CONTRADICTED,
        )
    )

    result = gate.evaluate_report(outline, report_md, claims_registry=registry)
    assert result.is_publishable is False
    assert result.final_status == QualityStatus.FAILED
    claim_check = next(c for c in result.checks if c.category == QualityCategory.CLAIM_VERIFICATION)
    assert claim_check.status == QualityStatus.FAILED


# =====================================================================
# 4. Tests de SimulationAuditService (T5, Critère C10)
# =====================================================================

def test_simulation_audit_service_package_generation(monkeypatch, tmp_path):
    from app.config import Config
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

    sim_id = "sim_audit_100"
    rep_id = "rep_audit_100"

    sim_dir = tmp_path / "simulations" / sim_id
    rep_dir = tmp_path / "reports" / rep_id
    sim_dir.mkdir(parents=True, exist_ok=True)
    rep_dir.mkdir(parents=True, exist_ok=True)

    # Créer les fichiers réels
    with open(sim_dir / "simulation_brief.json", "w") as f:
        json.dump({"goal": "Test audit", "time_horizon": "72h"}, f)
    with open(sim_dir / "actors.json", "w") as f:
        json.dump({"simulation_id": sim_id, "actors": ["Florence", "Simon"]}, f)
    with open(sim_dir / "cohort_coverage.json", "w") as f:
        json.dump({"simulation_id": sim_id, "members": []}, f)
    with open(sim_dir / "report_claims.json", "w") as f:
        json.dump({"simulation_id": sim_id, "claims": []}, f)
    with open(rep_dir / "quality_checks.json", "w") as f:
        json.dump({"simulation_id": sim_id, "report_id": rep_id, "final_status": "passed"}, f)
    with open(rep_dir / "full_report.md", "w") as f:
        f.write("# Rapport complet d'audit\n\nTexte du rapport.\n")

    audit_service = SimulationAuditService(simulation_id=sim_id, report_id=rep_id)
    zip_bytes = audit_service.build_audit_package()
    assert zip_bytes is not None
    assert len(zip_bytes) > 0

    # Vérification du contenu du ZIP
    zip_buf = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(zip_buf, "r") as zf:
        file_list = zf.namelist()
        expected_files = [
            "run_manifest.json",
            "simulation_brief.json",
            "actors.json",
            "source_manifest.json",
            "observed_events.jsonl",
            "cohort_coverage.json",
            "report_claims.json",
            "quality_checks.json",
            "report.md",
            "checksums.sha256",
        ]
        for exp in expected_files:
            assert exp in file_list, f"Fichier {exp} absent de l'archive ZIP"

        # Vérifier l'intégrité scellée par checksums.sha256
        checksum_content = zf.read("checksums.sha256").decode("utf-8")
        assert "run_manifest.json" in checksum_content
        assert "report.md" in checksum_content
        assert "quality_checks.json" in checksum_content


# =====================================================================
# 5. Tests d'intégration API Flask (T6)
# =====================================================================

def test_api_report_quality_and_audit_endpoints(client, monkeypatch, tmp_path):
    from app.config import Config
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

    sim_id = "sim_api_test"
    rep_id = "rep_api_test"

    sim_dir = tmp_path / "simulations" / sim_id
    rep_dir = tmp_path / "reports" / rep_id
    sim_dir.mkdir(parents=True, exist_ok=True)
    rep_dir.mkdir(parents=True, exist_ok=True)

    # Créer les métadonnées et fichiers requis
    with open(rep_dir / "meta.json", "w") as f:
        json.dump({"report_id": rep_id, "simulation_id": sim_id, "status": "completed"}, f)
    with open(rep_dir / "full_report.md", "w") as f:
        f.write("# Titre\n\nContenu du rapport.\n")
    with open(rep_dir / "quality_checks.json", "w") as f:
        json.dump({
            "simulation_id": sim_id,
            "report_id": rep_id,
            "is_publishable": True,
            "final_status": "passed",
            "summary": "5/5 checks passed",
            "checks": [],
        }, f)

    # 1. Tester GET /api/report/<report_id>/quality
    res_quality = client.get(f"/api/report/{rep_id}/quality")
    assert res_quality.status_code == 200
    q_data = res_quality.get_json()
    assert q_data["success"] is True
    assert q_data["data"]["is_publishable"] is True
    assert q_data["data"]["final_status"] == "passed"

    # 2. Tester GET /api/report/<report_id>/audit/download
    res_download = client.get(f"/api/report/{rep_id}/audit/download")
    assert res_download.status_code == 200
    assert res_download.mimetype == "application/zip"
    assert f"simulation_audit_{sim_id}.zip" in res_download.headers.get("Content-Disposition", "")

    # 3. Tester GET /api/report/simulation/<simulation_id>/audit/download
    with open(sim_dir / "state.json", "w") as f:
        json.dump({"simulation_id": sim_id, "status": "completed"}, f)
    res_sim_download = client.get(f"/api/report/simulation/{sim_id}/audit/download")
    assert res_sim_download.status_code == 200
    assert res_sim_download.mimetype == "application/zip"

    # 4. Tester 404 sur rapport inexistant
    res_404 = client.get("/api/report/rep_inexistant/quality")
    assert res_404.status_code == 404


def test_section_completion_guard_question_with_suspensive_words():
    # Phrase interrogative se terminant par un mot du dictionnaire suspensif mais close par '?'
    q1 = "Quels sont les acteurs concernés et par qui ?"
    truncated, reason = SectionCompletionGuard.is_text_truncated(q1)
    assert truncated is False, f"Faux positif sur question fermée : {reason}"

    q2 = "Florence hésite entre deux scénarios : lesquels et pour qui ?"
    truncated, reason = SectionCompletionGuard.is_text_truncated(q2)
    assert truncated is False, f"Faux positif sur question fermée : {reason}"


def test_section_completion_guard_assemble_continuation_punctuation():
    orig = "Voici le premier membre de phrase"
    cont = ", qui se prolonge sans espace parasite avant la virgule."
    merged = SectionCompletionGuard.assemble_continuation(orig, cont)
    assert merged == "Voici le premier membre de phrase, qui se prolonge sans espace parasite avant la virgule."
    assert "phrase ," not in merged


def test_report_quality_gate_limitations_heading_case_insensitivity():
    gate = ReportQualityGate("sim_002", "rep_002", locale="fr")
    outline = DummyOutline(["Introduction", "Objections et limites"])
    report_md = (
        "## Introduction\n\nIntroduction complète et substantielle dépassant largement cinquante caractères.\n\n"
        "## Objections et limites\n\nVoici les objections et limites rédigées en casse française standard (> 50 caractères).\n"
    )

    table = CohortCoverageTable(
        simulation_id="sim_002",
        members=[
            CohortMemberStatus(
                persona_name="Florence",
                scenario_role=ScenarioRole.PROSPECT,
                decision_status=DecisionStatus.REJECTED,
                objections=["Trop cher"],
            )
        ],
    )

    result = gate.evaluate_report(outline, report_md, cohort_table=table)
    assert result.is_publishable is True
    assert result.final_status == QualityStatus.PASSED
    lim_check = next(c for c in result.checks if c.category == QualityCategory.LIMITATIONS_SECTION)
    assert lim_check.status == QualityStatus.PASSED


def test_api_audit_download_generating_conflict_409(client, monkeypatch, tmp_path):
    from app.config import Config
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

    sim_id = "sim_conflict_test"
    rep_id = "rep_conflict_test"

    sim_dir = tmp_path / "simulations" / sim_id
    rep_dir = tmp_path / "reports" / rep_id
    sim_dir.mkdir(parents=True, exist_ok=True)
    rep_dir.mkdir(parents=True, exist_ok=True)

    with open(rep_dir / "meta.json", "w") as f:
        json.dump({"report_id": rep_id, "simulation_id": sim_id, "status": "generating"}, f)
    with open(sim_dir / "state.json", "w") as f:
        json.dump({"simulation_id": sim_id, "status": "running"}, f)

    res_report = client.get(f"/api/report/{rep_id}/audit/download")
    assert res_report.status_code == 409
    assert res_report.get_json()["success"] is False

    res_sim = client.get(f"/api/report/simulation/{sim_id}/audit/download")
    assert res_sim.status_code == 409
    assert res_sim.get_json()["success"] is False


def test_simulation_audit_service_source_manifest_with_objects(monkeypatch, tmp_path):
    from app.config import Config
    from app.services.simulation_manager import SimulationManager
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path / "simulations"))

    from app.models.source_document import SourceDocument, EpistemicSourceKind, DocumentRole
    from app.models.project import ProjectManager

    sim_id = "sim_audit_obj"
    pm = ProjectManager()
    proj = pm.create_project(name="Test Project")
    proj_id = proj.project_id

    sim_dir = tmp_path / "simulations" / sim_id
    sim_dir.mkdir(parents=True, exist_ok=True)
    with open(sim_dir / "state.json", "w") as f:
        json.dump({"simulation_id": sim_id, "project_id": proj_id, "status": "completed"}, f)

    doc_obj = SourceDocument(
        document_id="doc_01",
        filename="document_test.txt",
        role=DocumentRole.FACTS,
        saved_filename="document_test.txt",
        epistemic_kind=EpistemicSourceKind.CANONICAL_DOCUMENT,
    )

    proj.source_documents = [doc_obj.to_dict()]
    pm.save_project(proj)

    audit_service = SimulationAuditService(simulation_id=sim_id)
    manifest = audit_service.build_source_manifest()
    assert manifest["total_documents"] == 1
    assert manifest["documents"][0]["document_id"] == "doc_01"

    # Tester la résilience si un objet SourceDocument est passé directement en mémoire
    proj_in_memory = pm.get_project(proj_id)
    proj_in_memory.source_documents = [doc_obj]
    monkeypatch.setattr(ProjectManager, "get_project", lambda self, pid: proj_in_memory)
    manifest_obj = audit_service.build_source_manifest()
    assert manifest_obj["total_documents"] == 1
    assert manifest_obj["documents"][0]["document_id"] == "doc_01"

