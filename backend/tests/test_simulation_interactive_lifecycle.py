"""
Tests hermétiques pour le cycle de vie interactif d'OASIS post-rounds,
le rétablissement de interview_agents et la clôture différée.
Epic 011 — Story 011-1 (AC1 à AC6).
"""

import json
import os
import subprocess
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from app.api import simulation as simulation_api
from app.services import simulation_runner as runner_module
from app.services.report_agent import ReportAgent, ReportStatus
from app.services.simulation_action_verifier import ActionEventRecord, SimulationActionVerifier
from app.services.simulation_ipc import CommandStatus, CommandType, IPCResponse, SimulationIPCClient
from app.services.simulation_runner import (
    RunnerStatus,
    SimulationRunState,
    SimulationRunner,
)
from app.services.zep_tools import ZepToolsService


@pytest.fixture(autouse=True)
def clean_runner_state():
    """Nettoie les registres statiques de SimulationRunner avant et après chaque test."""
    SimulationRunner._processes.clear()
    SimulationRunner._run_states.clear()
    SimulationRunner._state_file_mtimes.clear()
    SimulationRunner._graph_memory_enabled.clear()
    SimulationRunner._manual_stop_requests.clear()
    SimulationRunner._monitor_threads.clear()
    SimulationRunner._stdout_files.clear()
    SimulationRunner._stderr_files.clear()
    yield
    SimulationRunner._processes.clear()
    SimulationRunner._run_states.clear()
    SimulationRunner._state_file_mtimes.clear()
    SimulationRunner._graph_memory_enabled.clear()
    SimulationRunner._manual_stop_requests.clear()
    SimulationRunner._monitor_threads.clear()
    SimulationRunner._stdout_files.clear()
    SimulationRunner._stderr_files.clear()


class MockSubprocess:
    """Mock de sous-processus simulant un processus persistant en attente de commandes IPC."""

    def __init__(self, pid: int = 12345):
        self.pid = pid
        self.returncode = None
        self._alive = True
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self._alive else 0

    def wait(self, timeout=None):
        if not self._alive:
            return 0
        self._alive = False
        self.returncode = 0
        return 0

    def terminate(self):
        self.terminated = True
        self._alive = False
        self.returncode = 0

    def kill(self):
        self.killed = True
        self._alive = False
        self.returncode = -9


# ==============================================================================
# AC1: Découplage complétion logique / vivacité du processus
# ==============================================================================

def test_ac1_decoupled_completion_preserves_running_subprocess(tmp_path, monkeypatch):
    """
    AC1: Lorsque _check_all_platforms_completed(state) devient True en mode keep_alive,
    state.runner_status passe à COMPLETED, completed_at est renseigné,
    mais le sous-processus OS n'est pas terminé et check_env_alive reste True.
    """
    sim_id = "sim-ac1-decoupled"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
        twitter_completed=True,
        reddit_completed=True,
        keep_alive_on_completion=True,
    )
    SimulationRunner._run_states[sim_id] = state

    proc = MockSubprocess(pid=55101)
    SimulationRunner._processes[sim_id] = proc

    # Mock _check_all_platforms_completed
    monkeypatch.setattr(
        SimulationRunner,
        "_check_all_platforms_completed",
        classmethod(lambda _cls, _st: True),
    )

    # Mock IPC client toujours vivant
    class MockIPC:
        def __init__(self, directory):
            self.directory = directory
        def check_env_alive(self):
            return True

    monkeypatch.setattr(runner_module, "SimulationIPCClient", MockIPC)

    synced_statuses = []
    monkeypatch.setattr(
        SimulationRunner,
        "_sync_simulation_status",
        classmethod(lambda _cls, _sid, status, *args, **kwargs: synced_statuses.append(status)),
    )

    # Faire tourner une itération de la boucle de monitoring puis simuler la sortie
    iterations = [0]

    def mock_sleep(_s):
        iterations[0] += 1
        if iterations[0] >= 1:
            # Sortir de la boucle while process.poll() is None
            proc._alive = False

    monkeypatch.setattr(time, "sleep", mock_sleep)

    SimulationRunner._monitor_simulation(sim_id)

    # Vérifications AC1
    assert state.runner_status == RunnerStatus.COMPLETED
    assert state.completed_at is not None
    assert state.twitter_running is False
    assert state.reddit_running is False
    assert RunnerStatus.COMPLETED in synced_statuses
    # Le processus ne doit pas avoir reçu de SIGTERM destructeur prématuré
    assert proc.terminated is False
    assert proc.killed is False


def test_ac1_memory_updater_drained_at_logical_completion(tmp_path, monkeypatch):
    """
    AC1: Le drain mémoire Zep/Neo4j est déclenché sous verrou dès la complétion logique
    des plateformes sans attendre la mort du sous-processus.
    """
    sim_id = "sim-ac1-drain"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
        twitter_completed=True,
        reddit_completed=True,
        keep_alive_on_completion=True,
    )
    SimulationRunner._run_states[sim_id] = state
    SimulationRunner._graph_memory_enabled[sim_id] = True

    proc = MockSubprocess(pid=55102)
    SimulationRunner._processes[sim_id] = proc

    updater_stopped = []
    mock_updater = MagicMock()
    mock_updater.stop_updater.side_effect = lambda sid: updater_stopped.append(sid)
    monkeypatch.setattr(runner_module, "ZepGraphMemoryManager", mock_updater)

    monkeypatch.setattr(
        SimulationRunner,
        "_check_all_platforms_completed",
        classmethod(lambda _cls, _st: True),
    )
    monkeypatch.setattr(
        SimulationRunner,
        "_sync_simulation_status",
        classmethod(lambda *args, **kwargs: None),
    )

    def mock_sleep(_s):
        proc._alive = False

    monkeypatch.setattr(time, "sleep", mock_sleep)

    SimulationRunner._monitor_simulation(sim_id)

    assert sim_id in updater_stopped
    assert state.runner_status == RunnerStatus.COMPLETED


# ==============================================================================
# AC2: Rétablissement du succès de interview_agents en direct
# ==============================================================================

def test_ac2_interview_agents_batch_succeeds_when_completed_and_alive(tmp_path, monkeypatch):
    """
    AC2: Lorsque SimulationRunner.interview_agents_batch est appelé sur une simulation COMPLETED
    avec processus actif en attente IPC, la commande est transmise et renvoie 100% de succès.
    """
    sim_id = "sim-ac2-interview"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.COMPLETED,
        completed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        keep_alive_on_completion=True,
    )
    SimulationRunner._run_states[sim_id] = state

    proc = MockSubprocess(pid=55201)
    SimulationRunner._processes[sim_id] = proc

    interview_payload = [
        {"agent_id": 0, "prompt": "Qu'en pensez-vous ?"},
        {"agent_id": 1, "prompt": "Qu'en pensez-vous ?"},
    ]

    sent_commands = []

    class MockLiveIPC:
        def __init__(self, directory):
            self.directory = directory

        def check_env_alive(self):
            return True

        def send_batch_interview(self, interviews, platform=None, timeout=120.0):
            sent_commands.append({"interviews": interviews, "platform": platform})
            return IPCResponse(
                command_id="cmd-batch-1",
                status=CommandStatus.COMPLETED,
                result={
                    "results": {
                        "twitter_0": {"response": "Je soutiens cette initiative."},
                        "reddit_0": {"response": "Intéressant mais à voir."},
                        "twitter_1": {"response": "Opposé totalement."},
                        "reddit_1": {"response": "Inacceptable."},
                    }
                },
            )

    monkeypatch.setattr(runner_module, "SimulationIPCClient", MockLiveIPC)

    res = SimulationRunner.interview_agents_batch(
        simulation_id=sim_id,
        interviews=interview_payload,
        platform=None,
    )

    assert res["success"] is True
    assert res["interviews_count"] == 2
    assert "results" in res["result"]
    assert len(sent_commands) == 1
    assert sent_commands[0]["interviews"] == interview_payload


def test_ac2_zep_tools_service_interview_agents_live_full_flow(tmp_path, monkeypatch):
    """
    AC2: ZepToolsService.interview_agents interroge avec succès les agents via IPC vivant
    et enrichit InterviewResult avec les citations et réponses formatées.
    """
    sim_id = "sim-ac2-live-tool"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)

    # Fichier profiles
    reddit_profiles = [
        {"username": "DrMartin", "profession": "Chercheur", "bio": "Expert climat", "persona": "Rationnel"},
        {"username": "CitizenX", "profession": "Citoyen", "bio": "Habitant engagé", "persona": "Critique"},
    ]
    (sim_dir / "reddit_profiles.json").write_text(json.dumps(reddit_profiles), encoding="utf-8")

    mock_llm = MagicMock()
    mock_llm.chat_json.return_value = {
        "selected_indices": [0, 1],
        "reasoning": "Diversité des avis",
        "questions": ["Quel est votre point de vue ?"],
    }
    mock_llm.chat.return_value = "Synthèse d'interview"

    service = ZepToolsService(llm_client=mock_llm)
    monkeypatch.setattr(service, "_load_agent_profiles", lambda sid: reddit_profiles)

    # SimulationRunner interview_agents_batch mock retournant le format OASIS
    mock_batch_res = {
        "success": True,
        "interviews_count": 2,
        "result": {
            "results": {
                "twitter_0": {"response": "Le réchauffement climatique est une priorité absolue et urgente pour nos enfants."},
                "reddit_0": {"response": "Il est impératif d'agir immédiatement sur les infrastructures."},
                "twitter_1": {"response": "Les coûts économiques associés doivent être répartis équitablement entre tous."},
                "reddit_1": {"response": "La transition écologique doit préserver le pouvoir d'achat des classes moyennes."},
            }
        },
    }
    monkeypatch.setattr(SimulationRunner, "interview_agents_batch", classmethod(lambda *args, **kwargs: mock_batch_res))

    result = service.interview_agents(
        simulation_id=sim_id,
        interview_requirement="Recueillir les avis sur le climat",
        max_agents=2,
    )

    assert result.interviewed_count == 2
    assert len(result.interviews) == 2
    assert "DrMartin" in [inv.agent_name for inv in result.interviews]
    assert "【Twitter平台回答】" in result.interviews[0].response


# ==============================================================================
# AC3: Clôture différée ordonnée post-rapport (send_close_env)
# ==============================================================================

def test_ac3_close_simulation_environment_sends_ipc_and_cleans_resources(tmp_path, monkeypatch):
    """
    AC3: close_simulation_environment envoie send_close_env(), attend la fin du sous-processus
    et ferme les descripteurs de logs et registres statiques.
    """
    sim_id = "sim-ac3-close"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    proc = MockSubprocess(pid=55301)
    SimulationRunner._processes[sim_id] = proc

    log_file = tmp_path / "sim.log"
    log_handle = open(log_file, "w")
    SimulationRunner._stdout_files[sim_id] = log_handle

    close_calls = []

    class MockIPC:
        def __init__(self, directory):
            self.directory = directory

        def check_env_alive(self):
            return True

        def send_close_env(self, timeout=5.0):
            close_calls.append("send_close_env")
            proc._alive = False  # Simuler la terminaison gracieuse du processus
            return IPCResponse(
                command_id="cmd-close-1",
                status=CommandStatus.COMPLETED,
                result={"status": "stopped"},
            )

    monkeypatch.setattr(runner_module, "SimulationIPCClient", MockIPC)

    res = SimulationRunner.close_simulation_environment(sim_id, timeout=5.0)

    assert res["success"] is True
    assert "send_close_env" in close_calls
    # Vérifier le nettoyage des registres statiques
    assert sim_id not in SimulationRunner._processes
    assert sim_id not in SimulationRunner._stdout_files
    assert log_handle.closed is True


def test_ac3_report_agent_triggers_close_simulation_environment_in_finally(tmp_path, monkeypatch):
    """
    AC3: ReportAgent._generate_report_internal déclenche systématiquement
    SimulationRunner.close_simulation_environment(simulation_id) dans son bloc finally.
    """
    sim_id = "sim-ac3-agent"
    closed_sims = []

    monkeypatch.setattr(
        SimulationRunner,
        "close_simulation_environment",
        classmethod(lambda _cls, sid, *args, **kwargs: closed_sims.append(sid)),
    )

    agent = ReportAgent(
        simulation_id=sim_id,
        graph_id="grp-1",
        simulation_requirement="Test requirement",
    )

    # Simuler une génération de rapport échouant ou réussissant
    monkeypatch.setattr(agent, "plan_outline", MagicMock(side_effect=RuntimeError("Erreur simulée")))

    agent.generate_report()

    # Le bloc finally doit impérativement avoir déclenché la clôture
    assert sim_id in closed_sims



# ==============================================================================
# AC4: Repli gracieux hors-ligne sur simulation éteinte
# ==============================================================================

def test_ac4_offline_fallback_when_env_not_alive(tmp_path, monkeypatch):
    """
    AC4: Lorsque SimulationRunner.check_env_alive() est False ou que interview_agents_batch
    lève ValueError, interview_agents bascule sans exception vers la synthèse hors-ligne étiquetée.
    """
    sim_id = "sim-ac4-offline"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)

    reddit_profiles = [
        {"username": "Historian", "profession": "Historien", "bio": "Spécialiste archives", "persona": "Rigoureux"},
    ]

    mock_llm = MagicMock()
    mock_llm.chat_json.return_value = {
        "selected_indices": [0],
        "reasoning": "Rôle pertinent",
        "questions": ["Quelle analyse rétrospective ?"],
    }
    # Réponse LLM hors-ligne
    mock_llm.chat.return_value = "En analysant les archives de cette simulation, les faits confirment l'hypothèse de départ."

    service = ZepToolsService(llm_client=mock_llm)
    monkeypatch.setattr(service, "_load_agent_profiles", lambda sid: reddit_profiles)

    # Simuler un environnement arrêté (check_env_alive -> False / ValueError)
    def mock_fail_batch(*args, **kwargs):
        raise ValueError(f"模拟环境未运行或已关闭，无法执行Interview: {sim_id}")

    monkeypatch.setattr(SimulationRunner, "interview_agents_batch", classmethod(mock_fail_batch))

    # Mock load_simulation_actions
    mock_action = ActionEventRecord(
        event_id="evt-1",
        simulation_id=sim_id,
        platform="twitter",
        round_num=1,
        agent_id=0,
        agent_name="Historian",
        action_type="post",
        timestamp="2026-10-16T10:00:00",
        action_args={"content": "Je publie un avertissement sur l'inflation."},
    )
    monkeypatch.setattr(
        SimulationActionVerifier,
        "load_simulation_actions",
        lambda self, sid=None, sim_dir=None: [mock_action],
    )

    result = service.interview_agents(
        simulation_id=sim_id,
        interview_requirement="Analyse rétrospective",
        max_agents=1,
    )

    # Vérifications AC4
    assert result.interviewed_count == 1
    assert len(result.interviews) == 1
    interview = result.interviews[0]
    assert interview.agent_name == "Historian"
    assert "Mode archives / Hors-ligne" in interview.response
    assert len(interview.key_quotes) > 0


# ==============================================================================
# AC5: Garantie anti-zombie et nettoyage d'urgence
# ==============================================================================

def test_ac5_inactivity_watchdog_terminates_idle_completed_process(tmp_path, monkeypatch):
    """
    AC5: Si un processus OASIS reste en veille interactive plus longtemps que le timeout
    d'inactivité sans déclenchement de rapport, le watchdog déclenche l'extinction.
    """
    sim_id = "sim-ac5-watchdog"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
        twitter_completed=True,
        reddit_completed=True,
        keep_alive_on_completion=True,
    )
    SimulationRunner._run_states[sim_id] = state

    proc = MockSubprocess(pid=55501)
    SimulationRunner._processes[sim_id] = proc

    monkeypatch.setattr(
        SimulationRunner,
        "_check_all_platforms_completed",
        classmethod(lambda _cls, _st: True),
    )
    monkeypatch.setattr(
        SimulationRunner,
        "_sync_simulation_status",
        classmethod(lambda *args, **kwargs: None),
    )

    # Réduire le timeout watchdog pour le test à 10 secondes
    monkeypatch.setattr(runner_module.Config, "SIMULATION_INACTIVITY_TIMEOUT_SECONDS", 10.0, raising=False)

    closed_envs = []
    monkeypatch.setattr(
        SimulationRunner,
        "close_simulation_environment",
        classmethod(lambda _cls, sid, timeout=5.0: closed_envs.append(sid)),
    )

    # Simuler le temps : t=0 (complétion), t=15 (dépassement watchdog 10s)
    mock_times = [0.0, 15.0]
    monkeypatch.setattr(time, "time", lambda: mock_times.pop(0) if mock_times else 20.0)
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    SimulationRunner._monitor_simulation(sim_id)

    assert sim_id in closed_envs


def test_ac5_cleanup_all_simulations_terminates_all_active_processes(tmp_path, monkeypatch):
    """
    AC5: cleanup_all_simulations s'assure qu'aucun sous-processus zombie ne subsiste
    même pour les simulations en état COMPLETED en attente interactive.
    """
    sim_id = "sim-ac5-cleanup"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    proc = MockSubprocess(pid=55502)
    SimulationRunner._processes[sim_id] = proc

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.COMPLETED,
        keep_alive_on_completion=True,
    )
    SimulationRunner._run_states[sim_id] = state

    stopped_sims = []
    monkeypatch.setattr(
        SimulationRunner,
        "stop_simulation",
        classmethod(lambda _cls, sid: stopped_sims.append(sid)),
    )

    SimulationRunner._cleanup_done = False
    SimulationRunner.cleanup_all_simulations()

    assert sim_id in stopped_sims
