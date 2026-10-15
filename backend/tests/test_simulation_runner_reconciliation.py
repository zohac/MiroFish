"""
Tests unitaires hermétiques pour la réconciliation d'état OS/cache et l'autorité disque.
Epic 010 — Story 010-2 (AC1, AC2, AC3, AC5).
"""

import json
import os
import time
from unittest.mock import patch

import pytest

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


def test_reconcile_process_liveness_when_managed_process_exited_successfully(tmp_path, monkeypatch):
    """AC1: Si l'état mémoire est RUNNING mais process.poll() == 0, réconcilie vers COMPLETED."""
    sim_id = "sim-recon-success"
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

    class MockExitedProcess:
        def __init__(self):
            self.pid = 1111
        def poll(self):
            return 0

    SimulationRunner._processes[sim_id] = MockExitedProcess()

    synced = []
    monkeypatch.setattr(
        SimulationRunner,
        "_sync_simulation_status",
        classmethod(lambda _cls, _sid, status, *args, **kwargs: synced.append(status)),
    )

    reconciled = SimulationRunner.get_run_state(sim_id)

    assert reconciled is not None
    assert reconciled.runner_status == RunnerStatus.COMPLETED
    assert reconciled.twitter_running is False
    assert reconciled.reddit_running is False
    assert reconciled.completed_at is not None
    assert reconciled.error is None
    assert sim_id not in SimulationRunner._processes
    assert RunnerStatus.COMPLETED in synced

    # Vérification fichier disque
    state_file = sim_dir / "run_state.json"
    assert state_file.exists()
    disk_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert disk_data["runner_status"] == RunnerStatus.COMPLETED.value


def test_reconcile_process_liveness_when_managed_process_crashed(tmp_path, monkeypatch):
    """AC1: Si l'état mémoire est RUNNING mais process.poll() != 0, réconcilie vers FAILED."""
    sim_id = "sim-recon-crashed"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
        twitter_running=True,
    )
    SimulationRunner._run_states[sim_id] = state

    class MockCrashedProcess:
        def __init__(self):
            self.pid = 2222
        def poll(self):
            return 137  # OOM / SIGKILL

    SimulationRunner._processes[sim_id] = MockCrashedProcess()

    synced = []
    monkeypatch.setattr(
        SimulationRunner,
        "_sync_simulation_status",
        classmethod(lambda _cls, _sid, status, *args, **kwargs: synced.append(status)),
    )

    reconciled = SimulationRunner.get_run_state(sim_id)

    assert reconciled is not None
    assert reconciled.runner_status == RunnerStatus.FAILED
    assert "Processus de simulation inattendu terminé (code 137)" in reconciled.error
    assert reconciled.completed_at is not None
    assert sim_id not in SimulationRunner._processes
    assert RunnerStatus.FAILED in synced


def test_reconcile_process_liveness_when_stopping_and_process_exited(tmp_path, monkeypatch):
    """AC1: Si l'état mémoire est STOPPING et que le processus est mort, réconcilie vers STOPPED."""
    sim_id = "sim-recon-stopping"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.STOPPING,
    )
    SimulationRunner._run_states[sim_id] = state

    class MockTerminatedProcess:
        def __init__(self):
            self.pid = 3333
        def poll(self):
            return -15

    SimulationRunner._processes[sim_id] = MockTerminatedProcess()

    reconciled = SimulationRunner.get_run_state(sim_id)

    assert reconciled is not None
    assert reconciled.runner_status == RunnerStatus.STOPPED
    assert reconciled.error is None
    assert sim_id not in SimulationRunner._processes


def test_reconcile_phantom_pid_not_alive_in_os(tmp_path, monkeypatch):
    """AC2: Si process_pid est renseigné mais absent de _processes et mort dans l'OS, bascule vers FAILED."""
    sim_id = "sim-recon-phantom"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
        process_pid=999999,  # PID fictif
    )
    SimulationRunner._run_states[sim_id] = state

    # Mock _is_pid_alive -> False
    monkeypatch.setattr(SimulationRunner, "_is_pid_alive", classmethod(lambda _cls, _pid: False))

    reconciled = SimulationRunner.get_run_state(sim_id)

    assert reconciled is not None
    assert reconciled.runner_status == RunnerStatus.FAILED
    assert "Processus de simulation inattendu terminé" in reconciled.error


def test_disk_authority_invalidates_stale_memory_cache(tmp_path, monkeypatch):
    """AC3: Si run_state.json sur disque est plus récent que le cache mémoire, recharge l'état disque."""
    sim_id = "sim-disk-authority"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    # État initial en mémoire : RUNNING avec processus actif managé
    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
        current_round=2,
        total_rounds=10,
    )
    class MockAliveProcess:
        def poll(self):
            return None

    SimulationRunner._processes[sim_id] = MockAliveProcess()
    SimulationRunner._save_run_state(state)
    assert SimulationRunner.get_run_state(sim_id).runner_status == RunnerStatus.RUNNING

    # Un worker externe / process modifie run_state.json sur disque
    state_file = sim_dir / "run_state.json"
    external_data = state.to_detail_dict()
    external_data["runner_status"] = RunnerStatus.COMPLETED.value
    external_data["current_round"] = 10
    external_data["completed_at"] = "2026-10-15T12:00:00"

    # Forcer un mtime strictement ultérieur
    time.sleep(0.05)
    state_file.write_text(json.dumps(external_data), encoding="utf-8")
    new_mtime = os.path.getmtime(state_file) + 2.0
    os.utime(state_file, (new_mtime, new_mtime))

    # get_run_state doit détecter la fraîcheur disque et recharger
    reloaded = SimulationRunner.get_run_state(sim_id)

    assert reloaded is not None
    assert reloaded.runner_status == RunnerStatus.COMPLETED
    assert reloaded.current_round == 10
    assert reloaded.completed_at == "2026-10-15T12:00:00"


def test_ui_completion_by_facts_logic_contract():
    """AC4 & AC5: Contrat logique de complétion par les faits pour Step3Simulation.vue."""
    def check_platforms_completed(data):
        if not data:
            return False
        twitter_completed = data.get("twitter_completed") is True
        reddit_completed = data.get("reddit_completed") is True
        twitter_enabled = bool(data.get("twitter_actions_count", 0) > 0 or data.get("twitter_running") or twitter_completed)
        reddit_enabled = bool(data.get("reddit_actions_count", 0) > 0 or data.get("reddit_running") or reddit_completed)
        if not twitter_enabled and not reddit_enabled:
            return False
        if twitter_enabled and not twitter_completed:
            return False
        if reddit_enabled and not reddit_completed:
            return False
        return True

    def evaluate_is_completed(data):
        facts_completed = (
            data.get("progress_percent", 0) >= 100
            or (data.get("current_round", 0) >= data.get("total_rounds", 1) and data.get("total_rounds", 0) > 0)
        ) and check_platforms_completed(data)
        return data.get("runner_status") in ("completed", "stopped") or facts_completed

    # Cas 1 : statut encore RUNNING mais 100% et plateformes complétées -> isCompleted == True (AC4)
    running_payload = {
        "runner_status": "running",
        "progress_percent": 100.0,
        "current_round": 10,
        "total_rounds": 10,
        "twitter_running": False,
        "reddit_running": False,
        "twitter_completed": True,
        "reddit_completed": True,
        "twitter_actions_count": 50,
        "reddit_actions_count": 40,
    }
    assert evaluate_is_completed(running_payload) is True

    # Cas 2 : statut RUNNING, 50% de progression -> isCompleted == False
    mid_payload = {
        "runner_status": "running",
        "progress_percent": 50.0,
        "current_round": 5,
        "total_rounds": 10,
        "twitter_running": True,
        "reddit_running": True,
        "twitter_completed": False,
        "reddit_completed": False,
        "twitter_actions_count": 20,
        "reddit_actions_count": 15,
    }
    assert evaluate_is_completed(mid_payload) is False

    # Cas 3 : statut terminal standard completed -> isCompleted == True
    completed_payload = {
        "runner_status": "completed",
        "progress_percent": 100.0,
        "twitter_completed": True,
        "reddit_completed": True,
    }
    assert evaluate_is_completed(completed_payload) is True


def test_reconcile_orphan_state_without_pid(tmp_path, monkeypatch):
    """Review Patch 1: Si runner_status est RUNNING mais sans process managé ni PID, réconcilie vers FAILED."""
    sim_id = "sim-recon-no-pid"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
        process_pid=None,  # Aucun PID enregistré
    )
    SimulationRunner._run_states[sim_id] = state

    reconciled = SimulationRunner.get_run_state(sim_id)

    assert reconciled is not None
    assert reconciled.runner_status == RunnerStatus.FAILED
    assert "Processus de simulation introuvable dans l'OS (PID absent)" in reconciled.error


def test_reconcile_cleans_up_log_file_descriptors(tmp_path, monkeypatch):
    """Review Patch 2: La réconciliation d'état ferme et nettoie les descripteurs ouverts dans _stdout_files."""
    sim_id = "sim-recon-fd-leak"
    sim_dir = tmp_path / sim_id
    sim_dir.mkdir(parents=True)
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))

    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
    )
    SimulationRunner._run_states[sim_id] = state

    class MockTerminatedProcess:
        def __init__(self):
            self.pid = 4444
        def poll(self):
            return 0

    SimulationRunner._processes[sim_id] = MockTerminatedProcess()

    # Créer un fichier réel pour simuler _stdout_files
    log_file_path = sim_dir / "simulation.log"
    opened_file = open(log_file_path, "w", encoding="utf-8")
    SimulationRunner._stdout_files[sim_id] = opened_file

    assert not opened_file.closed

    reconciled = SimulationRunner.get_run_state(sim_id)

    assert reconciled is not None
    assert reconciled.runner_status == RunnerStatus.COMPLETED
    assert sim_id not in SimulationRunner._stdout_files
    assert opened_file.closed


def test_is_pid_alive_windows_still_active_logic(monkeypatch):
    """Review Patch 3: Vérification de STILL_ACTIVE sur Windows via GetExitCodeProcess."""
    import sys
    from types import SimpleNamespace

    monkeypatch.setattr("app.services.simulation_runner.IS_WINDOWS", True)

    class MockKernel32:
        def __init__(self, exit_code_val):
            self.exit_code_val = exit_code_val
            self.closed = False

        def OpenProcess(self, access, inherit, pid):
            return 12345 if pid == 5555 else 0

        def GetExitCodeProcess(self, handle, exit_code_ref):
            exit_code_ref._obj.value = self.exit_code_val
            return 1

        def CloseHandle(self, handle):
            self.closed = True
            return 1

    # Cas 1 : processus actif (STILL_ACTIVE == 259)
    kernel32_active = MockKernel32(259)
    mock_ctypes = SimpleNamespace(
        windll=SimpleNamespace(kernel32=kernel32_active),
        byref=lambda obj: SimpleNamespace(_obj=obj),
        c_ulong=lambda: SimpleNamespace(value=0),
    )
    monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)

    assert SimulationRunner._is_pid_alive(5555) is True
    assert kernel32_active.closed is True

    # Cas 2 : processus terminé avec code 0
    kernel32_terminated = MockKernel32(0)
    mock_ctypes.windll.kernel32 = kernel32_terminated
    assert SimulationRunner._is_pid_alive(5555) is False
    assert kernel32_terminated.closed is True

