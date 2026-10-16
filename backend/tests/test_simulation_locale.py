"""Tests hermétiques de la locale canonique des simulations (story 008-3)."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest
from flask import Flask

from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.simulation_config_generator import (
    SimulationConfigGenerator,
    SimulationParameters,
)
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


def test_api_create_simulation_respects_payload_locale_over_header(monkeypatch):
    """Vérifie que POST /api/simulation/create privilégie le champ locale du body."""
    from app.api import simulation as simulation_api
    from types import SimpleNamespace

    app = Flask(__name__)
    captured = {}

    def mock_create_simulation(self, project_id, graph_id, simulation_requirement="",
                               enable_twitter=True, enable_reddit=True, locale="zh"):
        captured["locale"] = locale
        state = SimpleNamespace(
            simulation_id="sim-test",
            project_id=project_id,
            graph_id=graph_id,
            locale=locale,
            to_dict=lambda: {"simulation_id": "sim-test", "locale": locale},
        )
        return state

    monkeypatch.setattr(SimulationManager, "create_simulation", mock_create_simulation)

    with app.test_request_context(
        "/api/simulation/create",
        method="POST",
        json={"project_id": "proj-1", "locale": "fr"},
        headers={"Accept-Language": "en-US"},
    ):
        with monkeypatch.context() as m:
            from app.models.project import ProjectManager
            m.setattr(ProjectManager, "get_project", lambda pid: SimpleNamespace(graph_id="g-1"))
            resp = simulation_api.create_simulation()
            data = resp.get_json() if hasattr(resp, "get_json") else resp[0].get_json()
            assert data["success"] is True
            assert captured["locale"] == "fr"


def test_prepare_simulation_enforces_canonical_locale_internally(tmp_path, monkeypatch):
    """Vérifie que prepare_simulation confine son exécution sous use_locale(state.locale)."""
    manager = SimulationManager()
    manager.SIMULATION_DATA_DIR = str(tmp_path)
    state = manager.create_simulation("proj-1", "graph-1", locale="fr")

    observed_locale = []

    def mock_execute_prepare(self, *args, **kwargs):
        observed_locale.append(get_locale())
        return state

    monkeypatch.setattr(SimulationManager, "_execute_prepare", mock_execute_prepare)

    # Thread appelant configuré en 'en'
    with use_locale("en"):
        assert get_locale() == "en"
        manager.prepare_simulation(state.simulation_id, "req", "doc")
        assert get_locale() == "en"

    assert observed_locale == ["fr"]


def test_localized_fallback_and_guidance_tolerate_unknown_locale(monkeypatch):
    """Vérifie l'absence de KeyError sur locale non répertoriée dans les gabarits."""
    generator = object.__new__(OasisProfileGenerator)
    monkeypatch.setattr("app.services.oasis_profile_generator.get_locale", lambda: "es_ES")

    fallback = generator._localized_fallback("Alice", "Person", "")
    assert "Alice" in fallback["bio"]
    assert "参与公共讨论" in fallback["persona"]

    guided = generator._add_agent_language_guidance({"persona": "Base"})
    assert "Base" in guided["persona"]
    assert "在本次模拟中" in guided["persona"]


def test_add_agent_language_guidance_cleans_former_multilingual_guidance():
    """Vérifie qu'un persona régénéré sous une autre locale ne conserve pas les consignes antérieures."""
    generator = object.__new__(OasisProfileGenerator)
    zh_persona = "Biographie initiale.\n在本次模拟中，帖子和回复均使用中文。"
    profile_data = {"persona": zh_persona}

    with use_locale("fr"):
        result = generator._add_agent_language_guidance(profile_data)

    assert "在本次模拟中" not in result["persona"]
    assert "Biographie initiale." in result["persona"]
    assert "Dans cette simulation, les publications et les réponses sont rédigées en français." in result["persona"]


# ── Tests hermétiques de localisation de SimulationConfigGenerator (T4) ──

@pytest.mark.parametrize(
    ("locale", "expected_fragment"),
    [
        ("fr", "Configuration horaire par défaut"),
        ("en", "Default schedule configuration"),
        ("zh", "默认中国人作息配置"),
    ],
)
def test_simulation_config_generator_default_time_config_localized(locale, expected_fragment):
    generator = object.__new__(SimulationConfigGenerator)
    with use_locale(locale):
        cfg = generator._get_default_time_config(10)
    assert expected_fragment in cfg["reasoning"]
    assert cfg["total_simulation_hours"] == 72
    assert cfg["minutes_per_round"] == 60


@pytest.mark.parametrize(
    ("locale", "expected_fragment"),
    [
        ("fr", "Configuration par défaut"),
        ("en", "Default configuration"),
        ("zh", "使用默认配置"),
    ],
)
def test_simulation_config_generator_event_fallback_localized(monkeypatch, locale, expected_fragment):
    generator = object.__new__(SimulationConfigGenerator)
    monkeypatch.setattr(generator, "_call_llm_with_retry", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("LLM error")))
    with use_locale(locale):
        cfg = generator._generate_event_config("doc", "req", [])
    assert cfg["reasoning"] == expected_fragment
    assert cfg["initial_posts"] == []


# ── Tests hermétiques de localisation de ReportAgent (T5) ──

@pytest.mark.parametrize(
    ("locale", "expected_title", "expected_sec_title"),
    [
        ("fr", "Rapport de prédiction et simulation", "Scénario simulé et constats fondamentaux"),
        ("en", "Simulation Prediction Report", "Simulation Scenario and Core Findings"),
        ("zh", "未来预测报告", "预测场景与核心发现"),
    ],
)
def test_report_agent_default_outline_localized(locale, expected_title, expected_sec_title):
    from app.services.report_agent import _get_default_outline
    with use_locale(locale):
        outline = _get_default_outline()
    assert outline.title == expected_title
    assert len(outline.sections) == 3
    assert outline.sections[0].title == expected_sec_title


def test_report_agent_plan_outline_prompts_and_parses_french(monkeypatch):
    from app.services.report_agent import ReportAgent

    captured_messages = []

    class MockLLM:
        def chat_json(self, messages, **kwargs):
            captured_messages.append(messages)
            return {
                "title": "Rapport Prédictif IA",
                "summary": "Résumé de simulation francophone",
                "sections": [
                    {"title": "Dynamiques d'adoption", "description": "Analyse des flux"},
                    {"title": "Réactions institutionnelles", "description": "Mesures prises"},
                ],
            }

    agent = ReportAgent(
        graph_id="g-1",
        simulation_id="s-1",
        simulation_requirement="Impact IA en France",
        llm_client=MockLLM(),
        locale="fr",
    )
    monkeypatch.setattr(agent.zep_tools, "get_simulation_context", lambda **kw: {"total_entities": 5})

    # Thread appelant configuré en 'en' pour tester le confinement
    with use_locale("en"):
        outline = agent.plan_outline()

    assert outline.title == "Rapport Prédictif IA"
    assert outline.summary == "Résumé de simulation francophone"
    assert len(outline.sections) == 2
    assert outline.sections[0].title == "Dynamiques d'adoption"

    # Vérifier que le prompt système contient la consigne française et l'invariant des clés
    system_content = captured_messages[0][0]["content"]
    assert "Veuillez répondre en français." in system_content
    assert "IMPORTANT: The JSON keys ('title', 'summary', 'sections', 'description') MUST remain in English." in system_content


def test_report_agent_plan_outline_fallback_on_llm_error(monkeypatch):
    from app.services.report_agent import ReportAgent

    class FailingLLM:
        def chat_json(self, *args, **kwargs):
            raise RuntimeError("LLM unavailable")

    agent = ReportAgent(
        graph_id="g-1",
        simulation_id="s-1",
        simulation_requirement="Impact IA en France",
        llm_client=FailingLLM(),
        locale="fr",
    )
    monkeypatch.setattr(agent.zep_tools, "get_simulation_context", lambda **kw: {})

    outline = agent.plan_outline()
    assert outline.title == "Rapport de prédiction et simulation"
    assert len(outline.sections) == 3
    assert outline.sections[0].title == "Scénario simulé et constats fondamentaux"


@pytest.mark.parametrize(
    ("locale", "expected_fragment"),
    [
        ("fr", "La limite d'appels d'outils est atteinte"),
        ("en", "Tool call limit reached"),
        ("zh", "已达到工具调用限制"),
    ],
)
def test_report_agent_react_force_final_message_localized(locale, expected_fragment):
    from app.services.report_agent import _get_react_force_final_msg
    with use_locale(locale):
        msg = _get_react_force_final_msg()
    assert expected_fragment in msg
    assert "Final Answer:" in msg


@pytest.mark.parametrize(
    ("locale", "expected_obs_header", "expected_tool_limit"),
    [
        ("fr", "Observation (résultats de recherche) :", "Limite d'appels d'outils atteinte"),
        ("en", "Observation (search results):", "Tool call limit reached"),
        ("zh", "Observation（检索结果）:", "工具调用次数已达上限"),
    ],
)
def test_report_agent_react_loop_messages_localized(locale, expected_obs_header, expected_tool_limit):
    from app.services.report_agent import _get_react_observation_msg, _get_react_tool_limit_msg
    with use_locale(locale):
        obs = _get_react_observation_msg("quick_search", "Fact 1", 2, 5, "quick_search", "")
        limit = _get_react_tool_limit_msg(5, 5)
    assert expected_obs_header in obs
    assert expected_tool_limit in limit


def test_report_agent_chat_hermetic_french_confinement(monkeypatch):
    from app.services.report_agent import ReportAgent

    captured = []

    class MockChatLLM:
        def chat(self, messages, **kwargs):
            captured.append(messages)
            return "Voici la réponse d'analyse en français."

    agent = ReportAgent(
        graph_id="g-1",
        simulation_id="s-1",
        simulation_requirement="Simulation test",
        llm_client=MockChatLLM(),
        locale="fr",
    )

    with use_locale("zh"):
        result = agent.chat("Quel est l'impact principal ?")

    assert result["response"] == "Voici la réponse d'analyse en français."
    system_prompt = captured[0][0]["content"]
    assert "Veuillez répondre en français." in system_prompt


def test_report_agent_section_react_french_workflow(monkeypatch):
    """Vérifie le cycle ReACT en français : prompt invariant, gestion de conflit et messages localisés."""
    from app.services.report_agent import ReportAgent, ReportOutline, ReportSection

    captured_turns = []

    # Séquence de réponses LLM :
    # 1. Conflit tool_call + Final Answer -> déclenche message de rejet formaté en FR
    # 2. Tool call valide -> exécute l'outil, retourne observation en FR
    # 3. Final Answer avec citations fidèles -> acceptation et fin
    responses = [
        '<tool_call>{"name": "quick_search", "parameters": {"query": "test"}}</tool_call>\nFinal Answer: Première ébauche',
        '<tool_call>{"name": "quick_search", "parameters": {"query": "test"}}</tool_call>',
        'Final Answer: Analyse détaillée en français.\n\n> "Citation originale verbatim"',
    ]

    class SequenceLLM:
        def __init__(self):
            self.call_idx = 0

        def chat(self, messages, **kwargs):
            captured_turns.append(list(messages))
            resp = responses[min(self.call_idx, len(responses) - 1)]
            self.call_idx += 1
            return resp

    agent = ReportAgent(
        graph_id="g-1",
        simulation_id="s-1",
        simulation_requirement="Test scénario",
        llm_client=SequenceLLM(),
        locale="fr",
    )
    monkeypatch.setattr(agent, "_execute_tool", lambda name, params, report_context=None: "Donnée de simulation factuelle")

    section = ReportSection(title="Section test")
    outline = ReportOutline(title="Rapport", summary="Résumé", sections=[section])

    content = agent._generate_section_react(
        section=section,
        outline=outline,
        previous_sections=[],
        section_index=0
    )

    assert "Analyse détaillée en français." in content
    assert '> "Citation originale verbatim"' in content

    # Vérification du prompt système initial
    first_turn_system = captured_turns[0][0]["content"]
    assert "Veuillez répondre en français." in first_turn_system
    assert "ReACT markers ('Thought:', 'Action:', 'Final Answer:') and tool call formats must remain intact in English." in first_turn_system
    assert "Verbatim quotes from source documents or simulated actions must be faithfully reproduced in their original language" in first_turn_system

    # Vérification du message de conflit (tour 1 -> user message de rejet)
    second_turn_user = captured_turns[1][-1]["content"]
    assert "【Erreur de format】" in second_turn_user
    assert "Chaque réponse doit faire exclusivement l'une des deux actions suivantes" in second_turn_user



