"""Journal local durable des avertissements de validation ontologique."""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Dict, List, Optional

from ...config import Config
from .base import GraphValidationWarning
from .errors import GraphValidationError

_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _normalize_since(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise GraphValidationError("since doit être une date ISO 8601 avec fuseau")
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GraphValidationError("since doit être une date ISO 8601 avec fuseau") from exc
    if parsed.tzinfo is None:
        raise GraphValidationError("since doit contenir un fuseau horaire")
    return parsed.astimezone(timezone.utc).isoformat()


def _path_for(graph_id: str) -> Path:
    if not isinstance(graph_id, str) or not graph_id.strip():
        raise GraphValidationError("graph_id est requis")
    digest = hashlib.sha256(graph_id.strip().encode("utf-8")).hexdigest()
    return Path(Config.UPLOAD_FOLDER) / "ontology-warnings" / f"{digest}.json"


def append_ontology_warning(warning: GraphValidationWarning) -> None:
    path = _path_for(warning.graph_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_for(path)
    with lock:
        lock_path = path.with_suffix(".lock")
        with lock_path.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                records: List[Dict[str, Any]] = []
                if path.exists():
                    try:
                        records = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as exc:
                        raise GraphValidationError(
                            f"Journal d'avertissements illisible : {path}"
                        ) from exc
                records.append(warning.to_dict())
                records.sort(key=lambda item: item["timestamp"])
                fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        json.dump(records, handle, ensure_ascii=False, indent=2)
                        handle.write("\n")
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(tmp_name, path)
                finally:
                    if os.path.exists(tmp_name):
                        os.unlink(tmp_name)
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def read_ontology_warnings(
    graph_id: str, since: Optional[str] = None
) -> List[GraphValidationWarning]:
    path = _path_for(graph_id)
    normalized_since = _normalize_since(since)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphValidationError(f"Journal d'avertissements illisible : {path}") from exc
    records = []
    for item in payload:
        if item.get("graph_id") != graph_id.strip():
            continue
        if normalized_since is not None:
            timestamp = _normalize_since(item.get("timestamp"))
            if timestamp < normalized_since:
                continue
        records.append(GraphValidationWarning(**item))
    records.sort(key=lambda item: item.timestamp)
    return list(records)
