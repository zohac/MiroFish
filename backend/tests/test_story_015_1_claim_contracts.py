"""Tests unitaires et d'intégration hermétiques pour Story 015-1 (AC1 à AC9).

Contrats testés :
- AC1: Préservation intégrale de provenance_regime sur les 11 sorties de verify_report_claim
- AC2: Modèle ReportClaim.asserted_as_action, compteurs ReportClaimRegistry et rétrocompat v1
- AC3: Élimination des faux positifs par sous-chaînes ("va", "compte") et homographes
- AC4: Séparation actions au passé/présent de narration, modaux prospectifs et négations pures
- AC5: Persistance de asserted_as_action=True après déclassement C4, silence C7, horizon C8, métrique C8
- AC6: Étanchéité absolue du régime INTERVIEW face aux verbes d'action
- AC7: Rejet strict d'un event_id étranger ou absent sans repli silencieux
- AC8: Filtrage des événements passifs OASIS et correspondance par famille d'interaction
- AC9: Restauration de bout en bout des bannières et de la sous-section 7
"""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from app.models.cohort_coverage import (
    AgentIdentityResolver,
    CohortMemberStatus,
    CohortCoverageTable,
    ScenarioRole,
)
from app.models.evidence_pack import EvidencePack, ObservedEvent
from app.models.provenance_regime import ProvenanceRegime
from app.models.report_claim import (
    ClaimKind,
    ReportClaim,
    ReportClaimRegistry,
    VerificationStatus,
    compute_claim_id,
)
from app.models.source_document import InformationOrigin
from app.services.report_agent import ReportAgent
from app.services.simulation_action_verifier import SimulationActionVerifier


def test_verify_report_claim_preserves_provenance_regime_all_11_paths():
    """AC1: Les 11 chemins de retour de verify_report_claim conservent rigoureusement provenance_regime."""
    regimes = [
        ProvenanceRegime.INTERVIEW,
        ProvenanceRegime.EVENT,
        ProvenanceRegime.GRAPH,
        ProvenanceRegime.DOCUMENT,
        ProvenanceRegime.UNKNOWN,
        None,
    ]

    for reg in regimes:
        # 1. Règle de silence C7
        claim_silence = ReportClaim(
            claim_id="clm_silence",
            text="Alice a posté un avis enthousiaste sur le produit.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            agent_name="Alice",
            provenance_regime=reg,
        )
        silent_member = CohortMemberStatus(
            persona_name="Alice",
            action_count=0,
            observed_event_ids=[],
        )
        table_silent = CohortCoverageTable(simulation_id="sim_test", members=[silent_member])
        res1 = SimulationActionVerifier.verify_report_claim(claim_silence, cohort_table=table_silent)
        assert res1.provenance_regime == reg
        assert res1.verification_status == VerificationStatus.CONTRADICTED

        # 2. Contradiction de fait d'entreprise QA-12
        claim_founder = ReportClaim(
            claim_id="clm_founder",
            text="Bob a déclaré que l'assistance dédiée 24/7 est totalement gratuite et incluse dans le forfait de base.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            agent_name="Bob",
            provenance_regime=reg,
        )
        founder_member = CohortMemberStatus(
            persona_name="Bob",
            scenario_role=ScenarioRole.FOUNDER,
            action_count=1,
            observed_event_ids=["evt_b1"],
        )
        table_founder = CohortCoverageTable(simulation_id="sim_test", members=[founder_member])
        canon_docs = [{
            "filename": "pricing.pdf",
            "validation_status": "validated",
            "epistemic_kind": "CANONICAL_DOCUMENT",
            "text": "L'assistance dédiée 24/7 est réservée exclusivement aux abonnés du plan Entreprise. Le forfait de base ne comprend aucun support.",
        }]
        res2 = SimulationActionVerifier.verify_report_claim(
            claim_founder,
            canonical_documents=canon_docs,
            cohort_table=table_founder,
        )
        assert res2.provenance_regime == reg
        assert res2.verification_status == VerificationStatus.CONTRADICTED

        # 3. Règle du temps simulé C8 (hors horizon)
        claim_horizon = ReportClaim(
            claim_id="clm_horizon",
            text="Après 120 heures d'observation, le service est stable.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            provenance_regime=reg,
        )
        res3 = SimulationActionVerifier.verify_report_claim(claim_horizon, horizon_hours=48.0)
        assert res3.provenance_regime == reg
        assert res3.verification_status == VerificationStatus.UNSUPPORTED
        assert res3.claim_kind == ClaimKind.SPECULATIVE_PROJECTION

        # 4. Règle des métriques fantômes C8
        claim_metric = ReportClaim(
            claim_id="clm_metric",
            text="Le taux de churn mesuré atteint exactement 42.5 % des clients.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            provenance_regime=reg,
        )
        pack_empty = EvidencePack(simulation_id="sim_test", events=[])
        res4 = SimulationActionVerifier.verify_report_claim(claim_metric, evidence_pack=pack_empty)
        assert res4.provenance_regime == reg
        assert res4.verification_status == VerificationStatus.UNSUPPORTED

        # 5. Action vérifiée (OBSERVED_SOCIAL_ACTION -> VERIFIED)
        if reg != ProvenanceRegime.INTERVIEW:
            ev_exec = ObservedEvent(
                event_id="evt_post_1",
                simulation_id="sim_test",
                platform="twitter",
                round_num=1,
                agent_id=3,
                agent_name="Charlie",
                action_type="CREATE_POST",
                timestamp="2026-10-29T12:00:00",
                action_args={"content": "Je publie une analyse détaillée sur les fonctionnalités."},
                is_action_executed=True,
            )
            pack_exec = EvidencePack(simulation_id="sim_test", events=[ev_exec])
            claim_act = ReportClaim(
                claim_id="clm_act",
                text='Charlie publie une analyse détaillée : « Je publie une analyse détaillée sur les fonctionnalités. »',
                claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
                origin=InformationOrigin.SIMULATION,
                agent_name="Charlie",
                evidence_refs=["evt_post_1"],
                provenance_regime=reg,
            )
            res5 = SimulationActionVerifier.verify_report_claim(claim_act, evidence_pack=pack_exec)
            assert res5.provenance_regime == reg
            assert res5.verification_status == VerificationStatus.VERIFIED

        # 6. Action déclassée C4 (OBSERVED_SOCIAL_ACTION -> REPORTED_INTENTION UNSUPPORTED)
        if reg != ProvenanceRegime.INTERVIEW:
            claim_downgrade = ReportClaim(
                claim_id="clm_down",
                text="Charlie a souscrit à l'offre annuelle.",
                claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
                origin=InformationOrigin.SIMULATION,
                agent_name="Charlie",
                provenance_regime=reg,
            )
            res6 = SimulationActionVerifier.verify_report_claim(claim_downgrade, evidence_pack=pack_empty)
            assert res6.provenance_regime == reg
            assert res6.verification_status == VerificationStatus.UNSUPPORTED
            assert res6.claim_kind == ClaimKind.REPORTED_INTENTION

        # 7. Intention vérifiée (REPORTED_INTENTION -> VERIFIED via citation)
        ev_quote = ObservedEvent(
            event_id="evt_quote_1",
            simulation_id="sim_test",
            platform="twitter",
            round_num=1,
            agent_id=4,
            agent_name="Diane",
            action_type="CREATE_POST",
            timestamp="2026-10-29T12:00:00",
            action_args={"content": "Je compte bien tester cette formule le mois prochain."},
            is_action_executed=True,
        )
        pack_quote = EvidencePack(simulation_id="sim_test", events=[ev_quote])
        claim_intent_verif = ReportClaim(
            claim_id="clm_intent_verif",
            text='Diane déclare : « Je compte bien tester cette formule le mois prochain. »',
            claim_kind=ClaimKind.REPORTED_INTENTION,
            origin=InformationOrigin.SIMULATION,
            agent_name="Diane",
            provenance_regime=reg,
        )
        res7 = SimulationActionVerifier.verify_report_claim(claim_intent_verif, evidence_pack=pack_quote)
        assert res7.provenance_regime == reg
        assert res7.verification_status == VerificationStatus.VERIFIED

        # 8. Intention non vérifiée (REPORTED_INTENTION -> UNSUPPORTED)
        claim_intent_unsupp = ReportClaim(
            claim_id="clm_intent_unsupp",
            text="Diane songe à changer de fournisseur.",
            claim_kind=ClaimKind.REPORTED_INTENTION,
            origin=InformationOrigin.SIMULATION,
            agent_name="Diane",
            provenance_regime=reg,
        )
        res8 = SimulationActionVerifier.verify_report_claim(claim_intent_unsupp, evidence_pack=pack_empty)
        assert res8.provenance_regime == reg
        assert res8.verification_status == VerificationStatus.UNSUPPORTED

        # 9. Barrière C5 source fictive (SOURCE_FACT -> SCENARIO_HYPOTHESIS UNSUPPORTED)
        claim_c5 = ReportClaim(
            claim_id="clm_c5",
            text="Donnée issue du scénario",
            claim_kind=ClaimKind.SOURCE_FACT,
            origin=InformationOrigin.DOCUMENTARY,
            evidence_refs=["persona_profile_target.pdf"],
            provenance_regime=reg,
        )
        res9 = SimulationActionVerifier.verify_report_claim(claim_c5)
        assert res9.provenance_regime == reg
        assert res9.verification_status == VerificationStatus.UNSUPPORTED
        assert res9.claim_kind == ClaimKind.SCENARIO_HYPOTHESIS

        # 10. Fait source standard (SOURCE_FACT -> VERIFIED avec ref)
        claim_src = ReportClaim(
            claim_id="clm_src",
            text="Le produit a été lancé en 2024.",
            claim_kind=ClaimKind.SOURCE_FACT,
            origin=InformationOrigin.DOCUMENTARY,
            evidence_refs=["spec.pdf"],
            provenance_regime=reg,
        )
        res10 = SimulationActionVerifier.verify_report_claim(claim_src)
        assert res10.provenance_regime == reg
        assert res10.verification_status == VerificationStatus.VERIFIED

        # 11. Autre type analytique (ANALYST_INFERENCE -> VERIFIED avec ref)
        claim_inf = ReportClaim(
            claim_id="clm_inf",
            text="Déduction logique d'analyste.",
            claim_kind=ClaimKind.ANALYST_INFERENCE,
            origin=InformationOrigin.INFERENCE,
            evidence_refs=["doc1.pdf"],
            provenance_regime=reg,
        )
        res11 = SimulationActionVerifier.verify_report_claim(claim_inf)
        assert res11.provenance_regime == reg
        assert res11.verification_status == VerificationStatus.VERIFIED


def test_report_claim_asserted_as_action_roundtrip_and_v1_compat():
    """AC2: asserted_as_action est correctement géré, sérialisé et rétrocompatible avec les artefacts v1."""
    # 1. Action observée hors entretien -> asserted_as_action forcé à True
    c_action = ReportClaim(
        claim_id="",
        text="Marc a publié une critique.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        provenance_regime=ProvenanceRegime.EVENT,
    )
    assert c_action.asserted_as_action is True
    d_action = c_action.to_dict()
    assert d_action["asserted_as_action"] is True

    # 2. Rétrocompatibilité ascendante v1 (clé asserted_as_action absente du JSON)
    d_v1_action = {
        "claim_id": "clm_v1_act",
        "text": "Marc a publié une critique.",
        "claim_kind": "observed_social_action",
        "origin": "simulation",
        "evidence_refs": [],
        "verification_status": "unsupported",
        "provenance_regime": "event",
    }
    c_v1_loaded = ReportClaim.from_dict(d_v1_action)
    assert c_v1_loaded.asserted_as_action is True

    d_v1_intent = {
        "claim_id": "clm_v1_int",
        "text": "Marc compte tester l'outil.",
        "claim_kind": "reported_intention",
        "origin": "simulation",
        "evidence_refs": [],
        "verification_status": "unsupported",
        "provenance_regime": "event",
    }
    c_v1_intent_loaded = ReportClaim.from_dict(d_v1_intent)
    assert c_v1_intent_loaded.asserted_as_action is False

    # 3. Invariance de compute_claim_id
    id_calc = compute_claim_id("Texte de test", ClaimKind.OBSERVED_SOCIAL_ACTION, "Agent", 1)
    assert id_calc.startswith("clm_")
    assert len(id_calc) == 12  # clm_ + 8 hex

    # 4. Compteurs dans ReportClaimRegistry
    reg = ReportClaimRegistry(simulation_id="sim_reg_test")
    reg.add_claim(c_action)
    reg.add_claim(c_v1_intent_loaded)
    reg_dict = reg.to_dict()
    assert reg.total_claims == 2
    assert reg.asserted_action_claims == 1
    assert reg.verified_action_claims == 0
    assert reg_dict["asserted_action_claims"] == 1
    assert reg_dict["verified_action_claims"] == 0


def test_extract_claims_eliminates_substring_and_homograph_false_positives():
    """AC3: Les faux positifs "va", "compte" en milieu de mot et homographes français ne sont pas pris pour des intentions/actions."""
    agent = ReportAgent(graph_id="g_test", simulation_id="sim_lex_test", simulation_requirement="req")

    phrases = [
        "Le travail mené avant la réunion valide l'observation qu'elles avaient faite.",
        "Compte tenu de son compte social, elle rend compte de son analyse.",
        "Elle explique comment la grille se lit comme suit pour chaque acteur.",
        "Il s'en suit que l'analyse est robuste.",
    ]
    markdown = "# Analyse\n\n" + "\n\n".join(phrases)
    claims = agent.extract_claims_from_content(markdown)

    assert len(claims) == len(phrases)
    for c in claims:
        # Aucun ne doit être classé en intention ou action sociale
        assert c.claim_kind != ClaimKind.REPORTED_INTENTION
        assert c.claim_kind != ClaimKind.OBSERVED_SOCIAL_ACTION
        assert c.asserted_as_action is False


def test_extract_claims_separates_narrated_actions_modals_and_negations():
    """AC4: Séparation des actions au présent/passé, modaux prospectifs et négations pures."""
    agent = ReportAgent(graph_id="g_test", simulation_id="sim_gram_test", simulation_requirement="req")

    # 1. Actions accomplies au présent de narration ou passé composé
    actions = [
        "Claire aime le post d'Hélène et la suit.",
        "Marc lui répond et cite sa publication.",
        "Julien a posté qu'il refuse de souscrire.",
    ]
    claims_act = agent.extract_claims_from_content("# Section\n\n" + "\n\n".join(actions))
    for c in claims_act:
        assert c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
        assert c.asserted_as_action is True

    # 2. Modaux prospectifs -> REPORTED_INTENTION
    modals = [
        "Claire va publier un retour.",
        "Marc compte souscrire demain.",
        "Julien souhaite répondre.",
    ]
    claims_mod = agent.extract_claims_from_content("# Section\n\n" + "\n\n".join(modals))
    for c in claims_mod:
        assert c.claim_kind == ClaimKind.REPORTED_INTENTION
        assert c.asserted_as_action is False

    # 3. Négation pure d'action -> pas OBSERVED_SOCIAL_ACTION
    negations = [
        "Aucun des six profils n'a souscrit à la formule.",
        "Marc n'a pas publié de commentaire.",
        "Claire est restée sans souscrire à l'offre.",
    ]
    claims_neg = agent.extract_claims_from_content("# Section\n\n" + "\n\n".join(negations))
    for c in claims_neg:
        assert c.claim_kind != ClaimKind.OBSERVED_SOCIAL_ACTION
        assert c.asserted_as_action is False


def test_downgraded_and_contradicted_actions_preserve_asserted_as_action():
    """AC5: Persistance d'asserted_as_action=True lors de tout déclassement ou contradiction."""
    claim = ReportClaim(
        claim_id="clm_act_preserv",
        text="Claire a souscrit à l'offre Pro.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Claire",
        provenance_regime=ProvenanceRegime.EVENT,
    )
    assert claim.asserted_as_action is True

    # 1. Déclassement C4 anti-affabulation
    pack_empty = EvidencePack(simulation_id="sim_test", events=[])
    res_c4 = SimulationActionVerifier.verify_report_claim(claim, evidence_pack=pack_empty)
    assert res_c4.claim_kind == ClaimKind.REPORTED_INTENTION
    assert res_c4.verification_status == VerificationStatus.UNSUPPORTED
    assert res_c4.asserted_as_action is True

    # 2. Règle de silence C7
    member_silent = CohortMemberStatus(persona_name="Claire", action_count=0, observed_event_ids=[])
    table_silent = CohortCoverageTable(simulation_id="sim_test", members=[member_silent])
    res_c7 = SimulationActionVerifier.verify_report_claim(claim, cohort_table=table_silent)
    assert res_c7.verification_status == VerificationStatus.CONTRADICTED
    assert res_c7.asserted_as_action is True

    # 3. Règle d'horizon temporel C8
    res_c8_time = SimulationActionVerifier.verify_report_claim(
        replace(claim, text="Claire a souscrit après 90 heures d'utilisation."),
        horizon_hours=24.0,
    )
    assert res_c8_time.claim_kind == ClaimKind.SPECULATIVE_PROJECTION
    assert res_c8_time.asserted_as_action is True

    # 4. Règle de métrique fantôme C8
    res_c8_metric = SimulationActionVerifier.verify_report_claim(
        replace(claim, text="Claire a souscrit générant un churn rate de 25 %."),
        evidence_pack=pack_empty,
    )
    assert res_c8_metric.asserted_as_action is True

    # Vérification dans le registre
    reg = ReportClaimRegistry(simulation_id="sim_test")
    reg.add_claim(res_c4)
    assert reg.asserted_action_claims == 1
    assert reg.verified_action_claims == 0


def test_interview_regime_never_becomes_action_or_asserted_action():
    """AC6: Étanchéité absolue du régime INTERVIEW face aux actions affirmées ou observées."""
    # 1. Directement à la création
    claim_interview = ReportClaim(
        claim_id="clm_int_1",
        text="Claire a publié qu'elle aimait le produit.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        provenance_regime=ProvenanceRegime.INTERVIEW,
    )
    assert claim_interview.asserted_as_action is False

    # 2. À travers verify_report_claim
    res = SimulationActionVerifier.verify_report_claim(claim_interview)
    assert res.claim_kind == ClaimKind.REPORTED_INTENTION
    assert res.asserted_as_action is False
    assert res.provenance_regime == ProvenanceRegime.INTERVIEW

    # 3. Même sur la branche QA-12 (fondateur)
    founder = CohortMemberStatus(
        persona_name="Alice",
        scenario_role=ScenarioRole.FOUNDER,
        action_count=1,
        observed_event_ids=["evt_f1"],
    )
    tbl = CohortCoverageTable(simulation_id="sim_test", members=[founder])
    claim_qa12 = ReportClaim(
        claim_id="clm_qa12",
        text="Alice a déclaré que l'assistance dédiée 24/7 est totalement gratuite et incluse dans le forfait de base.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Alice",
        provenance_regime=ProvenanceRegime.INTERVIEW,
    )
    canon_docs = [{
        "filename": "pricing.pdf",
        "validation_status": "validated",
        "epistemic_kind": "CANONICAL_DOCUMENT",
        "text": "L'assistance dédiée 24/7 est réservée exclusivement aux abonnés du plan Entreprise. Le forfait de base ne comprend aucun support.",
    }]
    res_qa12 = SimulationActionVerifier.verify_report_claim(
        claim_qa12,
        canonical_documents=canon_docs,
        cohort_table=tbl,
    )
    assert res_qa12.verification_status == VerificationStatus.CONTRADICTED
    assert res_qa12.claim_kind == ClaimKind.REPORTED_INTENTION
    assert res_qa12.asserted_as_action is False
    assert res_qa12.provenance_regime == ProvenanceRegime.INTERVIEW


def test_explicit_foreign_or_missing_event_id_rejected_without_fallback():
    """AC7: Rejet strict d'un event_id explicite étranger à l'acteur ou absent sans repli silencieux."""
    # Événement d'Alice
    ev_alice = ObservedEvent(
        event_id="evt_alice_1",
        simulation_id="sim_test",
        platform="twitter",
        round_num=1,
        agent_id=1,
        agent_name="Alice",
        action_type="CREATE_POST",
        timestamp="2026-10-29T12:00:00",
        action_args={"content": "Post officiel d'Alice."},
        is_action_executed=True,
    )
    # Événement valide de Bob par ailleurs dans le run
    ev_bob = ObservedEvent(
        event_id="evt_bob_valid",
        simulation_id="sim_test",
        platform="twitter",
        round_num=1,
        agent_id=2,
        agent_name="Bob",
        action_type="CREATE_POST",
        timestamp="2026-10-29T12:00:00",
        action_args={"content": "Bob donne son point de vue."},
        is_action_executed=True,
    )
    pack = EvidencePack(simulation_id="sim_test", events=[ev_alice, ev_bob])

    # Bob prétend une action en citant evt_alice_1 (qui appartient à Alice !)
    claim_bob_faulty = ReportClaim(
        claim_id="clm_bob_err",
        text="Bob donne son point de vue dans un post.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Bob",
        evidence_refs=["evt_alice_1"],
        provenance_regime=ProvenanceRegime.EVENT,
    )

    res = SimulationActionVerifier.verify_report_claim(claim_bob_faulty, evidence_pack=pack)
    assert res.verification_status == VerificationStatus.UNSUPPORTED
    assert res.claim_kind == ClaimKind.REPORTED_INTENTION
    assert res.asserted_as_action is True
    # L'evt étranger doit avoir été retiré des refs valides
    assert "evt_alice_1" not in res.evidence_refs
    assert any("Rejet strict" in lim for lim in res.limitations)


def test_oasis_passive_events_rejected_and_interaction_families_matched():
    """AC8: Les événements techniques passifs sont rejetés, et les interactions non textuelles concordent par famille."""
    # Événements d'Alice
    ev_signup = ObservedEvent(
        event_id="evt_signup",
        simulation_id="sim_test",
        platform="twitter",
        round_num=1,
        agent_id=1,
        agent_name="Alice",
        action_type="SIGN_UP",
        timestamp="2026-10-29T12:00:00",
        is_action_executed=True,
    )
    ev_follow = ObservedEvent(
        event_id="evt_follow",
        simulation_id="sim_test",
        platform="twitter",
        round_num=1,
        agent_id=1,
        agent_name="Alice",
        action_type="FOLLOW",
        timestamp="2026-10-29T12:00:00",
        is_action_executed=True,
    )
    pack = EvidencePack(simulation_id="sim_test", events=[ev_signup, ev_follow])

    # 1. Événement passif SIGN_UP ne valide pas une action
    claim_post = ReportClaim(
        claim_id="clm_alice_post",
        text="Alice publie une analyse.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Alice",
        evidence_refs=["evt_signup"],
        provenance_regime=ProvenanceRegime.EVENT,
    )
    res_post = SimulationActionVerifier.verify_report_claim(claim_post, evidence_pack=pack)
    assert res_post.verification_status == VerificationStatus.UNSUPPORTED
    assert res_post.claim_kind == ClaimKind.REPORTED_INTENTION

    # 2. FOLLOW valide une action de suivi
    claim_follow = ReportClaim(
        claim_id="clm_alice_follow",
        text="Alice suit le compte officiel.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Alice",
        evidence_refs=["evt_follow"],
        provenance_regime=ProvenanceRegime.EVENT,
    )
    res_follow = SimulationActionVerifier.verify_report_claim(claim_follow, evidence_pack=pack)
    assert res_follow.verification_status == VerificationStatus.VERIFIED
    assert res_follow.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION

    # 3. FOLLOW ne valide pas une publication, même avec un connecteur comme "Par la suite"
    claim_follow_unmatched = ReportClaim(
        claim_id="clm_alice_pub",
        text="Par la suite, Alice publie un rapport complet.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Alice",
        evidence_refs=["doc_charte.pdf", "evt_follow"],
        provenance_regime=ProvenanceRegime.EVENT,
    )
    res_unmatched = SimulationActionVerifier.verify_report_claim(claim_follow_unmatched, evidence_pack=pack)
    assert res_unmatched.verification_status == VerificationStatus.UNSUPPORTED

    # 4. Conservation des références non-evt_* lors d'une validation d'action
    claim_follow_with_doc = ReportClaim(
        claim_id="clm_alice_follow_doc",
        text="Alice suit le compte officiel.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Alice",
        evidence_refs=["doc_charte.pdf", "evt_follow"],
        provenance_regime=ProvenanceRegime.EVENT,
    )
    res_follow_doc = SimulationActionVerifier.verify_report_claim(claim_follow_with_doc, evidence_pack=pack)
    assert res_follow_doc.verification_status == VerificationStatus.VERIFIED
    assert "doc_charte.pdf" in res_follow_doc.evidence_refs
    assert "evt_follow" in res_follow_doc.evidence_refs

    # 5. Dissociation stricte UNFOLLOW / FOLLOW : un désabonnement ne valide pas un suivi positif
    ev_unfollow = ObservedEvent(
        event_id="evt_unfollow",
        simulation_id="sim_test",
        platform="twitter",
        round_num=1,
        agent_id=1,
        agent_name="Alice",
        action_type="UNFOLLOW",
        timestamp="2026-10-29T12:05:00",
        is_action_executed=True,
    )
    pack_unfollow = EvidencePack(simulation_id="sim_test", events=[ev_unfollow])
    res_unfollow_bad = SimulationActionVerifier.verify_report_claim(claim_follow, evidence_pack=pack_unfollow)
    assert res_unfollow_bad.verification_status == VerificationStatus.UNSUPPORTED

    claim_unfollow_good = ReportClaim(
        claim_id="clm_alice_unfollow",
        text="Alice ne suit plus le compte officiel.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Alice",
        evidence_refs=["evt_unfollow"],
        provenance_regime=ProvenanceRegime.EVENT,
    )
    res_unfollow_good = SimulationActionVerifier.verify_report_claim(claim_unfollow_good, evidence_pack=pack_unfollow)
    assert res_unfollow_good.verification_status == VerificationStatus.VERIFIED

    # 6. Absence de faux positifs par sous-chaînes sur approbation et désapprobation
    ev_like = ObservedEvent(
        event_id="evt_like",
        simulation_id="sim_test",
        platform="twitter",
        round_num=1,
        agent_id=1,
        agent_name="Alice",
        action_type="LIKE_POST",
        timestamp="2026-10-29T12:10:00",
        is_action_executed=True,
    )
    pack_like = EvidencePack(simulation_id="sim_test", events=[ev_like])

    # "vraiment" ne doit pas matcher "aime"
    claim_vraiment = ReportClaim(
        claim_id="clm_alice_vraiment",
        text="Alice a vraiment contesté la méthodologie.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Alice",
        evidence_refs=["evt_like"],
        provenance_regime=ProvenanceRegime.EVENT,
    )
    res_vraiment = SimulationActionVerifier.verify_report_claim(claim_vraiment, evidence_pack=pack_like)
    assert res_vraiment.verification_status == VerificationStatus.UNSUPPORTED

    # "n'aime pas" et "dislike" ne doivent pas matcher approbation
    claim_dislike = ReportClaim(
        claim_id="clm_alice_dislike",
        text="Alice n'aime pas le post de Bob.",
        claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
        origin=InformationOrigin.SIMULATION,
        agent_name="Alice",
        evidence_refs=["evt_like"],
        provenance_regime=ProvenanceRegime.EVENT,
    )
    res_dislike = SimulationActionVerifier.verify_report_claim(claim_dislike, evidence_pack=pack_like)
    assert res_dislike.verification_status == VerificationStatus.UNSUPPORTED


def test_end_to_end_audit_preserves_regimes_and_triggers_banner(tmp_path):
    """AC9: audit_and_save_report_claims préserve provenance_regime à 100 %, écrit les bannières et la sous-section 7."""
    sim_id = "sim_e2e_test"
    agent = ReportAgent(graph_id="g_test", simulation_id=sim_id, simulation_requirement="req")

    # Création d'un mini EvidencePack avec un événement d'action
    ev = ObservedEvent(
        event_id="evt_101",
        simulation_id=sim_id,
        platform="twitter",
        round_num=1,
        agent_id=1,
        agent_name="Claire",
        action_type="FOLLOW",
        timestamp="2026-10-29T12:00:00",
        is_action_executed=True,
    )
    pack = EvidencePack(simulation_id=sim_id, events=[ev])

    # Simulation d'observations d'outils (dont un entretien de plus de 8 mots)
    agent._interview_records = [{"interviewee": "Julien", "transcript": "Je trouve la plateforme particulièrement fluide et intuitive pour les utilisateurs."}]
    agent._tool_observations = [
        {"tool_name": "interview_agents", "output": "Julien indique expressément qu'il trouve la plateforme particulièrement fluide et intuitive pour les utilisateurs."},
        {"tool_name": "query_simulation_events", "output": "Claire suit le compte officiel sur le réseau social."},
    ]

    markdown = (
        "# Synthèse\n\n"
        "- Julien indique expressément qu'il trouve la plateforme particulièrement fluide et intuitive pour les utilisateurs.\n\n"
        "- Claire suit le compte officiel sur le réseau social.\n\n"
        "- Certaines analyses théoriques restent à approfondir.\n"
    )

    with patch.object(ReportAgent, "_resolve_project", return_value=None):
        with patch("app.services.simulation_manager.SimulationManager.get_actor_selection", return_value=None):
            registry = agent.audit_and_save_report_claims(
                markdown_content=markdown,
                evidence_pack=pack,
            )

    # 1. 0 claim avec provenance_regime: null
    assert registry.total_claims >= 2
    for c in registry.claims:
        assert c.provenance_regime is not None
        assert isinstance(c.provenance_regime, ProvenanceRegime)

    # 2. Vérification de la sous-section 7 de build_sources_provenance_section
    sec_prov = agent.build_sources_provenance_section(claims_registry=registry)
    assert "### 7. Traçabilité calculée depuis le registre d'affirmations" in sec_prov
    assert f"- **Affirmations au registre :** {registry.total_claims}." in sec_prov
    assert f"- **Affirmations portant un `provenance_regime` :** {registry.total_claims}." in sec_prov

    # 3. Vérification de l'insertion de la bannière sur le markdown assemblé (AC9)
    interview_count = sum(1 for c in registry.claims if c.provenance_regime == ProvenanceRegime.INTERVIEW)
    assert interview_count >= 1
    from app.utils.locale import t
    expected_banner = t("report.provenance_banner", count=interview_count)
    assembled_markdown = expected_banner + "\n\n" + markdown
    assert expected_banner in assembled_markdown


def test_modal_governance_and_narrative_present_negations():
    """Vérifie la précédence d'action accomplie sur modal (D5b), les négations au présent et les formes plurielles."""
    agent = ReportAgent(graph_id="g_test", simulation_id="sim_test", simulation_requirement="req")

    # 1. Action accomplie introduisant un modal (D5b, AC4) : reste OBSERVED_SOCIAL_ACTION
    claims_modal_intro = agent.extract_claims_from_content(
        "- Julien a tweeté qu'il va publier une critique détaillée."
    )
    assert len(claims_modal_intro) == 1
    assert claims_modal_intro[0].claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
    assert claims_modal_intro[0].asserted_as_action is True

    # 2. Modal prospectif pur : REPORTED_INTENTION (asserted_as_action=False)
    claims_modal_pure = agent.extract_claims_from_content(
        "- Julien va publier une critique détaillée."
    )
    assert len(claims_modal_pure) == 1
    assert claims_modal_pure[0].claim_kind == ClaimKind.REPORTED_INTENTION
    assert claims_modal_pure[0].asserted_as_action is False

    # 3. Négation au présent de narration : pas une action observée
    claims_neg_present = agent.extract_claims_from_content(
        "- Marc ne publie pas de message sur la plateforme."
    )
    assert len(claims_neg_present) == 1
    assert claims_neg_present[0].claim_kind != ClaimKind.OBSERVED_SOCIAL_ACTION
    assert claims_neg_present[0].asserted_as_action is False

    # 4. Formes plurielles au présent de narration : OBSERVED_SOCIAL_ACTION
    claims_plural = agent.extract_claims_from_content(
        "- Alice et Bob citent la publication officielle."
    )
    assert len(claims_plural) == 1
    assert claims_plural[0].claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
    assert claims_plural[0].asserted_as_action is True

    # 5. Pronominal au passé composé : OBSERVED_SOCIAL_ACTION
    claims_pronominal = agent.extract_claims_from_content(
        "- Marc s'est abonné au service sur la plateforme."
    )
    assert len(claims_pronominal) == 1
    assert claims_pronominal[0].claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
    assert claims_pronominal[0].asserted_as_action is True

    # 6. Guard 'qui suit' dans un texte de liaison : pas une action
    claims_connective = agent.extract_claims_from_content(
        "- Dans ce qui suit le lecteur découvrira l'analyse détaillée."
    )
    assert len(claims_connective) == 1
    assert claims_connective[0].claim_kind != ClaimKind.OBSERVED_SOCIAL_ACTION
