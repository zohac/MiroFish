"""Tests hermétiques pour la règle de silence jusqu'à la prose et la barrière (Story 014-3)."""

import pytest

from app.models.cohort_coverage import CohortCoverageTable, CohortMemberStatus
from app.models.report_claim import ClaimKind, ReportClaim, ReportClaimRegistry
from app.models.report_quality import PublicationStatus
from app.services.report_agent import ReportAgent
from app.services.report_quality_gate import ReportQualityGate


def _silent_table():
    silent = CohortMemberStatus(
        persona_name="Émilie",
        scenario_role=__import__("app.models.cohort_coverage", fromlist=["ScenarioRole"]).ScenarioRole.PROSPECT,
        action_count=0,
        observed_event_ids=[],
    )
    active = CohortMemberStatus(
        persona_name="Florence",
        scenario_role=__import__("app.models.cohort_coverage", fromlist=["ScenarioRole"]).ScenarioRole.PROSPECT,
        action_count=2,
        observed_event_ids=["evt_1", "evt_2"],
    )
    return CohortCoverageTable(simulation_id="sim_silence", members=[silent, active])


def test_silent_persona_gets_no_speech_or_section():
    """AC1 : un persona silencieux ne reçoit ni parole, ni décision, ni section."""
    sample_md = """
## Événements simulés
- Round 2 : Agent Émilie a publié un tweet d'indignation face au prix evt_twitter_2_1_abc.
- Round 3 : Agent Florence a souscrit à l'offre evt_twitter_3_1_def.
"""
    agent = ReportAgent(graph_id="g", simulation_id="sim_silence", simulation_requirement="test", locale="fr")
    table = _silent_table()
    claims = agent.extract_claims_from_content(sample_md, cohort_table=table)
    silent_claims = [c for c in claims if (c.agent_name or "").lower() == "émilie"]
    for c in silent_claims:
        assert c.claim_kind != ClaimKind.OBSERVED_SOCIAL_ACTION
        assert "Règle de silence" in " ".join(c.limitations or [])


def test_non_admitted_persona_filtered_from_context():
    """AC2 : les acteurs review/ineligible sont filtrés de la cohorte (contexte de rédaction)."""
    from app.models.actor_selection import ActorItem, ActorSelection, EligibilityStatus
    from app.models.actor_eligibility import ActorRole

    item_review = ActorItem(
        entity_uuid="u_rev", entity_name="Persona Review",
        qualified_role=ActorRole.PERSON, eligibility_status=EligibilityStatus.REVIEW,
    )
    item_eligible = ActorItem(
        entity_uuid="u_ok", entity_name="Persona OK",
        qualified_role=ActorRole.PERSON, eligibility_status=EligibilityStatus.ELIGIBLE,
    )
    selection = ActorSelection(simulation_id="sim_f", project_id="p", graph_id="g", input_fingerprint="fp", actors=[item_review, item_eligible])
    table = __import__("app.models.cohort_coverage", fromlist=["CohortCoverageTable"]).CohortCoverageTable.build_from_simulation(
        simulation_id="sim_f", actor_selection=selection, evidence_pack=None, brief=None,
    )
    names = [m.persona_name for m in table.members]
    assert "Persona Review" not in names
    assert "Persona OK" in names


def test_silence_contradiction_fails_barrier():
    """AC3 : une contradiction de silence déclenche FAILED_VALIDATION et is_publishable=False."""
    table = _silent_table()
    registry = ReportClaimRegistry(simulation_id="sim_silence")
    from app.models.report_claim import VerificationStatus
    from app.models.source_document import InformationOrigin
    claim = ReportClaim(
        claim_id="",
        text="Émilie a souscrit à l'offre",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.INFERENCE,
        verification_status=VerificationStatus.CONTRADICTED,
        agent_name="Émilie",
    )
    registry.add_claim(claim)
    gate = ReportQualityGate(simulation_id="sim_silence", report_id="rep_silence")
    result = gate.evaluate_report(outline=None, report_markdown="", cohort_table=table, claims_registry=registry)
    assert result.final_status.value == "failed"
    assert result.is_publishable is False


def test_silence_rule_inhibits_prose_passage():
    """AC4 : le passage attribué à un silencieux est déclassé et annoté dans limitations."""
    sample_md = "- Round 2 : Agent Émilie a publié un tweet d'indignation evt_twitter_2_1_abc."
    agent = ReportAgent(graph_id="g", simulation_id="sim_silence", simulation_requirement="test", locale="fr")
    table = _silent_table()
    claims = agent.extract_claims_from_content(sample_md, cohort_table=table)
    # Au moins un claim a été extrait et déclassé
    assert len(claims) >= 1
    for c in claims:
        if (c.agent_name or "").lower() == "émilie":
            assert c.claim_kind == ClaimKind.REPORTED_INTENTION
            assert any("Règle de silence" in lim for lim in (c.limitations or []))


def test_cohort_table_passed_to_report():
    """AC5 : la table de cohorte est transmise, pas recalculée (paramètre cohort_table)."""
    import inspect
    sig = inspect.signature(ReportAgent.extract_claims_from_content)
    assert "cohort_table" in sig.parameters
    # L'appelant interne transmet cohort_table=cohort_table
    src = inspect.getsource(ReportAgent.audit_and_save_report_claims)
    assert "cohort_table=cohort_table" in src


def test_silence_marker_in_claim_text():
    """AC1/AC4 (prose) : le marqueur d'inhibition est présent dans le texte de l'affirmation."""
    sample_md = "- Round 2 : Agent Émilie a publié un tweet d'indignation evt_twitter_2_1_abc."
    agent = ReportAgent(graph_id="g", simulation_id="sim_silence", simulation_requirement="test", locale="fr")
    table = _silent_table()
    claims = agent.extract_claims_from_content(sample_md, cohort_table=table)
    silent_claims = [c for c in claims if (c.agent_name or "").lower() == "émilie"]
    assert silent_claims, "aucun claim extrait pour le silencieux"
    for c in silent_claims:
        assert "inhibé" in (c.text or "")
        assert "Règle de silence" in " ".join(c.limitations or [])