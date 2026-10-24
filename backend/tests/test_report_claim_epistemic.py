"""Tests unitaires hermétiques pour la Story 011-3.

Valide :
  - AC1 : Modèle ReportClaim, énumérations ClaimKind, VerificationStatus et conteneur ReportClaimRegistry.
  - AC2 : Typage épistémique EpistemicSourceKind et dérivation automatique déterministe.
  - AC3 : Étanchéité épistémique stricte (C5) interdisant 100 % des promotions de personas fictifs en documentaire.
  - AC4 : Règle anti-affabulation action vs intention (C4) rétrogradant les actions non exécutées.
  - AC5 : Contrôle verbatim des citations simulées face aux traces réelles et forgées.
  - AC6 : Extraction et persistance du registre report_claims.json.
  - AC7 : Filet hermétique sans dépendance réseau.
"""

import json
import os
import pytest

from app.models.evidence_pack import EvidencePack, ObservedEvent
from app.models.provenance_regime import ProvenanceRegime
from app.models.report_claim import (
    ClaimKind,
    ReportClaim,
    ReportClaimRegistry,
    VerificationStatus,
    compute_claim_id,
)
from app.models.source_document import (
    DocumentChunk,
    DocumentRole,
    DocumentValidationStatus,
    EpistemicSourceKind,
    InformationOrigin,
    SourceDocument,
    SourceReference,
    classify_record_origin,
    create_source_document,
    derive_epistemic_kind,
)
from app.services.report_agent import ReportAgent
from app.services.simulation_action_verifier import SimulationActionVerifier


# ============================================================================
# AC1 : Modèle ReportClaim, énumérations et conteneur ReportClaimRegistry
# ============================================================================


def test_report_claim_instantiation_and_deterministic_id():
    """Vérifie l'instanciation, le typage strict et le calcul d'identifiant déterministe."""
    claim = ReportClaim(
        claim_id="",
        text="Émilie a souscrit au forfait annuel",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Émilie",
        round_num=2,
    )
    expected_id = compute_claim_id("Émilie a souscrit au forfait annuel", ClaimKind.OBSERVED_SOCIAL_ACTION, "Émilie", 2)
    assert claim.claim_id == expected_id
    assert claim.claim_id.startswith("clm_")
    assert claim.verification_status == VerificationStatus.UNSUPPORTED
    assert claim.confidence == 1.0


def test_report_claim_serialization_roundtrip():
    """Vérifie la sérialisation to_dict / from_dict de ReportClaim."""
    claim = ReportClaim(
        claim_id="clm_12345678",
        text="Tarif fixe à 29 euros",
        claim_kind=ClaimKind.SOURCE_FACT,
        origin=InformationOrigin.DOCUMENTARY,
        evidence_refs=["doc_uuid_1"],
        verification_status=VerificationStatus.VERIFIED,
        confidence=0.95,
        limitations=["Source 2025"],
        provenance_regime=ProvenanceRegime.INTERVIEW,
    )
    data = claim.to_dict()
    assert data["claim_id"] == "clm_12345678"
    assert data["claim_kind"] == "SOURCE_FACT"
    assert data["origin"] == "documentary"
    assert data["verification_status"] == "VERIFIED"
    assert data["provenance_regime"] == "interview"

    restored = ReportClaim.from_dict(data)
    assert restored.claim_id == claim.claim_id
    assert restored.text == claim.text
    assert restored.claim_kind == ClaimKind.SOURCE_FACT
    assert restored.origin == InformationOrigin.DOCUMENTARY
    assert restored.verification_status == VerificationStatus.VERIFIED
    assert restored.confidence == 0.95
    assert restored.provenance_regime == ProvenanceRegime.INTERVIEW

    # Tolérance à l'absence du champ (rétrocompatibilité).
    legacy = dict(data)
    legacy.pop("provenance_regime", None)
    assert ReportClaim.from_dict(legacy).provenance_regime is None


def test_claim_kind_and_verification_status_robust_parsing():
    """Vérifie la robustesse du parsing des énumérations ClaimKind et VerificationStatus."""
    assert ClaimKind.from_str("observed_social_action") == ClaimKind.OBSERVED_SOCIAL_ACTION
    assert ClaimKind.from_str("action") == ClaimKind.OBSERVED_SOCIAL_ACTION
    assert ClaimKind.from_str("intention") == ClaimKind.REPORTED_INTENTION
    assert ClaimKind.from_str("source_fact") == ClaimKind.SOURCE_FACT
    assert ClaimKind.from_str("unknown_nonsense") == ClaimKind.ANALYST_INFERENCE

    assert VerificationStatus.from_str("verified") == VerificationStatus.VERIFIED
    assert VerificationStatus.from_str("contradicted") == VerificationStatus.CONTRADICTED
    assert VerificationStatus.from_str("unknown") == VerificationStatus.UNSUPPORTED


def test_report_claim_registry_statistics_and_persistence(tmp_path):
    """Vérifie le calcul des statistiques de ReportClaimRegistry et sa sauvegarde JSON."""
    registry = ReportClaimRegistry(simulation_id="sim_test_001")
    c1 = ReportClaim(
        claim_id="clm_01",
        text="Fait vérifié",
        claim_kind=ClaimKind.SOURCE_FACT,
        origin=InformationOrigin.DOCUMENTARY,
        verification_status=VerificationStatus.VERIFIED,
    )
    c2 = ReportClaim(
        claim_id="clm_02",
        text="Action non prouvée",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        verification_status=VerificationStatus.UNSUPPORTED,
    )
    c3 = ReportClaim(
        claim_id="clm_03",
        text="Contradiction",
        claim_kind=ClaimKind.SOURCE_FACT,
        origin=InformationOrigin.DOCUMENTARY,
        verification_status=VerificationStatus.CONTRADICTED,
    )

    registry.add_claim(c1)
    registry.add_claim(c2)
    registry.add_claim(c3)

    assert registry.total_claims == 3
    assert registry.verified_claims == 1
    assert registry.unsupported_claims == 1
    assert registry.contradicted_claims == 1
    assert registry.verification_ratio == 0.3333

    target_file = tmp_path / "report_claims.json"
    registry.save_to_file(str(target_file))

    loaded = ReportClaimRegistry.load_from_file(str(target_file))
    assert loaded.simulation_id == "sim_test_001"
    assert loaded.total_claims == 3
    assert loaded.verified_claims == 1


# ============================================================================
# AC2 : Typage épistémique EpistemicSourceKind et dérivation automatique
# ============================================================================


def test_derive_epistemic_kind_from_role_and_filename():
    """Vérifie la dérivation déterministe de EpistemicSourceKind selon rôle et nom de fichier."""
    # Rôle explicite
    assert derive_epistemic_kind(role=DocumentRole.PERSONAS) == EpistemicSourceKind.PERSONA_SPECIFICATION
    assert derive_epistemic_kind(role=DocumentRole.SCENARIO) == EpistemicSourceKind.SCENARIO_BRIEF
    assert derive_epistemic_kind(role=DocumentRole.HYPOTHESES) == EpistemicSourceKind.SCENARIO_BRIEF
    assert derive_epistemic_kind(role=DocumentRole.FACTS) == EpistemicSourceKind.CANONICAL_DOCUMENT

    # Nom de fichier en repli
    assert derive_epistemic_kind(filename="personas-et-cibles-keova.md") == EpistemicSourceKind.PERSONA_SPECIFICATION
    assert derive_epistemic_kind(filename="brief-scenario-tarifs.md") == EpistemicSourceKind.SCENARIO_BRIEF
    assert derive_epistemic_kind(filename="historique-litiges-2024.txt") == EpistemicSourceKind.HISTORICAL_CASE
    assert derive_epistemic_kind(filename="cgu-keova-essentiel.pdf") == EpistemicSourceKind.CANONICAL_DOCUMENT


def test_source_document_and_chunk_epistemic_integration():
    """Vérifie que SourceDocument et DocumentChunk portent et propagent epistemic_kind."""
    doc = create_source_document(
        filename="personas-keova.md",
        saved_filename="personas_keova_hash.md",
        role=DocumentRole.PERSONAS,
    )
    assert doc.epistemic_kind == EpistemicSourceKind.PERSONA_SPECIFICATION

    doc_dict = doc.to_dict()
    assert doc_dict["epistemic_kind"] == "PERSONA_SPECIFICATION"

    restored = SourceDocument.from_dict(doc_dict)
    assert restored.epistemic_kind == EpistemicSourceKind.PERSONA_SPECIFICATION

    chunk = DocumentChunk(
        source_document_id=doc.document_id,
        source_filename=doc.filename,
        chunk_index=0,
        text="Émilie, 34 ans, graphiste freelance",
        source_role=doc.role,
        char_start=0,
        char_end=35,
    )
    assert chunk.epistemic_kind == EpistemicSourceKind.PERSONA_SPECIFICATION
    assert chunk.to_dict()["epistemic_kind"] == "PERSONA_SPECIFICATION"
    assert chunk.to_metadata()["epistemic_kind"] == "PERSONA_SPECIFICATION"


# ============================================================================
# AC3 : Étanchéité épistémique stricte (Critère C5)
# ============================================================================


def test_epistemic_barrier_blocks_persona_as_documentary_context():
    """Critère C5 : un profil fictif (ex: Émilie) ne peut JAMAIS être DOCUMENTARY."""
    # Enregistrement issu d'un persona avec des offsets valides
    persona_record = {
        "source_filename": "personas-et-cibles-keova.md",
        "char_start": 100,
        "char_end": 180,
        "role": "personas",
        "content": "Émilie a perdu 1 500 € suite à un litige en 2024",
    }

    origin = classify_record_origin(persona_record)
    # L'étanchéité stricte force HYPOTHESIS pour tout persona ou brief
    assert origin == InformationOrigin.HYPOTHESIS
    assert origin != InformationOrigin.DOCUMENTARY


def test_epistemic_barrier_in_verify_report_claim():
    """Critère C5 : verify_report_claim bloque le transfert d'une claim de persona en SOURCE_FACT historique."""
    claim = ReportClaim(
        claim_id="clm_emilie_litige",
        text="Émilie a perdu 1 500 € suite à un litige en 2024",
        claim_kind=ClaimKind.SOURCE_FACT,
        origin=InformationOrigin.DOCUMENTARY,
        evidence_refs=["personas-et-cibles-keova.md"],
        agent_name="Émilie",
    )

    verified = SimulationActionVerifier.verify_report_claim(claim)
    assert verified.claim_kind == ClaimKind.SCENARIO_HYPOTHESIS
    assert verified.origin == InformationOrigin.HYPOTHESIS
    assert verified.verification_status == VerificationStatus.UNSUPPORTED
    assert any("Barrière épistémique C5" in lim for lim in verified.limitations)


# ============================================================================
# AC4 : Règle anti-affabulation action vs intention (Critère C4)
# ============================================================================


def test_anti_affabulation_demotes_unexecuted_action_to_intention():
    """Critère C4 : une OBSERVED_SOCIAL_ACTION sans event_id exécuté est déclassée en REPORTED_INTENTION."""
    # EvidencePack ne contenant qu'un post textuel (intention), sans achat réel
    event = ObservedEvent(
        event_id="evt_twitter_1_1_abc12345",
        simulation_id="sim_test",
        platform="twitter",
        round_num=1,
        agent_id=1,
        agent_name="Émilie",
        action_type="CREATE_POST",
        timestamp="2026-10-16T12:00:00Z",
        action_args={"content": "Le tarif est honnête, je vais m'abonner dès ce soir."},
        is_action_executed=True,
    )
    evidence_pack = EvidencePack.from_events("sim_test", [event])

    # Claim affirmant un achat effectif non tracé
    unproven_claim = ReportClaim(
        claim_id="",
        text="Émilie a acheté l'abonnement annuel Keova",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        evidence_refs=["evt_twitter_1_1_abc12345"],  # Ne correspond pas à un subscribe
        agent_name="Émilie",
        round_num=1,
    )

    verified = SimulationActionVerifier.verify_report_claim(unproven_claim, evidence_pack=evidence_pack)
    # L'affirmation doit être rétrogradée en REPORTED_INTENTION avec statut UNSUPPORTED
    assert verified.claim_kind == ClaimKind.REPORTED_INTENTION
    assert verified.verification_status == VerificationStatus.UNSUPPORTED
    assert any("anti-affabulation (C4)" in lim for lim in verified.limitations)


def test_anti_affabulation_validates_proven_action():
    """Critère C4 : une action effectivement tracée avec is_action_executed=True est validée."""
    event = ObservedEvent(
        event_id="evt_reddit_2_1_subscribe99",
        simulation_id="sim_test",
        platform="reddit",
        round_num=2,
        agent_id=1,
        agent_name="Émilie",
        action_type="SUBSCRIBE",
        timestamp="2026-10-16T13:00:00Z",
        action_args={"plan": "annual"},
        is_action_executed=True,
    )
    evidence_pack = EvidencePack.from_events("sim_test", [event])

    claim = ReportClaim(
        claim_id="",
        text="Émilie a souscrit au forfait",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        evidence_refs=["evt_reddit_2_1_subscribe99"],
        agent_name="Émilie",
        round_num=2,
    )

    verified = SimulationActionVerifier.verify_report_claim(claim, evidence_pack=evidence_pack)
    assert verified.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
    assert verified.verification_status == VerificationStatus.VERIFIED
    assert "evt_reddit_2_1_subscribe99" in verified.evidence_refs


# ============================================================================
# AC5 : Contrôle verbatim des citations simulées (Critère C4)
# ============================================================================


def test_verify_simulated_citation_exact_and_normalized():
    """Critère C4 : vérification verbatim d'une citation authentique et normalisée."""
    event = ObservedEvent(
        event_id="evt_tw_10",
        simulation_id="sim_test",
        platform="twitter",
        round_num=3,
        agent_id=2,
        agent_name="Sylvie",
        action_type="POST",
        timestamp="2026-10-16T14:00:00Z",
        action_args={"content": "Sans option mensuelle, nous ne signerons pas !"},
        is_action_executed=True,
    )
    evidence_pack = EvidencePack.from_events("sim_test", [event])

    # 1. Correspondance exacte
    valid, exact, ev_id = SimulationActionVerifier.verify_simulated_citation(
        agent_name="Sylvie",
        claimed_text="Sans option mensuelle, nous ne signerons pas !",
        evidence_pack=evidence_pack,
    )
    assert valid is True
    assert exact is True
    assert ev_id == "evt_tw_10"

    # 2. Correspondance normalisée (ponctuation/espaces légers)
    valid_norm, exact_norm, ev_id_norm = SimulationActionVerifier.verify_simulated_citation(
        agent_name="Sylvie",
        claimed_text="Sans option mensuelle nous ne signerons pas",
        evidence_pack=evidence_pack,
    )
    assert valid_norm is True
    assert ev_id_norm == "evt_tw_10"

    # 3. Citation forgée non existante
    valid_fake, exact_fake, _ = SimulationActionVerifier.verify_simulated_citation(
        agent_name="Sylvie",
        claimed_text="Je trouve cette offre merveilleuse et parfaite",
        evidence_pack=evidence_pack,
    )
    assert valid_fake is False
    assert exact_fake is False


# ============================================================================
# AC6 : Pipeline d'audit et persistance de report_claims.json
# ============================================================================


def test_report_agent_extract_claims_from_content():
    """Vérifie l'extraction déterministe des claims à partir de fragments de rapport Markdown."""
    sample_markdown = """
# Synthèse de la simulation

## Contexte documentaire
- Le document `cgu-keova.pdf` fixe le délai de préavis à 30 jours.

## Événements simulés
- Round 2 : Agent Émilie a publié un tweet d'indignation face au prix evt_twitter_2_1_abc.
- Sylvie va quitter la plateforme dès demain faute d'accord.
- Le churn prévisible atteindra 40 % d'ici 90 jours.
"""
    agent = ReportAgent(
        graph_id="graph_test",
        simulation_id="sim_audit_001",
        simulation_requirement="Tester l'extraction de claims",
        locale="fr",
    )
    claims = agent.extract_claims_from_content(sample_markdown)

    assert len(claims) >= 4
    kinds = [c.claim_kind for c in claims]
    assert ClaimKind.SOURCE_FACT in kinds
    assert ClaimKind.OBSERVED_SOCIAL_ACTION in kinds
    assert ClaimKind.REPORTED_INTENTION in kinds
    assert ClaimKind.SPECULATIVE_PROJECTION in kinds
    # Régime de provenance (Story 014-1) : sans observation, tout est unknown.
    assert all(
        getattr(c, "provenance_regime", None) is not None
        and getattr(c.provenance_regime, "value", c.provenance_regime) == "unknown"
        for c in claims
    )
    assert all("Régime de provenance non établi (unknown)." in (c.limitations or []) for c in claims)


def test_report_agent_audit_and_save_report_claims(tmp_path, monkeypatch):
    """Vérifie l'audit global et la création effective de simulations/<sim_id>/report_claims.json."""
    from app.config import Config
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

    sim_id = "sim_test_audit_flow"
    event = ObservedEvent(
        event_id="evt_twitter_2_1_abc",
        simulation_id=sim_id,
        platform="twitter",
        round_num=2,
        agent_id=1,
        agent_name="Émilie",
        action_type="POST",
        timestamp="2026-10-16T15:00:00Z",
        action_args={"content": "indignation face au prix"},
        is_action_executed=True,
    )
    evidence_pack = EvidencePack.from_events(sim_id, [event])

    sample_md = """
## Événements simulés
- Round 2 : Agent Émilie a publié un tweet d'indignation face au prix evt_twitter_2_1_abc.
"""
    agent = ReportAgent(
        graph_id="graph_test",
        simulation_id=sim_id,
        simulation_requirement="Vérifier la persistance des claims",
    )
    registry = agent.audit_and_save_report_claims(sample_md, evidence_pack=evidence_pack)

    assert registry.total_claims >= 1
    assert registry.verified_claims >= 1

    expected_path = tmp_path / "simulations" / sim_id / "report_claims.json"
    assert os.path.exists(expected_path)

    with open(expected_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["simulation_id"] == sim_id
    assert data["total_claims"] == registry.total_claims
    assert data["verified_claims"] == registry.verified_claims


def test_report_claim_registry_filters():
    """Vérifie le filtrage par statut et par nature dans ReportClaimRegistry."""
    reg = ReportClaimRegistry(simulation_id="sim_filters")
    c1 = ReportClaim(
        claim_id="1",
        text="Affirmation 1",
        claim_kind=ClaimKind.SOURCE_FACT,
        origin=InformationOrigin.DOCUMENTARY,
        verification_status=VerificationStatus.VERIFIED,
    )
    c2 = ReportClaim(
        claim_id="2",
        text="Affirmation 2",
        claim_kind=ClaimKind.REPORTED_INTENTION,
        origin=InformationOrigin.SIMULATION,
        verification_status=VerificationStatus.UNSUPPORTED,
    )
    reg.add_claim(c1)
    reg.add_claim(c2)

    assert len(reg.filter_by_kind(ClaimKind.SOURCE_FACT)) == 1
    assert len(reg.filter_by_kind(ClaimKind.REPORTED_INTENTION)) == 1
    assert len(reg.filter_by_status(VerificationStatus.VERIFIED)) == 1
    assert len(reg.filter_by_status(VerificationStatus.UNSUPPORTED)) == 1


def test_epistemic_barrier_multiple_personas_keova():
    """Vérifie la barrière épistémique sur les profils de personas du cas Keova (Sylvie, Simon)."""
    for persona_name in ("Sylvie", "Simon"):
        claim = ReportClaim(
            claim_id=f"clm_{persona_name.lower()}",
            text=f"{persona_name} est un client type défini dans la cible",
            claim_kind=ClaimKind.SOURCE_FACT,
            origin=InformationOrigin.DOCUMENTARY,
            evidence_refs=["personas-et-cibles-keova.md"],
            agent_name=persona_name,
        )
        verified = SimulationActionVerifier.verify_report_claim(claim)
        assert verified.claim_kind == ClaimKind.SCENARIO_HYPOTHESIS
        assert verified.origin == InformationOrigin.HYPOTHESIS
        assert verified.verification_status == VerificationStatus.UNSUPPORTED


def test_verify_report_claim_reported_intention_without_citation():
    """Vérifie le traitement d'une intention sans citation ni trace dans l'evidence_pack."""
    claim = ReportClaim(
        claim_id="",
        text="Christine a l'intention de voter contre la proposition",
        claim_kind=ClaimKind.REPORTED_INTENTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Christine",
    )
    evidence_pack = EvidencePack.from_events("sim_test", [])
    verified = SimulationActionVerifier.verify_report_claim(claim, evidence_pack=evidence_pack)
    assert verified.claim_kind == ClaimKind.REPORTED_INTENTION
    assert verified.verification_status == VerificationStatus.UNSUPPORTED


def test_source_reference_epistemic_roundtrip_and_edge_cases():
    """Valide le roundtrip de SourceReference avec epistemic_kind et les edge cases durcis."""
    ref = SourceReference(
        document_id="doc_persona_01",
        filename="personas-keova.md",
        role=DocumentRole.PERSONAS,
        priority=2,
        date="2026-10-16",
        validation_status=DocumentValidationStatus.VALIDATED,
        epistemic_kind=EpistemicSourceKind.PERSONA_SPECIFICATION,
    )
    d = ref.to_dict()
    assert d["epistemic_kind"] == "PERSONA_SPECIFICATION"
    restored = SourceReference.from_dict(d)
    assert restored.epistemic_kind == EpistemicSourceKind.PERSONA_SPECIFICATION
    assert restored.role == DocumentRole.PERSONAS

    # Edge case 1 : ReportClaimRegistry.from_dict avec claims: null
    empty_reg = ReportClaimRegistry.from_dict({"simulation_id": "sim_null", "claims": None})
    assert empty_reg.total_claims == 0

    # Edge case 2 : barrière C5 active même sans agent_name
    anon_claim = ReportClaim(
        claim_id="",
        text="Un dommage de 1500 euros a été subi",
        claim_kind=ClaimKind.SOURCE_FACT,
        origin=InformationOrigin.DOCUMENTARY,
        evidence_refs=["personas-et-cibles-keova.md"],
        agent_name=None,
    )
    v_anon = SimulationActionVerifier.verify_report_claim(anon_claim)
    assert v_anon.claim_kind == ClaimKind.SCENARIO_HYPOTHESIS
    assert v_anon.origin == InformationOrigin.HYPOTHESIS

    # Edge case 3 : rejet de citation asymétrique plus longue que le texte réel
    ev = ObservedEvent(
        event_id="evt_short",
        simulation_id="sim_test",
        platform="twitter",
        round_num=1,
        agent_id=1,
        agent_name="Bob",
        action_type="POST",
        timestamp="2026-10-16T10:00:00Z",
        action_args={"content": "Je refuse de payer."},
        is_action_executed=True,
    )
    pack = EvidencePack.from_events("sim_test", [ev])
    # Citation forgée incluant la phrase mais y ajoutant des allégations fictives
    forged_quote = "Je refuse de payer et je vais attaquer en justice cette entreprise frauduleuse"
    valid, exact, _ = SimulationActionVerifier.verify_simulated_citation("Bob", forged_quote, evidence_pack=pack)
    assert valid is False


