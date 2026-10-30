"""Tests hermétiques pour la Story 015-4 (Lot B).

Couvre les critères d'acceptation AC1 à AC9 :
- AC1 : Filtre chirurgical `[persona non admis]` restreint aux personnes physiques (D1).
- AC2 : Séparation éligibilité ontologique / participation au scénario (AT-10, D2, D3).
- AC3 : Contre-test institutionnel : préservation des organisations actives (AT-09, D3).
- AC4 : Arbitrage humain et rétrocompatibilité `actors.json` (NFR-5, D2).
- AC5 : Résolution déterministe enrichie de `ScenarioRole` (RC-3, D4).
- AC6 : Dénominateur d'adoption par inclusion positive stricte (AT-08, C4, D5).
- AC7 : Scénario non commercial sans prospect (AT-19, D5).
- AC8 : Anti-affabulation : suivi social vs souscription commerciale (AT-07, D6).
- AC9 : Généricité absolue du code applicatif (NFR-2, D7).
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from app.api.report import _filter_simulation_requirement_for_report
from app.models.actor_eligibility import (
    ACTOR_ELIGIBILITY_POLICY_VERSION,
    ActorRole,
    EligibilityStatus,
)
from app.models.actor_selection import (
    ActorItem,
    ActorSelection,
    ScenarioParticipationPolicy,
    ScenarioParticipationStatus,
    SelectionValidationError,
)
from app.models.cohort_coverage import (
    CohortCoverageTable,
    CohortMemberStatus,
    DecisionStatus,
    ScenarioRole,
)
from app.models.evidence_pack import EvidencePack, ObservedEvent
from app.models.simulation_brief import SimulationBrief


class DummyManager:
    """Double de test simple retournant une ActorSelection."""

    def __init__(self, actor_selection: ActorSelection) -> None:
        self._actor_selection = actor_selection

    def get_actor_selection(self, simulation_id: str) -> ActorSelection:
        return self._actor_selection


class TestAC1SurgicalPersonaFilter:
    """AC1 : Filtre chirurgical [persona non admis] (FR-05, RC-1, D1)."""

    def test_surgical_filter_ignores_ineligible_products_and_domains(self) -> None:
        """Les produits, services, domaines et concepts inéligibles ne sont JAMAIS caviardés."""
        actors = [
            ActorItem(
                entity_uuid="u-prod",
                entity_name="MonLogicielPro",
                original_type="Product",
                qualified_role=ActorRole.PRODUCT,
                eligibility_status=EligibilityStatus.INELIGIBLE,
            ),
            ActorItem(
                entity_uuid="u-dom",
                entity_name="monsite.fr",
                original_type="Domain",
                qualified_role=ActorRole.DOMAIN,
                eligibility_status=EligibilityStatus.INELIGIBLE,
            ),
            ActorItem(
                entity_uuid="u-concept",
                entity_name="Formule Éco",
                original_type="Concept",
                qualified_role=ActorRole.CONCEPT,
                eligibility_status=EligibilityStatus.INELIGIBLE,
            ),
            ActorItem(
                entity_uuid="u-persona-rejected",
                entity_name="Jean Dupont",
                original_type="Person",
                qualified_role=ActorRole.PERSON,
                eligibility_status=EligibilityStatus.INELIGIBLE,
            ),
            ActorItem(
                entity_uuid="u-persona-admitted",
                entity_name="Alice Martin",
                original_type="Person",
                qualified_role=ActorRole.PERSON,
                eligibility_status=EligibilityStatus.ELIGIBLE,
            ),
        ]
        sel = ActorSelection(
            simulation_id="sim-test",
            project_id="proj-test",
            graph_id="graph-test",
            input_fingerprint="fp1",
            actors=actors,
        )

        assert sel.excluded_persona_names() == ["Jean Dupont"]

        text = (
            "Découverte de MonLogicielPro sur monsite.fr avec la Formule Éco.\n"
            "- Jean Dupont refuse la proposition.\n"
            "- Alice Martin apprécie la démonstration."
        )
        filtered = _filter_simulation_requirement_for_report(
            "sim-test", text, manager=DummyManager(sel)
        )

        assert "MonLogicielPro" in filtered
        assert "monsite.fr" in filtered
        assert "Formule Éco" in filtered
        assert "Jean Dupont" not in filtered
        assert "[persona non admis]" in filtered
        assert "Alice Martin apprécie la démonstration." in filtered

    def test_surgical_filter_on_r8_data_preserves_concepts_and_products(self) -> None:
        """Vérifie sur les artefacts réels de R8 que les entités passives ne sont pas caviardées."""
        actors_path = Path(__file__).parents[1] / "uploads" / "simulations" / "sim_7a1b02b8c092" / "actors.json"
        if not actors_path.exists():
            pytest.skip("Artefacts de la simulation R8 absents")

        sel = ActorSelection.load(str(actors_path))
        assert sel is not None

        excluded_names = sel.excluded_persona_names()
        # Dans R8, toutes les 31 entités ineligible étaient des outils/concepts/domaines, 0 persona humain
        for passive in ("keova.app", "keova.fr", "WordPress", "Google Forms", "Doctolib", "Stripe", "Wix"):
            assert passive not in excluded_names

        brief_text = (
            "Les praticiennes découvrent l'offre Essentiel à 29 € TTC sur keova.app.\n"
            "Certaines sortent d'un échec sur Wix ou WordPress, bricolent sur Google Forms ou WhatsApp."
        )
        filtered = _filter_simulation_requirement_for_report(
            "sim_7a1b02b8c092", brief_text, manager=DummyManager(sel)
        )

        assert "[persona non admis]" not in filtered
        assert "keova.app" in filtered
        assert "WordPress" in filtered
        assert "Wix" in filtered


class TestAC2AndAC3ScenarioParticipation:
    """AC2 & AC3 : Participation au scénario (AT-10, AT-09, D2, D3)."""

    def test_ac2_passive_software_tool_marked_context_only(self) -> None:
        """AT-10 : Organisation outil passif marquée context_only et exclue des agents actifs."""
        actors = [
            ActorItem(
                entity_uuid="u-org-tool",
                entity_name="PasserellePaiement",
                original_type="Organization",
                qualified_role=ActorRole.ORGANIZATION,
                eligibility_status=EligibilityStatus.ELIGIBLE,
                reasoning="Infrastructure de paiement en ligne sécurisée utilisée pour les règlements.",
            ),
            ActorItem(
                entity_uuid="u-user",
                entity_name="Marie",
                original_type="Person",
                qualified_role=ActorRole.PERSON,
                eligibility_status=EligibilityStatus.ELIGIBLE,
            ),
        ]
        brief = SimulationBrief(
            goal="Test de paiement",
            rules=["Les logiciels et passerelles de paiement ne doivent jamais être personnifiés en agents humains."],
        )

        ScenarioParticipationPolicy.evaluate(
            actors=actors,
            simulation_requirement="Observer les réactions des praticiennes.",
            simulation_brief=brief,
        )

        org = next(a for a in actors if a.entity_name == "PasserellePaiement")
        user = next(a for a in actors if a.entity_name == "Marie")

        assert org.scenario_participation == ScenarioParticipationStatus.CONTEXT_ONLY
        assert "AT-10" in org.scenario_participation_reason or "clause explicite" in org.scenario_participation_reason
        assert user.scenario_participation == ScenarioParticipationStatus.ACTIVE_AGENT

        sel = ActorSelection(
            simulation_id="sim-1", project_id="p-1", graph_id="g-1",
            input_fingerprint="fp", actors=actors
        )
        assert len(sel.eligible_actors) == 2
        assert len(sel.active_eligible_actors) == 1
        assert sel.active_eligible_actors[0].entity_name == "Marie"

    def test_ac3_active_organization_in_strike_preserved(self) -> None:
        """AT-09 : Organisation active (syndicat, opérateur de transport) maintenue active_agent."""
        actors = [
            ActorItem(
                entity_uuid="u-operator",
                entity_name="Régie des Transports",
                original_type="Organization",
                qualified_role=ActorRole.ORGANIZATION,
                eligibility_status=EligibilityStatus.ELIGIBLE,
                reasoning="Opérateur public des métros et bus doté d'une direction et d'un compte officiel.",
            ),
            ActorItem(
                entity_uuid="u-union",
                entity_name="Syndicat Métro Unifié",
                original_type="Organization",
                qualified_role=ActorRole.ORGANIZATION,
                eligibility_status=EligibilityStatus.ELIGIBLE,
                reasoning="Syndicat représentatif des agents de conduite, porte-parole de la grève.",
            ),
        ]
        brief = SimulationBrief(
            goal="Simulation d'une grève des transports de 48h.",
            target_audiences=["Régie des Transports", "Syndicat Métro Unifié"],
        )

        ScenarioParticipationPolicy.evaluate(
            actors=actors,
            simulation_requirement="Négociations sous tension entre syndicats et direction.",
            simulation_brief=brief,
        )

        for a in actors:
            assert a.scenario_participation == ScenarioParticipationStatus.ACTIVE_AGENT

    def test_ac2_r8_passive_organizations_demoted_to_context_only(self) -> None:
        """AC2 : Sur les données réelles R8, Stripe, Wix, CPAM et Keova sont classés context_only."""
        sim_dir = Path(__file__).parents[1] / "uploads" / "simulations" / "sim_7a1b02b8c092"
        if not sim_dir.exists():
            pytest.skip("Fixture R8 absente")

        actors_sel = ActorSelection.load(str(sim_dir / "actors.json"))
        assert actors_sel is not None
        cfg = json.loads((sim_dir / "simulation_config.json").read_text(encoding="utf-8"))
        evaluated = ScenarioParticipationPolicy.evaluate(
            actors=actors_sel.actors,
            simulation_requirement=cfg.get("simulation_requirement", ""),
        )
        actors_by_name = {a.entity_name: a for a in evaluated}
        for passive_name in ("Stripe", "Wix", "CPAM", "Keova"):
            actor = actors_by_name.get(passive_name)
            assert actor is not None, f"Acteur {passive_name} manquant dans R8"
            assert actor.scenario_participation == ScenarioParticipationStatus.CONTEXT_ONLY, (
                f"{passive_name} aurait dû être classé CONTEXT_ONLY, obtenu : {actor.scenario_participation}"
            )

    def test_execute_prepare_filters_context_only_entities_from_oasis_profiles(self) -> None:
        """SimulationManager._execute_prepare filtre les acteurs context_only des entités passées aux profils (V1)."""
        from app.services.simulation_manager import (
            SimulationManager,
            SimulationState,
            SimulationStatus,
        )

        mgr = SimulationManager()
        state = SimulationState(
            simulation_id="sim-prep-test",
            project_id="proj-prep",
            graph_id="graph-prep",
            status=SimulationStatus.CREATED,
        )
        mgr._save_simulation_state(state)

        actors = [
            ActorItem(
                entity_uuid="uuid-tool",
                entity_name="OutilTechnique",
                qualified_role=ActorRole.ORGANIZATION,
                eligibility_status=EligibilityStatus.ELIGIBLE,
                scenario_participation=ScenarioParticipationStatus.CONTEXT_ONLY,
                reasoning="Outil technique passif du scénario.",
            ),
            ActorItem(
                entity_uuid="uuid-human",
                entity_name="ActeurHumain",
                qualified_role=ActorRole.PERSON,
                eligibility_status=EligibilityStatus.ELIGIBLE,
                scenario_participation=ScenarioParticipationStatus.ACTIVE_AGENT,
                reasoning="Acteur humain actif du scénario.",
            ),
        ]
        sel = ActorSelection(
            simulation_id="sim-prep-test",
            project_id="proj-prep",
            graph_id="graph-prep",
            input_fingerprint="fp-prep",
            actors=actors,
        )
        mgr.save_actor_selection(sel)

        from types import SimpleNamespace

        mock_tool_entity = SimpleNamespace(uuid="uuid-tool", name="OutilTechnique", entity_type="Organization")
        mock_human_entity = SimpleNamespace(uuid="uuid-human", name="ActeurHumain", entity_type="Person")
        mock_filtered = MagicMock(
            entities=[mock_tool_entity, mock_human_entity],
            filtered_count=2,
            entity_types=["Organization", "Person"],
        )
        mock_params = MagicMock()
        mock_params.to_json.return_value = "{}"
        mock_params.generation_reasoning = "Test reasoning"

        with patch("app.services.simulation_manager.ZepEntityReader") as mock_reader_cls, \
             patch("app.services.simulation_manager.fingerprint_qualification_inputs", return_value="fp-prep"), \
             patch("app.services.simulation_manager.SimulationConfigGenerator") as mock_cfg_cls, \
             patch("app.services.simulation_manager.OasisProfileGenerator") as mock_gen_cls:
            mock_reader = MagicMock()
            mock_reader_cls.return_value = mock_reader
            mock_reader.filter_defined_entities.return_value = mock_filtered

            mock_cfg = MagicMock()
            mock_cfg_cls.return_value = mock_cfg
            mock_cfg.generate_config.return_value = mock_params

            mock_gen = MagicMock()
            mock_gen_cls.return_value = mock_gen
            mock_gen.generate_profiles_from_entities.return_value = ([], {})

            mgr._execute_prepare(
                simulation_id="sim-prep-test",
                state=state,
                project=None,
                simulation_requirement="Test requirement",
                document_text="Document text",
            )

            saved_state = mgr._load_simulation_state("sim-prep-test")
            assert saved_state is not None
            assert saved_state.qualified_actor_uuids == ["uuid-human"]
            assert "uuid-tool" not in saved_state.qualified_actor_uuids

            gen_call_args = mock_gen.generate_profiles_from_entities.call_args
            assert gen_call_args is not None
            passed_entities = gen_call_args.kwargs.get("entities", gen_call_args[0][0] if gen_call_args[0] else [])
            passed_uuids = [e.uuid for e in passed_entities]
            assert passed_uuids == ["uuid-human"]


class TestAC4HumanReviewAndBackwardCompatibility:
    """AC4 : Arbitrage humain et rétrocompatibilité actors.json (NFR-5, D2)."""

    def test_backward_compatibility_v1_actors_json(self) -> None:
        """Un fichier actors.json v1 sans scenario_participation est chargé avec repli cohérent."""
        data = {
            "schema_version": 1,
            "policy_version": ACTOR_ELIGIBILITY_POLICY_VERSION,
            "simulation_id": "sim-old",
            "project_id": "proj-old",
            "graph_id": "graph-old",
            "revision": 1,
            "input_fingerprint": "abc",
            "counts": {"total": 3, "eligible": 1, "review": 1, "ineligible": 1},
            "actors": [
                {
                    "entity_uuid": "u1",
                    "entity_name": "Alice",
                    "original_type": "Person",
                    "qualified_role": "person",
                    "eligibility_status": "eligible",
                },
                {
                    "entity_uuid": "u2",
                    "entity_name": "Bob",
                    "original_type": "Person",
                    "qualified_role": "person",
                    "eligibility_status": "review",
                },
                {
                    "entity_uuid": "u3",
                    "entity_name": "Serveur",
                    "original_type": "Product",
                    "qualified_role": "product",
                    "eligibility_status": "ineligible",
                },
            ],
        }
        sel = ActorSelection.from_dict(data)
        assert len(sel.counts) == 4
        assert set(sel.counts.keys()) == {"total", "eligible", "review", "ineligible"}

        a1 = sel.by_uuid()["u1"]
        a2 = sel.by_uuid()["u2"]
        a3 = sel.by_uuid()["u3"]

        assert a1.scenario_participation == ScenarioParticipationStatus.ACTIVE_AGENT
        assert a2.scenario_participation == ScenarioParticipationStatus.REVIEW
        assert a3.scenario_participation == ScenarioParticipationStatus.EXCLUDED

    def test_human_review_promotes_context_only_to_active(self) -> None:
        """L'opérateur humain peut arbitrer et changer le statut de participation."""
        actor = ActorItem(
            entity_uuid="u-org",
            entity_name="Partenaire Tech",
            original_type="Organization",
            qualified_role=ActorRole.ORGANIZATION,
            eligibility_status=EligibilityStatus.ELIGIBLE,
            scenario_participation=ScenarioParticipationStatus.CONTEXT_ONLY,
        )
        sel = ActorSelection(
            simulation_id="sim-rev", project_id="p-rev", graph_id="g-rev",
            input_fingerprint="fp", revision=1, actors=[actor],
        )

        mod = [{
            "entity_uuid": "u-org",
            "role": "organization",
            "status": "eligible",
            "scenario_participation": "active_agent",
            "justification": "L'organisation doit prendre la parole dans ce scénario spécifique.",
        }]
        sel.apply_review(expected_revision=1, modifications=mod)

        updated_actor = sel.by_uuid()["u-org"]
        assert updated_actor.is_human_modified is True
        assert updated_actor.scenario_participation == ScenarioParticipationStatus.ACTIVE_AGENT
        assert sel.revision == 2


class TestAC5ToAC8CohortRolesAndAdoption:
    """AC5 à AC8 : Résolution des rôles, inclusion positive et anti-affabulation."""

    def test_ac5_trainer_resolved_to_prescriber(self) -> None:
        """original_type Trainer / Formatrice est résolu en ScenarioRole.PRESCRIBER."""
        assert ScenarioRole.from_str("Trainer") == ScenarioRole.PRESCRIBER
        assert ScenarioRole.from_str("Formatrice") == ScenarioRole.PRESCRIBER
        assert ScenarioRole.from_str("Formateur") == ScenarioRole.PRESCRIBER

    def test_ac6_adoption_denominator_on_r8_data(self) -> None:
        """Sur la cohorte et le brief R8, le dénominateur vaut exactement 5 (AT-08, RC-3)."""
        sim_dir = Path(__file__).parents[1] / "uploads" / "simulations" / "sim_7a1b02b8c092"
        rep_dir = Path(__file__).parents[1] / "uploads" / "reports" / "report_934d3254004b"

        if not sim_dir.exists() or not rep_dir.exists():
            pytest.skip("Artefacts de la simulation R8 absents")

        actors_sel = ActorSelection.load(str(sim_dir / "actors.json"))
        cfg = json.loads((sim_dir / "simulation_config.json").read_text(encoding="utf-8"))
        brief = SimulationBrief(
            goal=cfg["simulation_requirement"],
            rules=[
                "Sophie Jouan est une praticienne pilote existante déjà installée en production (sophiejouan.fr). Simon est le fondateur et opérateur de Keova. Aucun des deux ne doit être simulé comme une nouvelle prospect découvrant l'offre.",
                "Les logiciels (Wix, WordPress, Doctolib, Stripe), noms de domaine, entreprises et offres commerciales ne doivent jamais être personnifiés en agents humains fictifs.",
            ],
            target_audiences=[
                "Nathalie", "Florence", "Sylvie", "Émilie", "Christine", "Hélène",
            ],
        )

        # Charger le pack d'événements si disponible, sinon pack vide
        ev_file = rep_dir / "evidence_pack.json"
        ev_pack = None
        if ev_file.exists():
            import json as _json
            ev_pack = EvidencePack.from_dict(_json.loads(ev_file.read_text(encoding="utf-8")))

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_7a1b02b8c092",
            total_rounds=40,
            actor_selection=actors_sel,
            evidence_pack=ev_pack,
            brief=brief,
        )

        prospect_names = sorted(m.persona_name for m in table.prospect_members)
        expected_prospects = ["Christine", "Florence", "Nathalie", "Sylvie", "Émilie"]
        assert prospect_names == expected_prospects
        assert len(table.prospect_members) == 5
        assert table.to_dict()["adoption_denominator"] == 5
        assert table.to_dict()["adoption_applicable"] is True

        # Vérifier que les formatrices et clients pilotes sont bien écartés
        sophie = table.get_member("Sophie Jouan")
        assert sophie is not None
        assert sophie.scenario_role == ScenarioRole.EXISTING_USER
        assert sophie.decision_status == DecisionStatus.NOT_APPLICABLE
        assert sophie.conversion_eligible is False

        helene = table.get_member("Hélène")
        assert helene is not None
        assert helene.scenario_role == ScenarioRole.PRESCRIBER
        assert helene.decision_status == DecisionStatus.NOT_APPLICABLE

    def test_context_only_actor_without_events_omitted_from_cohort_table(self) -> None:
        """Un acteur context_only sans aucun événement dans evidence_pack est omis du tableau (V2)."""
        actors = [
            ActorItem(
                entity_uuid="uuid-tool",
                entity_name="OutilPassif",
                qualified_role=ActorRole.ORGANIZATION,
                eligibility_status=EligibilityStatus.ELIGIBLE,
                scenario_participation=ScenarioParticipationStatus.CONTEXT_ONLY,
            ),
            ActorItem(
                entity_uuid="uuid-prospect",
                entity_name="ProspectActif",
                qualified_role=ActorRole.PERSON,
                eligibility_status=EligibilityStatus.ELIGIBLE,
                scenario_participation=ScenarioParticipationStatus.ACTIVE_AGENT,
            ),
        ]
        sel = ActorSelection(
            simulation_id="sim-test-ctx",
            project_id="proj-1",
            graph_id="g1",
            input_fingerprint="fp1",
            actors=actors,
        )
        brief = SimulationBrief(goal="Test", target_audiences=["ProspectActif"])
        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim-test-ctx",
            total_rounds=10,
            actor_selection=sel,
            brief=brief,
        )
        assert table.get_member("OutilPassif") is None
        assert table.get_member("ProspectActif") is not None

    def test_ac7_non_commercial_scenario_without_prospects(self) -> None:
        """AT-19 : Scénario non commercial : adoption_denominator == 0, adoption_applicable is False."""
        members = [
            CohortMemberStatus(
                persona_name="Maire",
                scenario_role=ScenarioRole.INSTITUTION,
                action_count=10,
                observed_event_ids=["ev1"],
                decision_status=DecisionStatus.NOT_APPLICABLE,
            ),
            CohortMemberStatus(
                persona_name="Observateur Citoyen",
                scenario_role=ScenarioRole.OBSERVER,
                action_count=5,
                observed_event_ids=["ev2"],
                decision_status=DecisionStatus.NO_DECISION,
            ),
        ]
        table = CohortCoverageTable(
            simulation_id="sim-noncom",
            horizon_hours=48.0,
            total_rounds=20,
            members=members,
        )

        d = table.to_dict()
        assert d["adoption_denominator"] == 0
        assert d["adoption_applicable"] is False
        assert d["adoption_rate"] == 0.0

    def test_ac8_social_follow_not_counted_as_adopted(self) -> None:
        """AT-07 : Un simple suivi social ne produit JAMAIS ADOPTED_VERIFIED."""
        brief = SimulationBrief(goal="Lancement réseau social", target_audiences=["ProspectA"])
        ev_pack = EvidencePack(
            simulation_id="sim-soc",
            events=[
                ObservedEvent(
                    event_id="ev_tw_1",
                    simulation_id="sim-soc",
                    platform="twitter",
                    round_num=1,
                    agent_id=1,
                    agent_name="ProspectA",
                    action_type="follow",
                    timestamp="2026-10-29T10:00:00Z",
                    action_args={"target": "@OffrePro"},
                    result="ProspectA s'abonne au compte Twitter de l'offre.",
                ),
            ],
        )
        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim-soc",
            total_rounds=5,
            evidence_pack=ev_pack,
            brief=brief,
        )

        member = table.get_member("ProspectA")
        assert member is not None
        assert member.decision_status != DecisionStatus.ADOPTED_VERIFIED
        assert member.decision_status == DecisionStatus.INTERESTED

    def test_ac8_purchase_after_social_follow_is_adopted_verified(self) -> None:
        """Un prospect ayant suivi le compte PUIS souscrit formellement est ADOPTED_VERIFIED."""
        brief = SimulationBrief(goal="Lancement", target_audiences=["ProspectAcheteur"])
        ev_pack = EvidencePack(
            simulation_id="sim-follow-buy",
            events=[
                ObservedEvent(
                    event_id="ev_1",
                    simulation_id="sim-follow-buy",
                    platform="twitter",
                    round_num=1,
                    agent_id=1,
                    agent_name="ProspectAcheteur",
                    action_type="follow",
                    timestamp="2026-10-29T10:00:00Z",
                    action_args={"target": "@OffrePro"},
                    result="ProspectAcheteur s'abonne au compte Twitter.",
                ),
                ObservedEvent(
                    event_id="ev_2",
                    simulation_id="sim-follow-buy",
                    platform="twitter",
                    round_num=10,
                    agent_id=1,
                    agent_name="ProspectAcheteur",
                    action_type="post",
                    timestamp="2026-10-29T15:00:00Z",
                    action_args={"content": "J'ai validé la commande et souscrit au forfait payant !"},
                    result="ProspectAcheteur confirme son passage à l'acte.",
                ),
            ],
        )
        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim-follow-buy",
            total_rounds=15,
            evidence_pack=ev_pack,
            brief=brief,
        )
        member = table.get_member("ProspectAcheteur")
        assert member is not None
        assert member.decision_status == DecisionStatus.ADOPTED_VERIFIED


class TestAC9GenericCodebaseHygiene:
    """AC9 : Généricité absolue du code applicatif (NFR-2)."""

    FORBIDDEN_TERMS = [
        "Keova", "Essentiel", "Menopulse", "Sophrologue", "Stripe", "Wix", "Doctolib",
        "WordPress", "CPAM", "Nathalie", "Florence", "Sylvie", "Émilie", "Christine",
        "Martine", "Sophie Jouan", "Marie-Claude", "Hélène", "Marie Bourel", "Valérie", "Blandinières",
    ]

    def test_no_r8_literals_in_core_models(self) -> None:
        """Vérifie qu'aucun terme spécifique à la fixture R8 n'est présent dans le code applicatif modifié."""
        files_to_check = [
            Path(__file__).parents[1] / "app" / "models" / "actor_selection.py",
            Path(__file__).parents[1] / "app" / "models" / "cohort_coverage.py",
            Path(__file__).parents[1] / "app" / "services" / "simulation_manager.py",
            Path(__file__).parents[1] / "app" / "api" / "report.py",
        ]

        for filepath in files_to_check:
            code = filepath.read_text(encoding="utf-8")
            parsed = ast.parse(code)
            for node in ast.walk(parsed):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for term in self.FORBIDDEN_TERMS:
                        assert term.lower() not in node.value.lower(), (
                            f"Terme interdit '{term}' détecté dans {filepath.name} : '{node.value}'"
                        )
