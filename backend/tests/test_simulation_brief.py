"""Contrat du brief de simulation versionné (story 009-2, AC6).

`additional_context` était perdu après l'ontologie ; ces tests prouvent qu'il
survit désormais, et qu'un projet ancien reste lisible sans reconstruction.
"""

import json
from pathlib import Path

import pytest

from app.models.simulation_brief import (
    SIMULATION_BRIEF_SCHEMA_VERSION,
    SimulationBrief,
    SimulationBriefError,
    build_minimal_brief,
)

FIXTURES = Path(__file__).parent / "fixtures" / "source_documents"


class TestBriefFields:
    def test_le_brief_minimal_ne_demande_que_l_objectif(self):
        brief = SimulationBrief(goal="Explorer la reaction au lancement.")
        assert brief.goal == "Explorer la reaction au lancement."
        assert brief.is_minimal()
        assert brief.schema_version == SIMULATION_BRIEF_SCHEMA_VERSION

    def test_un_brief_complet_accepte_tous_les_champs_avances(self):
        brief = SimulationBrief(
            goal="Observer l'adoption",
            initial_state="Le service vient d'etre ouvert.",
            target_audiences=["utilisateurs existants", "nouveaux comptes"],
            excluded_actors=["documentation"],
            rules=["ne pas mentionner de remise", "rester factuel"],
            hypotheses=["la gratuité attire les curieux"],
            additional_context="Le budget média est limité.",
            time_horizon="six semaines",
            trigger_event="Ouverture du service",
            expected_outputs=["un profil d'adoption"],
            source_document_ids=["doc_1", "doc_2"],
        )
        assert brief.is_minimal() is False
        assert brief.time_horizon == "six semaines"
        assert brief.trigger_event == "Ouverture du service"
        assert len(brief.source_document_ids) == 2

    def test_objectif_vide_refuse(self):
        with pytest.raises(SimulationBriefError):
            SimulationBrief(goal="   ")

    def test_champ_liste_refusant_une_chaine_nue(self):
        """Une chaîne dans un champ liste deviendrait sinon une consigne silencieuse."""
        with pytest.raises(SimulationBriefError):
            SimulationBrief(goal="x", rules="regle_a, regle_b")

    def test_liste_refusant_un_element_non_chaine(self):
        with pytest.raises(SimulationBriefError):
            SimulationBrief(goal="x", rules=[{"rule": "a"}])

    def test_version_invalide_refusee(self):
        with pytest.raises(SimulationBriefError):
            SimulationBrief(goal="x", schema_version=0)


class TestBriefRoundTrip:
    def test_round_trip_ne_perd_aucun_champ(self):
        brief = SimulationBrief(
            goal="Observer l'adoption",
            initial_state="Service ouvert.",
            target_audiences=["grand public"],
            excluded_actors=["documentation"],
            rules=["rester factuel"],
            hypotheses=["la gratuité attire"],
            additional_context="Budget média limité.",
            time_horizon="six semaines",
            trigger_event="Ouverture",
            expected_outputs=["profil d'adoption"],
            source_document_ids=["doc_1"],
        )
        relu = SimulationBrief.from_dict(brief.to_dict())
        assert relu.to_dict() == brief.to_dict()

    def test_champs_vides_survivent_a_la_serie(self):
        brief = build_minimal_brief(goal="Observer")
        payload = json.loads(json.dumps(brief.to_dict()))
        for champ in (
            "initial_state",
            "target_audiences",
            "excluded_actors",
            "rules",
            "hypotheses",
            "time_horizon",
            "trigger_event",
            "expected_outputs",
            "source_document_ids",
        ):
            assert champ in payload

    def test_additional_context_est_conserve(self):
        """Le champ perdu après l'ontologie : il doit survivre au round-trip."""
        brief = build_minimal_brief(
            goal="Observer", additional_context="Le budget média est limité."
        )
        relu = SimulationBrief.from_dict(brief.to_dict())
        assert relu.additional_context == "Le budget média est limité."

    def test_le_brief_depuis_none_ne_reconstruit_rien(self):
        assert SimulationBrief.from_dict(None) is None


class TestLegacyProject:
    def test_un_projet_ancien_s_est_lisible_sans_brief(self):
        payload = json.loads((FIXTURES / "project_legacy.json").read_text(encoding="utf-8"))
        assert "simulation_brief" not in payload
        assert "source_documents" not in payload

        from app.models.project import Project

        project = Project.from_dict(payload)
        assert project.get_brief() is None
        assert project.get_source_documents() == []
        assert project.simulation_requirement == (
            "Explorer la reaction des utilisateurs au lancement."
        )

    def test_un_projet_ancien_ne_fabrique_aucune_position(self):
        from app.models.project import Project

        payload = json.loads((FIXTURES / "project_legacy.json").read_text(encoding="utf-8"))
        project = Project.from_dict(payload)
        assert project.source_documents == []
        assert project.additional_context is None


class TestBriefRendering:
    def test_le_brief_minimal_ne_produit_que_son_objectif(self):
        brief = build_minimal_brief(goal="Explorer la reaction.")
        rendered = brief.instructions_text()
        assert "Explorer la reaction." in rendered
        assert "Règles" not in rendered
        assert "Horizon" not in rendered

    def test_les_champs_avances_apparaissent_dans_le_rendu(self):
        brief = SimulationBrief(
            goal="Observer",
            rules=["rester factuel"],
            time_horizon="six semaines",
            trigger_event="Ouverture",
        )
        rendered = brief.advanced_text()
        assert "six semaines" in rendered
        assert "Ouverture" in rendered
        assert "rester factuel" in rendered

    def test_l_objectif_n_est_pature_pas_dans_les_champs_avances(self):
        """L'objectif est transmis une seule fois, sinon il deviendrait deux consignes."""
        brief = SimulationBrief(goal="UNIQUE", rules=["une regle"])
        assert "UNIQUE" not in brief.advanced_text()