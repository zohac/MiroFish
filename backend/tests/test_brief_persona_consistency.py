"""Tests unitaires et hermétiques pour l'audit de cohérence brief/fiches persona et filtrage des non-admis (Story 014-4, FR-07, AC1-AC8)."""

from __future__ import annotations

import json
import os
import tempfile
import unicodedata
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api.report import _filter_simulation_requirement_for_report, report_bp
from app.models.actor_eligibility import ActorRole, EligibilityStatus
from app.models.actor_selection import ACTOR_SELECTION_FILENAME, ActorItem, ActorSelection
from app.models.project import ProjectStatus
from app.services.simulation_manager import SimulationState, SimulationStatus
from app.services.simulation_runner import RunnerStatus
from app.services.brief_consistency import (
    BriefPersonaContradictionError,
    ConsistencyResult,
    PersonaContradiction,
    audit_brief_persona_consistency,
    extract_episodes,
    filter_non_admitted_personas_from_text,
)
from app.services.oasis_profile_generator import OasisAgentProfile
from app.services.simulation_audit_service import SimulationAuditService
from app.services.simulation_manager import SimulationManager


def test_shared_episode_across_two_personas_is_contradiction():
    """AC1 : Quand le même couple (montant, mot-clé) apparaît dans les fiches de deux personas distincts."""
    brief_text = "Brief générique de test sans attribution particulière."
    profiles = [
        {
            "name": "Persona_A",
            "bio": "Bio A",
            "persona": "A perdu 1 500 € en agence WordPress lors de son lancement.",
        },
        {
            "name": "Persona_B",
            "bio": "Bio B",
            "persona": "Hésite car a dépensé 1 500 € en agence WordPress l'année passée.",
        },
    ]

    result = audit_brief_persona_consistency(brief_text, profiles)
    assert result.is_consistent is False
    assert len(result.contradictions) >= 1
    c = result.contradictions[0]
    assert "1500eur:wordpress" in c.signature
    assert c.carrier == "Persona_A"
    assert "Persona_B" in c.other_carriers


def test_episode_owner_mismatch_is_contradiction():
    """AC2 : Quand le brief attribue un épisode au persona A et que la fiche du persona B le contient."""
    brief_text = (
        "Émilie a perdu 1 500 € en agence WordPress.\n"
        "Nathalie est une débutante qui redoute la technique."
    )
    profiles = [
        {
            "name": "Nathalie",
            "bio": "Bio Nathalie",
            "persona": "Après avoir perdu 1 500 € en agence WordPress, elle refuse de payer.",
        }
    ]

    result = audit_brief_persona_consistency(brief_text, profiles)
    assert result.is_consistent is False
    assert len(result.contradictions) >= 1
    mismatch = [c for c in result.contradictions if c.owner == "Émilie" and c.carrier == "Nathalie"]
    assert len(mismatch) == 1
    assert "1500eur:wordpress" in mismatch[0].signature


def test_consistent_brief_passes():
    """AC3 : Quand chaque épisode reste dans la fiche de son owner et qu'aucun épisode n'est partagé."""
    brief_text = (
        "Émilie a perdu 1 500 € en agence WordPress.\n"
        "Nathalie est une débutante qui craint la technique."
    )
    profiles = [
        {
            "name": "Émilie",
            "bio": "Bio Émilie",
            "persona": "A perdu 1 500 € en agence WordPress, donc très méfiante.",
        },
        {
            "name": "Nathalie",
            "bio": "Bio Nathalie",
            "persona": "Débutante sans expérience précédente de site web.",
        },
    ]

    result = audit_brief_persona_consistency(brief_text, profiles)
    assert result.is_consistent is True
    assert result.contradictions == []


def test_prepare_simulation_fails_on_contradiction():
    """AC4 : SimulationManager.prepare_simulation lève BriefPersonaContradictionError et bascule le statut en FAILED."""
    sim_id = "sim_test_contradiction_fail"
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SimulationManager()
        # Mock _get_simulation_dir pour utiliser tmpdir
        with patch.object(manager, "_get_simulation_dir", return_value=tmpdir):
            state = SimulationState(
                simulation_id=sim_id,
                project_id="proj_test",
                graph_id="graph_test",
                status=SimulationStatus.CREATED,
            )
            manager._save_simulation_state(state)

            # Simuler un retour de graphe et sélection
            mock_selection = ActorSelection(
                simulation_id=sim_id,
                project_id="proj_test",
                graph_id="graph_test",
                input_fingerprint="fp_test",
                policy_version="1.0.0",
                actors=[
                    ActorItem(
                        entity_uuid="uuid_nathalie",
                        entity_name="Nathalie",
                        qualified_role=ActorRole.PERSON,
                        eligibility_status=EligibilityStatus.ELIGIBLE,
                        reasoning="Persona de test",
                    )
                ],
            )
            mock_filtered = MagicMock()
            mock_filtered.filtered_count = 1
            mock_filtered.entity_types = ["person"]
            mock_filtered.entities = [
                MagicMock(uuid="uuid_nathalie", name="Nathalie", entity_type="person")
            ]

            contradictory_brief = (
                "Émilie a perdu 1 500 € en agence WordPress.\n"
                "Nathalie est une débutante."
            )
            contradictory_profile = OasisAgentProfile(
                user_id=1,
                user_name="nathalie_test",
                name="Nathalie",
                bio="Bio de Nathalie",
                persona="A perdu 1 500 € en agence WordPress, d'où sa défiance.",
            )

            with patch.object(manager, "preview_actors", return_value=(mock_selection, {})), \
                 patch.object(manager, "get_actor_selection", return_value=mock_selection), \
                 patch("app.services.simulation_manager.fingerprint_qualification_inputs", return_value="fp_test"), \
                 patch("app.services.simulation_manager.ProjectManager.get_project", return_value=MagicMock(graph_id="graph_test", source_documents=[], applied_ontology_id=None, get_brief=lambda: None, get_source_conflicts=lambda: [])), \
                 patch("app.services.simulation_manager.ZepEntityReader.filter_defined_entities", return_value=mock_filtered), \
                 patch("app.services.simulation_manager.OasisProfileGenerator.generate_profiles_from_entities", return_value=[contradictory_profile]), \
                 patch("app.services.simulation_manager.OasisProfileGenerator.save_profiles") as mock_save_profiles:

                with pytest.raises(BriefPersonaContradictionError) as exc_info:
                    manager.prepare_simulation(
                        simulation_id=sim_id,
                        simulation_requirement=contradictory_brief,
                        document_text="Contenu doc",
                    )

                assert "Contradiction biographique détectée" in str(exc_info.value)
                # Vérifier qu'aucun profil n'a été persisté
                assert mock_save_profiles.call_count == 0
                assert not os.path.exists(os.path.join(tmpdir, "reddit_profiles.json"))
                assert not os.path.exists(os.path.join(tmpdir, "twitter_profiles.csv"))

                # Vérifier que le statut de simulation est FAILED
                reloaded = manager.get_simulation(sim_id)
                assert reloaded.status == SimulationStatus.FAILED
                assert "Contradiction biographique" in reloaded.error

                # Vérifier que brief_consistency.json est bien persisté
                bc_path = os.path.join(tmpdir, "brief_consistency.json")
                assert os.path.exists(bc_path)
                with open(bc_path, "r", encoding="utf-8") as f_bc:
                    bc_data = json.load(f_bc)
                assert bc_data["is_consistent"] is False
                assert len(bc_data["contradictions"]) >= 1


def test_non_admitted_personas_filtered_from_drafting_context():
    """AC5 : filter_non_admitted_personas_from_text retire ou caviarde les personas non admis."""
    text = (
        "Nathalie est ravie de l'offre.\n\n"
        "Émilie a perdu 1 500 € en agence WordPress et refuse tout compromis.\n\n"
        "- Christine hésite à faire payer ses clientes."
    )
    admitted = ["Nathalie"]
    excluded = ["Émilie", "Christine"]

    filtered = filter_non_admitted_personas_from_text(
        text,
        admitted_names=admitted,
        excluded_names=excluded,
    )

    # Émilie ne doit plus apparaître dans le texte
    assert "Émilie" not in filtered
    # Nathalie doit être conservée
    assert "Nathalie est ravie de l'offre." in filtered
    # La phrase contenant Christine (liste) doit avoir caviardé Christine
    assert "[persona non admis]" in filtered
    assert "Christine" not in filtered


def test_eligible_persona_is_preserved():
    """AC5 : Un persona eligible n'est jamais retiré ni caviardé."""
    text = "Nathalie et Sophie découvrent la plateforme avec enthousiasme."
    admitted = ["Nathalie", "Sophie"]
    excluded = ["Émilie"]

    filtered = filter_non_admitted_personas_from_text(
        text,
        admitted_names=admitted,
        excluded_names=excluded,
    )
    assert filtered == text
    assert "Nathalie" in filtered
    assert "Sophie" in filtered


def test_consistency_audit_persisted():
    """AC6 : SimulationManager.prepare_simulation persiste brief_consistency.json avec is_consistent=True."""
    sim_id = "sim_test_consistency_persisted"
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SimulationManager()
        with patch.object(manager, "_get_simulation_dir", return_value=tmpdir):
            state = SimulationState(
                simulation_id=sim_id,
                project_id="proj_test",
                graph_id="graph_test",
                status=SimulationStatus.CREATED,
            )
            manager._save_simulation_state(state)

            mock_selection = ActorSelection(
                simulation_id=sim_id,
                project_id="proj_test",
                graph_id="graph_test",
                input_fingerprint="fp_test",
                policy_version="1.0.0",
                actors=[
                    ActorItem(
                        entity_uuid="uuid_nathalie",
                        entity_name="Nathalie",
                        qualified_role=ActorRole.PERSON,
                        eligibility_status=EligibilityStatus.ELIGIBLE,
                        reasoning="Persona de test",
                    )
                ],
            )
            mock_filtered = MagicMock()
            mock_filtered.filtered_count = 1
            mock_filtered.entity_types = ["person"]
            mock_filtered.entities = [
                MagicMock(uuid="uuid_nathalie", name="Nathalie", entity_type="person")
            ]

            consistent_brief = "Nathalie est une débutante en création d'entreprise."
            consistent_profile = OasisAgentProfile(
                user_id=1,
                user_name="nathalie_test",
                name="Nathalie",
                bio="Bio de Nathalie",
                persona="Débute en création d'entreprise.",
            )

            with patch.object(manager, "preview_actors", return_value=(mock_selection, {})), \
                 patch.object(manager, "get_actor_selection", return_value=mock_selection), \
                 patch("app.services.simulation_manager.fingerprint_qualification_inputs", return_value="fp_test"), \
                 patch("app.services.simulation_manager.ProjectManager.get_project", return_value=MagicMock(graph_id="graph_test", source_documents=[], applied_ontology_id=None, get_brief=lambda: None, get_source_conflicts=lambda: [])), \
                 patch("app.services.simulation_manager.ZepEntityReader.filter_defined_entities", return_value=mock_filtered), \
                 patch("app.services.simulation_manager.OasisProfileGenerator.generate_profiles_from_entities", return_value=[consistent_profile]), \
                 patch("app.services.simulation_manager.OasisProfileGenerator.save_profiles"), \
                 patch("app.services.simulation_manager.SimulationConfigGenerator.generate_config", return_value=MagicMock(to_json=lambda: "{}", generation_reasoning="ok")):

                manager.prepare_simulation(
                    simulation_id=sim_id,
                    simulation_requirement=consistent_brief,
                    document_text="Contenu doc",
                )

            bc_path = os.path.join(tmpdir, "brief_consistency.json")
            assert os.path.exists(bc_path)
            with open(bc_path, "r", encoding="utf-8") as f_bc:
                data = json.load(f_bc)

            assert data["is_consistent"] is True
            assert data["contradictions"] == []
            assert "total_profiles" in data["diagnostics"]


def test_consistency_audit_in_archive():
    """AC6 : brief_consistency.json est joint à l'archive d'audit générée."""
    sim_id = "sim_audit_bc_archive_test"
    with tempfile.TemporaryDirectory() as tmpdir:
        # Créer le répertoire de simulation
        sim_dir = os.path.join(tmpdir, sim_id)
        os.makedirs(sim_dir, exist_ok=True)

        # Écrire brief_consistency.json
        bc_content = {
            "is_consistent": True,
            "contradictions": [],
            "diagnostics": {"test": "ok"},
        }
        with open(os.path.join(sim_dir, "brief_consistency.json"), "w", encoding="utf-8") as f:
            json.dump(bc_content, f)

        mock_sim_state = SimulationState(
            simulation_id=sim_id,
            project_id="p1",
            graph_id="g1",
            status=SimulationStatus.COMPLETED,
        )
        mock_sim_state.locale = "fr"

        # Configurer le service d'audit
        audit_service = SimulationAuditService(simulation_id=sim_id)
        with patch.object(SimulationManager, "_get_simulation_dir", return_value=sim_dir), \
             patch.object(SimulationManager, "get_simulation", return_value=mock_sim_state), \
             patch("app.services.simulation_audit_service.OasisLogReaderService.load_events", return_value=[]), \
             patch("app.services.simulation_audit_service.ProjectManager.get_project", return_value=MagicMock(source_documents=[], simulation_brief={})):

            files = audit_service.gather_audit_files()
            assert "brief_consistency.json" in files

            # Vérifier la présence dans l'archive zip
            zip_bytes = audit_service.build_audit_package()
            import io
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zip_in:
                namelist = zip_in.namelist()
                assert "brief_consistency.json" in namelist
                bc_unpacked = json.loads(zip_in.read("brief_consistency.json").decode("utf-8"))
                assert bc_unpacked["is_consistent"] is True


def test_consistency_is_deterministic():
    """AC7 : Deux appels successifs sur le même brief et les mêmes fiches renvoient la même liste dans le même ordre."""
    brief_text = (
        "Émilie a perdu 1 500 € en agence WordPress.\n"
        "Alice a dépensé 2 000 € en agence Marketing."
    )
    profiles = [
        {
            "name": "Nathalie",
            "bio": "Bio Nathalie",
            "persona": "A perdu 1 500 € en agence WordPress l'an dernier.",
        },
        {
            "name": "Bob",
            "bio": "Bio Bob",
            "persona": "A dépensé 2 000 € en agence Marketing.",
        },
    ]

    res1 = audit_brief_persona_consistency(brief_text, profiles)
    res2 = audit_brief_persona_consistency(brief_text, profiles)

    assert res1.is_consistent == res2.is_consistent
    assert len(res1.contradictions) == len(res2.contradictions)
    for c1, c2 in zip(res1.contradictions, res2.contradictions):
        assert c1.to_dict() == c2.to_dict()


def test_r7_episode_leak_detected():
    """AC8 : Une fixture reproduisant l'épisode « 1 500 € / WordPress » d'Émilie repris par Nathalie produit une contradiction."""
    fixture_path = os.path.join(
        os.path.dirname(__file__),
        "fixtures",
        "brief_consistency",
        "brief_contradictory.json",
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    brief_text = data["simulation_requirement"]
    profiles = data["profiles"]

    result = audit_brief_persona_consistency(brief_text, profiles)
    assert result.is_consistent is False
    assert len(result.contradictions) >= 1

    r7_contradiction = [
        c for c in result.contradictions
        if c.owner == "Émilie" and c.carrier == "Nathalie" and "1500eur:wordpress" in c.signature
    ]
    assert len(r7_contradiction) == 1
    assert "Émilie" in r7_contradiction[0].reason
    assert "Nathalie" in r7_contradiction[0].reason


def test_filter_non_admitted_personas_accent_and_nfd_normalization():
    """AC5 : filter_non_admitted_personas_from_text gère les formes sans accent et l'Unicode NFD."""
    nfd_name = unicodedata.normalize("NFD", "Émilie")
    text = (
        f"{nfd_name} refuse l'offre à cause de sa mauvaise expérience.\n\n"
        "Emilie (sans accent) est également citée.\n\n"
        "Nathalie reste satisfaite."
    )
    filtered = filter_non_admitted_personas_from_text(
        text,
        admitted_names=["Nathalie"],
        excluded_names=["Émilie"],
    )
    assert "Émilie" not in filtered
    assert "Emilie" not in filtered
    assert "Nathalie reste satisfaite." in filtered


def test_filter_non_admitted_personas_multiline_list_preserved():
    """AC5 : Une liste markdown avec puces conserve ses retours à la ligne lorsqu'un persona est caviardé."""
    text = (
        "- Point 1 : Nathalie est présente.\n"
        "- Point 2 : Christine hésite encore.\n"
        "- Point 3 : Sophie confirme son inscription."
    )
    filtered = filter_non_admitted_personas_from_text(
        text,
        admitted_names=["Nathalie", "Sophie"],
        excluded_names=["Christine"],
    )
    assert "- Point 1 : Nathalie est présente." in filtered
    assert "- Point 2 : [persona non admis] hésite encore." in filtered
    assert "- Point 3 : Sophie confirme son inscription." in filtered
    assert "\n- Point 2 :" in filtered
    assert "\n- Point 3 :" in filtered


def test_audit_amount_with_decimals_and_commas():
    """AC1/AC2 : Les montants formatés avec virgules ou décimales (.00, ,00) sont extraits avec succès."""
    brief_text = "Émilie a perdu 1 500,00 € en agence WordPress."
    profiles = [
        {
            "name": "Nathalie",
            "bio": "Bio",
            "persona": "A perdu 1500.00 EUR en agence WordPress.",
        }
    ]
    res = audit_brief_persona_consistency(brief_text, profiles)
    assert res.is_consistent is False
    assert len(res.contradictions) == 1
    assert res.contradictions[0].owner == "Émilie"
    assert res.contradictions[0].carrier == "Nathalie"


def test_filter_simulation_requirement_for_report_uses_actor_selection():
    """AC5 : _filter_simulation_requirement_for_report filtre les personas exclus ou non_actor."""
    sim_id = "sim_test_report_filter"
    raw_req = "Nathalie adore l'outil. Émilie refuse l'offre à 1500 euros."

    mock_selection = ActorSelection(
        simulation_id=sim_id,
        project_id="p1",
        graph_id="g1",
        input_fingerprint="fp1",
        policy_version="1.0.0",
        actors=[
            ActorItem(
                entity_uuid="u1",
                entity_name="Nathalie",
                qualified_role=ActorRole.PERSON,
                eligibility_status=EligibilityStatus.ELIGIBLE,
                reasoning="Eligible",
            ),
            ActorItem(
                entity_uuid="u2",
                entity_name="Émilie",
                qualified_role=ActorRole.PERSON,
                eligibility_status=EligibilityStatus.INELIGIBLE,
                reasoning="Non acteur",
            ),
        ],
    )

    with patch.object(SimulationManager, "get_actor_selection", return_value=mock_selection):
        filtered = _filter_simulation_requirement_for_report(sim_id, raw_req)
        assert "Émilie" not in filtered
        assert "Nathalie adore l'outil." in filtered


def test_filter_simulation_requirement_for_report_fallback_when_no_selection():
    """AC5 : En l'absence d'actor_selection, le texte brut est préservé sans altération."""
    sim_id = "sim_test_no_selection"
    raw_req = "Texte brut sans sélection."
    with patch.object(SimulationManager, "get_actor_selection", return_value=None):
        filtered = _filter_simulation_requirement_for_report(sim_id, raw_req)
        assert filtered == raw_req


def test_generate_report_route_filters_brief_before_agent(monkeypatch):
    """AC5 : La route POST /api/report/generate passe le brief filtré au ReportAgent."""
    sim_id = "sim_route_test"
    raw_brief = "Nathalie participe activement. Émilie n'a pas voulu souscrire."
    mock_sim = SimpleNamespace(
        project_id="proj_1",
        graph_id="graph_1",
        status=SimulationStatus.COMPLETED,
        locale="fr",
        simulation_requirement=raw_brief,
    )
    mock_project = SimpleNamespace(
        status=ProjectStatus.GRAPH_COMPLETED,
        graph_id="graph_1",
        simulation_requirement=raw_brief,
        simulation_brief={"content": raw_brief},
    )

    mock_selection = ActorSelection(
        simulation_id=sim_id,
        project_id="proj_1",
        graph_id="graph_1",
        input_fingerprint="fp_route",
        policy_version="1.0.0",
        actors=[
            ActorItem(
                entity_uuid="u1",
                entity_name="Nathalie",
                qualified_role=ActorRole.PERSON,
                eligibility_status=EligibilityStatus.ELIGIBLE,
                reasoning="Eligible",
            ),
            ActorItem(
                entity_uuid="u2",
                entity_name="Émilie",
                qualified_role=ActorRole.PERSON,
                eligibility_status=EligibilityStatus.INELIGIBLE,
                reasoning="Non acteur",
            ),
        ],
    )

    app = Flask(__name__)
    app.register_blueprint(report_bp, url_prefix="/api/report")

    import threading
    received_briefs = []
    done_event = threading.Event()

    def fake_agent_init(self, *args, **kwargs):
        received_briefs.append(kwargs.get("simulation_requirement"))
        self.simulation_id = kwargs.get("simulation_id")
        self.graph_id = kwargs.get("graph_id")
        self.locale = kwargs.get("locale")

    def fake_generate_report(self, *args, **kwargs):
        done_event.set()
        return SimpleNamespace(
            status=SimpleNamespace(value="completed"),
            report_id="rep_test",
            to_dict=lambda: {"report_id": "rep_test"},
        )

    monkeypatch.setattr(
        "app.api.report.SimulationManager",
        lambda: SimpleNamespace(
            get_simulation=lambda _sid: mock_sim,
            get_actor_selection=lambda _sid: mock_selection,
        ),
    )
    monkeypatch.setattr(
        "app.api.report.ProjectManager",
        SimpleNamespace(get_project=lambda _pid: mock_project),
    )
    monkeypatch.setattr(
        "app.api.report.ReportManager.get_report_by_simulation",
        classmethod(lambda cls, _sid: None),
    )
    monkeypatch.setattr(
        "app.api.report.ReportManager.save_report",
        classmethod(lambda cls, _r: None),
    )
    monkeypatch.setattr(
        "app.api.report.SimulationRunner.get_run_state",
        classmethod(lambda cls, _sid: SimpleNamespace(runner_status=RunnerStatus.COMPLETED)),
    )
    monkeypatch.setattr(
        "app.api.report.ZepGraphMemoryManager.get_updater",
        classmethod(lambda cls, _sid: None),
    )
    monkeypatch.setattr("app.api.report.ReportAgent.__init__", fake_agent_init)
    monkeypatch.setattr("app.api.report.ReportAgent.generate_report", fake_generate_report)

    with app.test_client() as client:
        resp = client.post("/api/report/generate", json={"simulation_id": sim_id})
        assert resp.status_code == 200
        assert done_event.wait(timeout=5.0)
        assert len(received_briefs) == 1
        filtered_brief = received_briefs[0]
        assert "Émilie" not in filtered_brief
        assert "Nathalie participe activement." in filtered_brief
