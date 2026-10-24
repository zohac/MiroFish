"""Tests hermétiques pour Story 012-3 : Extraction assainie et réconciliation déterministe avec l'EvidencePack.

Vérifie l'ensemble des critères d'acceptation AC1 à AC6 :
  - AC1 : Zéro faux agent extrait (anti-mots parasites: « Si », « Dès », etc.).
  - AC2 : Exclusion des titres et en-têtes Markdown (#, ##, ###).
  - AC3 : Extraction d'actions sans dépendance d'identifiants evt_* dans le texte Markdown.
  - AC4 : Réconciliation déterministe avec l'EvidencePack (sans collision d'identités, attribution d'event_id, VERIFIED).
  - AC5 : Contrôle anti-affabulation et diagnostic transparent (déclassement motivé, limitations enrichies, interdiction d'inférence d'achat).
  - AC6 : Rétrocompatibilité (from_dict/to_dict) et non-régression.
"""

import json
import os
import pytest

from app.models.cohort_coverage import AgentIdentityResolver, ScenarioRole
from app.models.evidence_pack import EvidencePack, ObservedEvent
from app.models.report_claim import (
    ClaimKind,
    InformationOrigin,
    ReportClaim,
    ReportClaimRegistry,
    VerificationStatus,
)
from app.services.report_agent import ReportAgent
from app.services.simulation_action_verifier import SimulationActionVerifier


class TestReportClaimsExtractionAndReconciliation:
    """Suite de tests unitaires et d'intégration hermétiques pour Story 012-3."""

    def test_ac1_zero_false_agent_extracted_anti_parasite(self):
        """AC1 : Mots de liaison ou conjonctions (« Si », « Dès », « Or », « Donc », etc.) ne sont jamais extraits comme agents."""
        agent = ReportAgent(
            graph_id="graph_test",
            simulation_id="sim_ac1_test",
            simulation_requirement="Tester AC1",
        )

        known_names = {"Simon", "Sophie Jouan", "Émilie", "Julien"}
        sample_markdown = """
# Section 1 : Observations
- Si Simon avait su pour l'offre, la réaction aurait été différente.
- Dès le début du Round 1, la discussion s'est fortement animée.
- Or, Julien a exprimé son désaccord sur la grille tarifaire.
- Donc l'équipe a dû revoir sa copie.
- Selon Sophie Jouan, l'infrastructure est prête.
- Après analyse, les perspectives demeurent favorables.
- Tout porte à croire qu'un accord est proche.
- En conclusion, les débats furent riches.
"""
        claims = agent.extract_claims_from_content(sample_markdown, known_agent_names=known_names)

        extracted_agents = [c.agent_name for c in claims if c.agent_name is not None]

        # Aucun des mots parasites ne doit être pris pour un nom d'agent
        parasite_words = {"Si", "Dès", "Or", "Donc", "Selon", "Après", "Tout", "En"}
        for word in parasite_words:
            assert word not in extracted_agents, f"Le mot parasite '{word}' a été extrait comme nom d'agent !"

        # Les agents réels doivent être détectés
        assert "Julien" in extracted_agents
        assert "Sophie Jouan" in extracted_agents

    def test_ac2_exclusion_of_markdown_headings(self):
        """AC2 : Les lignes d'en-têtes Markdown ne sont JAMAIS converties en ReportClaim."""
        agent = ReportAgent(
            graph_id="graph_test",
            simulation_id="sim_ac2_test",
            simulation_requirement="Tester AC2",
        )

        sample_markdown = """
# Synthèse Exécutive et Perspectives
## 1. Contexte documentaire du projet Keova
### 1.1 Objectifs de la simulation sociale
#### 1.1.1 Détails techniques et rounds
##### 2. Observations majeures
- Émilie a publié un tweet enthousiaste sur la plateforme.
"""
        claims = agent.extract_claims_from_content(sample_markdown)

        # Seule la puce doit être extraite comme affirmation
        assert len(claims) == 1
        assert "Émilie a publié un tweet" in claims[0].text
        # Aucun titre ne doit se trouver dans les claims
        for c in claims:
            assert not c.text.startswith("#")
            assert "Synthèse Exécutive" not in c.text
            assert "Contexte documentaire" not in c.text

    def test_ac3_action_extraction_without_hardcoded_event_ids(self):
        """AC3 : Phrases décrivant des actions sont typées OBSERVED_SOCIAL_ACTION sans exiger d'evt_* littéral."""
        agent = ReportAgent(
            graph_id="graph_test",
            simulation_id="sim_ac3_test",
            simulation_requirement="Tester AC3",
        )

        sample_markdown = """
## Événements simulés
- Round 2 : Agent Julien a vivement critiqué l'augmentation du prix du forfait.
- Sophie Jouan a répondu au message en proposant un compromis technique.
- Émilie a partagé une capture d'écran du devis.
"""
        claims = agent.extract_claims_from_content(
            sample_markdown,
            known_agent_names={"Julien", "Sophie Jouan", "Émilie"},
        )

        assert len(claims) == 3
        for c in claims:
            assert c.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
            assert c.origin == InformationOrigin.SIMULATION
            # Aucun evt_* n'était dans le texte Markdown
            assert len(c.evidence_refs) == 0

    def test_ac4_deterministic_reconciliation_with_evidence_pack(self):
        """AC4 : Réconciliation déterministe par acteur et contenu, injection d'event_id et statut VERIFIED."""
        sim_id = "sim_reconcile_001"
        resolver = AgentIdentityResolver(simulation_id=sim_id)
        resolver.register_persona(1, "Julien", role=ScenarioRole.PROSPECT)
        resolver.register_persona(16, "Simon", role=ScenarioRole.FOUNDER)

        event_julien = ObservedEvent(
            event_id="evt_reddit_1_1_julien_post",
            simulation_id=sim_id,
            platform="reddit",
            round_num=1,
            agent_id=1,
            agent_name="Agent_1",  # Alias technique résolu en 'Julien'
            action_type="CREATE_POST",
            timestamp="2026-10-18T10:00:00Z",
            action_args={"content": "Le nouveau tarif de 49€ est beaucoup trop cher pour mon équipe."},
            is_action_executed=True,
        )
        event_simon = ObservedEvent(
            event_id="evt_reddit_1_16_simon_post",
            simulation_id=sim_id,
            platform="reddit",
            round_num=1,
            agent_id=16,
            agent_name="Agent_16",
            action_type="CREATE_POST",
            timestamp="2026-10-18T10:05:00Z",
            action_args={"content": "Nous avons prévu une remise pour les early adopters."},
            is_action_executed=True,
        )
        evidence_pack = EvidencePack.from_events(sim_id, [event_julien, event_simon])

        # Claim formulé en langage naturel avec citation exacte
        claim = ReportClaim(
            claim_id="",
            text="Round 1 : Julien a posté « Le nouveau tarif de 49€ est beaucoup trop cher » sur Reddit.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            evidence_refs=[],  # Pas d'ID en dur dans le texte !
            agent_name="Julien",
            round_num=1,
        )

        verified = SimulationActionVerifier.verify_report_claim(
            claim=claim,
            evidence_pack=evidence_pack,
            resolver=resolver,
        )

        # Doit être VERIFIED grâce à la réconciliation déterministe
        assert verified.verification_status == VerificationStatus.VERIFIED
        assert verified.claim_kind == ClaimKind.OBSERVED_SOCIAL_ACTION
        assert "evt_reddit_1_1_julien_post" in verified.evidence_refs
        # Ne doit JAMAIS contenir l'événement de Simon (Agent_16)
        assert "evt_reddit_1_16_simon_post" not in verified.evidence_refs

    def test_ac5_anti_affabulation_transaction_downgrade(self):
        """AC5 : Un simple tweet affirmant un achat est rétrogradé en REPORTED_INTENTION (UNSUPPORTED) avec justification."""
        sim_id = "sim_affabulation_test"
        resolver = AgentIdentityResolver(simulation_id=sim_id)
        resolver.register_persona(2, "Clara", role=ScenarioRole.PROSPECT)

        # Clara a juste tweeté qu'elle aimait le produit
        event = ObservedEvent(
            event_id="evt_twitter_1_2_tweet",
            simulation_id=sim_id,
            platform="twitter",
            round_num=1,
            agent_id=2,
            agent_name="Clara",
            action_type="POST",
            timestamp="2026-10-18T10:00:00Z",
            action_args={"content": "Superbe produit !"},
            is_action_executed=True,
        )
        evidence_pack = EvidencePack.from_events(sim_id, [event])

        # Claim prétendant une transaction d'achat réelle
        claim_purchase = ReportClaim(
            claim_id="",
            text="Clara a acheté la formule annuelle de la solution.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            evidence_refs=[],
            agent_name="Clara",
            round_num=1,
        )

        verified = SimulationActionVerifier.verify_report_claim(
            claim=claim_purchase,
            evidence_pack=evidence_pack,
            resolver=resolver,
        )

        assert verified.verification_status == VerificationStatus.UNSUPPORTED
        assert verified.claim_kind == ClaimKind.REPORTED_INTENTION
        assert any("anti-affabulation (C4)" in lim for lim in verified.limitations)

    def test_ac5_unobserved_action_downgrade_with_limitations(self):
        """AC5 : Une action sans aucun événement exécuté dans le run est déclassée avec motif explicite."""
        sim_id = "sim_empty_run"
        evidence_pack = EvidencePack.from_events(sim_id, [])

        claim = ReportClaim(
            claim_id="",
            text="Julien a vivement manifesté son accord.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            evidence_refs=[],
            agent_name="Julien",
            round_num=1,
        )

        verified = SimulationActionVerifier.verify_report_claim(
            claim=claim,
            evidence_pack=evidence_pack,
        )

        assert verified.verification_status == VerificationStatus.UNSUPPORTED
        assert verified.claim_kind == ClaimKind.REPORTED_INTENTION
        assert any("aucune action exécutée" in lim for lim in verified.limitations)

    def test_ac6_roundtrip_retrocompatibility_and_registry(self, tmp_path, monkeypatch):
        """AC6 : Sérialisation/désérialisation roundtrip et sauvegarde report_claims.json conforme."""
        from app.config import Config
        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))

        sim_id = "sim_audit_r6_compat"
        agent = ReportAgent(
            graph_id="graph_test",
            simulation_id=sim_id,
            simulation_requirement="Tester l'audit global",
        )

        event = ObservedEvent(
            event_id="evt_twitter_1_1_post",
            simulation_id=sim_id,
            platform="twitter",
            round_num=1,
            agent_id=1,
            agent_name="Émilie",
            action_type="POST",
            timestamp="2026-10-18T10:00:00Z",
            action_args={"content": "J'ai publié mon avis critique sur la plateforme."},
            is_action_executed=True,
        )
        evidence_pack = EvidencePack.from_events(sim_id, [event])

        markdown_content = """
# Synthèse
## 1. Observations
- Agent Émilie a publié son avis critique sur la plateforme.
- Si le prix change, les usagers réagiront.
"""
        registry = agent.audit_and_save_report_claims(
            markdown_content=markdown_content,
            evidence_pack=evidence_pack,
        )

        assert registry.total_claims >= 1
        # Vérifier que le fichier est sauvegardé
        saved_file = tmp_path / "simulations" / sim_id / "report_claims.json"
        assert os.path.exists(saved_file)

        # Vérifier la relecture via from_dict
        loaded_reg = ReportClaimRegistry.load_from_file(str(saved_file))
        assert loaded_reg.simulation_id == sim_id
        assert len(loaded_reg.claims) == registry.total_claims

        for clm in loaded_reg.claims:
            d = clm.to_dict()
            restored = ReportClaim.from_dict(d)
            assert restored.claim_id == clm.claim_id
            assert restored.claim_kind == clm.claim_kind
            assert restored.verification_status == clm.verification_status

    def test_ac4_reconciliation_round_filter_priority(self):
        """AC4 : Priorité stricte au round spécifié lors de la réconciliation d'actions multiples."""
        sim_id = "sim_round_priority"
        resolver = AgentIdentityResolver(simulation_id=sim_id)
        resolver.register_persona(1, "Julien", role=ScenarioRole.PROSPECT)

        ev_r1 = ObservedEvent(
            event_id="evt_reddit_1_1_early",
            simulation_id=sim_id,
            platform="reddit",
            round_num=1,
            agent_id=1,
            agent_name="Julien",
            action_type="POST",
            timestamp="2026-10-18T10:00:00Z",
            action_args={"content": "Je découvre l'outil."},
            is_action_executed=True,
        )
        ev_r3 = ObservedEvent(
            event_id="evt_reddit_3_1_late",
            simulation_id=sim_id,
            platform="reddit",
            round_num=3,
            agent_id=1,
            agent_name="Julien",
            action_type="POST",
            timestamp="2026-10-18T12:00:00Z",
            action_args={"content": "Je confirme mon intérêt pour la démo technique."},
            is_action_executed=True,
        )
        evidence_pack = EvidencePack.from_events(sim_id, [ev_r1, ev_r3])

        claim_round_3 = ReportClaim(
            claim_id="",
            text="Round 3 : Julien a posté sur son intérêt pour la démo.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            evidence_refs=[],
            agent_name="Julien",
            round_num=3,
        )

        verified = SimulationActionVerifier.verify_report_claim(
            claim=claim_round_3,
            evidence_pack=evidence_pack,
            resolver=resolver,
        )

        assert verified.verification_status == VerificationStatus.VERIFIED
        assert "evt_reddit_3_1_late" in verified.evidence_refs
        assert "evt_reddit_1_1_early" not in verified.evidence_refs

    def test_ac1_english_blacklist_and_whitespace_robustness(self):
        """AC1 : Mots de liaison anglais ('If', 'When', 'Then', 'As') rejetés même avec ponctuation ou espaces."""
        agent = ReportAgent(
            graph_id="graph_test",
            simulation_id="sim_en_test",
            simulation_requirement="Tester blacklist anglais",
        )
        known_names = {"Alice", "Bob"}
        sample_md = """
- If Alice agreed to terms, adoption would follow.
- When Bob joined the thread, he shared his opinion.
- Then the round ended quietly.
- As discussed in the brief, targets were set.
"""
        claims = agent.extract_claims_from_content(sample_md, known_agent_names=known_names)
        agents = [c.agent_name for c in claims if c.agent_name]

        for banned in ("If", "When", "Then", "As"):
            assert banned not in agents
        assert "Alice" in agents
        assert "Bob" in agents

    def test_patch1_unquoted_claim_requires_semantic_overlap(self):
        """Review Patch 1 : Un claim sans guillemets exige un recouvrement sémantique des termes clés de l'action."""
        sim_id = "sim_semantic_leak"
        resolver = AgentIdentityResolver(simulation_id=sim_id)
        resolver.register_persona(1, "Julien", role=ScenarioRole.PROSPECT)

        ev = ObservedEvent(
            event_id="evt_reddit_1_1",
            simulation_id=sim_id,
            platform="reddit",
            round_num=1,
            agent_id=1,
            agent_name="Julien",
            action_type="POST",
            timestamp="2026-10-18T10:00:00Z",
            action_args={"content": "Salut tout le monde il fait beau aujourd'hui."},
            is_action_executed=True,
        )
        ep = EvidencePack.from_events(sim_id, [ev])

        # Claim non relié au contenu du post
        fabricated_claim = ReportClaim(
            claim_id="",
            text="Julien a révélé un scandale financier de détournement de fonds.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            evidence_refs=[],
            agent_name="Julien",
            round_num=1,
        )

        verified = SimulationActionVerifier.verify_report_claim(
            claim=fabricated_claim,
            evidence_pack=ep,
            resolver=resolver,
        )
        # Doit être déclassé en UNSUPPORTED car les termes de l'action ne sont pas dans l'événement
        assert verified.verification_status == VerificationStatus.UNSUPPORTED
        assert verified.claim_kind == ClaimKind.REPORTED_INTENTION

    def test_patch2_verify_simulated_citation_with_oasis_alias(self):
        """Review Patch 2 : verify_simulated_citation résout les alias OASIS 'Agent_X' via AgentIdentityResolver."""
        sim_id = "sim_citation_alias"
        resolver = AgentIdentityResolver(simulation_id=sim_id)
        resolver.register_persona(1, "Julien", role=ScenarioRole.PROSPECT)

        ev = ObservedEvent(
            event_id="evt_reddit_1_1",
            simulation_id=sim_id,
            platform="reddit",
            round_num=1,
            agent_id=1,
            agent_name="Agent_1",  # Nom brut de log OASIS
            action_type="POST",
            timestamp="2026-10-18T10:00:00Z",
            action_args={"content": "Le tarif est excessif pour notre structure."},
            is_action_executed=True,
        )
        ep = EvidencePack.from_events(sim_id, [ev])

        valid, exact, ev_id = SimulationActionVerifier.verify_simulated_citation(
            agent_name="Julien",
            claimed_text="Le tarif est excessif pour notre structure.",
            evidence_pack=ep,
            resolver=resolver,
        )

        assert valid is True
        assert exact is True
        assert ev_id == "evt_reddit_1_1"

    def test_patch3_earliest_agent_in_sentence_is_extracted(self):
        """Review Patch 3 : Dans une phrase à agents multiples, le sujet grammatical apparaissant en premier est retenu."""
        from unittest.mock import MagicMock
        agent = ReportAgent("graph_test", "sim_test", "Tester ordre agents", zep_tools=MagicMock())

        resolver = MagicMock()
        # Julien inséré en premier dans le dictionnaire
        resolver.name_to_canonical = {"julien": "Julien", "sophie jouan": "Sophie Jouan"}
        resolver.id_to_name = {1: "Julien", 2: "Sophie Jouan"}

        md = "- Sophie Jouan a répondu au message de Julien."
        claims = agent.extract_claims_from_content(md, resolver=resolver)

        assert len(claims) == 1
        assert claims[0].agent_name == "Sophie Jouan"

    def test_patch5_agent_alias_unregistered_resolves_to_none(self):
        """Review Patch 5 : resolve_name retourne None si un alias Agent_X ne correspond à aucun persona de la simulation."""
        resolver = AgentIdentityResolver(simulation_id="sim_unreg")
        resolver.register_persona(1, "Julien", role=ScenarioRole.PROSPECT)

        assert resolver.resolve_name("Agent_1") == "Julien"
        assert resolver.resolve_name("Agent_999") is None

    def test_patch7_evidence_refs_belonging_to_other_agent_is_ignored(self):
        """Review Patch 7 : Un event_id cité appartenant à un autre agent n'est pas utilisé pour valider l'action."""
        sim_id = "sim_other_agent"
        resolver = AgentIdentityResolver(simulation_id=sim_id)
        resolver.register_persona(1, "Julien", role=ScenarioRole.PROSPECT)
        resolver.register_persona(2, "Simon", role=ScenarioRole.FOUNDER)

        ev_simon = ObservedEvent(
            event_id="evt_simon_action",
            simulation_id=sim_id,
            platform="reddit",
            round_num=1,
            agent_id=2,
            agent_name="Simon",
            action_type="POST",
            timestamp="2026-10-18T10:00:00Z",
            action_args={"content": "Offre spéciale de lancement disponible."},
            is_action_executed=True,
        )
        ep = EvidencePack.from_events(sim_id, [ev_simon])

        claim = ReportClaim(
            claim_id="",
            text="Julien a publié l'offre spéciale de lancement.",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            evidence_refs=["evt_simon_action"],
            agent_name="Julien",
            round_num=1,
        )

        verified = SimulationActionVerifier.verify_report_claim(
            claim=claim,
            evidence_pack=ep,
            resolver=resolver,
        )

        # Doit être déclassé car evt_simon_action appartient à Simon et non à Julien
        assert verified.verification_status == VerificationStatus.UNSUPPORTED
        assert "evt_simon_action" not in verified.evidence_refs

    def test_patch9_transaction_claim_with_explicit_refusal(self):
        """Review Patch 9 : Un refus ou désaccord de souscription n'est pas déclassé par la règle anti-affabulation transactionnelle."""
        sim_id = "sim_refusal"
        resolver = AgentIdentityResolver(simulation_id=sim_id)
        resolver.register_persona(1, "Julien", role=ScenarioRole.PROSPECT)

        ev = ObservedEvent(
            event_id="evt_reddit_1_1_refusal",
            simulation_id=sim_id,
            platform="reddit",
            round_num=1,
            agent_id=1,
            agent_name="Julien",
            action_type="POST",
            timestamp="2026-10-18T10:00:00Z",
            action_args={"content": "Je refuse de souscrire à ce prix là."},
            is_action_executed=True,
        )
        ep = EvidencePack.from_events(sim_id, [ev])

        claim = ReportClaim(
            claim_id="",
            text="Round 1 : Julien a posté qu'il « refuse de souscrire à ce prix là ».",
            claim_kind=ClaimKind.OBSERVED_SOCIAL_ACTION,
            origin=InformationOrigin.SIMULATION,
            evidence_refs=[],
            agent_name="Julien",
            round_num=1,
        )

        verified = SimulationActionVerifier.verify_report_claim(
            claim=claim,
            evidence_pack=ep,
            resolver=resolver,
        )

        assert verified.verification_status == VerificationStatus.VERIFIED
        assert "evt_reddit_1_1_refusal" in verified.evidence_refs


    def test_bracketed_label_is_never_an_agent_name(self):
        """Story 014-1, AC6 : une étiquette entre crochets n'est jamais résolue comme nom d'agent."""
        agent = ReportAgent(
            graph_id="graph_test",
            simulation_id="sim_bracket_test",
            simulation_requirement="Tester AC6",
        )
        known_names = {"Émilie", "Julien"}
        sample_markdown = """
# Section
- [Événements simulés réels] : Émilie a publié un tweet d'indignation.
- [[PROVENANCE:interview;mode:live]] : Julien a déclaré son refus.
"""
        claims = agent.extract_claims_from_content(sample_markdown, known_agent_names=known_names)
        extracted_agents = [c.agent_name for c in claims if c.agent_name is not None]
        assert "Événements" not in extracted_agents
        assert "PROVENANCE" not in extracted_agents


