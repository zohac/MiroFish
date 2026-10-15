"""
Tests hermétiques pour l'arrêt déterministe (--no-wait) et la complétion automatique.
Epic 010 — Story 010-1 (AC1 à AC6).
"""

import json
import os
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import simulation as simulation_api
from app.services import simulation_runner as runner_module
from app.services.simulation_ipc import CommandType, IPCResponse
from app.services.simulation_runner import (
    RunnerStatus,
    SimulationRunState,
    SimulationRunner,
)


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


def test_start_simulation_injects_no_wait_by_default(tmp_path, monkeypatch):
    """AC1: Lors du lancement par défaut, --no-wait est présent dans les arguments cmd."""
    sim_id = "sim-nowait-default"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    config_file = sim_dir / "simulation_config.json"
    config_file.write_text(json.dumps({
        "time_config": {"total_simulation_hours": 24, "minutes_per_round": 60}
    }), encoding="utf-8")

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "SCRIPTS_DIR", str(tmp_path))
    script_path = tmp_path / "run_parallel_simulation.py"
    script_path.write_text("# dummy", encoding="utf-8")

    spawned_cmds = []

    class MockPopen:
        def __init__(self, cmd, *args, **kwargs):
            spawned_cmds.append(list(cmd))
            self.pid = 99999
            self.returncode = None
        def poll(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", MockPopen)
    monkeypatch.setattr(SimulationRunner, "_sync_simulation_status", classmethod(lambda *args, **kwargs: None))

    state = SimulationRunner.start_simulation(sim_id, platform="parallel")

    assert state.simulation_id == sim_id
    assert len(spawned_cmds) == 1
    cmd = spawned_cmds[0]
    assert "--no-wait" in cmd
    assert "--config" in cmd
    assert str(config_file) in cmd


def test_start_simulation_omits_no_wait_when_keep_alive_requested(tmp_path, monkeypatch):
    """AC1: Si keep_alive_on_completion=True, --no-wait n'est pas injecté."""
    sim_id = "sim-keep-alive"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    config_file = sim_dir / "simulation_config.json"
    config_file.write_text(json.dumps({
        "time_config": {"total_simulation_hours": 12, "minutes_per_round": 60}
    }), encoding="utf-8")

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "SCRIPTS_DIR", str(tmp_path))
    script_path = tmp_path / "run_parallel_simulation.py"
    script_path.write_text("# dummy", encoding="utf-8")

    spawned_cmds = []

    class MockPopen:
        def __init__(self, cmd, *args, **kwargs):
            spawned_cmds.append(list(cmd))
            self.pid = 88888
            self.returncode = None
        def poll(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", MockPopen)
    monkeypatch.setattr(SimulationRunner, "_sync_simulation_status", classmethod(lambda *args, **kwargs: None))

    state = SimulationRunner.start_simulation(sim_id, platform="parallel", keep_alive_on_completion=True)

    assert state.simulation_id == sim_id
    assert len(spawned_cmds) == 1
    cmd = spawned_cmds[0]
    assert "--no-wait" not in cmd


def test_start_simulation_reads_keep_alive_from_config(tmp_path, monkeypatch):
    """AC1: Si simulation_config.json contient keep_alive_on_completion: true, --no-wait est omis."""
    sim_id = "sim-keep-alive-cfg"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    config_file = sim_dir / "simulation_config.json"
    config_file.write_text(json.dumps({
        "time_config": {"total_simulation_hours": 6, "minutes_per_round": 30},
        "keep_alive_on_completion": True,
    }), encoding="utf-8")

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "SCRIPTS_DIR", str(tmp_path))
    script_path = tmp_path / "run_parallel_simulation.py"
    script_path.write_text("# dummy", encoding="utf-8")

    spawned_cmds = []

    class MockPopen:
        def __init__(self, cmd, *args, **kwargs):
            spawned_cmds.append(list(cmd))
            self.pid = 77777
            self.returncode = None
        def poll(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", MockPopen)
    monkeypatch.setattr(SimulationRunner, "_sync_simulation_status", classmethod(lambda *args, **kwargs: None))

    state = SimulationRunner.start_simulation(sim_id, platform="parallel")

    assert len(spawned_cmds) == 1
    cmd = spawned_cmds[0]
    assert "--no-wait" not in cmd


def test_monitor_simulation_natural_completion_transitions_to_completed(tmp_path, monkeypatch):
    """AC2 & AC4: Quand le processus s'éteint avec code 0, runner_status bascule à COMPLETED."""
    sim_id = "sim-natural-end"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
        twitter_running=True,
        reddit_running=True,
    )
    SimulationRunner._run_states[sim_id] = state

    class MockProcess:
        def __init__(self):
            self.polls = [None, 0]
            self.returncode = 0
            self.pid = 1234
        def poll(self):
            if self.polls:
                return self.polls.pop(0)
            return 0

    process = MockProcess()
    SimulationRunner._processes[sim_id] = process

    monkeypatch.setattr(time, "sleep", lambda _s: None)
    synced_statuses = []
    monkeypatch.setattr(
        SimulationRunner,
        "_sync_simulation_status",
        classmethod(lambda _cls, _sid, status, *args, **kwargs: synced_statuses.append(status)),
    )

    SimulationRunner._monitor_simulation(sim_id)

    assert state.runner_status == RunnerStatus.COMPLETED
    assert state.completed_at is not None
    assert state.twitter_running is False
    assert state.reddit_running is False
    assert RunnerStatus.COMPLETED in synced_statuses

    # Vérification persistance run_state.json sur disque
    state_file = sim_dir / "run_state.json"
    assert state_file.exists()
    persisted = json.loads(state_file.read_text(encoding="utf-8"))
    assert persisted["runner_status"] == RunnerStatus.COMPLETED.value
    assert persisted["completed_at"] == state.completed_at


def test_monitor_simulation_sends_ipc_close_env_after_grace_period(tmp_path, monkeypatch):
    """AC3: Si les plateformes sont terminées mais le processus ne quitte pas après 5s, close_env est envoyé."""
    sim_id = "sim-ipc-fallback"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
        twitter_completed=True,
        reddit_completed=True,
    )
    SimulationRunner._run_states[sim_id] = state

    # Mock _check_all_platforms_completed -> True
    monkeypatch.setattr(SimulationRunner, "_check_all_platforms_completed", classmethod(lambda _cls, _st: True))

    ipc_calls = []
    class MockIPCClient:
        def __init__(self, directory):
            self.directory = directory
        def check_env_alive(self):
            return True
        def send_close_env(self, timeout=3.0):
            ipc_calls.append("close_env")
            return IPCResponse(
                command_id="cmd-1",
                command_type=CommandType.CLOSE_ENV,
                status=runner_module.CommandStatus.COMPLETED,
                result={},
            )

    monkeypatch.setattr(runner_module, "SimulationIPCClient", MockIPCClient)

    # Simuler le temps: t=0 (détection), t=6s (dépassement 5s -> IPC envoyé), puis processus quitte
    mock_times = [0.0, 6.0, 7.0]
    monkeypatch.setattr(time, "time", lambda: mock_times.pop(0) if mock_times else 10.0)
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    class MockProcess:
        def __init__(self):
            self.polls = [None, None, 0]
            self.returncode = 0
            self.pid = 4321
        def poll(self):
            if self.polls:
                return self.polls.pop(0)
            return 0

    process = MockProcess()
    SimulationRunner._processes[sim_id] = process
    monkeypatch.setattr(SimulationRunner, "_sync_simulation_status", classmethod(lambda *args, **kwargs: None))

    SimulationRunner._monitor_simulation(sim_id)

    assert "close_env" in ipc_calls
    assert state.runner_status == RunnerStatus.COMPLETED


def test_monitor_simulation_forces_terminate_after_total_timeout(tmp_path, monkeypatch):
    """AC3: Si le processus résiste 10s après complétion, _terminate_process est invoqué de force."""
    sim_id = "sim-terminate-fallback"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
        twitter_completed=True,
    )
    SimulationRunner._run_states[sim_id] = state

    monkeypatch.setattr(SimulationRunner, "_check_all_platforms_completed", classmethod(lambda _cls, _st: True))

    class MockIPCClient:
        def __init__(self, directory):
            pass
        def check_env_alive(self):
            return False
        def send_close_env(self, timeout=3.0):
            pass

    monkeypatch.setattr(runner_module, "SimulationIPCClient", MockIPCClient)

    # Simuler le temps: 0.0 -> 6.0 (IPC tenté) -> 11.0 (>= 10s -> terminate)
    mock_times = [0.0, 6.0, 11.0, 12.0]
    monkeypatch.setattr(time, "time", lambda: mock_times.pop(0) if mock_times else 20.0)
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    terminated_calls = []

    class MockStubbornProcess:
        def __init__(self):
            self.returncode = 0
            self.pid = 6789
        def poll(self):
            # Le processus ne quitte jamais par lui-même
            return None

    process = MockStubbornProcess()
    SimulationRunner._processes[sim_id] = process

    def fake_terminate(cls, proc, sid, timeout=3):
        terminated_calls.append(sid)
        proc.returncode = -15  # SIGTERM

    monkeypatch.setattr(SimulationRunner, "_terminate_process", classmethod(fake_terminate))
    monkeypatch.setattr(SimulationRunner, "_sync_simulation_status", classmethod(lambda *args, **kwargs: None))

    SimulationRunner._monitor_simulation(sim_id)

    assert sim_id in terminated_calls
    # Terminaison par signal -> code non nul -> FAILED avec information d'arrêt
    assert state.runner_status == RunnerStatus.FAILED
    assert "进程退出码: -15" in state.error


def test_monitor_simulation_fails_on_memory_updater_drain_error(tmp_path, monkeypatch):
    """AC5: Si le drain de ZepGraphMemoryManager échoue, la simulation bascule en FAILED."""
    sim_id = "sim-drain-fail"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
    )
    SimulationRunner._run_states[sim_id] = state
    SimulationRunner._graph_memory_enabled[sim_id] = True

    class MockProcess:
        def __init__(self):
            self.returncode = 0
            self.pid = 1111
        def poll(self):
            return 0

    SimulationRunner._processes[sim_id] = MockProcess()

    monkeypatch.setattr(
        runner_module.ZepGraphMemoryManager,
        "stop_updater",
        classmethod(lambda _cls, _sid: (_ for _ in ()).throw(RuntimeError("Neo4j Bolt connection lost"))),
    )
    monkeypatch.setattr(SimulationRunner, "_sync_simulation_status", classmethod(lambda *args, **kwargs: None))

    SimulationRunner._monitor_simulation(sim_id)

    assert state.runner_status == RunnerStatus.FAILED
    assert "Zep图谱写入未完整完成" in state.error
    assert "Neo4j Bolt connection lost" in state.error


def test_api_start_simulation_handles_keep_alive_on_completion(monkeypatch):
    """AC1: L'API POST /api/simulation/start valide et propage keep_alive_on_completion."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    captured_kwargs = {}

    def mock_start(simulation_id, platform="parallel", max_rounds=None,
                   enable_graph_memory_update=False, graph_id=None,
                   keep_alive_on_completion=False):
        captured_kwargs["keep_alive_on_completion"] = keep_alive_on_completion
        state = SimulationRunState(
            simulation_id=simulation_id,
            runner_status=RunnerStatus.RUNNING,
        )
        return state

    monkeypatch.setattr(SimulationRunner, "start_simulation", mock_start)
    monkeypatch.setattr(simulation_api, "_check_simulation_prepared", lambda _sid: (True, {}))
    monkeypatch.setattr(simulation_api, "_qualification_inputs_are_fresh", lambda _st, _et: (True, "fresh"))

    mock_state = SimpleNamespace(
        simulation_id="sim-api-1",
        project_id="proj-1",
        status=simulation_api.SimulationStatus.READY,
        entity_types=[],
        graph_id=None,
    )
    monkeypatch.setattr(
        simulation_api.SimulationManager,
        "get_simulation",
        lambda self, _sid: mock_state,
    )

    with app.test_request_context(
        "/api/simulation/start",
        method="POST",
        json={"simulation_id": "sim-api-1", "keep_alive_on_completion": True},
    ):
        resp = simulation_api.start_simulation()
        code = resp.status_code if hasattr(resp, "status_code") else resp[1]
        assert code == 200
        assert captured_kwargs.get("keep_alive_on_completion") is True

    # Validation du type booléen
    with app.test_request_context(
        "/api/simulation/start",
        method="POST",
        json={"simulation_id": "sim-api-1", "keep_alive_on_completion": "invalid_string"},
    ):
        resp = simulation_api.start_simulation()
        code = resp.status_code if hasattr(resp, "status_code") else resp[1]
        resp_obj = resp if hasattr(resp, "get_json") else resp[0]
        assert code == 400
        assert "keep_alive_on_completion must be a JSON boolean" in resp_obj.get_json()["error"]


def test_monitor_simulation_respects_keep_alive_on_completion(tmp_path, monkeypatch):
    """Patch BMAD 1: Si keep_alive_on_completion=True, _monitor_simulation n'envoie pas close_env et ne tue pas."""
    sim_id = "sim-keepalive-monitor"
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
    monkeypatch.setattr(SimulationRunner, "_check_all_platforms_completed", classmethod(lambda _cls, _st: True))

    ipc_called = []
    class MockIPCClient:
        def __init__(self, directory):
            pass
        def check_env_alive(self):
            return True
        def send_close_env(self, timeout=3.0):
            ipc_called.append(True)

    monkeypatch.setattr(runner_module, "SimulationIPCClient", MockIPCClient)

    terminate_called = []
    monkeypatch.setattr(
        SimulationRunner,
        "_terminate_process",
        classmethod(lambda *args, **kwargs: terminate_called.append(True)),
    )

    # Processus qui reste en vie 2 itérations puis quitte normalement
    class MockProcess:
        def __init__(self):
            self.polls = [None, None, 0]
            self.returncode = 0
            self.pid = 5555
        def poll(self):
            if self.polls:
                return self.polls.pop(0)
            return 0

    process = MockProcess()
    SimulationRunner._processes[sim_id] = process
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    monkeypatch.setattr(SimulationRunner, "_sync_simulation_status", classmethod(lambda *args, **kwargs: None))

    SimulationRunner._monitor_simulation(sim_id)

    # Le timer de fermeture ne doit pas s'être déclenché
    assert len(ipc_called) == 0
    assert len(terminate_called) == 0
    assert state.runner_status == RunnerStatus.COMPLETED


def test_start_simulation_explicit_false_overrides_config_true(tmp_path, monkeypatch):
    """Patch BMAD 2: Un appel explicite avec keep_alive_on_completion=False surcharge la config True."""
    sim_id = "sim-override-false"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    config_file = sim_dir / "simulation_config.json"
    config_file.write_text(json.dumps({
        "time_config": {"total_simulation_hours": 12, "minutes_per_round": 60},
        "keep_alive_on_completion": True,
    }), encoding="utf-8")

    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(SimulationRunner, "SCRIPTS_DIR", str(tmp_path))
    script_path = tmp_path / "run_parallel_simulation.py"
    script_path.write_text("# dummy", encoding="utf-8")

    spawned_cmds = []

    class MockPopen:
        def __init__(self, cmd, *args, **kwargs):
            spawned_cmds.append(list(cmd))
            self.pid = 44444
            self.returncode = None
        def poll(self):
            return 0

    monkeypatch.setattr(subprocess, "Popen", MockPopen)
    monkeypatch.setattr(SimulationRunner, "_sync_simulation_status", classmethod(lambda *args, **kwargs: None))

    state = SimulationRunner.start_simulation(sim_id, platform="parallel", keep_alive_on_completion=False)

    assert state.keep_alive_on_completion is False
    assert len(spawned_cmds) == 1
    assert "--no-wait" in spawned_cmds[0]


def test_simulation_run_state_serialization_preserves_keep_alive(tmp_path, monkeypatch):
    """Patch BMAD 3: keep_alive_on_completion est sérialisé dans to_dict et restauré par _load_run_state."""
    sim_id = "sim-state-ser"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
        keep_alive_on_completion=True,
    )
    as_dict = state.to_dict()
    assert as_dict["keep_alive_on_completion"] is True

    # Écriture sur disque
    state_file = sim_dir / "run_state.json"
    state_file.write_text(json.dumps(as_dict), encoding="utf-8")

    loaded = SimulationRunner._load_run_state(sim_id)
    assert loaded is not None
    assert loaded.keep_alive_on_completion is True
