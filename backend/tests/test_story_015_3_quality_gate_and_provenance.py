"""Suite de tests unitaires et d'intégration hermétiques pour la Story 015-3 (FR-04, C3, C7, AT-12..AT-14).

Couvre :
- AC1 : Fermeture de l'angle mort « rapport conceptuel » quand 100 % des actions affirmées sont déclassées.
- AC2 : Calcul de action_ratio avec pour dénominateur l'ensemble des actions affirmées (asserted_actions).
- AC3 : Filet Markdown anti-contournement quand asserted_actions == 0 mais la prose narre des actions simulées.
- AC4 : Contrat structurel ReportSection.section_role et propagation dans ReportOutline / plan_outline.
- AC5 : Validation de QualityCategory.LIMITATIONS_SECTION par section_role="limitations" et repli rétrocompatible v1.
- AC6 : Détection d'adoption (ADOPTED_VERIFIED) par frontières de mots sans faux positifs par sous-chaîne.
- AC7 : Suppression du littéral statique et calcul 100 % honnête de la sous-section 3 dans build_sources_provenance_section.
- AC8 : Qualification directe sur la structure exacte du cas R8 (report_934d3254004b / sim_7a1b02b8c092).
- AC9 : Alignement des compteurs d'actions vérifiées dans report_history.json.
"""

from __future__ import annotations

import json
import os
import unittest.mock
from unittest.mock import MagicMock, patch

import pytest

from app.models.cohort_coverage import (
    CohortCoverageTable,
    CohortMemberStatus,
    DecisionStatus,
    ScenarioRole,
)
from app.models.report_claim import (
    ClaimKind,
    InformationOrigin,
    ProvenanceRegime,
    ReportClaim,
    ReportClaimRegistry,
    VerificationStatus,
)
from app.models.report_quality import (
    PublicationStatus,
    QualityCategory,
    QualityGateResult,
    QualityStatus,
)
from app.services.report_agent import (
    ReportAgent,
    ReportManager,
    ReportOutline,
    ReportSection,
    _get_default_outline,
)
from app.services.report_quality_gate import (
    ReportQualityGate,
    _markdown_alleges_simulated_actions,
)


@pytest.fixture
def minimal_cohort_table() -> CohortCoverageTable:
    """Cohorte simple avec un rejet et une non-adoption pour tester limitations_section."""
    m1 = CohortMemberStatus(
        persona_name="Florence",
        scenario_role=ScenarioRole.PROSPECT,
        action_count=2,
        observed_event_ids=["evt_florence_1", "evt_florence_2"],
        decision_status=DecisionStatus.REJECTED,
        is_silent=False,
        objections=["Coût récurrent mensuel inadapté aux rentrées"],
    )
    m2 = CohortMemberStatus(
        persona_name="Sylvie",
        scenario_role=ScenarioRole.PROSPECT,
        action_count=1,
        observed_event_ids=["evt_sylvie_1"],
        decision_status=DecisionStatus.HESITANT,
        is_silent=False,
        objections=["Manque de phase de test préalable"],
    )
    return CohortCoverageTable(
        simulation_id="sim_test_015_3",
        members=[m1, m2],
    )


def test_ac1_all_downgraded_actions_fail_quality_gate_not_conceptual_warning(
    minimal_cohort_table: CohortCoverageTable,
):
    """AC1 : Si 100 % des actions affirmées sont déclassées, le QualityGate FAILED (jamais WARNING)."""
    # 2 claims créés comme actions mais déclassés faute de preuve (asserted_as_action=True, claim_kind=REPORTED_INTENTION)
    c1 = ReportClaim(
        claim_id="clm_1",
        text="Claire Dumont a publié un post de retour d'expérience",
        claim_kind=ClaimKind.REPORTED_INTENTION,
        origin=InformationOrigin.SIMULATION,
        verification_status=VerificationStatus.UNSUPPORTED,
        asserted_as_action=True,
        evidence_refs=[],
    )
    c2 = ReportClaim(
        claim_id="clm_2",
        text="Florence a souscrit à l'offre après discussion",
        claim_kind=ClaimKind.SPECULATIVE_PROJECTION,
        origin=InformationOrigin.SIMULATION,
        verification_status=VerificationStatus.UNSUPPORTED,
        asserted_as_action=True,
        evidence_refs=[],
    )
    registry = ReportClaimRegistry(simulation_id="sim_ac1", claims=[c1, c2])

    assert registry.asserted_action_claims == 2
    assert registry.verified_action_claims == 0
    # strict_action_claims est vide car les 2 sont déclassés
    assert len([c for c in registry.claims if c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION]) == 0

    gate = ReportQualityGate(
        simulation_id="sim_ac1", report_id="rep_ac1", locale="fr"
    )
    markdown = (
        "## Contexte\n\nAnalyse générale.\n\n"
        "## Objections et limites\n\nDes limites et verrous substantiels ont été identifiés dans la cohorte avec plusieurs refus nets observés.\n\n"
        "## Sources & Provenance\n\nTraçabilité d'audit."
    )
    res = gate.evaluate_report(
        outline=None,
        report_markdown=markdown,
        cohort_table=minimal_cohort_table,
        claims_registry=registry,
    )

    claim_check = next(
        c for c in res.checks if c.category == QualityCategory.CLAIM_VERIFICATION
    )
    assert claim_check.status == QualityStatus.FAILED
    assert "Absence totale de preuves authentiques" in claim_check.message
    assert claim_check.details["r6_anomaly_detected"] is True
    assert claim_check.details["asserted_action_claims"] == 2
    assert claim_check.details["downgraded_action_claims"] == 2
    assert claim_check.details["verified_action_claims"] == 0
    assert res.is_publishable is False
    assert res.publication_status == PublicationStatus.FAILED_VALIDATION


def test_ac2_action_ratio_uses_all_asserted_actions_as_denominator(
    minimal_cohort_table: CohortCoverageTable,
):
    """AC2 : action_ratio a pour dénominateur len(asserted_actions) (ex: 1 vérifié sur 10 affirmés = 10 % < 50 % -> FAILED)."""
    claims = []
    # 1 action vérifiée
    claims.append(
        ReportClaim(
            claim_id="clm_v1",
            text="Alice a publié un message sur Reddit",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            verification_status=VerificationStatus.VERIFIED,
            asserted_as_action=True,
            evidence_refs=["evt_reddit_1"],
        )
    )
    # 9 actions déclassées en REPORTED_INTENTION non prouvées
    for i in range(2, 11):
        claims.append(
            ReportClaim(
                claim_id=f"clm_d{i}",
                text=f"Agent_{i} a souscrit au service en ligne",
                claim_kind=ClaimKind.REPORTED_INTENTION,
                origin=InformationOrigin.SIMULATION,
                verification_status=VerificationStatus.UNSUPPORTED,
                asserted_as_action=True,
                evidence_refs=[],
            )
        )
    registry = ReportClaimRegistry(simulation_id="sim_ac2", claims=claims)

    assert registry.asserted_action_claims == 10
    assert registry.verified_action_claims == 1

    gate = ReportQualityGate(
        simulation_id="sim_ac2", report_id="rep_ac2", locale="fr"
    )
    markdown = (
        "## Contexte\n\nAnalyse générale.\n\n"
        "## Objections et limites\n\nDes limites et réserves majeures ont été constatées dans la cohorte avec plusieurs refus.\n\n"
    )
    res = gate.evaluate_report(
        outline=None,
        report_markdown=markdown,
        cohort_table=minimal_cohort_table,
        claims_registry=registry,
    )

    claim_check = next(
        c for c in res.checks if c.category == QualityCategory.CLAIM_VERIFICATION
    )
    assert claim_check.status == QualityStatus.FAILED
    assert "Taux de vérification des actions simulées insuffisant" in claim_check.message
    assert claim_check.details["action_claims"] == 10
    assert claim_check.details["verified_action_claims"] == 1
    assert pytest.approx(claim_check.details["action_verification_ratio"], 0.01) == 0.10
    assert res.is_publishable is False


def test_ac3_zero_asserted_actions_with_narrative_action_prose_fails_gate(
    minimal_cohort_table: CohortCoverageTable,
):
    """AC3 : Si asserted_actions == 0 mais que le Markdown narre des actions simulées, le Gate FAILED."""
    # Registre avec seulement des hypothèses/inférences d'analyste
    c1 = ReportClaim(
        claim_id="clm_hyp1",
        text="L'hypothèse de conversion à 29€ est testée",
        claim_kind=ClaimKind.SCENARIO_HYPOTHESIS,
        origin=InformationOrigin.HYPOTHESIS,
        verification_status=VerificationStatus.VERIFIED,
        asserted_as_action=False,
    )
    registry = ReportClaimRegistry(simulation_id="sim_ac3", claims=[c1])

    # Cas A : Prose frauduleuse qui relate des actions d'agent exécutées dans les rounds
    markdown_fraud = (
        "## Déroulement de la simulation\n\n"
        "Durant le round 2, @ Claire_Dumont a publié un post sur Reddit et a souscrit à l'offre Essentiel.\n\n"
        "## Objections et limites\n\nDes refus nets et des réserves fortes ont été constatés parmi les membres de la cohorte.\n\n"
        "## Sources & Provenance\n\nTraçabilité."
    )
    gate = ReportQualityGate("sim_ac3", "rep_ac3", locale="fr")
    res_fraud = gate.evaluate_report(
        outline=None,
        report_markdown=markdown_fraud,
        cohort_table=minimal_cohort_table,
        claims_registry=registry,
    )
    claim_check_fraud = next(
        c for c in res_fraud.checks if c.category == QualityCategory.CLAIM_VERIFICATION
    )
    assert claim_check_fraud.status == QualityStatus.FAILED
    assert claim_check_fraud.details["unparseable_action_claims"] is True
    assert claim_check_fraud.details["r6_anomaly_detected"] is True

    # Cas B : Rapport purement théorique avec négation explicite -> WARNING (needs_review)
    markdown_clean = (
        "## Analyse théorique\n\n"
        "Ce document présente un modèle conceptuel sans actions simulées ni interactions directes d'agents.\n\n"
        "## Objections et limites\n\nLimites méthodologiques et réserves théoriques sur le modèle exploratoire.\n\n"
        "## Sources & Provenance\n\nDocumentation."
    )
    res_clean = gate.evaluate_report(
        outline=None,
        report_markdown=markdown_clean,
        cohort_table=minimal_cohort_table,
        claims_registry=registry,
    )
    claim_check_clean = next(
        c for c in res_clean.checks if c.category == QualityCategory.CLAIM_VERIFICATION
    )
    assert claim_check_clean.status == QualityStatus.WARNING
    assert "Rapport conceptuel sans allégation d'actions observées" in claim_check_clean.message


def test_ac4_report_section_role_serialization_and_plan_outline_assignment():
    """AC4 : section_role est sérialisé/désérialisé rétrocompatiblement et assigné dans plan_outline."""
    # 1. Vérification ReportSection to_dict / from_dict
    s_v2 = ReportSection(
        title="Limites et verrous", content="Corps", section_role="limitations"
    )
    d_v2 = s_v2.to_dict()
    assert d_v2["section_role"] == "limitations"
    loaded_v2 = ReportSection.from_dict(d_v2)
    assert loaded_v2.section_role == "limitations"

    # Rétrocompatibilité v1 (dictionnaire sans section_role)
    d_v1 = {"title": "Titre v1", "content": "Corps v1"}
    loaded_v1 = ReportSection.from_dict(d_v1)
    assert loaded_v1.title == "Titre v1"
    assert loaded_v1.section_role is None
    assert "section_role" not in loaded_v1.to_dict()

    # Normalisation str.strip().lower()
    s_dirty = ReportSection(title="T", section_role="  LIMITATIONS  ")
    assert s_dirty.section_role == "limitations"

    # 2. _get_default_outline assigne les 3 rôles canoniques
    default_outline = _get_default_outline()
    assert len(default_outline.sections) == 3
    assert default_outline.sections[0].section_role == "overview"
    assert default_outline.sections[1].section_role == "analysis"
    assert default_outline.sections[2].section_role == "limitations"

    # 3. Relecture via ReportManager.get_report
    fake_report_json = json.dumps({
        "report_id": "rep_test_restore",
        "simulation_id": "sim_test_restore",
        "title": "Grand Titre",
        "markdown_content": "## Contenu",
        "outline": {
            "title": "Grand Titre",
            "summary": "Résumé",
            "sections": [
                {
                    "title": "Verrous réels",
                    "content": "ABC",
                    "section_role": "limitations",
                },
                {"title": "Section historique", "content": "DEF"},
            ],
        },
    })
    with patch("os.path.exists", return_value=True), patch("builtins.open", unittest.mock.mock_open(read_data=fake_report_json)):
        restored = ReportManager.get_report("rep_test_restore")
        assert restored is not None
        assert restored.outline is not None
        assert restored.outline.sections[0].section_role == "limitations"
        assert restored.outline.sections[1].section_role is None

    # 4. Attribution de section_role="limitations" par plan_outline sur marqueur fort sans doublon
    agent = ReportAgent.__new__(ReportAgent)
    agent.simulation_id = "sim_test_plan"
    agent.graph_id = "graph_test"
    agent.simulation_requirement = "Tester l'offre"
    agent.locale = "fr"
    agent.zep_tools = MagicMock()
    agent.zep_tools.get_simulation_context.return_value = {
        "graph_statistics": {"total_nodes": 5, "total_edges": 4, "entity_types": {"Person": 3}},
        "total_entities": 5,
        "related_facts": [],
    }
    agent._resolve_project = MagicMock(return_value=None)

    class MockLLM:
        def __init__(self, sections_data):
            self.sections_data = sections_data

        def chat_json(self, *args, **kwargs):
            return {
                "title": "Rapport Test",
                "summary": "Résumé Test",
                "sections": self.sections_data,
            }

    # Cohorte avec un refus
    flo = CohortMemberStatus(
        persona_name="Florence",
        action_count=1,
        observed_event_ids=["evt_flo"],
        objections=["Prix trop élevé"],
        decision_status=DecisionStatus.REJECTED,
    )
    fake_cohort = CohortCoverageTable(simulation_id="sim_test_plan", members=[flo])

    with patch("app.models.cohort_coverage.CohortCoverageTable.build_from_simulation", return_value=fake_cohort):
        # Cas A : section 3 a le titre avec marqueur fort "Les verrous réels..." sans rôle explicite
        agent.llm = MockLLM([
            {"title": "1. Synthèse globale", "description": "Intro"},
            {"title": "2. Analyse détaillée", "description": "Analyse"},
            {"title": "3. Les verrous réels et leviers qui fonctionnent", "description": "Verrous"},
        ])
        outline_assigned = agent.plan_outline()
        assert len(outline_assigned.sections) == 3
        assert outline_assigned.sections[2].section_role == "limitations"

        # Cas B : aucune section n'a de marqueur de limites -> injection du repli canonique avec section_role="limitations"
        agent.llm = MockLLM([
            {"title": "1. Synthèse globale", "description": "Intro"},
            {"title": "2. Analyse détaillée", "description": "Analyse"},
        ])
        outline_injected = agent.plan_outline()
        assert len(outline_injected.sections) == 3
        assert outline_injected.sections[2].section_role == "limitations"
        assert "Objections non levées" in outline_injected.sections[2].title


def test_ac5_limitations_section_validated_by_role_and_v1_fallback(
    minimal_cohort_table: CohortCoverageTable,
):
    """AC5 : Validation par section_role='limitations' ou repli v1, et rejet si le contenu est vide ou non pertinent."""
    gate = ReportQualityGate("sim_ac5", "rep_ac5", locale="fr")

    # 1. Succès via rôle structurel section_role="limitations"
    outline_role = ReportOutline(
        title="T",
        summary="S",
        sections=[
            ReportSection(
                title="Les verrous réels et les leviers observés",
                section_role="limitations",
            )
        ],
    )
    md_valid = (
        "## Introduction\n\nIntro.\n\n"
        "## Les verrous réels et les leviers observés\n\n"
        "Des blocages substantiels, des verrous majeurs et deux refus fermes ont été documentés dans la cohorte.\n\n"
        "## Sources & Provenance\n\nAudit."
    )
    res_role = gate.evaluate_report(
        outline=outline_role,
        report_markdown=md_valid,
        cohort_table=minimal_cohort_table,
    )
    c_role = next(
        c
        for c in res_role.checks
        if c.category == QualityCategory.LIMITATIONS_SECTION
    )
    assert c_role.status == QualityStatus.PASSED
    assert c_role.details["limitations_role_matched"] is True
    assert (
        c_role.details["matched_section_title"]
        == "Les verrous réels et les leviers observés"
    )

    # 2. Succès via repli v1 sans outline mais avec titre et corps contenant des marqueurs de limites
    res_v1 = gate.evaluate_report(
        outline=None,
        report_markdown=md_valid,
        cohort_table=minimal_cohort_table,
    )
    c_v1 = next(
        c
        for c in res_v1.checks
        if c.category == QualityCategory.LIMITATIONS_SECTION
    )
    assert c_v1.status == QualityStatus.PASSED
    assert c_v1.details["limitations_heading_present"] is True

    # 3. Échec si la section taguée limitations fait < 50 caractères
    md_too_short = (
        "## Les verrous réels et les leviers observés\n\n"
        "Trop court.\n\n"
        "## Sources & Provenance\n\nAudit."
    )
    res_short = gate.evaluate_report(
        outline=outline_role,
        report_markdown=md_too_short,
        cohort_table=minimal_cohort_table,
    )
    c_short = next(
        c
        for c in res_short.checks
        if c.category == QualityCategory.LIMITATIONS_SECTION
    )
    assert c_short.status == QualityStatus.FAILED

    # 4. Échec si la section taguée limitations ne contient aucun lexique d'objections/limites/refus/verrous dans son corps
    # Même avec un titre explicite "Les verrous réels...", le corps doit traiter des limites (invariant AC5)
    md_no_lexicon = (
        "## Les verrous réels et les leviers observés\n\n"
        "Tout le monde est extrêmement heureux, le produit est parfait, la conversion est totale et sans accroc.\n\n"
        "## Sources & Provenance\n\nAudit."
    )
    res_no_lex = gate.evaluate_report(
        outline=outline_role,
        report_markdown=md_no_lexicon,
        cohort_table=minimal_cohort_table,
    )
    c_no_lex = next(
        c
        for c in res_no_lex.checks
        if c.category == QualityCategory.LIMITATIONS_SECTION
    )
    assert c_no_lex.status == QualityStatus.FAILED

    # 5. Support de la locale chinoise zh avec idéogrammes d'objections/limites
    gate_zh = ReportQualityGate("sim_ac5_zh", "rep_ac5_zh", locale="zh")
    outline_zh = {
        "title": "测试报告",
        "sections": [
            {"title": "概述", "content": "内容", "section_role": "overview"},
            {"title": "分析", "content": "内容", "section_role": "analysis"},
            {"title": "趋势展望与风险提示", "content": "详细内容", "section_role": "limitations"},
        ],
    }
    md_zh = (
        "## 概述\n\n正常概述内容。\n\n"
        "## 趋势展望与风险提示\n\n在本模拟中，我们观察到多重显著风险与异议，部分用户明确拒绝采纳并提出了实质性阻碍，需要深入跟进与解决。\n\n"
        "## 数据来源与证明\n\n审计。"
    )
    res_zh = gate_zh.evaluate_report(
        outline=outline_zh,
        report_markdown=md_zh,
        cohort_table=minimal_cohort_table,
    )
    lim_zh = next(
        c for c in res_zh.checks if c.category == QualityCategory.LIMITATIONS_SECTION
    )
    assert lim_zh.status == QualityStatus.PASSED
    assert lim_zh.details["limitations_role_matched"] is True


def test_ac6_adoption_detection_word_boundaries_and_negation_guard():
    """AC6 : La détection d'adoption n'a pas de faux positifs sur 'signal', 'souligne' ou 'n'a pas adopté'."""
    # Cohorte avec 0 membre ADOPTED_VERIFIED
    m1 = CohortMemberStatus(
        persona_name="Florence",
        scenario_role=ScenarioRole.PROSPECT,
        action_count=1,
        observed_event_ids=["evt_florence_1"],
        decision_status=DecisionStatus.REJECTED,
    )
    cohort = CohortCoverageTable(simulation_id="sim_ac6", members=[m1])

    # Claim vérifié contenant "signal" et "souligne" (qui matchaient l'ancien substring 'sign')
    c1 = ReportClaim(
        claim_id="clm_1",
        text="Florence souligne un signal d'alerte sur le coût récurrent",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        verification_status=VerificationStatus.VERIFIED,
        evidence_refs=["evt_1"],
    )
    # Claim vérifié avec négation explicite
    c2 = ReportClaim(
        claim_id="clm_2",
        text="Nathalie n'a pas adopté l'offre à 29 euros",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        verification_status=VerificationStatus.VERIFIED,
        evidence_refs=["evt_2"],
    )
    registry = ReportClaimRegistry(simulation_id="sim_ac6", claims=[c1, c2])

    gate = ReportQualityGate("sim_ac6", "rep_ac6", locale="fr")
    md = "## Objections et limites\n\nDes limites et refus substantiels ont été identifiés dans la cohorte.\n\n"
    res = gate.evaluate_report(
        outline=None,
        report_markdown=md,
        cohort_table=cohort,
        claims_registry=registry,
    )
    claim_check = next(
        c for c in res.checks if c.category == QualityCategory.CLAIM_VERIFICATION
    )
    # Pas d'affabulation d'adoption détectée
    assert "unverified_adoptions" not in claim_check.details

    # En revanche, si la cohorte a un membre ADOPTED_VERIFIED mais que le claim d'adoption est non vérifié ou manquant
    m_adopted = CohortMemberStatus(
        persona_name="Chloé",
        scenario_role=ScenarioRole.PROSPECT,
        action_count=1,
        observed_event_ids=["evt_chloe_1"],
        decision_status=DecisionStatus.ADOPTED_VERIFIED,
    )
    cohort_with_adopted = CohortCoverageTable(
        simulation_id="sim_ac6_adopt", members=[m_adopted]
    )
    res_adopt_fail = gate.evaluate_report(
        outline=None,
        report_markdown=md,
        cohort_table=cohort_with_adopted,
        claims_registry=registry,  # Aucun claim d'adoption probant
    )
    claim_check_fail = next(
        c
        for c in res_adopt_fail.checks
        if c.category == QualityCategory.CLAIM_VERIFICATION
    )
    assert claim_check_fail.status == QualityStatus.FAILED
    assert claim_check_fail.details.get("unverified_adoptions") is True

    # 3. Test positif : claim d'adoption VERIFIED avec evt_* et agent_name correspondant à un persona adopté (persona_name)
    c_valid_adopt = ReportClaim(
        claim_id="clm_adopt_valid",
        text="Chloé a souscrit à l'offre Keova après son analyse",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        verification_status=VerificationStatus.VERIFIED,
        evidence_refs=["evt_chloe_1"],
        agent_name="Chloé",
        asserted_as_action=True,
    )
    registry_valid = ReportClaimRegistry(simulation_id="sim_ac6_ok", claims=[c_valid_adopt])
    res_adopt_pass = gate.evaluate_report(
        outline=None,
        report_markdown=md,
        cohort_table=cohort_with_adopted,
        claims_registry=registry_valid,
    )
    claim_check_pass = next(
        c for c in res_adopt_pass.checks if c.category == QualityCategory.CLAIM_VERIFICATION
    )
    assert "unverified_adoptions" not in claim_check_pass.details
    assert claim_check_pass.status == QualityStatus.PASSED

    # 4. Test affabulation : si adopted_count == 0 mais qu'un claim affirme que Chloé a souscrit (AC6)
    c_false_adopt = ReportClaim(
        claim_id="clm_adopt_fraud",
        text="Chloé a souscrit à l'offre Keova au round 2",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        verification_status=VerificationStatus.VERIFIED,
        evidence_refs=["evt_chloe_fake"],
        agent_name="Chloé",
        asserted_as_action=True,
    )
    registry_false = ReportClaimRegistry(simulation_id="sim_ac6_zero", claims=[c_false_adopt])
    res_adopt_zero = gate.evaluate_report(
        outline=None,
        report_markdown=md,
        cohort_table=cohort,  # adopted_count == 0
        claims_registry=registry_false,
    )
    claim_check_zero = next(
        c for c in res_adopt_zero.checks if c.category == QualityCategory.CLAIM_VERIFICATION
    )
    assert claim_check_zero.status == QualityStatus.FAILED
    assert claim_check_zero.details.get("unverified_adoptions") is True
    assert claim_check_zero.details.get("adoption_affabulation") is True


def test_ac7_sources_provenance_subsection3_is_fully_computed_and_matches_subsection7():
    """AC7 : build_sources_provenance_section n'émet plus de chaîne statique et calcule la règle anti-affabulation."""
    agent = ReportAgent.__new__(ReportAgent)
    agent.simulation_id = "sim_ac7"
    agent._current_report_id = "rep_ac7"
    agent.graph_id = "graph_test"
    agent.action_verifier = MagicMock()
    agent.action_verifier.load_simulation_actions.return_value = []
    agent.action_verifier.analyze_intentions.return_value = []
    agent._resolve_project = MagicMock(return_value=None)

    # Cas 1 : claims_registry is None
    sec1 = agent.build_sources_provenance_section(claims_registry=None)
    assert "Toute affirmation qualifiée d'action observée est reliée" not in sec1
    assert (
        "- **Règle anti-affabulation :** Traçabilité non établie (registre d'affirmations absent ou illisible"
        in sec1
    )

    # Cas 2 : Registre avec 12 actions affirmées et 0 vérifiée (cas R8)
    claims_r8 = [
        ReportClaim(
            claim_id=f"c_{i}",
            text=f"Action {i}",
            claim_kind=ClaimKind.REPORTED_INTENTION,
            origin=InformationOrigin.SIMULATION,
            verification_status=VerificationStatus.UNSUPPORTED,
            asserted_as_action=True,
        )
        for i in range(12)
    ]
    reg_r8 = ReportClaimRegistry(simulation_id="sim_ac7_r8", claims=claims_r8)
    sec2 = agent.build_sources_provenance_section(claims_registry=reg_r8)
    assert "Toute affirmation qualifiée d'action observée est reliée" not in sec2
    assert "0/12 vérifiée(s) par un événement horodaté du run" in sec2
    assert "- **Actions sociales affirmées (`asserted_as_action`) :** 12." in sec2
    assert (
        "- **Actions sociales vérifiées (`OBSERVED_SOCIAL_ACTION` + `VERIFIED`) :** 0."
        in sec2
    )

    # Cas 3 : Couverture partielle (2/4 vérifiées)
    claims_part = [
        ReportClaim(
            claim_id="c_v1",
            text="Action V1",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            verification_status=VerificationStatus.VERIFIED,
            asserted_as_action=True,
            evidence_refs=["evt_1"],
        ),
        ReportClaim(
            claim_id="c_v2",
            text="Action V2",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            verification_status=VerificationStatus.VERIFIED,
            asserted_as_action=True,
            evidence_refs=["evt_2"],
        ),
        ReportClaim(
            claim_id="c_u1",
            text="Action U1",
            claim_kind=ClaimKind.REPORTED_INTENTION,
            origin=InformationOrigin.SIMULATION,
            verification_status=VerificationStatus.UNSUPPORTED,
            asserted_as_action=True,
        ),
        ReportClaim(
            claim_id="c_u2",
            text="Action U2",
            claim_kind=ClaimKind.REPORTED_INTENTION,
            origin=InformationOrigin.SIMULATION,
            verification_status=VerificationStatus.UNSUPPORTED,
            asserted_as_action=True,
        ),
    ]
    reg_part = ReportClaimRegistry(simulation_id="sim_ac7_part", claims=claims_part)
    sec3 = agent.build_sources_provenance_section(claims_registry=reg_part)
    assert "Toute affirmation qualifiée d'action observée est reliée" not in sec3
    assert (
        "Couverture partielle des preuves d'action — 2/4 affirmation(s) d'action affirmée sont reliées à un événement horodaté du run (50.0 %)"
        in sec3
    )
    assert "- **Actions sociales affirmées (`asserted_as_action`) :** 4." in sec3
    assert (
        "- **Actions sociales vérifiées (`OBSERVED_SOCIAL_ACTION` + `VERIFIED`) :** 2."
        in sec3
    )

    # Cas 4 : 100 % vérifiées (5/5)
    claims_full = [
        ReportClaim(
            claim_id=f"cf_{i}",
            text=f"Action F{i}",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            verification_status=VerificationStatus.VERIFIED,
            asserted_as_action=True,
            evidence_refs=[f"evt_{i}"],
        )
        for i in range(5)
    ]
    reg_full = ReportClaimRegistry(simulation_id="sim_ac7_full", claims=claims_full)
    sec4 = agent.build_sources_provenance_section(claims_registry=reg_full)
    assert (
        "Les 5/5 affirmation(s) d'action observée du registre sont reliées à un événement horodaté du run (100.0 % vérifiées)."
        in sec4
    )
    assert "- **Actions sociales affirmées (`asserted_as_action`) :** 5." in sec4
    assert (
        "- **Actions sociales vérifiées (`OBSERVED_SOCIAL_ACTION` + `VERIFIED`) :** 5."
        in sec4
    )

    # 5. Test direct de la fonction pure _format_anti_affabulation_status
    from app.services.report_agent import _format_anti_affabulation_status
    assert "Traçabilité non établie" in _format_anti_affabulation_status(None)
    assert "0 action affirmée, 0 action vérifiée" in _format_anti_affabulation_status(ReportClaimRegistry(simulation_id="s", claims=[]))
    assert "100.0 % vérifiées" in _format_anti_affabulation_status(reg_full)
    assert "Couverture partielle" in _format_anti_affabulation_status(reg_part)


def test_ac8_r8_report_934d3254004b_exact_regression_verification():
    """AC8 : Vérification de non-régression directe sur les artefacts exacts de R8 (report_934d3254004b)."""
    fixture_dir = os.path.join(
        os.path.dirname(__file__), "fixtures", "r8_report_934d3254004b"
    )
    upload_dir = os.path.join(
        os.path.dirname(__file__), "..", "uploads", "reports", "report_934d3254004b"
    )
    base_dir = fixture_dir if os.path.exists(fixture_dir) else upload_dir
    assert os.path.exists(base_dir), f"Le dossier d'artefacts R8 {base_dir} doit exister pour garantir l'herméticité de l'audit."

    with open(os.path.join(base_dir, "full_report.md"), "r", encoding="utf-8") as f:
        report_md = f.read()
    with open(os.path.join(base_dir, "outline.json"), "r", encoding="utf-8") as f:
        outline_dict = json.load(f)
    with open(
        os.path.join(base_dir, "cohort_coverage.json"), "r", encoding="utf-8"
    ) as f:
        cohort = CohortCoverageTable.from_dict(json.load(f))
    with open(
        os.path.join(base_dir, "report_claims.json"), "r", encoding="utf-8"
    ) as f:
        registry = ReportClaimRegistry.from_dict(json.load(f))

    gate = ReportQualityGate(
        simulation_id="sim_7a1b02b8c092",
        report_id="report_934d3254004b",
        locale="fr",
    )
    res = gate.evaluate_report(
        outline=outline_dict,
        report_markdown=report_md,
        cohort_table=cohort,
        claims_registry=registry,
    )

    limitations_check = next(
        c for c in res.checks if c.category == QualityCategory.LIMITATIONS_SECTION
    )
    claim_check = next(
        c for c in res.checks if c.category == QualityCategory.CLAIM_VERIFICATION
    )

    # 1. LIMITATIONS_SECTION passe désormais à PASSED grâce à la reconnaissance de la section 'Les verrous réels...'
    assert limitations_check.status == QualityStatus.PASSED

    # 2. CLAIM_VERIFICATION passe désormais à FAILED (et non plus WARNING)
    assert claim_check.status == QualityStatus.FAILED
    assert res.is_publishable is False
    assert res.publication_status == PublicationStatus.FAILED_VALIDATION

    # 3. build_sources_provenance_section n'affiche plus l'auto-contradiction
    agent = ReportAgent.__new__(ReportAgent)
    agent.simulation_id = "sim_7a1b02b8c092"
    agent._current_report_id = "report_934d3254004b"
    agent.graph_id = "graph_test"
    agent.action_verifier = MagicMock()
    agent.action_verifier.load_simulation_actions.return_value = []
    agent.action_verifier.analyze_intentions.return_value = []
    agent._resolve_project = MagicMock(return_value=None)

    sec = agent.build_sources_provenance_section(claims_registry=registry)
    assert "Toute affirmation qualifiée d'action observée est reliée" not in sec


def test_ac9_report_history_counts_only_verified_social_actions(tmp_path, monkeypatch):
    """AC9 : report_history.json n'enregistre en verified_action_claims_count que les actions sociales vérifiées."""
    from app.config import Config
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

    # Simulation d'un registre contenant 3 claims SCENARIO_HYPOTHESIS vérifiés et 2 actions affirmées mais UNSUPPORTED
    c_hyp = [
        ReportClaim(
            claim_id=f"h_{i}",
            text=f"Hypothèse {i}",
            claim_kind=ClaimKind.SCENARIO_HYPOTHESIS,
            origin=InformationOrigin.HYPOTHESIS,
            verification_status=VerificationStatus.VERIFIED,
            asserted_as_action=False,
        )
        for i in range(3)
    ]
    c_act = [
        ReportClaim(
            claim_id=f"a_{i}",
            text=f"Action {i}",
            claim_kind=ClaimKind.REPORTED_INTENTION,
            origin=InformationOrigin.SIMULATION,
            verification_status=VerificationStatus.UNSUPPORTED,
            asserted_as_action=True,
        )
        for i in range(2)
    ]
    registry = ReportClaimRegistry(simulation_id="sim_ac9", claims=c_hyp + c_act)

    assert registry.verified_claims == 3
    assert registry.asserted_action_claims == 2
    assert registry.verified_action_claims == 0

    # Simuler la construction de hist_entry comme dans ReportAgent.generate_report
    hist_entry = {
        "report_id": "rep_test_hist",
        "simulation_id": "sim_ac9",
        "total_claims": registry.total_claims,
        "supported_claims": registry.verified_claims,
        "asserted_action_claims_count": getattr(
            registry, "asserted_action_claims", 0
        ),
        "verified_action_claims_count": getattr(
            registry, "verified_action_claims", 0
        ),
    }

    # Persister réellement via ReportManager._append_to_history
    ReportManager._append_to_history("sim_ac9", hist_entry)

    # Relire depuis le disque via ReportManager._load_history
    history = ReportManager._load_history("sim_ac9")
    reports = history.get("reports", [])
    assert len(reports) == 1
    assert reports[0]["supported_claims"] == 3
    assert reports[0]["asserted_action_claims_count"] == 2
    assert reports[0]["verified_action_claims_count"] == 0
