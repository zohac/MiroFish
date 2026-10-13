"""État durable de l'ontologie réellement appliquée, isolé par store et graphe."""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

from ...config import Config
from .errors import GraphNotFoundError, GraphValidationError


def _path(graph_id: str, backend: str) -> Path:
    if not isinstance(graph_id, str) or not graph_id.strip():
        raise GraphValidationError("graph_id est requis")
    digest = hashlib.sha256(graph_id.strip().encode()).hexdigest()
    return Path(Config.UPLOAD_FOLDER) / "applied-ontologies" / backend / f"{digest}.json"


def read_state(graph_id: str, backend: str):
    """La lecture atomique n'invente jamais une ontologie appliquée."""
    path = _path(graph_id, backend)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphValidationError("État de l'ontologie appliquée illisible") from exc


@contextmanager
def _state_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write(path: Path, state: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".ontology-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_state(graph_id: str, backend: str, ontology: dict, strict: bool) -> None:
    """Publication après application réussie ; aucun accès au projet métier."""
    path = _path(graph_id, backend)
    with _state_lock(path):
        _write(path, {"ontology": ontology, "strict": strict})


def update_policy(graph_id: str, backend: str, strict: bool) -> None:
    """Change seulement la politique, sans réécrire le graphe ni son ontologie."""
    if type(strict) is not bool:
        raise GraphValidationError("strict doit être un booléen")
    path = _path(graph_id, backend)
    with _state_lock(path):
        state = read_state(graph_id, backend)
        if state is None:
            raise GraphNotFoundError(f"Aucune ontologie appliquée au graphe : {graph_id}")
        if state["strict"] != strict:
            _write(path, {**state, "strict": strict})


def delete_state(graph_id: str, backend: str) -> None:
    path = _path(graph_id, backend)
    with _state_lock(path):
        path.unlink(missing_ok=True)
