"""Tests unitaires hermétiques pour la Story 011-4 :
Couverture de cohorte, respect du temps simulé, intégrité des silencieux et anti-biais.
"""

import json
import os
import pytest

from app.models.actor_selection import ActorItem, ActorRole, ActorSelection
from app.models.cohort_coverage import (
    CohortCoverageTable,
    CohortMemberStatus,
    DecisionStatus,
    ScenarioRole,
)
from app.models.evidence_pack import EvidencePack, ObservedEvent
from app.models.report_claim import ClaimKind, ReportClaim, VerificationStatus
from app.models.simulation_brief import SimulationBrief
from app.models.source_document import InformationOrigin
from app.services.simulation_action_verifier import SimulationActionVerifier
from app.services.time_horizon_guard import TimeHorizonGuard


class TestCohortCoverageModels:
    """Tests des modèles de données et énumérations (T1, AC1)."""

    def test_scenario_role_parsing(self):
        assert ScenarioRole.from_str("prospect") == ScenarioRole.PROSPECT
        assert ScenarioRole.from_str("lead") == ScenarioRole.PROSPECT
        assert ScenarioRole.from_str("user") == ScenarioRole.EXISTING_USER
        assert ScenarioRole.from_str("fondateur") == ScenarioRole.FOUNDER
        assert ScenarioRole.from_str("expert") == ScenarioRole.PRESCRIBER
        assert ScenarioRole.from_str("observer") == ScenarioRole.OBSERVER
        assert ScenarioRole.from_str("stakeholder") == ScenarioRole.STAKEHOLDER
        assert ScenarioRole.from_str("unknown_xyz") == ScenarioRole.UNKNOWN

    def test_decision_status_parsing(self):
        assert DecisionStatus.from_str("adopted") == DecisionStatus.ADOPTED
        assert DecisionStatus.from_str("refus") == DecisionStatus.REJECTED
        assert DecisionStatus.from_str("hesitant") == DecisionStatus.HESITANT
        assert DecisionStatus.from_str("present_no_action") == DecisionStatus.PRESENT_NO_ACTION
        assert DecisionStatus.from_str("absent") == DecisionStatus.ABSENT_FROM_SIMULATION

    def test_cohort_member_silent_invariant(self):
        # Si action_count == 0, is_silent DOIT valoir True et decision_status PRESENT_NO_ACTION
        member = CohortMemberStatus(
            persona_name="Simon",
            scenario_role=ScenarioRole.PRESCRIBER,
            action_count=0,
            observed_event_ids=[],
            decision_status=DecisionStatus.ADOPTED,  # Tentative erronée
        )
        assert member.is_silent is True
        assert member.decision_status == DecisionStatus.PRESENT_NO_ACTION

        # Si actions > 0, is_silent DOIT valoir False
        active_member = CohortMemberStatus(
            persona_name="Florence",
            scenario_role=ScenarioRole.PROSPECT,
            action_count=3,
            observed_event_ids=["evt_1", "evt_2"],
            decision_status=DecisionStatus.REJECTED,
        )
        assert active_member.is_silent is False
        assert active_member.decision_status == DecisionStatus.REJECTED

    def test_cohort_coverage_table_serialization(self, tmp_path):
        m1 = CohortMemberStatus(
            persona_name="Florence",
            scenario_role=ScenarioRole.PROSPECT,
            action_count=2,
            observed_event_ids=["e1", "e2"],
            objections=["Prix trop élevé"],
            decision_status=DecisionStatus.REJECTED,
        )
        m2 = CohortMemberStatus(
            persona_name="Simon",
            scenario_role=ScenarioRole.PRESCRIBER,
            action_count=0,
            observed_event_ids=[],
        )
        table = CohortCoverageTable(
            simulation_id="sim_test_123",
            horizon_hours=72.0,
            total_rounds=40,
            members=[m1, m2],
        )

        assert table.total_members == 2
        assert table.active_members == 1
        assert table.silent_members == 1
        assert table.status_summary == {"rejected": 1, "present_no_action": 1}

        # Sauvegarde et rechargement
        save_file = str(tmp_path / "cohort_coverage.json")
        table.save_to_file(save_file)
        loaded = CohortCoverageTable.load_from_file(save_file)

        assert loaded is not None
        assert loaded.simulation_id == "sim_test_123"
        assert loaded.horizon_hours == 72.0
        assert len(loaded.members) == 2
        assert loaded.get_member("Florence").decision_status == DecisionStatus.REJECTED
        assert loaded.get_member("Simon").is_silent is True

        # Markdown
        md = table.to_markdown_table()
        assert "| Florence | Prospect | 2 actions" in md
        assert "| Simon | Prescriber | 0 action" in md
        assert "`present_no_action`" in md
        assert "`observed_active`" in md


class TestCohortAggregation:
    """Tests d'agrégation de cohorte depuis actors.json et EvidencePack (T2, AC2)."""

    def test_build_from_simulation_with_silent_and_active(self):
        # Sélection d'acteurs
        item1 = ActorItem(
            entity_uuid="uuid_1",
            entity_name="Florence",
            qualified_role=ActorRole.PERSON,
        )
        item2 = ActorItem(
            entity_uuid="uuid_2",
            entity_name="Simon",
            qualified_role=ActorRole.PERSON,
        )
        selection = ActorSelection(
            simulation_id="sim_agg_1",
            project_id="prj_1",
            graph_id="grp_1",
            input_fingerprint="fp_123",
            actors=[item1, item2],
        )

        # Faits observés avec actions de Florence uniquement
        ev1 = ObservedEvent(
            event_id="evt_tw_1",
            simulation_id="sim_agg_1",
            platform="twitter",
            round_num=3,
            agent_id=1,
            agent_name="Florence",
            action_type="create_post",
            timestamp="2026-10-16T10:00:00Z",
            action_args={"content": "Le tarif de base est beaucoup trop cher et engageant sur 1 an !"},
        )
        ev_pack = EvidencePack.from_events("sim_agg_1", [ev1])
        brief = SimulationBrief(goal="Tester l'offre Keova", time_horizon="72h")

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_agg_1",
            actor_selection=selection,
            evidence_pack=ev_pack,
            brief=brief,
        )

        assert table.total_members == 2
        flo = table.get_member("Florence")
        sim = table.get_member("Simon")

        assert flo is not None
        assert flo.action_count == 1
        assert flo.is_silent is False
        assert flo.decision_status == DecisionStatus.REJECTED
        assert any("trop cher" in obj for obj in flo.objections)

        assert sim is not None
        assert sim.action_count == 0
        assert sim.is_silent is True
        assert sim.decision_status == DecisionStatus.PRESENT_NO_ACTION


class TestSilentPersonaGuard:
    """Règle anti-affabulation stricte sur persona silencieux (T3, C7, AC3)."""

    def test_silent_persona_claim_rejected(self):
        # Simon est silencieux
        sim_member = CohortMemberStatus(
            persona_name="Simon",
            scenario_role=ScenarioRole.PRESCRIBER,
            action_count=0,
            observed_event_ids=[],
        )
        table = CohortCoverageTable(simulation_id="sim_s", members=[sim_member])

        # Claim prétendant que Simon a agi
        claim = ReportClaim(
            claim_id="cl_simon",
            text="Simon a soulevé des doutes techniques au Round 14",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            agent_name="Simon",
            round_num=14,
        )

        verified = SimulationActionVerifier.verify_report_claim(
            claim=claim,
            evidence_pack=None,
            cohort_table=table,
        )

        assert verified.verification_status == VerificationStatus.CONTRADICTED
        assert verified.confidence == 0.0
        assert any("present_no_action" in lim for lim in verified.limitations)


class TestAntiConfirmationBias:
    """Contrôle anti-biais de confirmation sur la synthèse (T5, AC5)."""

    def test_executive_summary_bias_detected_on_rejection(self):
        flo_member = CohortMemberStatus(
            persona_name="Florence",
            scenario_role=ScenarioRole.PROSPECT,
            action_count=4,
            observed_event_ids=["e1"],
            decision_status=DecisionStatus.REJECTED,
        )
        table = CohortCoverageTable(simulation_id="sim_b", members=[flo_member])

        summary_biased = (
            "La simulation démontre une adhésion totale de tous les clients à l'offre Keova Essentiel."
        )

        res = SimulationActionVerifier.check_executive_summary_bias(summary_biased, table)
        assert res["has_bias"] is True
        assert len(res["contradictions"]) > 0
        assert any("Biais de confirmation critique" in c for c in res["contradictions"])

    def test_executive_summary_unbiased_passes(self):
        flo_member = CohortMemberStatus(
            persona_name="Florence",
            scenario_role=ScenarioRole.PROSPECT,
            action_count=4,
            observed_event_ids=["e1"],
            decision_status=DecisionStatus.REJECTED,
        )
        table = CohortCoverageTable(simulation_id="sim_b", members=[flo_member])

        summary_fair = (
            "L'offre suscite de l'intérêt mais rencontre des refus explicites liés au tarif annuel."
        )

        res = SimulationActionVerifier.check_executive_summary_bias(summary_fair, table)
        assert res["has_bias"] is False
        assert len(res["contradictions"]) == 0


class TestTimeHorizonAndGhostMetrics:
    """Tests du respect du temps simulé et des métriques fantômes (T6, T7, C8, AC6, AC7)."""

    def test_time_horizon_parsing(self):
        assert TimeHorizonGuard.parse_horizon_hours("72h") == 72.0
        assert TimeHorizonGuard.parse_horizon_hours("72 hours") == 72.0
        assert TimeHorizonGuard.parse_horizon_hours("3 jours") == 72.0
        assert TimeHorizonGuard.parse_horizon_hours("3 days") == 72.0
        assert TimeHorizonGuard.parse_horizon_hours("1 semaine") == 168.0
        assert TimeHorizonGuard.parse_horizon_hours("1 mois") == 720.0

    def test_round_to_simulated_hour(self):
        # 40 rounds pour 72 heures = 1.8h / tour
        assert TimeHorizonGuard.round_to_simulated_hour(20, 40, 72.0) == 36.0
        assert TimeHorizonGuard.round_to_simulated_hour(40, 40, 72.0) == 72.0

    def test_claim_violating_time_horizon_downgraded(self):
        # Claim affirmant un churn à 90 jours sur un run de 72 heures
        claim = ReportClaim(
            claim_id="cl_time",
            text="Un churn massif est observé à 90 jours après l'adoption.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
        )

        verified = SimulationActionVerifier.verify_report_claim(
            claim=claim,
            horizon_hours=72.0,
        )

        assert verified.claim_kind == ClaimKind.SPECULATIVE_PROJECTION
        assert verified.verification_status == VerificationStatus.UNSUPPORTED
        assert any("hors horizon temporel" in lim for lim in verified.limitations)

    def test_detect_unsupported_ghost_metrics(self):
        # Détection d'un coût mathématiquement insoutenable ou saturation sans calcul
        claim = ReportClaim(
            claim_id="cl_ghost",
            text="Le coût d'acquisition est mathématiquement insoutenable avec une saturation de 83 %.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
        )

        verified = SimulationActionVerifier.verify_report_claim(
            claim=claim,
            horizon_hours=72.0,
        )

        assert verified.claim_kind in (ClaimKind.SPECULATIVE_PROJECTION, ClaimKind.ANALYST_INFERENCE)
        assert verified.verification_status == VerificationStatus.UNSUPPORTED
        assert any("métriques quantitatives" in lim for lim in verified.limitations)


class TestReportAgentCohortIntegration:
    """Tests d'intégration du tableau de cohorte et section d'objections dans ReportAgent (T4, T8)."""

    def test_plan_outline_forces_objections_section(self, tmp_path, monkeypatch):
        from app.services.report_agent import ReportAgent, ReportSection, ReportOutline
        from app.models.cohort_coverage import CohortCoverageTable, CohortMemberStatus, DecisionStatus

        agent = ReportAgent(
            graph_id="grp_test",
            simulation_id="sim_outline_force",
            simulation_requirement="Tester l'offre Keova avec des prospects réticents",
            locale="fr",
        )

        # Mock hermétique de get_simulation_context
        monkeypatch.setattr(agent.zep_tools, "get_simulation_context", lambda *args, **kwargs: {
            "graph_statistics": {"total_nodes": 5, "total_edges": 4, "entity_types": {"Person": 3}},
            "total_entities": 5,
            "related_facts": [],
        })

        # Mock de LLMClient pour renvoyer un outline sans section objections
        class DummyLLM:
            def chat_json(self, *args, **kwargs):
                return {
                    "title": "Rapport de Simulation Keova",
                    "summary": "Synthèse générale",
                    "sections": [
                        {"title": "1. Contexte et objectifs"},
                        {"title": "2. Analyse des comportements"},
                    ]
                }

        agent.llm = DummyLLM()

        # Mock de SimulationManager et OasisLogReaderService pour simuler un membre REJECTED
        flo = CohortMemberStatus(
            persona_name="Florence",
            action_count=2,
            observed_event_ids=["e1"],
            objections=["Prix trop élevé"],
            decision_status=DecisionStatus.REJECTED,
        )
        fake_table = CohortCoverageTable(simulation_id="sim_outline_force", members=[flo])

        monkeypatch.setattr(CohortCoverageTable, "build_from_simulation", classmethod(lambda cls, *args, **kwargs: fake_table))

        outline = agent.plan_outline()
        section_titles = [s.title for s in outline.sections]

        assert any("Objections non levées, contradictions et limites" in t for t in section_titles)
        assert len(outline.sections) == 3

    def test_generate_and_save_cohort_coverage(self, tmp_path, monkeypatch):
        from app.services.report_agent import ReportAgent
        from app.config import Config

        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

        agent = ReportAgent(
            graph_id="grp_test",
            simulation_id="sim_gen_cov",
            simulation_requirement="Tester la cohorte",
            locale="fr",
        )

        table = agent.generate_and_save_cohort_coverage()
        assert table is not None
        saved_file = os.path.join(str(tmp_path), "simulations", "sim_gen_cov", "cohort_coverage.json")
        assert os.path.exists(saved_file)

        with open(saved_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["simulation_id"] == "sim_gen_cov"

    def test_audit_and_save_report_claims_with_cohort(self, tmp_path, monkeypatch):
        from app.services.report_agent import ReportAgent
        from app.config import Config
        from app.models.cohort_coverage import CohortCoverageTable, CohortMemberStatus, DecisionStatus

        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

        agent = ReportAgent(
            graph_id="grp_test",
            simulation_id="sim_audit_coh",
            simulation_requirement="Tester l'audit des claims",
            locale="fr",
        )

        sim_member = CohortMemberStatus(
            persona_name="Simon",
            action_count=0,
            observed_event_ids=[],
        )
        fake_table = CohortCoverageTable(simulation_id="sim_audit_coh", members=[sim_member])

        content = (
            "## Résultats\n\n"
            "Simon a posté un avis très favorable au Round 5.\n"
            "Un churn massif a été mesuré à 120 jours.\n"
        )

        registry = agent.audit_and_save_report_claims(markdown_content=content, cohort_table=fake_table)
        assert registry.total_claims >= 2

        # Simon est silencieux -> claim contredite
        simon_claims = [c for c in registry.claims if "simon" in c.text.lower()]
        assert len(simon_claims) > 0
        assert simon_claims[0].verification_status == VerificationStatus.CONTRADICTED

        # 120 jours -> hors horizon (72h) -> speculative projection unsupported
        churn_claims = [c for c in registry.claims if "120 jours" in c.text.lower()]
        assert len(churn_claims) > 0
        assert churn_claims[0].verification_status == VerificationStatus.UNSUPPORTED
        assert churn_claims[0].claim_kind == ClaimKind.SPECULATIVE_PROJECTION

    def test_cohort_markdown_rendering_formatting(self):
        m1 = CohortMemberStatus(
            persona_name="Florence",
            scenario_role=ScenarioRole.PROSPECT,
            action_count=4,
            observed_event_ids=["e1", "e2"],
            objections=["Prix trop élevé"],
            decision_status=DecisionStatus.REJECTED,
        )
        table = CohortCoverageTable(
            simulation_id="sim_render",
            members=[m1],
        )
        md = table.to_markdown_table()
        assert "| Florence | Prospect | 4 actions (2 événements) | Prix trop élevé | Rejected | `observed_active` |" in md

    def test_english_markdown_rendering(self):
        m1 = CohortMemberStatus(
            persona_name="Florence",
            scenario_role=ScenarioRole.PROSPECT,
            action_count=2,
            observed_event_ids=["e1"],
            objections=["Too expensive"],
            decision_status=DecisionStatus.REJECTED,
        )
        m2 = CohortMemberStatus(
            persona_name="Simon",
            scenario_role=ScenarioRole.PRESCRIBER,
            action_count=0,
            observed_event_ids=[],
        )
        table = CohortCoverageTable(
            simulation_id="sim_render_en",
            members=[m1, m2],
        )
        md = table.to_markdown_table(locale="en")
        assert "| Persona | Scenario Role | Observed Actions | Major Objections | Simulated Decision | Coverage Status |" in md
        assert "| Florence | Prospect | 2 actions (1 events) | Too expensive | Rejected | `observed_active` |" in md
        assert "| Simon | Prescriber | 0 action | None | No observation | `present_no_action` |" in md

    def test_default_horizon_fallback_when_brief_is_none(self):
        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_no_brief",
            actor_selection=None,
            evidence_pack=None,
            brief=None,
        )
        assert table.horizon_hours == 72.0

    def test_exact_match_priority_over_substring_overlap(self):
        # Deux personas où l'un est sous-chaîne de l'autre ("Al" et "Alan")
        item1 = ActorItem(entity_uuid="u1", entity_name="Al", qualified_role=ActorRole.PERSON)
        item2 = ActorItem(entity_uuid="u2", entity_name="Alan", qualified_role=ActorRole.PERSON)
        selection = ActorSelection(
            simulation_id="sim_sub",
            project_id="p",
            graph_id="g",
            input_fingerprint="fp",
            actors=[item1, item2],
        )

        ev_alan = ObservedEvent(
            event_id="evt_alan_1",
            simulation_id="sim_sub",
            platform="twitter",
            round_num=1,
            agent_id=2,
            agent_name="Alan",
            action_type="create_post",
            timestamp="2026-10-16T10:00:00Z",
            action_args={"content": "Je suis Alan et j'adore MiroFish !"},
        )
        ev_pack = EvidencePack.from_events("sim_sub", [ev_alan])

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_sub",
            actor_selection=selection,
            evidence_pack=ev_pack,
        )

        al_member = table.get_member("Al")
        alan_member = table.get_member("Alan")

        assert al_member.is_silent is True
        assert al_member.action_count == 0
        assert alan_member.is_silent is False
        assert alan_member.action_count == 1
        assert alan_member.observed_event_ids == ["evt_alan_1"]

    def test_recursive_extraction_of_nested_args_and_result(self):
        item = ActorItem(entity_uuid="u1", entity_name="Florence", qualified_role=ActorRole.PERSON)
        selection = ActorSelection(
            simulation_id="sim_rec",
            project_id="p",
            graph_id="g",
            input_fingerprint="fp",
            actors=[item],
        )
        # Arguments imbriqués (dict dans dict, liste dans dict)
        ev = ObservedEvent(
            event_id="evt_rec_1",
            simulation_id="sim_rec",
            platform="reddit",
            round_num=2,
            agent_id=1,
            agent_name="Florence",
            action_type="comment",
            timestamp="2026-10-16T10:00:00Z",
            action_args={
                "payload": {
                    "messages": ["Le tarif annuel est trop cher pour notre équipe."],
                    "metadata": {"reason": "Refus d'engagement"},
                }
            },
            result={"response": "Désaccord sur les conditions tarifaires."},
        )
        ev_pack = EvidencePack.from_events("sim_rec", [ev])
        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_rec",
            actor_selection=selection,
            evidence_pack=ev_pack,
        )
        flo = table.get_member("Florence")
        assert flo.decision_status == DecisionStatus.REJECTED
        assert any("trop cher" in o for o in flo.objections)

    def test_anti_bias_english_patterns_and_hesitation(self):
        flo_member = CohortMemberStatus(
            persona_name="Florence",
            scenario_role=ScenarioRole.PROSPECT,
            action_count=4,
            observed_event_ids=["e1"],
            decision_status=DecisionStatus.REJECTED,
        )
        table = CohortCoverageTable(simulation_id="sim_b_en", members=[flo_member])

        # Synthèse biaisée en anglais
        summary_en_biased = "The experiment demonstrates unanimous conversion of all users to the platform."
        res = SimulationActionVerifier.check_executive_summary_bias(summary_en_biased, table)
        assert res["has_bias"] is True
        assert any("Biais de confirmation" in c for c in res["contradictions"])

        # Hésitation seule avec "without hesitation"
        hes_member = CohortMemberStatus(
            persona_name="Émilie",
            scenario_role=ScenarioRole.PROSPECT,
            action_count=2,
            observed_event_ids=["e2"],
            decision_status=DecisionStatus.HESITANT,
        )
        table_hes = CohortCoverageTable(simulation_id="sim_hes", members=[hes_member])
        summary_hes = "All targets accepted without hesitation and showed full confidence."
        res_hes = SimulationActionVerifier.check_executive_summary_bias(summary_hes, table_hes)
        assert res_hes["has_bias"] is True
        assert len(res_hes["warnings"]) > 0

    def test_detect_unsupported_ghost_metrics_english(self):
        claim_en = ReportClaim(
            claim_id="cl_en_ghost",
            text="A 90-day churn was observed with mathematically unsustainable onboarding costs.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
        )
        verified = SimulationActionVerifier.verify_report_claim(
            claim=claim_en,
            horizon_hours=72.0,
        )
        assert verified.verification_status == VerificationStatus.UNSUPPORTED
        assert verified.claim_kind in (ClaimKind.SPECULATIVE_PROJECTION, ClaimKind.ANALYST_INFERENCE)

    def test_silent_persona_priority_over_out_of_bounds_time(self):
        # Simon est silencieux ET la claim cite une date hors horizon (120 jours)
        sim_member = CohortMemberStatus(
            persona_name="Simon",
            scenario_role=ScenarioRole.PRESCRIBER,
            action_count=0,
            observed_event_ids=[],
        )
        table = CohortCoverageTable(simulation_id="sim_prio", members=[sim_member])
        claim = ReportClaim(
            claim_id="cl_prio",
            text="Simon a confirmé l'abandon à 120 jours.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            agent_name="Simon",
        )
        verified = SimulationActionVerifier.verify_report_claim(
            claim=claim,
            cohort_table=table,
            horizon_hours=72.0,
        )
        # La règle de silence C7 doit primer et marquer CONTRADICTED avec confidence 0.0
        assert verified.verification_status == VerificationStatus.CONTRADICTED
        assert verified.confidence == 0.0
        assert any("present_no_action" in lim for lim in verified.limitations)



