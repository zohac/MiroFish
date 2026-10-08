"""Factory pour l'instanciation unifiée du GraphStore selon la configuration."""

from contextlib import contextmanager
import os
from typing import Iterator, Optional

from app.config import Config

from .base import GraphStore
from .errors import GraphValidationError
from .graphiti_store import GraphitiGraphStore
from .zep_store import ZepGraphStore

_store_override: Optional[GraphStore] = None


def set_graph_store_override(store: Optional[GraphStore]) -> None:
    """Permet aux tests unitaires d'injecter un faux store en mémoire ou de réinitialiser l'override."""
    if store is not None and not isinstance(store, GraphStore):
        raise TypeError(
            f"Le store de remplacement doit hériter de GraphStore ou valoir None, reçu : {type(store).__name__}"
        )
    global _store_override
    _store_override = store


@contextmanager
def override_graph_store(store: Optional[GraphStore]) -> Iterator[Optional[GraphStore]]:
    """Gestionnaire de contexte pour isoler l'injection temporaire d'un store pendant un test."""
    old_override = _store_override
    set_graph_store_override(store)
    try:
        yield store
    finally:
        set_graph_store_override(old_override)


def get_graph_store(
    backend: Optional[str] = None,
    api_key: Optional[str] = None,
) -> GraphStore:
    """Retourne l'instance concrète du GraphStore configuré.

    Priorité de résolution :
    1. Override actif (si configuré via set_graph_store_override / override_graph_store)
    2. Paramètre explicite `backend`
    3. Configuration Flask `Config.ZEP_BACKEND`
    4. Variable d'environnement `ZEP_BACKEND`
    5. Défaut : 'cloud'
    """
    if _store_override is not None:
        return _store_override

    if backend is not None:
        raw_backend = backend
    elif getattr(Config, "ZEP_BACKEND", None) is not None:
        raw_backend = Config.ZEP_BACKEND
    elif "ZEP_BACKEND" in os.environ:
        raw_backend = os.environ["ZEP_BACKEND"]
    else:
        raw_backend = "cloud"

    if not isinstance(raw_backend, str) or not raw_backend.strip():
        raise GraphValidationError(
            f"Backend de graphe invalide : '{raw_backend}'. Valeurs autorisées : 'cloud', 'graphiti'."
        )

    selected_backend = raw_backend.lower().strip()
    normalized_api_key = api_key.strip() if isinstance(api_key, str) else api_key

    if selected_backend == "cloud":
        return ZepGraphStore(api_key=normalized_api_key)
    elif selected_backend == "graphiti":
        return GraphitiGraphStore()
    else:
        raise GraphValidationError(
            f"Backend de graphe non supporté : '{selected_backend}'. Valeurs autorisées : 'cloud', 'graphiti'."
        )
