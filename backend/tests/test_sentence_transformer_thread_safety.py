"""Tests unitaires hermétiques pour la Story 010-3.

Thread-safety de SentenceTransformerEmbedder et drain mémoire résilient dans ZepGraphMemoryUpdater.
Conformément à AGENTS.md :
- Pas d'accès réseau réel.
- Tests hermétiques reproductibles.
- Validation des critères d'acceptation AC1 à AC6.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.services.simulation_runner import (
    RunnerStatus,
    SimulationRunState,
    SimulationRunner,
)
from app.services.zep_graph_memory_updater import (
    AgentActivity,
    ZepGraphMemoryManager,
    ZepGraphMemoryUpdater,
)
from app.utils.graphiti_embedder import (
    SentenceTransformerEmbedder,
    SentenceTransformerEmbedderConfig,
)


class ConcurrencyCheckingSentenceTransformer:
    """Modèle factice qui vérifie qu'aucun appel concurrent n'entre dans encode()."""

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.active_calls = 0
        self.max_concurrent_calls = 0
        self.total_calls = 0
        self._lock = threading.Lock()

    def encode(
        self,
        texts: List[str],
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
    ) -> np.ndarray:
        with self._lock:
            self.active_calls += 1
            if self.active_calls > self.max_concurrent_calls:
                self.max_concurrent_calls = self.active_calls
            self.total_calls += 1

        # Petite pause pour maximiser le risque de collision en l'absence de verrou externe
        time.sleep(0.01)

        with self._lock:
            self.active_calls -= 1

        arrays = [np.full((self.dim,), 0.1, dtype=np.float32) for _ in texts]
        return np.array(arrays)


@pytest.mark.asyncio
async def test_sentence_transformer_thread_safety_under_concurrent_load():
    """AC1: L'appel à model.encode est sérialisé sous self._lock sans chevauchement concurrent."""
    model = ConcurrencyCheckingSentenceTransformer()
    embedder = SentenceTransformerEmbedder(
        config=SentenceTransformerEmbedderConfig(embedding_dim=384),
        model=model,
    )

    # Lancer 20 requêtes concurrentes via asyncio.gather (chacune sur un thread du pool)
    tasks = [
        embedder.create(f"Test sentence number {i}")
        for i in range(20)
    ]
    results = await asyncio.gather(*tasks)

    # 1. Toutes les requêtes doivent avoir abouti
    assert len(results) == 20
    for res in results:
        assert len(res) == 384
        assert pytest.approx(res[0], 0.01) == 0.1

    # 2. Le modèle n'a JAMAIS dû être exécuté de manière concurrente
    assert model.total_calls == 20
    assert model.max_concurrent_calls == 1, (
        f"Concurrence non protégée détectée : {model.max_concurrent_calls} appels simultanés dans model.encode"
    )


def test_sentence_transformer_thread_pool_executor_concurrency():
    """AC1: Sérialisation thread-safe directe sous forte charge multi-threads ThreadPoolExecutor."""
    model = ConcurrencyCheckingSentenceTransformer()
    embedder = SentenceTransformerEmbedder(
        config=SentenceTransformerEmbedderConfig(embedding_dim=384),
        model=model,
    )

    def worker(idx: int) -> List[List[float]]:
        return embedder._encode_sync([f"Text {idx}a", f"Text {idx}b"])

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(worker, i) for i in range(15)]
        results = [f.result() for f in futures]

    assert len(results) == 15
    for batch_res in results:
        assert len(batch_res) == 2
        assert len(batch_res[0]) == 384

    assert model.total_calls == 15
    assert model.max_concurrent_calls == 1


def test_updater_stop_resilient_mode_tolerates_failed_batches(monkeypatch):
    """AC2: stop(strict=False) consigne un avertissement sans lever RuntimeError sur les lots échoués."""
    updater = ZepGraphMemoryUpdater("graph-test")
    updater._worker_thread = None  # Non démarré
    updater._failed_batches.append({
        "platform": "twitter",
        "activities": [],
        "error": "PyTorch tensor error",
    })
    updater._failed_count = 1

    # Ne doit pas lever RuntimeError
    updater.stop(strict=False)

    stats = updater.get_stats()
    assert stats["failed_count"] == 1
    assert stats["failed_batches_count"] == 1


def test_updater_stop_strict_mode_raises_runtime_error():
    """AC4: stop(strict=True) ou stop() lève RuntimeError si des lots ont échoué."""
    updater = ZepGraphMemoryUpdater("graph-test-strict")
    updater._worker_thread = None
    updater._failed_batches.append({
        "platform": "reddit",
        "activities": [],
        "error": "Batch error",
    })

    # Mode explicite strict=True
    with pytest.raises(RuntimeError, match="simulation graph ingestion is incomplete"):
        updater.stop(strict=True)

    # Mode par défaut sans argument (strict=True)
    with pytest.raises(RuntimeError, match="simulation graph ingestion is incomplete"):
        updater.stop()


def test_manager_stop_updater_resilient_mode_and_cleanup():
    """AC2, AC5: ZepGraphMemoryManager.stop_updater utilise strict=False et nettoie les updaters."""
    sim_id = "sim-manager-resilient"
    updater = ZepGraphMemoryUpdater("graph-resilient")
    updater._worker_thread = None
    updater._failed_batches.append({
        "platform": "twitter",
        "activities": [],
        "error": "Batch error",
    })
    updater._failed_count = 3

    ZepGraphMemoryManager._updaters[sim_id] = updater
    try:
        # Doit réussir en mode résilient et retourner les stats
        stats = ZepGraphMemoryManager.stop_updater(sim_id)
        assert stats is not None
        assert stats["failed_count"] == 3
        assert stats["failed_batches_count"] == 1

        # L'updater doit être désenregistré
        assert sim_id not in ZepGraphMemoryManager._updaters
    finally:
        ZepGraphMemoryManager._updaters.pop(sim_id, None)


def test_manager_stop_updater_strict_mode_cleans_up_on_exception():
    """AC4, AC5: Même en cas d'exception sous strict=True, l'updater est désenregistré via finally."""
    sim_id = "sim-manager-strict-cleanup"
    updater = ZepGraphMemoryUpdater("graph-strict-cleanup")
    updater._worker_thread = None
    updater._failed_batches.append({
        "platform": "twitter",
        "activities": [],
        "error": "Fatal batch error",
    })

    ZepGraphMemoryManager._updaters[sim_id] = updater
    try:
        with pytest.raises(RuntimeError, match="simulation graph ingestion is incomplete"):
            ZepGraphMemoryManager.stop_updater(sim_id, strict=True)

        # Doit quand même être retiré du manager malgré l'exception
        assert sim_id not in ZepGraphMemoryManager._updaters
    finally:
        ZepGraphMemoryManager._updaters.pop(sim_id, None)


def test_simulation_runner_monitor_tolerates_failed_batches_and_completes(monkeypatch, tmp_path):
    """AC3: _monitor_simulation bascule en COMPLETED avec journalisation même si des lots ont échoué."""
    sim_id = "sim-drain-resilient"
    state = SimulationRunState(
        simulation_id=sim_id,
        runner_status=RunnerStatus.RUNNING,
        twitter_running=True,
        reddit_running=True,
    )

    monkeypatch.setattr(SimulationRunner, "get_run_state", classmethod(lambda _cls, _sid, **_kwargs: state))
    saved_states = []
    monkeypatch.setattr(SimulationRunner, "_save_run_state", classmethod(lambda _cls, s: saved_states.append(s)))
    monkeypatch.setattr(SimulationRunner, "_sync_simulation_status", classmethod(lambda *args, **kwargs: None))

    # Mock un updater avec échecs partiels mais arrêt réussi en résilient
    stats_with_failures = {
        "graph_id": "graph-resilient-sim",
        "total_activities": 10,
        "batches_sent": 8,
        "items_sent": 8,
        "failed_count": 2,
        "failed_batches_count": 1,
    }
    monkeypatch.setattr(
        ZepGraphMemoryManager,
        "stop_updater",
        classmethod(lambda _cls, _sid, strict=False: stats_with_failures),
    )

    class MockProcess:
        def __init__(self):
            self.returncode = 0
            self.pid = 9999
        def poll(self):
            return 0

    SimulationRunner._processes[sim_id] = MockProcess()
    SimulationRunner._graph_memory_enabled[sim_id] = True

    try:
        SimulationRunner._monitor_simulation(sim_id)

        # La simulation doit s'achever en COMPLETED malgré les 2 échecs partiels
        assert state.runner_status == RunnerStatus.COMPLETED
        assert state.completed_at is not None
        assert state.error is None
    finally:
        SimulationRunner._processes.pop(sim_id, None)
        SimulationRunner._graph_memory_enabled.pop(sim_id, None)
        SimulationRunner._manual_stop_requests.discard(sim_id)
