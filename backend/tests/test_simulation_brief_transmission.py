"""Transmission de bout en bout du brief (story 009-2, AC6).

Ces tests vérifient que le brief atteint réellement la classification, les
personas et la configuration — pas seulement qu'il se sérialise.
"""

from unittest.mock import MagicMock

import pytest

from app.models.simulation_brief import SimulationBrief
from app.services import simulation_manager as sm_module
from app.services.simulation_manager import SimulationManager, SimulationStatus


@pytest.fixture
def manager(tmp_path, monkeypatch):
    instance = SimulationManager()
    monkeypatch.setattr(instance, "_get_simulation_dir", lambda _sid: str(tmp_path))
    state = instance.create_simulation(
        project_id="proj_test", graph_id="graph_test",
        enable_twitter=True, enable_reddit=True,
    )
    return instance, state, tmp_path


class CapturingClassifier:
    def __init__(self):
        self.policy_version = "test-policy"
        self.calls = []

    def classify_entities(self, entities, simulation_requirement="", simulation_brief=None):
        from app.models.actor_eligibility import (
            ActorEligibility,
            ActorRole,
            EligibilityStatus,
        )
        from app.services.actor_classifier import ActorClassificationResult

        self.calls.append(simulation_brief)
        qualifications = [
            ActorEligibility(
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                role=ActorRole.PERSON,
                status=EligibilityStatus.ELIGIBLE,
                rationale="acteur de test",
                confidence=0.9,
            )
            for entity in entities
        ]
        return ActorClassificationResult(qualifications=qualifications)

    def no_actor_diagnostic(self, *a, **k):  # pragma: no cover - non atteint
        return "aucun"


def _make_entity():
    from app.services.zep_entity_reader import EntityNode

    return EntityNode(
        uuid="u1", name="Alice Martin", labels=["Person"],
        summary="Praticienne.", attributes={},
    )


def test_le_brief_atteint_le_classifieur_les_personas_et_la_configuration(
    manager, monkeypatch
):
    instance, state, tmp_path = manager

    filtered = MagicMock()
    filtered.entities = [_make_entity()]
    filtered.filtered_count = 1
    filtered.entity_types = ["Person"]
    reader = MagicMock()
    reader.filter_defined_entities.return_value = filtered
    monkeypatch.setattr(sm_module, "ZepEntityReader", lambda: reader)

    classifier = CapturingClassifier()
    generator = MagicMock()
    generator.generate_profiles_from_entities.return_value = [MagicMock()]
    monkeypatch.setattr(sm_module, "OasisProfileGenerator", lambda **kwargs: generator)

    config_generator = MagicMock()
    config_generator.generate_config.return_value = MagicMock(
        to_json=lambda: "{}", generation_reasoning="ok"
    )
    monkeypatch.setattr(
        sm_module, "SimulationConfigGenerator", lambda: config_generator
    )
    monkeypatch.setattr(sm_module, "build_qualification_proof", lambda **k: {"ok": True})
    monkeypatch.setattr(sm_module, "write_qualification_proof", lambda *a, **k: None)

    brief = SimulationBrief(
        goal="Observer l'adoption", rules=["rester factuel"],
        additional_context="Budget média limité.",
    )

    instance.prepare_simulation(
        simulation_id=state.simulation_id,
        simulation_requirement="Observer l'adoption",
        document_text="un document",
        classifier=classifier,
        simulation_brief=brief,
        document_sections=[{"document_id": "d1", "filename": "a.txt", "text": "X"}],
    )

    # Le brief est arrivé au classifieur…
    assert classifier.calls == [brief]
    # …aux personas…
    assert generator.generate_profiles_from_entities.call_args.kwargs["simulation_brief"] is brief
    # …et à la configuration, avec les documents par document.
    config_kwargs = config_generator.generate_config.call_args.kwargs
    assert config_kwargs["simulation_brief"] is brief
    assert config_kwargs["document_sections"] == [
        {"document_id": "d1", "filename": "a.txt", "text": "X"}
    ]


def test_sans_brief_un_brief_minimal_est_construit(manager, monkeypatch):
    """Un appelant historique reste valide : un brief minimal est reconstruit."""
    instance, state, tmp_path = manager

    filtered = MagicMock()
    filtered.entities = [_make_entity()]
    filtered.filtered_count = 1
    filtered.entity_types = ["Person"]
    reader = MagicMock()
    reader.filter_defined_entities.return_value = filtered
    monkeypatch.setattr(sm_module, "ZepEntityReader", lambda: reader)

    classifier = CapturingClassifier()
    generator = MagicMock()
    generator.generate_profiles_from_entities.return_value = [MagicMock()]
    monkeypatch.setattr(sm_module, "OasisProfileGenerator", lambda **kwargs: generator)
    config_generator = MagicMock()
    config_generator.generate_config.return_value = MagicMock(
        to_json=lambda: "{}", generation_reasoning="ok"
    )
    monkeypatch.setattr(sm_module, "SimulationConfigGenerator", lambda: config_generator)
    monkeypatch.setattr(sm_module, "build_qualification_proof", lambda **k: {"ok": True})
    monkeypatch.setattr(sm_module, "write_qualification_proof", lambda *a, **k: None)

    instance.prepare_simulation(
        simulation_id=state.simulation_id,
        simulation_requirement="UNE_CONSIGNE",
        document_text="un document",
        classifier=classifier,
    )

    forwarded = classifier.calls[0]
    assert isinstance(forwarded, SimulationBrief)
    assert forwarded.goal == "UNE_CONSIGNE"


class TestFingerprintIncludesBrief:
    """Le brief influence la classification : il doit entrer dans la fraîcheur."""

    def _entity(self):
        return _make_entity()

    def test_editer_le_brief_change_l_empreinte(self):
        from app.services.actor_classifier import fingerprint_qualification_inputs

        base = SimulationBrief(goal="Observer")
        change = SimulationBrief(goal="Observer", rules=["rester factuel"])
        assert fingerprint_qualification_inputs(
            [self._entity()], "Observer", "v1", base
        ) != fingerprint_qualification_inputs([self._entity()], "Observer", "v1", change)

    def test_meme_brief_meme_empreinte(self):
        from app.services.actor_classifier import fingerprint_qualification_inputs

        brief = SimulationBrief(goal="Observer", rules=["rester factuel"])
        assert fingerprint_qualification_inputs(
            [self._entity()], "Observer", "v1", brief
        ) == fingerprint_qualification_inputs([self._entity()], "Observer", "v1", brief)

    def test_un_brief_reference_seul_reste_minimal(self):
        """`source_document_ids` n'est pas une consigne avancée."""
        brief = SimulationBrief(goal="Observer", source_document_ids=["doc_1"])
        assert brief.is_minimal()