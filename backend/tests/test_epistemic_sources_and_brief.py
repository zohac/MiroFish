"""Tests de qualification unitaire et hermétique pour la Story 012-5 (Critères AC1 à AC6, QA-10, QA-11, QA-12).

Couvre :
  - AC1 : Prévalence épistémique absolue (QA-10) — derive_epistemic_kind et classify_record_origin forcent HYPOTHESIS.
  - AC2 : Audit du manifeste de sources (audit_source_manifest) détectant METADATA_ROLE_EPISTEMIC_MISMATCH et EMPTY_OR_UNCHUNKED_SOURCE.
  - AC3 : Intégrité et structuration traçable du brief (QA-11) — extraction/inférence déterministe d'horizon temporel et détection de lacunes.
  - AC4 : Restitution fidèle de toutes les sources dans ReportAgent.build_sources_provenance_section (même si total_chunks == 0).
  - AC5 : Contrat de faits non négociables pour fondateurs/collaborateurs (QA-12) — déclassement immédiat CONTRADICTED.
  - AC6 : Généricité absolue (zéro mot-clé spécifique à un domaine) et non-régression.
"""

from typing import Any, Dict, List
import pytest

from app.models.source_document import (
    DocumentRole,
    DocumentValidationStatus,
    EpistemicSourceKind,
    InformationOrigin,
    SourceDocument,
    audit_source_manifest,
    classify_record_origin,
    create_source_document,
    derive_epistemic_kind,
)
from app.models.simulation_brief import (
    SimulationBrief,
    audit_brief,
    extract_inferred_horizon,
)
from app.models.report_claim import (
    ClaimKind,
    ReportClaim,
    VerificationStatus,
)
from app.models.cohort_coverage import (
    CohortCoverageTable,
    CohortMemberStatus,
    ScenarioRole,
)
from app.services.simulation_action_verifier import SimulationActionVerifier
from app.services.report_agent import ReportAgent


# ============================================================================
# AC1 : Prévalence épistémique absolue (QA-10)
# ============================================================================

def test_ac1_epistemic_kind_prevalence_over_role():
    """AC1 : epistemic_kind fait autorité absolue sur DocumentRole."""
    # 1. Un document typé explicitement PERSONA_SPECIFICATION mais avec role="facts"
    epistemic = derive_epistemic_kind(
        role=DocumentRole.FACTS,
        filename="custom_file.txt",
        explicit_kind=EpistemicSourceKind.PERSONA_SPECIFICATION,
    )
    assert epistemic == EpistemicSourceKind.PERSONA_SPECIFICATION

    # 2. classify_record_origin doit renvoyer HYPOTHESIS même avec role="facts", is_documentary=True
    record = {
        "filename": "personas_cibles.md",
        "source_filename": "personas_cibles.md",
        "role": "facts",
        "epistemic_kind": "PERSONA_SPECIFICATION",
        "char_start": 0,
        "char_end": 120,
        "is_documentary": True,
    }
    origin = classify_record_origin(record)
    assert origin == InformationOrigin.HYPOTHESIS
    assert origin != InformationOrigin.DOCUMENTARY


def test_ac1_scenario_brief_epistemic_prevalence():
    """AC1 : Un brief ou consigne de scénario même avec role='facts' donne HYPOTHESIS."""
    record = {
        "filename": "brief_experimentation.txt",
        "role": DocumentRole.FACTS.value,
        "epistemic_kind": EpistemicSourceKind.SCENARIO_BRIEF.value,
        "char_start": 10,
        "char_end": 80,
    }
    origin = classify_record_origin(record)
    assert origin == InformationOrigin.HYPOTHESIS


# ============================================================================
# AC2 : Détection explicite des conflits de métadonnées de sources (QA-10)
# ============================================================================

def test_ac2_audit_source_manifest_detects_mismatch_and_unchunked():
    """AC2 : audit_source_manifest signale METADATA_ROLE_EPISTEMIC_MISMATCH et EMPTY_OR_UNCHUNKED_SOURCE."""
    # Manifeste contenant l'anomalie exacte constatée dans le run réel R6
    manifest = {
        "simulation_id": "sim_r6_test",
        "total_documents": 3,
        "documents": [
            {
                "document_id": "doc_personas",
                "filename": "personas_cibles.md",
                "role": "facts",
                "epistemic_kind": "PERSONA_SPECIFICATION",
                "total_chunks": 0,
                "validation_status": "unvalidated",
            },
            {
                "document_id": "doc_specs",
                "filename": "specifications_produit.pdf",
                "role": "facts",
                "epistemic_kind": "CANONICAL_DOCUMENT",
                "total_chunks": 0,
                "validation_status": "unvalidated",
            },
            {
                "document_id": "doc_brief",
                "filename": "consignes_simulation.md",
                "role": "scenario",
                "epistemic_kind": "SCENARIO_BRIEF",
                "total_chunks": 4,
                "validation_status": "validated",
            },
        ],
    }

    audit_res = audit_source_manifest(manifest)
    assert audit_res.total_documents == 3
    assert audit_res.has_conflicts is True
    assert audit_res.has_unchunked is True

    # Vérifier la présence du diagnostic de conflit de métadonnées
    mismatch_diags = [d for d in audit_res.diagnostics if d.code == "METADATA_ROLE_EPISTEMIC_MISMATCH"]
    assert len(mismatch_diags) == 1
    assert mismatch_diags[0].filename == "personas_cibles.md"
    assert mismatch_diags[0].severity == "warning"
    assert mismatch_diags[0].details["declared_role"] == "facts"
    assert mismatch_diags[0].details["epistemic_kind"] == "PERSONA_SPECIFICATION"

    # Vérifier les diagnostics de documents non découpés (2 documents à total_chunks == 0)
    unchunked_diags = [d for d in audit_res.diagnostics if d.code == "EMPTY_OR_UNCHUNKED_SOURCE"]
    assert len(unchunked_diags) == 2
    filenames_unchunked = {d.filename for d in unchunked_diags}
    assert filenames_unchunked == {"personas_cibles.md", "specifications_produit.pdf"}


def test_ac2_audit_source_manifest_nominal_clean():
    """AC2 : Un manifeste propre ne produit ni conflit ni avertissement non découpé."""
    clean_manifest = [
        {
            "document_id": "doc_1",
            "filename": "guide_reglementaire.pdf",
            "role": "facts",
            "epistemic_kind": "CANONICAL_DOCUMENT",
            "total_chunks": 12,
            "validation_status": "validated",
        }
    ]
    res = audit_source_manifest(clean_manifest)
    assert res.has_conflicts is False
    assert res.has_unchunked is False
    assert len(res.diagnostics) == 0


# ============================================================================
# AC3 : Intégrité et structuration traçable du brief (QA-11)
# ============================================================================

def test_ac3_extract_inferred_horizon_from_goal():
    """AC3 : Extraction d'horizon temporel depuis le goal quand time_horizon est vide."""
    # Cas 1 : Heures (ex: 72h de simulation)
    goal_1 = "Évaluer la réaction du marché face à la tarification sur 72h de simulation active."
    res_1 = extract_inferred_horizon(goal_1, current_horizon="")
    assert res_1.is_inferred is True
    assert res_1.time_horizon == "72h"
    assert "72h" in res_1.source_mention
    assert len(res_1.diagnostics) > 0

    # Cas 2 : Jours (ex: sur 3 jours)
    goal_2 = "Simuler la propagation d'une rumeur pendant 3 jours sur les réseaux."
    res_2 = extract_inferred_horizon(goal_2, current_horizon="")
    assert res_2.is_inferred is True
    assert res_2.time_horizon == "3j"

    # Cas 3 : Semaines (ex: 2 semaines)
    goal_3 = "Mesurer l'impact d'une campagne sur 2 semaines d'observation."
    res_3 = extract_inferred_horizon(goal_3, current_horizon="")
    assert res_3.is_inferred is True
    assert res_3.time_horizon == "2 semaines"

    # Cas 4 : Déjà renseigné de manière explicite (préservé tel quel)
    res_4 = extract_inferred_horizon(goal_1, current_horizon="48h")
    assert res_4.is_inferred is False
    assert res_4.time_horizon == "48h"

    # Cas 5 : Aucun horizon détectable -> marqué explicitement "unknown"
    goal_5 = "Observer le comportement général des participants sans contrainte temporelle."
    res_5 = extract_inferred_horizon(goal_5, current_horizon="")
    assert res_5.is_inferred is False
    assert res_5.time_horizon == "unknown"


def test_ac3_audit_brief_diagnostics():
    """AC3 : audit_brief identifie les lacunes de consignes sans écrasement silencieux."""
    # Brief avec goal portant 72h mais sans champs structurés (cas R6 QA-11)
    brief = SimulationBrief(
        goal="Tester l'accueil d'une réforme territoriale sur 72h de débat public.",
        time_horizon="",
        target_audiences=[],
        rules=[],
    )

    audit_res = audit_brief(brief)
    assert audit_res.inferred_time_horizon == "72h"
    assert audit_res.has_lacunae is True

    codes = [d.code for d in audit_res.diagnostics]
    assert "TIME_HORIZON_INFERRED" in codes
    assert "TARGET_AUDIENCES_EMPTY" in codes
    assert "RULES_EMPTY" in codes


# ============================================================================
# AC4 : Restitution exhaustive des sources dans le rapport
# ============================================================================

def test_ac4_report_agent_build_sources_provenance_displays_all_documents(tmp_path, monkeypatch):
    """AC4 : La section Sources & Provenance énumère fidèlement tous les documents déclarés."""
    from app.config import Config
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

    sim_id = "sim_test_sources_manifest"
    sim_dir = tmp_path / "simulations" / sim_id
    sim_dir.mkdir(parents=True, exist_ok=True)

    # Créer un faux projet avec 3 documents dont un non découpé et un unvalidated
    doc1 = create_source_document(
        filename="guide_officiel.pdf",
        saved_filename="guide_officiel.pdf",
        role=DocumentRole.FACTS,
        validation_status=DocumentValidationStatus.VALIDATED,
        total_chunks=15,
        priority=1,
    )
    doc2 = create_source_document(
        filename="personas_cibles.md",
        saved_filename="personas_cibles.md",
        role=DocumentRole.FACTS,
        validation_status=DocumentValidationStatus.UNVALIDATED,
        total_chunks=0,
        priority=2,
    )
    doc3 = create_source_document(
        filename="scenario_consignes.md",
        saved_filename="scenario_consignes.md",
        role=DocumentRole.SCENARIO,
        validation_status=DocumentValidationStatus.UNVALIDATED,
        total_chunks=0,
        priority=3,
    )

    class FakeProject:
        project_id = "proj_test"
        source_documents = [doc1.to_dict(), doc2.to_dict(), doc3.to_dict()]
        source_conflicts = []
        applied_ontology_id = None
        graph_id = "graph_test"

    agent = ReportAgent(
        graph_id="graph_test",
        simulation_id=sim_id,
        simulation_requirement="Tester l'accueil de la tarification",
    )
    monkeypatch.setattr(agent, "_resolve_project", lambda: FakeProject())

    section = agent.build_sources_provenance_section()

    # Vérification AC4 : Tous les documents sont présents dans le tableau
    assert "### 2. Documents sources et statut de validation" in section
    assert "3 document(s) inventorié(s)" in section
    assert "`guide_officiel.pdf`" in section
    assert "`personas_cibles.md`" in section
    assert "`scenario_consignes.md`" in section
    assert "15 fragment(s)" in section
    assert "0 (non découpé)" in section
    assert "Aucun document source structuré rattaché au projet" not in section


# ============================================================================
# AC5 : Contrat de faits non négociables de l'entreprise (QA-12)
# ============================================================================

def test_ac5_company_facts_contract_contradiction_detection():
    """AC5 / QA-12 : Toute allégation d'un agent d'entreprise contredisant un fait canonique est CONTRADICTED."""
    # Document canonique validé fixant la règle tarifaire / offre
    canonical_doc = {
        "filename": "grille_tarifaire_officielle.md",
        "validation_status": "validated",
        "epistemic_kind": "CANONICAL_DOCUMENT",
        "text": (
            "L'assistance dédiée 24/7 est réservée exclusivement aux abonnés du plan Entreprise. "
            "Le forfait Découverte de base ne comprend aucun support personnalisé."
        ),
    }

    # Configuration de la cohorte avec un fondateur et un prospect
    cohort = CohortCoverageTable(
        simulation_id="sim_facts_test",
        members=[
            CohortMemberStatus(
                persona_name="Alexandre",
                scenario_role=ScenarioRole.FOUNDER,
                action_count=1,
                observed_event_ids=["evt_alex_1"],
            ),
            CohortMemberStatus(
                persona_name="Camille",
                scenario_role=ScenarioRole.PROSPECT,
                action_count=1,
                observed_event_ids=["evt_cam_1"],
            ),
        ],
    )

    # 1. Le fondateur affirme une contre-vérité directe (l'assistance est gratuite dans le forfait de base)
    claim_founder_lie = ReportClaim(
        claim_id="clm_alex_support",
        text="Alexandre a déclaré aux prospects que l'assistance dédiée 24/7 est totalement gratuite et incluse dans le forfait de base.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Alexandre",
        round_num=3,
        confidence=0.9,
    )

    verified_lie = SimulationActionVerifier.verify_report_claim(
        claim=claim_founder_lie,
        canonical_documents=[canonical_doc],
        cohort_table=cohort,
    )

    # L'assertion doit être impérativement CONTRADICTED
    assert verified_lie.verification_status == VerificationStatus.CONTRADICTED
    assert any("Contrat de faits de l'entreprise" in lim for lim in verified_lie.limitations)
    assert any("grille_tarifaire_officielle.md" in lim for lim in verified_lie.limitations)

    # 2. Un prospect (Camille) peut exprimer librement une opinion ou un doute sans être bloqué par ce contrat
    claim_prospect_opinion = ReportClaim(
        claim_id="clm_camille_opinion",
        text="Camille estime que le forfait de base devrait offrir le support gratuit.",
        claim_kind=ClaimKind.REPORTED_INTENTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Camille",
        round_num=4,
        confidence=0.8,
    )

    verified_prospect = SimulationActionVerifier.verify_report_claim(
        claim=claim_prospect_opinion,
        canonical_documents=[canonical_doc],
        cohort_table=cohort,
    )

    # La liberté d'opinion du prospect n'est pas censurée en COMPANY_FACT_CONTRADICTION
    assert not any("Contrat de faits de l'entreprise" in lim for lim in verified_prospect.limitations)


# ============================================================================
# AC6 : Généricité absolue (NFR-1) et non-régression
# ============================================================================

def test_ac6_genericity_no_hardcoded_domain_terms():
    """AC6 / NFR-1 : Vérifier l'absence de termes en dur spécifiques à Keova."""
    import inspect
    from app.models import source_document, simulation_brief
    from app.services import simulation_action_verifier

    for mod in (source_document, simulation_brief, simulation_action_verifier):
        src = inspect.getsource(mod)
        # Aucune règle métier ne doit dépendre en dur de ces termes
        assert "keova" not in src.lower() or "exemple" in src.lower() or "r6" in src.lower()


def test_ac2_reverse_role_epistemic_mismatch():
    """AC2 : Rôle personas ou scenario sur document canonique validé détecté en mismatch."""
    manifest = [
        {
            "document_id": "doc_rev",
            "filename": "loi_cadre.pdf",
            "role": "personas",
            "epistemic_kind": "CANONICAL_DOCUMENT",
            "total_chunks": 10,
            "validation_status": "validated",
        }
    ]
    res = audit_source_manifest(manifest)
    assert res.has_conflicts is True
    assert any(d.code == "METADATA_ROLE_EPISTEMIC_MISMATCH" for d in res.diagnostics)


def test_ac5_team_member_company_facts_contradiction():
    """AC5 : Un collaborateur interne (TEAM_MEMBER) est également soumis au contrat de faits."""
    canonical_doc = {
        "filename": "charte_deontologique.md",
        "validation_status": "validated",
        "epistemic_kind": "CANONICAL_DOCUMENT",
        "text": "Tout partage de données avec des tiers publicitaires est formellement interdit.",
    }
    cohort = CohortCoverageTable(
        simulation_id="sim_facts_team",
        members=[
            CohortMemberStatus(
                persona_name="Julien_Dev",
                scenario_role=ScenarioRole.TEAM_MEMBER,
                action_count=1,
                observed_event_ids=["evt_j1"],
            ),
        ],
    )
    claim = ReportClaim(
        claim_id="clm_julien_data",
        text="Julien_Dev a confirmé que le partage de données avec des régies publicitaires partenaires est autorisé.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Julien_Dev",
        round_num=2,
    )
    verified = SimulationActionVerifier.verify_report_claim(
        claim=claim,
        canonical_documents=[canonical_doc],
        cohort_table=cohort,
    )
    assert verified.verification_status == VerificationStatus.CONTRADICTED
    assert any("Contrat de faits de l'entreprise" in lim for lim in verified.limitations)


def test_ac4_report_agent_loads_canonical_document_text_from_disk(tmp_path, monkeypatch):
    """Revue BMAD : ReportAgent lit le texte du document canonique sur disque via saved_filename."""
    import os
    from app.config import Config
    from app.models.project import ProjectManager

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

    project_id = "proj_disk_facts"
    files_dir = os.path.join(str(tmp_path), "projects", project_id, "files")
    os.makedirs(files_dir, exist_ok=True)

    saved_fn = "fact_doc_01.txt"
    file_path = os.path.join(files_dir, saved_fn)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("L'accès à l'API temps réel est strictement payant et réservé au plan Entreprise. Aucun accès gratuit n'est consenti.")

    doc = SourceDocument(
        document_id="doc_disk_1",
        filename="conditions_api.txt",
        role=DocumentRole.FACTS,
        saved_filename=saved_fn,
        validation_status=DocumentValidationStatus.VALIDATED,
        epistemic_kind=EpistemicSourceKind.CANONICAL_DOCUMENT,
    )

    class FakeProject:
        def __init__(self):
            self.project_id = project_id
            self.source_documents = [doc.to_dict()]  # to_dict() ne contient PAS 'text'

        def get_brief(self):
            return SimulationBrief(goal="Simulation API", time_horizon="24h")

    agent = ReportAgent(
        graph_id="g_test",
        simulation_id="sim_disk_test",
        simulation_requirement="Tester API",
    )
    monkeypatch.setattr(agent, "_resolve_project", lambda: FakeProject())

    # Extraction et vérification d'une assertion du fondateur
    cohort = CohortCoverageTable(
        simulation_id="sim_disk_test",
        members=[
            CohortMemberStatus(
                persona_name="Fondateur_Marc",
                scenario_role=ScenarioRole.FOUNDER,
                action_count=1,
                observed_event_ids=["evt_m1"],
            )
        ],
    )
    markdown_with_claim = "Le Fondateur_Marc affirme que l'accès à l'API temps réel est entièrement gratuit pour tous les utilisateurs."

    registry = agent.audit_and_save_report_claims(markdown_with_claim, cohort_table=cohort)
    claims = registry.claims
    assert len(claims) >= 1
    founder_claim = next(c for c in claims if c.agent_name == "Fondateur_Marc")
    assert founder_claim.verification_status == VerificationStatus.CONTRADICTED
    assert any("Contrat de faits de l'entreprise" in lim for lim in founder_claim.limitations)


def test_ac3_report_agent_infers_horizon_from_goal_when_empty(tmp_path, monkeypatch):
    """Revue BMAD : ReportAgent infère l'horizon depuis brief.goal quand brief.time_horizon est vide."""
    from app.config import Config
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

    class FakeProject:
        project_id = "proj_inferred"
        source_documents = []

        def get_brief(self):
            return SimulationBrief(
                goal="Évaluer l'impact d'une campagne sur 24h de diffusion intensive.",
                time_horizon="",  # Vide -> doit être inféré en 24h (24.0 heures)
            )

    agent = ReportAgent(
        graph_id="g_test",
        simulation_id="sim_inferred_test",
        simulation_requirement="Campagne 24h",
    )
    monkeypatch.setattr(agent, "_resolve_project", lambda: FakeProject())

    # Cohorte sans horizon_hours fixé pour déclencher le repli
    cohort = CohortCoverageTable(
        simulation_id="sim_inferred_test",
        members=[],
        horizon_hours=0.0,
    )

    markdown = "Rapport sans claims spécifiques."
    registry = agent.audit_and_save_report_claims(markdown, cohort_table=cohort)
    assert registry is not None


def test_ac2_audit_source_manifest_handles_invalid_chunks_and_details():
    """Revue BMAD : audit_source_manifest tolère les valeurs non-int de total_chunks sans exception."""
    manifest = {
        "documents": [
            {
                "document_id": "doc_bad_chunk",
                "filename": "document_corrompu.pdf",
                "role": "facts",
                "total_chunks": "non_numeric",
            }
        ]
    }
    audit = audit_source_manifest(manifest)
    assert audit.has_unchunked is True
    assert audit.diagnostics[0].details["total_chunks"] == 0


def test_ac3_extract_inferred_horizon_singular_week_agreement():
    """Revue BMAD : Accord grammatical singulier pour 1 semaine."""
    res = extract_inferred_horizon("Observation sur 1 semaine complète.")
    assert res.is_inferred is True
    assert res.time_horizon == "1 semaine"

    res_plural = extract_inferred_horizon("Observation sur 3 semaines.")
    assert res_plural.is_inferred is True
    assert res_plural.time_horizon == "3 semaines"


