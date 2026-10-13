"""Verrous partagés des mutations d'un projet dans le processus applicatif."""

import threading

_locks: dict[str, threading.RLock] = {}
_guard = threading.Lock()


def project_lock(project_id: str) -> threading.RLock:
    """Sérialise construction, remise à zéro et changement de politique."""
    with _guard:
        return _locks.setdefault(project_id, threading.RLock())
