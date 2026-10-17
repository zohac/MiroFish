"""Tests hermétiques pour les rôles de scénario et statuts de décision d'adoption déterministes (Story 012-2, AC1-AC6).

Valide :
  - AC1 : Typologie de rôles sans inférence commerciale aveugle (FOUNDER, TEAM_MEMBER, EXISTING_USER, PROSPECT, PARTNER, INSTITUTION, UNKNOWN).
          Aucun acteur n'est forcé en PROSPECT par simple statut PERSON. Repli sur UNKNOWN.
  - AC2 : Statut NOT_APPLICABLE pour les fondateurs, collaborateurs internes et institutions non clientes.
  - AC3 : Zéro faux statut ADOPTED par simple absence d'objection (Anti-Affabulation). Un acteur actif sans objection est NO_DECISION ou INTERESTED, jamais ADOPTED.
  - AC4 : Nuance et détection probante des statuts décisionnels (ADOPTED_VERIFIED, DEMO_REQUESTED, INTERESTED, HESITANT, REJECTED_EXPRESSED, NO_DECISION).
  - AC5 : Calcul assaini du taux d'adoption de la cohorte excluant strictement les membres NOT_APPLICABLE et fondateurs du dénominateur.
  - AC6 : Rétrocompatibilité ascendante avec les formats historiques (ADOPTED, REJECTED, UNDECIDED) et non-régression.
"""

from __future__ import annotations

import json
import os
from typing import List

import pytest

from app.models.actor_eligibility import ActorRole, EligibilityStatus
from app.models.actor_selection import ActorItem, ActorSelection
from app.models.cohort_coverage import (
    AgentIdentityResolver,
    CohortCoverageTable,
    CohortMemberStatus,
    DecisionStatus,
    ScenarioRole,
)
from app.models.evidence_pack import EvidencePack, ObservedEvent
from app.models.simulation_brief import SimulationBrief


class TestScenarioRoleResolution:
    """Tests unitaires et d'intégration pour l'attribution des rôles de scénario (AC1)."""

    def test_ac1_scenario_role_parsing_and_synonyms(self):
        """Vérifie le parsing complet et les synonymes de ScenarioRole."""
        assert ScenarioRole.from_str("founder") == ScenarioRole.FOUNDER
        assert ScenarioRole.from_str("fondateur") == ScenarioRole.FOUNDER
        assert ScenarioRole.from_str("creator") == ScenarioRole.FOUNDER
        assert ScenarioRole.from_str("team_member") == ScenarioRole.TEAM_MEMBER
        assert ScenarioRole.from_str("collaborateur") == ScenarioRole.TEAM_MEMBER
        assert ScenarioRole.from_str("employé") == ScenarioRole.TEAM_MEMBER
        assert ScenarioRole.from_str("existing_user") == ScenarioRole.EXISTING_USER
        assert ScenarioRole.from_str("client") == ScenarioRole.EXISTING_USER
        assert ScenarioRole.from_str("prospect") == ScenarioRole.PROSPECT
        assert ScenarioRole.from_str("lead") == ScenarioRole.PROSPECT
        assert ScenarioRole.from_str("partner") == ScenarioRole.PARTNER
        assert ScenarioRole.from_str("partenaire") == ScenarioRole.PARTNER
        assert ScenarioRole.from_str("institution") == ScenarioRole.INSTITUTION
        assert ScenarioRole.from_str("régulateur") == ScenarioRole.INSTITUTION
        assert ScenarioRole.from_str("unknown") == ScenarioRole.UNKNOWN
        assert ScenarioRole.from_str("anything_else") == ScenarioRole.UNKNOWN
        assert ScenarioRole.from_str(None) == ScenarioRole.UNKNOWN

    def test_ac1_no_blind_prospect_forcing_from_actor_role(self):
        """Vérifie qu'un ActorRole.PERSON n'est plus forcé en PROSPECT (AC1)."""
        # Auparavant: PERSON -> PROSPECT
        # Désormais: PERSON -> UNKNOWN sans preuve contextuelle
        assert ScenarioRole.from_actor_role(ActorRole.PERSON) == ScenarioRole.UNKNOWN
        assert ScenarioRole.from_actor_role(ActorRole.ORGANIZATION) == ScenarioRole.INSTITUTION
        assert ScenarioRole.from_actor_role(ActorRole.COLLECTIVE) == ScenarioRole.OBSERVER
        assert ScenarioRole.from_actor_role(None) == ScenarioRole.UNKNOWN

    def test_ac1_hierarchical_role_resolution(self, tmp_path, monkeypatch):
        """Vérifie la hiérarchie de résolution du rôle : brief > config > selection > repli UNKNOWN."""
        from app.config import Config
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

        # Brief avec fondateur et audience
        brief = SimulationBrief(
            goal="Lancement plateforme. Le fondateur est Simon Jouan.",
            target_audiences=["Développeurs", "Alice"],
        )

        # Config simulation OASIS avec rôle explicite pour Bob
        sim_dir = tmp_path / "simulations" / "sim_role_hier"
        sim_dir.mkdir(parents=True)
        config_path = sim_dir / "simulation_config.json"
        config_data = {
            "profiles": [
                {"name": "Bob", "role": "team_member"},
                {"name": "Charlie", "role": "partner"},
            ]
        }
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        # Actor selection
        actors = [
            ActorItem(entity_uuid="u1", entity_name="Simon Jouan", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u2", entity_name="Alice", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u3", entity_name="Bob", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u4", entity_name="Charlie", qualified_role=ActorRole.ORGANIZATION),
            ActorItem(entity_uuid="u5", entity_name="David Unknown", qualified_role=ActorRole.PERSON),
        ]
        selection = ActorSelection(
            simulation_id="sim_role_hier",
            project_id="p1",
            graph_id="g1",
            input_fingerprint="fp1",
            actors=actors,
        )

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_role_hier",
            actor_selection=selection,
            brief=brief,
        )

        assert table.get_member("Simon Jouan").scenario_role == ScenarioRole.FOUNDER
        assert table.get_member("Alice").scenario_role == ScenarioRole.PROSPECT
        assert table.get_member("Bob").scenario_role == ScenarioRole.TEAM_MEMBER
        assert table.get_member("Charlie").scenario_role == ScenarioRole.PARTNER
        # David Unknown n'est dans aucun brief ni config -> repli UNKNOWN, pas PROSPECT !
        assert table.get_member("David Unknown").scenario_role == ScenarioRole.UNKNOWN


class TestDecisionStatusDeterministic:
    """Tests de qualification honnête des décisions et règles anti-affabulation (AC2, AC3, AC4)."""

    def test_ac2_founder_team_institution_assigned_not_applicable(self):
        """Vérifie que les fondateurs, collaborateurs et institutions reçoivent NOT_APPLICABLE (AC2)."""
        brief = SimulationBrief(
            goal="Lancement Keova. Le fondateur est Simon et la cofondatrice est Sophie.",
        )
        actors = [
            ActorItem(entity_uuid="u1", entity_name="Simon", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u2", entity_name="Sophie", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u3", entity_name="Ministère de l'Économie", qualified_role=ActorRole.ORGANIZATION),
        ]
        selection = ActorSelection(
            simulation_id="sim_ac2",
            project_id="p1",
            graph_id="g1",
            input_fingerprint="fp1",
            actors=actors,
        )

        # Les fondateurs et institutions ont agi (posts, déclarations)
        events = [
            ObservedEvent(
                event_id="e1",
                simulation_id="sim_ac2",
                platform="twitter",
                round_num=1,
                agent_id=1,
                agent_name="Simon",
                action_type="post",
                timestamp="2026-10-17T10:00:00Z",
                action_args={"content": "Bienvenue sur notre nouvelle plateforme !"},
            ),
            ObservedEvent(
                event_id="e2",
                simulation_id="sim_ac2",
                platform="twitter",
                round_num=2,
                agent_id=2,
                agent_name="Sophie",
                action_type="post",
                timestamp="2026-10-17T10:05:00Z",
                action_args={"content": "Le service est ouvert à tous."},
            ),
            ObservedEvent(
                event_id="e3",
                simulation_id="sim_ac2",
                platform="twitter",
                round_num=3,
                agent_id=3,
                agent_name="Ministère de l'Économie",
                action_type="post",
                timestamp="2026-10-17T10:10:00Z",
                action_args={"content": "Publication du nouveau décret cadre."},
            ),
        ]
        evidence = EvidencePack(simulation_id="sim_ac2", events=events)

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_ac2",
            actor_selection=selection,
            evidence_pack=evidence,
            brief=brief,
        )

        simon = table.get_member("Simon")
        sophie = table.get_member("Sophie")
        institution = table.get_member("Ministère de l'Économie")

        assert simon.scenario_role == ScenarioRole.FOUNDER
        assert simon.decision_status == DecisionStatus.NOT_APPLICABLE
        assert simon.action_count == 1

        assert sophie.scenario_role == ScenarioRole.FOUNDER
        assert sophie.decision_status == DecisionStatus.NOT_APPLICABLE

        assert institution.scenario_role == ScenarioRole.INSTITUTION
        assert institution.decision_status == DecisionStatus.NOT_APPLICABLE

    def test_ac3_zero_adopted_without_probative_proof_anti_affabulation(self):
        """Vérifie qu'un prospect actif sans objection N'EST JAMAIS qualifié ADOPTED sans acte d'achat (AC3)."""
        actors = [
            ActorItem(entity_uuid="u1", entity_name="Camille", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u2", entity_name="Julien", qualified_role=ActorRole.PERSON),
        ]
        selection = ActorSelection(
            simulation_id="sim_ac3",
            project_id="p1",
            graph_id="g1",
            input_fingerprint="fp1",
            actors=actors,
        )

        # Camille poste un message d'encouragement général
        # Julien poste un message anodin
        # Aucun d'eux ne formule d'objection
        events = [
            ObservedEvent(
                event_id="e1",
                simulation_id="sim_ac3",
                platform="twitter",
                round_num=1,
                agent_id=1,
                agent_name="Camille",
                action_type="post",
                timestamp="2026-10-17T10:00:00Z",
                action_args={"content": "Bonne chance pour le projet !"},
            ),
            ObservedEvent(
                event_id="e2",
                simulation_id="sim_ac3",
                platform="twitter",
                round_num=2,
                agent_id=2,
                agent_name="Julien",
                action_type="post",
                timestamp="2026-10-17T10:05:00Z",
                action_args={"content": "Quel temps fait-il aujourd'hui ?"},
            ),
        ]
        evidence = EvidencePack(simulation_id="sim_ac3", events=events)

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_ac3",
            actor_selection=selection,
            evidence_pack=evidence,
        )

        camille = table.get_member("Camille")
        julien = table.get_member("Julien")

        # Règle anti-affabulation : JAMAIS ADOPTED
        assert camille.decision_status != DecisionStatus.ADOPTED_VERIFIED
        assert camille.decision_status in (DecisionStatus.NO_DECISION, DecisionStatus.INTERESTED)

        assert julien.decision_status != DecisionStatus.ADOPTED_VERIFIED
        assert julien.decision_status == DecisionStatus.NO_DECISION

    def test_ac4_decision_nuance_and_probative_transitions(self):
        """Vérifie les transitions et statuts : ADOPTED_VERIFIED, DEMO_REQUESTED, INTERESTED, HESITANT, REJECTED (AC4)."""
        actors = [
            ActorItem(entity_uuid="u1", entity_name="Alice Adoptée", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u2", entity_name="Bob Démo", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u3", entity_name="Claire Intéressée", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u4", entity_name="Denis Hésitant", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u5", entity_name="Emma Refus", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u6", entity_name="Félix Silencieux", qualified_role=ActorRole.PERSON),
        ]
        selection = ActorSelection(
            simulation_id="sim_ac4",
            project_id="p1",
            graph_id="g1",
            input_fingerprint="fp1",
            actors=actors,
        )

        events = [
            # Alice a souscrit formellement (preuve probante)
            ObservedEvent(
                event_id="e1",
                simulation_id="sim_ac4",
                platform="twitter",
                round_num=5,
                agent_id=1,
                agent_name="Alice Adoptée",
                action_type="post",
                timestamp="2026-10-17T10:00:00Z",
                action_args={"content": "Je viens de valider la commande et souscrit à l'offre payante !"},
            ),
            # Bob a demandé une démo
            ObservedEvent(
                event_id="e2",
                simulation_id="sim_ac4",
                platform="twitter",
                round_num=6,
                agent_id=2,
                agent_name="Bob Démo",
                action_type="post",
                timestamp="2026-10-17T10:05:00Z",
                action_args={"content": "Je demande une démo pour notre équipe technique."},
            ),
            # Claire est intéressée
            ObservedEvent(
                event_id="e3",
                simulation_id="sim_ac4",
                platform="twitter",
                round_num=7,
                agent_id=3,
                agent_name="Claire Intéressée",
                action_type="post",
                timestamp="2026-10-17T10:10:00Z",
                action_args={"content": "C'est très prometteur comme initiative, à suivre de près."},
            ),
            # Denis a des objections modérées (Hésitant)
            ObservedEvent(
                event_id="e4",
                simulation_id="sim_ac4",
                platform="twitter",
                round_num=8,
                agent_id=4,
                agent_name="Denis Hésitant",
                action_type="post",
                timestamp="2026-10-17T10:15:00Z",
                action_args={"content": "Je ne suis pas convaincu par l'ergonomie actuelle.", "objection": "Manque d'ergonomie"},
            ),
            # Emma refuse pour cause de prix trop élevé
            ObservedEvent(
                event_id="e5",
                simulation_id="sim_ac4",
                platform="twitter",
                round_num=9,
                agent_id=5,
                agent_name="Emma Refus",
                action_type="post",
                timestamp="2026-10-17T10:20:00Z",
                action_args={"content": "C'est beaucoup trop cher, je refuse cette offre.", "objection": "Prix trop élevé"},
            ),
            # Félix ne fait aucune action (silencieux)
        ]
        evidence = EvidencePack(simulation_id="sim_ac4", events=events)

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_ac4",
            actor_selection=selection,
            evidence_pack=evidence,
        )

        assert table.get_member("Alice Adoptée").decision_status == DecisionStatus.ADOPTED_VERIFIED
        assert table.get_member("Bob Démo").decision_status == DecisionStatus.DEMO_REQUESTED
        assert table.get_member("Claire Intéressée").decision_status == DecisionStatus.INTERESTED
        assert table.get_member("Denis Hésitant").decision_status == DecisionStatus.HESITANT
        assert table.get_member("Emma Refus").decision_status == DecisionStatus.REJECTED_EXPRESSED
        assert table.get_member("Félix Silencieux").decision_status == DecisionStatus.PRESENT_NO_ACTION
        assert table.get_member("Félix Silencieux").is_silent is True


class TestAdoptionRateSanitization:
    """Tests pour le calcul du taux d'adoption assaini sans pollution par les acteurs non clients (AC5)."""

    def test_ac5_adoption_rate_excludes_not_applicable_and_founders(self):
        """Vérifie que les fondateurs et NOT_APPLICABLE ne polluent pas le ratio d'adoption (AC5)."""
        m_founder = CohortMemberStatus(
            persona_name="Simon Founder",
            scenario_role=ScenarioRole.FOUNDER,
            action_count=10,
            observed_event_ids=["e1"],
            decision_status=DecisionStatus.NOT_APPLICABLE,
        )
        m_team = CohortMemberStatus(
            persona_name="Jean Intern",
            scenario_role=ScenarioRole.TEAM_MEMBER,
            action_count=5,
            observed_event_ids=["e2"],
            decision_status=DecisionStatus.NOT_APPLICABLE,
        )
        m_institution = CohortMemberStatus(
            persona_name="ANSSI",
            scenario_role=ScenarioRole.INSTITUTION,
            action_count=2,
            observed_event_ids=["e3"],
            decision_status=DecisionStatus.NOT_APPLICABLE,
        )
        # 2 prospects réels : 1 converti avéré, 1 rejeté
        m_prospect1 = CohortMemberStatus(
            persona_name="Client A",
            scenario_role=ScenarioRole.PROSPECT,
            action_count=3,
            observed_event_ids=["e4"],
            decision_status=DecisionStatus.ADOPTED_VERIFIED,
        )
        m_prospect2 = CohortMemberStatus(
            persona_name="Client B",
            scenario_role=ScenarioRole.PROSPECT,
            action_count=2,
            observed_event_ids=["e5"],
            decision_status=DecisionStatus.REJECTED_EXPRESSED,
        )

        table = CohortCoverageTable(
            simulation_id="sim_ac5",
            members=[m_founder, m_team, m_institution, m_prospect1, m_prospect2],
        )

        # 5 membres au total
        assert table.total_members == 5
        # Mais seulement 2 prospects réels
        assert len(table.prospect_members) == 2
        # Taux d'adoption = 1 converti sur 2 prospects = 50.0 % (0.5), et non 1 sur 5 (20 %) ni faussé par les fondateurs
        assert table.adoption_rate == 0.5

    def test_ac5_adoption_rate_zero_when_no_prospects(self):
        """Vérifie que adoption_rate retourne 0.0 sans crash si la cohorte n'a aucun prospect."""
        m_founder = CohortMemberStatus(
            persona_name="Simon",
            scenario_role=ScenarioRole.FOUNDER,
            action_count=5,
            observed_event_ids=["e1"],
            decision_status=DecisionStatus.NOT_APPLICABLE,
        )
        table = CohortCoverageTable(simulation_id="sim_empty_p", members=[m_founder])
        assert table.adoption_rate == 0.0


class TestBackwardCompatibilityAndNonRegression:
    """Tests de rétrocompatibilité et désérialisation ascendante (AC6)."""

    def test_ac6_backward_compatible_deserialization_from_legacy_json(self, tmp_path):
        """Vérifie la relecture transparente d'un export JSON historique contenant ADOPTED et REJECTED (AC6)."""
        legacy_data = {
            "simulation_id": "sim_legacy_011",
            "horizon_hours": 72.0,
            "total_rounds": 40,
            "members": [
                {
                    "persona_name": "Old Agent Adopted",
                    "scenario_role": "PROSPECT",
                    "action_count": 4,
                    "observed_event_ids": ["e1", "e2"],
                    "objections": [],
                    "citations": [],
                    "decision_status": "ADOPTED",  # Ancien format
                    "is_silent": False,
                },
                {
                    "persona_name": "Old Agent Rejected",
                    "scenario_role": "PROSPECT",
                    "action_count": 2,
                    "observed_event_ids": ["e3"],
                    "objections": ["Trop cher"],
                    "citations": [],
                    "decision_status": "REJECTED",  # Ancien format
                    "is_silent": False,
                },
                {
                    "persona_name": "Old Agent Undecided",
                    "scenario_role": "PROSPECT",
                    "action_count": 1,
                    "observed_event_ids": ["e4"],
                    "objections": [],
                    "citations": [],
                    "decision_status": "UNDECIDED",  # Ancien format
                    "is_silent": False,
                },
            ],
        }

        legacy_path = tmp_path / "legacy_cohort.json"
        legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")

        loaded = CohortCoverageTable.load_from_file(str(legacy_path))
        assert loaded is not None
        assert loaded.simulation_id == "sim_legacy_011"
        assert len(loaded.members) == 3

        # Vérification du mapping d'alias transparent
        m1 = loaded.get_member("Old Agent Adopted")
        assert m1.decision_status == DecisionStatus.ADOPTED_VERIFIED
        assert m1.decision_status == DecisionStatus.ADOPTED  # Alias transparent

        m2 = loaded.get_member("Old Agent Rejected")
        assert m2.decision_status == DecisionStatus.REJECTED_EXPRESSED
        assert m2.decision_status == DecisionStatus.REJECTED  # Alias transparent

        m3 = loaded.get_member("Old Agent Undecided")
        assert m3.decision_status == DecisionStatus.NO_DECISION
        assert m3.decision_status == DecisionStatus.UNDECIDED  # Alias transparent

        # Vérification de la persistance et re-sérialisation
        exported = loaded.to_dict()
        assert exported["adoption_rate"] == round(1 / 3, 4)
        assert exported["status_summary"]["adopted"] == 1
        assert exported["status_summary"]["rejected"] == 1
        assert exported["status_summary"]["undecided"] == 1


class TestReviewFindingsPatches:
    """Tests dédiés validant les 5 correctifs issus de la revue de code contradictoire BMAD."""

    def test_patch1_probative_detection_in_long_text_beyond_160_chars(self):
        """Vérifie que les preuves d'adoption situées au-delà du 160e caractère sont bien détectées (Patch 1)."""
        actors = [
            ActorItem(entity_uuid="u1", entity_name="LongText Client", qualified_role=ActorRole.PERSON),
        ]
        selection = ActorSelection(
            simulation_id="sim_patch1",
            project_id="p1",
            graph_id="g1",
            input_fingerprint="fp1",
            actors=actors,
        )
        # Message de 220 caractères où la preuve est après le 160e caractère
        long_content = (
            "Nous avons analysé toutes les alternatives du marché pendant plusieurs semaines "
            "avec l'ensemble du comité technique et après délibération approfondie et sérieuse, "
            "j'ai souscrit au plan annuel ce matin."
        )
        assert len(long_content) > 170
        assert "souscrit" in long_content[160:]

        events = [
            ObservedEvent(
                event_id="e1",
                simulation_id="sim_patch1",
                platform="twitter",
                round_num=2,
                agent_id=1,
                agent_name="LongText Client",
                action_type="post",
                timestamp="2026-10-17T10:00:00Z",
                action_args={"content": long_content},
            )
        ]
        evidence = EvidencePack(simulation_id="sim_patch1", events=events)

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_patch1",
            actor_selection=selection,
            evidence_pack=evidence,
        )

        member = table.get_member("LongText Client")
        assert member.decision_status == DecisionStatus.ADOPTED_VERIFIED
        # Les citations restent concises (<= 160 caractères)
        assert len(member.verbatim_citations[0]) <= 160

    def test_patch2_natural_founder_phrasing_in_brief(self):
        """Vérifie l'extraction robuste des fondateurs avec phrasés naturels (Patch 2)."""
        brief = SimulationBrief(
            goal="Le fondateur Simon Jouan a lancé la plateforme en 2024. Sophie, cofondatrice, supervise les opérations.",
        )
        actors = [
            ActorItem(entity_uuid="u1", entity_name="Simon Jouan", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u2", entity_name="Sophie", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u3", entity_name="Autre Personne", qualified_role=ActorRole.PERSON),
        ]
        selection = ActorSelection(
            simulation_id="sim_patch2",
            project_id="p1",
            graph_id="g1",
            input_fingerprint="fp1",
            actors=actors,
        )

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_patch2",
            actor_selection=selection,
            brief=brief,
        )

        assert table.get_member("Simon Jouan").scenario_role == ScenarioRole.FOUNDER
        assert table.get_member("Simon Jouan").decision_status == DecisionStatus.NOT_APPLICABLE
        assert table.get_member("Sophie").scenario_role == ScenarioRole.FOUNDER
        assert table.get_member("Sophie").decision_status == DecisionStatus.NOT_APPLICABLE
        assert table.get_member("Autre Personne").scenario_role == ScenarioRole.UNKNOWN

    def test_patch3_present_tense_adoption_demo_and_interest_inflections(self):
        """Vérifie la détection des verbes conjugués au présent et variantes non accentuées (Patch 3)."""
        actors = [
            ActorItem(entity_uuid="u1", entity_name="Client Souscrit", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u2", entity_name="Client Achete", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u3", entity_name="Client Commande", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u4", entity_name="Client Demo", qualified_role=ActorRole.PERSON),
            ActorItem(entity_uuid="u5", entity_name="Client Interesse", qualified_role=ActorRole.PERSON),
        ]
        selection = ActorSelection(
            simulation_id="sim_patch3",
            project_id="p1",
            graph_id="g1",
            input_fingerprint="fp1",
            actors=actors,
        )

        events = [
            ObservedEvent(
                event_id="e1", simulation_id="sim_patch3", platform="twitter", round_num=1,
                agent_id=1, agent_name="Client Souscrit", action_type="post",
                timestamp="2026-10-17T10:00:00Z", action_args={"content": "Je souscris immédiatement au forfait premium."},
            ),
            ObservedEvent(
                event_id="e2", simulation_id="sim_patch3", platform="twitter", round_num=2,
                agent_id=2, agent_name="Client Achete", action_type="post",
                timestamp="2026-10-17T10:05:00Z", action_args={"content": "J'achète la licence dès aujourd'hui."},
            ),
            ObservedEvent(
                event_id="e3", simulation_id="sim_patch3", platform="twitter", round_num=3,
                agent_id=3, agent_name="Client Commande", action_type="post",
                timestamp="2026-10-17T10:10:00Z", action_args={"content": "Je passe commande pour notre service."},
            ),
            ObservedEvent(
                event_id="e4", simulation_id="sim_patch3", platform="twitter", round_num=4,
                agent_id=4, agent_name="Client Demo", action_type="post",
                timestamp="2026-10-17T10:15:00Z", action_args={"content": "Demande de démo pour notre équipe technique."},
            ),
            ObservedEvent(
                event_id="e5", simulation_id="sim_patch3", platform="twitter", round_num=5,
                agent_id=5, agent_name="Client Interesse", action_type="post",
                timestamp="2026-10-17T10:20:00Z", action_args={"content": "Je suis très intéressé par cette solution."},
            ),
        ]
        evidence = EvidencePack(simulation_id="sim_patch3", events=events)

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_patch3",
            actor_selection=selection,
            evidence_pack=evidence,
        )

        assert table.get_member("Client Souscrit").decision_status == DecisionStatus.ADOPTED_VERIFIED
        assert table.get_member("Client Achete").decision_status == DecisionStatus.ADOPTED_VERIFIED
        assert table.get_member("Client Commande").decision_status == DecisionStatus.ADOPTED_VERIFIED
        assert table.get_member("Client Demo").decision_status == DecisionStatus.DEMO_REQUESTED
        assert table.get_member("Client Interesse").decision_status == DecisionStatus.INTERESTED

    def test_patch4_members_and_alias_lookup_in_enums(self):
        """Vérifie la résolution instantanée O(1) via cls.__members__ pour canonicals et alias (Patch 4)."""
        assert ScenarioRole.from_str("FOUNDER") == ScenarioRole.FOUNDER
        assert ScenarioRole.from_str("TEAM_MEMBER") == ScenarioRole.TEAM_MEMBER
        assert DecisionStatus.from_str("ADOPTED_VERIFIED") == DecisionStatus.ADOPTED_VERIFIED
        assert DecisionStatus.from_str("ADOPTED") == DecisionStatus.ADOPTED_VERIFIED
        assert DecisionStatus.from_str("REJECTED") == DecisionStatus.REJECTED_EXPRESSED
        assert DecisionStatus.from_str("UNDECIDED") == DecisionStatus.NO_DECISION
        assert DecisionStatus.from_str("NOT_APPLICABLE") == DecisionStatus.NOT_APPLICABLE

    def test_patch5_from_actor_role_case_insensitivity(self):
        """Vérifie la tolérance insensible à la casse des chaînes de rôles d'acteurs (Patch 5)."""
        assert ScenarioRole.from_actor_role(ActorRole.ORGANIZATION) == ScenarioRole.INSTITUTION
        assert ScenarioRole.from_actor_role("organization") == ScenarioRole.INSTITUTION
        assert ScenarioRole.from_actor_role("ORGANIZATION") == ScenarioRole.INSTITUTION
        assert ScenarioRole.from_actor_role("COLLECTIVE") == ScenarioRole.OBSERVER
        assert ScenarioRole.from_actor_role("collective") == ScenarioRole.OBSERVER
        assert ScenarioRole.from_actor_role("PERSON") == ScenarioRole.UNKNOWN
        assert ScenarioRole.from_actor_role("person") == ScenarioRole.UNKNOWN

