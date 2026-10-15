"""Tests hermétiques de la locale canonique des simulations (story 008-3)."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest
from flask import Flask

from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.simulation_config_generator import SimulationParameters
from app.services.simulation_manager import SimulationManager, SimulationState
from app.services.simulation_runner import SimulationRunner
from app.utils.locale import (
    get_language_instruction,
    get_locale,
    normalize_locale,
    use_locale,
)


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        ("fr", "fr"), ("fr-FR", "fr"), ("en-US", "en"), ("zh-CN", "zh"),
        ("invalid", "zh"), (None, "zh"), ([], "zh"), ({}, "zh"),
    ],
)
def test_normalization_never_stores_an_unsupported_locale(requested, expected):
    assert normalize_locale(requested) == expected


def test_scoped_language_has_priority_over_request_then_restores_it():
    app = Flask(__name__)
    with app.test_request_context(headers={"Accept-Language": "en"}):
        assert get_locale() == "en"
        with use_locale("fr-FR"):
            assert get_locale() == "fr"
            assert get_language_instruction() == "Veuillez répondre en français."
            with use_locale("zh"):
                assert get_locale() == "zh"
            assert get_locale() == "fr"
        assert get_locale() == "en"


def test_parallel_simulation_locales_do_not_leak_between_threads():
    def probe(locale):
        with use_locale(locale):
            return get_locale(), get_language_instruction()

    selected = ["fr", "en", "zh", "fr", "en", "zh"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(probe, selected))
    assert [key for key, _ in results] == selected
    assert results[0][1] == "Veuillez répondre en français."
    assert results[0][1] != results[1][1]


def test_scoped_language_restores_after_failure():
    app = Flask(__name__)
    with app.test_request_context(headers={"Accept-Language": "en"}):
        with pytest.raises(RuntimeError, match="failure"):
            with use_locale("fr"):
                raise RuntimeError("failure")
        assert get_locale() == "en"


@pytest.mark.parametrize("raw", ["fr-FR", "en", "zh", "unknown"])
def test_simulation_locale_is_persisted_and_canonical(tmp_path, raw):
    manager = SimulationManager()
    manager.SIMULATION_DATA_DIR = str(tmp_path)
    state = manager.create_simulation("project", "graph", locale=raw)
    expected = normalize_locale(raw)
    assert state.locale == expected
    assert state.to_dict()["locale"] == expected
    assert state.to_simple_dict()["locale"] == expected

    other_process = SimulationManager()
    other_process.SIMULATION_DATA_DIR = str(tmp_path)
    assert other_process.get_simulation(state.simulation_id).locale == expected


@pytest.mark.parametrize("recorded", [None, "unknown", [], "fr"])
def test_legacy_and_corrupt_simulation_state_falls_back(tmp_path, recorded):
    manager = SimulationManager()
    manager.SIMULATION_DATA_DIR = str(tmp_path)
    state = SimulationState("legacy", "project", "graph")
    manager._save_simulation_state(state)
    path = tmp_path / "legacy" / "state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if recorded is None:
        data.pop("locale")
    else:
        data["locale"] = recorded
    path.write_text(json.dumps(data), encoding="utf-8")
    fresh_manager = SimulationManager()
    fresh_manager.SIMULATION_DATA_DIR = str(tmp_path)
    assert fresh_manager.get_simulation("legacy").locale == (
        "fr" if recorded == "fr" else "zh"
    )


@pytest.mark.parametrize("locale", ["fr", "en", "zh"])
def test_profile_action_instruction_is_localized_and_idempotent(locale):
    generator = object.__new__(OasisProfileGenerator)
    original = {"bio": "Donnée source", "persona": "Persona source", "gender": "other"}
    with use_locale(locale):
        exported = generator._add_agent_language_guidance(original)
        repeated = generator._add_agent_language_guidance(exported)
    assert exported == repeated
    assert exported["persona"].startswith("Persona source\n")
    assert exported["bio"] == "Donnée source"
    assert exported["gender"] == "other"
    assert original["persona"] == "Persona source"
    if locale == "fr":
        assert "en français" in exported["persona"]


def test_fallback_does_not_fabricate_personal_information():
    generator = object.__new__(OasisProfileGenerator)
    with use_locale("fr"):
        profile = generator._localized_fallback("Camille", "Person", "")
    assert "Camille" in profile["bio"]
    assert "Camille" in profile["persona"]
    assert "participe" in profile["persona"]


def test_positional_parameters_remain_backward_compatible():
    state = SimulationState("id", "proj", "graph", False, True)
    assert state.enable_twitter is False
    assert state.enable_reddit is True
    assert state.locale == "zh"
    config = SimulationParameters("id", "proj", "graph", "request")
    assert config.locale == "zh"


def test_rule_based_french_fallback_preserves_original_context():
    generator = object.__new__(OasisProfileGenerator)
    with use_locale("fr"):
        value = generator._generate_profile_rule_based(
            "Camille", "Person", "Original text", {"occupation": "Designer"}
        )
    assert value["bio"].startswith("Camille")
    assert "Contexte fourni" in value["persona"]
    assert "Original text" in value["persona"]
    assert value["profession"] == "Designer"


def test_generated_config_serializes_locale_without_mutating_schema():
    config = SimulationParameters("sim", "project", "graph", "scenario", locale="fr")
    result = config.to_dict()
    assert result["locale"] == "fr"
    assert result["simulation_id"] == "sim"
    assert "event_config" in result
    assert "agent_configs" in result


@pytest.mark.parametrize(
    ("platform", "filename"),
    [
        ("twitter", "run_twitter_simulation.py"),
        ("reddit", "run_reddit_simulation.py"),
        ("parallel", "run_parallel_simulation.py"),
    ],
)
def test_subprocess_receives_simulation_locale_independent_of_caller(
    tmp_path, monkeypatch, platform, filename
):
    sim_id = f"sim-{platform}"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir()
    (sim_dir / "simulation_config.json").write_text(
        json.dumps({
            "time_config": {
                "total_simulation_hours": 1,
                "minutes_per_round": 60,
            },
            "locale": "fr",
        }), encoding="utf-8"
    )
    (tmp_path / filename).write_text("# simulation stub", encoding="utf-8")
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "SCRIPTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        SimulationRunner,
        "_sync_simulation_status",
        classmethod(lambda *args, **kwargs: None),
    )

    class Process:
        pid = 9100
        returncode = 0

        def poll(self):
            return 0

    spawned = []

    def spawn(cmd, *args, **kwargs):
        spawned.append((cmd, kwargs["env"]))
        return Process()

    monkeypatch.setattr(subprocess, "Popen", spawn)
    # This call has no Flask request; the persisted config is authoritative.
    state = SimulationRunner.start_simulation(
        sim_id, platform=platform, keep_alive_on_completion=False
    )
    try:
        assert state.simulation_id == sim_id
        assert len(spawned) == 1
        assert spawned[0][0][1].endswith(filename)
        assert spawned[0][1]["MIROFISH_SIMULATION_LOCALE"] == "fr"
    finally:
        SimulationRunner._run_states.pop(sim_id, None)
        SimulationRunner._processes.pop(sim_id, None)
        SimulationRunner._monitor_threads.pop(sim_id, None)
        SimulationRunner._stdout_files.pop(sim_id, None)
        SimulationRunner._stderr_files.pop(sim_id, None)
        SimulationRunner._state_file_mtimes.pop(sim_id, None)
        SimulationRunner._graph_memory_enabled.pop(sim_id, None)
