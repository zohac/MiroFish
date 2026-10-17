"""Tests hermétiques pour la résolution d'identités et la couverture de cohorte sans collision (Story 012-1, AC1-AC5).

Valide :
  - AC1 : Zéro collision numérique d'alias (Agent_1 vs Agent_16 avec ensembles d'actions strictement disjoints).
  - AC2 : Appariement nominatif strict sans absorption par sous-chaîne (Dan vs Daniel, Anne vs Marianne).
  - AC3 : Filtrage strict des entités inéligibles (Stripe, CPAM, WhatsApp exclus de la cohorte).
  - AC4 : Dédoublonnage des alias techniques OASIS associés aux personas nommés via simulation_config.
  - AC5 : Attribution univoque de chaque événement et absence de duplication d'event_id.
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
    DecisionStatus,
    ScenarioRole,
    normalize_agent_name,
)
from app.models.evidence_pack import EvidencePack, ObservedEvent
from app.models.simulation_brief import SimulationBrief


class TestAgentIdentityResolverUnit:
    """Tests unitaires du composant AgentIdentityResolver."""

    def test_normalize_agent_name(self):
        assert normalize_agent_name("  Sophie Jouan  ") == "sophie jouan"
        assert normalize_agent_name("Émilie") == "emilie"
        assert normalize_agent_name("Agent_1") == "agent_1"
        assert normalize_agent_name("") == ""
        assert normalize_agent_name(None) == ""

    def test_resolve_numerical_aliases_no_collision(self):
        resolver = AgentIdentityResolver(simulation_id="sim_test_resolve")

        ev1 = ObservedEvent(
            event_id="evt_1",
            simulation_id="sim_test_resolve",
            platform="twitter",
            round_num=1,
            agent_id=1,
            agent_name="Agent_1",
            action_type="post",
            timestamp="2026-10-17T10:00:00Z",
        )
        ev16 = ObservedEvent(
            event_id="evt_16",
            simulation_id="sim_test_resolve",
            platform="twitter",
            round_num=1,
            agent_id=16,
            agent_name="Agent_16",
            action_type="post",
            timestamp="2026-10-17T10:00:00Z",
        )

        name1 = resolver.resolve_event_actor(ev1)
        name16 = resolver.resolve_event_actor(ev16)

        assert name1 == "Agent_1"
        assert name16 == "Agent_16"
        assert name1 != name16

    def test_resolve_with_registered_persona(self):
        resolver = AgentIdentityResolver(simulation_id="sim_test_registered")
        resolver.register_persona(1, "Sophie Jouan")
        resolver.register_persona(16, "Thomas Martin")

        ev1 = ObservedEvent(
            event_id="evt_1",
            simulation_id="sim_test_registered",
            platform="twitter",
            round_num=1,
            agent_id=1,
            agent_name="Agent_1",
            action_type="post",
            timestamp="2026-10-17T10:00:00Z",
        )
        ev16 = ObservedEvent(
            event_id="evt_16",
            simulation_id="sim_test_registered",
            platform="twitter",
            round_num=1,
            agent_id=16,
            agent_name="Agent_16",
            action_type="post",
            timestamp="2026-10-17T10:00:00Z",
        )

        assert resolver.resolve_event_actor(ev1) == "Sophie Jouan"
        assert resolver.resolve_event_actor(ev16) == "Thomas Martin"

    def test_resolve_agent_0_falsy_guard(self):
        """Vérifie que l'agent_id 0 n'est jamais traité comme falsy/None."""
        resolver = AgentIdentityResolver(simulation_id="sim_test_zero")

        # Résolution sans persona nommé -> renvoie "Agent_0"
        ev0 = ObservedEvent(
            event_id="evt_0",
            simulation_id="sim_test_zero",
            platform="twitter",
            round_num=1,
            agent_id=0,
            agent_name="Agent_0",
            action_type="post",
            timestamp="2026-10-17T10:00:00Z",
        )
        assert resolver.resolve_event_actor(ev0) == "Agent_0"

        # Enregistrement explicite pour 0
        resolver.register_persona(0, "Simon Fondateur")
        assert resolver.resolve_event_actor(ev0) == "Simon Fondateur"

        # Même événement avec nom d'agent vide -> résolu via agent_id == 0
        ev_empty = ObservedEvent(
            event_id="evt_empty",
            simulation_id="sim_test_zero",
            platform="twitter",
            round_num=1,
            agent_id=0,
            agent_name="",
            action_type="post",
            timestamp="2026-10-17T10:00:00Z",
        )
        assert resolver.resolve_event_actor(ev_empty) == "Simon Fondateur"

    def test_agent_id_map_with_string_and_int_keys(self):
        """Vérifie que agent_id_map accepte indifféremment des clés chaînes ou entières."""
        resolver = AgentIdentityResolver(
            simulation_id="sim_test_map",
            agent_id_map={"0": "Admin", 1: "Sophie"},
        )
        assert resolver.id_to_name[0] == "Admin"
        assert resolver.id_to_name[1] == "Sophie"
        assert resolver.alias_to_name["agent_0"] == "Admin"
        assert resolver.alias_to_name["agent_1"] == "Sophie"
        assert resolver.name_to_canonical["admin"] == "Admin"
        assert resolver.name_to_canonical["sophie"] == "Sophie"

    def test_robustness_against_corrupted_config(self, tmp_path, monkeypatch):
        """Vérifie qu'un agent_id invalide ou un fichier malformé ne fait pas échouer les autres entrées."""
        sim_id = "sim_corrupt_test"
        sim_dir = tmp_path / "simulations" / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        cfg_content = {
            "simulation_id": sim_id,
            "agent_configs": [
                {"agent_id": "not_an_int", "entity_name": "Ghost"},
                {"agent_id": None, "entity_name": "Nameless"},
                {"agent_id": 2, "entity_name": "Valid Agent"},
            ],
        }
        (sim_dir / "simulation_config.json").write_text(json.dumps(cfg_content), encoding="utf-8")

        from app.config import Config
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

        resolver = AgentIdentityResolver(simulation_id=sim_id)
        # L'agent 2 valide doit être chargé malgré les erreurs des agents précédents
        assert 2 in resolver.id_to_name
        assert resolver.id_to_name[2] == "Valid Agent"
        assert resolver.alias_to_name["agent_2"] == "Valid Agent"


class TestCohortIdentityResolution:
    """Tests d'intégration de CohortCoverageTable avec résolution d'identités (Story 012-1)."""

    def test_ac1_zero_collision_agent1_vs_agent16(self):
        """AC1: 23 événements d'Agent_1 et 18 d'Agent_16 restent strictement disjoints."""
        events: List[ObservedEvent] = []

        # 23 événements pour Agent_1
        for i in range(23):
            events.append(
                ObservedEvent(
                    event_id=f"evt_agent1_{i}",
                    simulation_id="sim_ac1",
                    platform="twitter" if i % 2 == 0 else "reddit",
                    round_num=i,
                    agent_id=1,
                    agent_name="Agent_1",
                    action_type="post",
                    timestamp=f"2026-10-17T10:{i:02d}:00Z",
                    action_args={"content": f"Message de l'agent 1 num {i}"},
                )
            )

        # 18 événements pour Agent_16
        for i in range(18):
            events.append(
                ObservedEvent(
                    event_id=f"evt_agent16_{i}",
                    simulation_id="sim_ac1",
                    platform="twitter" if i % 2 == 0 else "reddit",
                    round_num=i,
                    agent_id=16,
                    agent_name="Agent_16",
                    action_type="post",
                    timestamp=f"2026-10-17T11:{i:02d}:00Z",
                    action_args={"content": f"Message de l'agent 16 num {i}"},
                )
            )

        ev_pack = EvidencePack.from_events("sim_ac1", events)

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_ac1",
            actor_selection=None,
            evidence_pack=ev_pack,
        )

        member1 = table.get_member("Agent_1")
        member16 = table.get_member("Agent_16")

        assert member1 is not None, "Agent_1 doit figurer dans la cohorte"
        assert member16 is not None, "Agent_16 doit figurer dans la cohorte"

        assert member1.action_count == 23, f"Agent_1 doit avoir 23 actions, trouvé {member1.action_count}"
        assert member16.action_count == 18, f"Agent_16 doit avoir 18 actions, trouvé {member16.action_count}"

        # ÉTANCHÉITÉ ABSOLUE : ensembles d'événements disjoints
        set1 = set(member1.observed_event_ids)
        set16 = set(member16.observed_event_ids)
        assert len(set1) == 23
        assert len(set16) == 18
        assert set1.isdisjoint(set16), "Aucun événement d'Agent_1 ne doit être attribué à Agent_16 !"

    def test_ac2_strict_name_matching_no_substring_derivation(self):
        """AC2: Dan ne doit pas absorber Daniel, Anne ne doit pas absorber Marianne."""
        item_dan = ActorItem(entity_uuid="u_dan", entity_name="Dan", qualified_role=ActorRole.PERSON)
        item_daniel = ActorItem(entity_uuid="u_daniel", entity_name="Daniel", qualified_role=ActorRole.PERSON)
        item_anne = ActorItem(entity_uuid="u_anne", entity_name="Anne", qualified_role=ActorRole.PERSON)
        item_marianne = ActorItem(entity_uuid="u_marianne", entity_name="Marianne", qualified_role=ActorRole.PERSON)

        selection = ActorSelection(
            simulation_id="sim_ac2",
            project_id="prj_1",
            graph_id="grp_1",
            input_fingerprint="fp_ac2",
            actors=[item_dan, item_daniel, item_anne, item_marianne],
        )

        # Seuls Daniel et Marianne agissent
        ev_daniel = ObservedEvent(
            event_id="evt_daniel_1",
            simulation_id="sim_ac2",
            platform="twitter",
            round_num=2,
            agent_id=10,
            agent_name="Daniel",
            action_type="post",
            timestamp="2026-10-17T12:00:00Z",
            action_args={"content": "Je suis Daniel et j'ai une objection sur le tarif"},
        )
        ev_marianne = ObservedEvent(
            event_id="evt_marianne_1",
            simulation_id="sim_ac2",
            platform="reddit",
            round_num=3,
            agent_id=11,
            agent_name="Marianne",
            action_type="comment",
            timestamp="2026-10-17T12:05:00Z",
            action_args={"content": "Je suis Marianne"},
        )

        ev_pack = EvidencePack.from_events("sim_ac2", [ev_daniel, ev_marianne])

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_ac2",
            actor_selection=selection,
            evidence_pack=ev_pack,
        )

        m_dan = table.get_member("Dan")
        m_daniel = table.get_member("Daniel")
        m_anne = table.get_member("Anne")
        m_marianne = table.get_member("Marianne")

        # Dan et Anne doivent rester strictement silencieux
        assert m_dan.is_silent is True
        assert m_dan.action_count == 0
        assert m_dan.decision_status == DecisionStatus.PRESENT_NO_ACTION

        assert m_anne.is_silent is True
        assert m_anne.action_count == 0
        assert m_anne.decision_status == DecisionStatus.PRESENT_NO_ACTION

        # Daniel et Marianne ont leurs actions respectives
        assert m_daniel.is_silent is False
        assert m_daniel.action_count == 1
        assert m_daniel.observed_event_ids == ["evt_daniel_1"]

        assert m_marianne.is_silent is False
        assert m_marianne.action_count == 1
        assert m_marianne.observed_event_ids == ["evt_marianne_1"]

    def test_ac3_ineligible_entities_excluded_from_cohort(self):
        """AC3: Les entités marquées 'ineligible' ne doivent pas figurer dans la cohorte."""
        item_eligible = ActorItem(
            entity_uuid="u_eligible",
            entity_name="Sophie Jouan",
            qualified_role=ActorRole.PERSON,
            eligibility_status=EligibilityStatus.ELIGIBLE,
        )
        item_stripe = ActorItem(
            entity_uuid="u_stripe",
            entity_name="Stripe",
            qualified_role=ActorRole.ORGANIZATION,
            eligibility_status=EligibilityStatus.INELIGIBLE,
        )
        item_cpam = ActorItem(
            entity_uuid="u_cpam",
            entity_name="CPAM",
            qualified_role=ActorRole.ORGANIZATION,
            eligibility_status=EligibilityStatus.INELIGIBLE,
        )

        selection = ActorSelection(
            simulation_id="sim_ac3",
            project_id="prj_1",
            graph_id="grp_1",
            input_fingerprint="fp_ac3",
            actors=[item_eligible, item_stripe, item_cpam],
        )

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_ac3",
            actor_selection=selection,
            evidence_pack=None,
        )

        assert table.total_members == 1
        assert table.get_member("Sophie Jouan") is not None
        assert table.get_member("Stripe") is None, "Stripe inéligible ne doit pas être dans la cohorte"
        assert table.get_member("CPAM") is None, "CPAM inéligible ne doit pas être dans la cohorte"

    def test_ac4_deduplication_of_technical_aliases_via_config(self, tmp_path, monkeypatch):
        """AC4: Unification des alias Agent_0 -> Simon et Agent_1 -> Sophie sans doublons."""
        sim_id = "sim_ac4_dedup"
        sim_dir = tmp_path / "simulations" / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        # Créer simulation_config.json
        cfg_content = {
            "simulation_id": sim_id,
            "agent_configs": [
                {"agent_id": 0, "entity_name": "Simon", "entity_uuid": "u_simon"},
                {"agent_id": 1, "entity_name": "Sophie", "entity_uuid": "u_sophie"},
            ],
        }
        (sim_dir / "simulation_config.json").write_text(json.dumps(cfg_content), encoding="utf-8")

        # Mock de Config.UPLOAD_FOLDER
        from app.config import Config
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

        # Événements émis sous forme Agent_0 et Agent_1
        ev0 = ObservedEvent(
            event_id="evt_0",
            simulation_id=sim_id,
            platform="twitter",
            round_num=1,
            agent_id=0,
            agent_name="Agent_0",
            action_type="post",
            timestamp="2026-10-17T10:00:00Z",
            action_args={"content": "Post du fondateur Simon"},
        )
        ev1 = ObservedEvent(
            event_id="evt_1",
            simulation_id=sim_id,
            platform="reddit",
            round_num=1,
            agent_id=1,
            agent_name="Agent_1",
            action_type="comment",
            timestamp="2026-10-17T10:01:00Z",
            action_args={"content": "Commentaire de Sophie"},
        )

        ev_pack = EvidencePack.from_events(sim_id, [ev0, ev1])

        # Actor selection avec Simon et Sophie
        item0 = ActorItem(entity_uuid="u_simon", entity_name="Simon", qualified_role=ActorRole.PERSON)
        item1 = ActorItem(entity_uuid="u_sophie", entity_name="Sophie", qualified_role=ActorRole.PERSON)
        selection = ActorSelection(
            simulation_id=sim_id,
            project_id="prj_1",
            graph_id="grp_1",
            input_fingerprint="fp_ac4",
            actors=[item0, item1],
        )

        table = CohortCoverageTable.build_from_simulation(
            simulation_id=sim_id,
            actor_selection=selection,
            evidence_pack=ev_pack,
        )

        # La cohorte ne doit avoir que 2 membres : Simon et Sophie
        assert table.total_members == 2
        assert table.get_member("Agent_0") is None, "L'alias Agent_0 ne doit pas être dupliqué"
        assert table.get_member("Agent_1") is None, "L'alias Agent_1 ne doit pas être dupliqué"

        m_simon = table.get_member("Simon")
        m_sophie = table.get_member("Sophie")

        assert m_simon is not None
        assert m_simon.action_count == 1
        assert m_simon.observed_event_ids == ["evt_0"]

        assert m_sophie is not None
        assert m_sophie.action_count == 1
        assert m_sophie.observed_event_ids == ["evt_1"]

    def test_ac5_unique_event_assignment_and_deduplication(self):
        """AC5: Chaque événement est attribué de manière univoque, 0 duplication d'event_id."""
        ev = ObservedEvent(
            event_id="evt_unique_1",
            simulation_id="sim_ac5",
            platform="twitter",
            round_num=1,
            agent_id=5,
            agent_name="Agent_5",
            action_type="post",
            timestamp="2026-10-17T10:00:00Z",
            action_args={"content": "Action unique"},
        )

        # Pack contenant accidentellement deux fois le même événement
        ev_pack = EvidencePack.from_events("sim_ac5", [ev, ev])

        table = CohortCoverageTable.build_from_simulation(
            simulation_id="sim_ac5",
            actor_selection=None,
            evidence_pack=ev_pack,
        )

        member = table.get_member("Agent_5")
        assert member is not None
        # L'action ne doit être comptée qu'une seule fois
        assert member.action_count == 1
        assert member.observed_event_ids == ["evt_unique_1"]

        # Contrôle global d'unicité sur toute la table
        all_refs = []
        for m in table.members:
            all_refs.extend(m.observed_event_ids)
        assert len(all_refs) == len(set(all_refs)), "Tous les event_ids de la table doivent être strictement uniques"
