"""Implémentation GraphitiGraphStore encapsulant Graphiti et Neo4j."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
import concurrent.futures
from contextlib import contextmanager
import logging
import os
from typing import Any, Callable, Dict, List, Optional, TypeVar

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.driver.neo4j_driver import Neo4jDriver

from ...config import Config
from ..graphiti_embedder import SentenceTransformerEmbedder
from ..graphiti_llm_client import MiroFishLLMClient
from ..logger import get_logger
from .base import (
    BatchSubmissionRecord,
    EpisodeRecord,
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphSearchResult,
    GraphStore,
)
from .errors import (
    GraphConnectionError,
    GraphNotFoundError,
    GraphStoreError,
    GraphTimeoutError,
    GraphValidationError,
)

logger = get_logger("mirofish.graph_store.graphiti")

T = TypeVar("T")


class LocalPassthroughCrossEncoder(CrossEncoderClient):
    """Cross-encoder local pass-through évitant tout appel externe ou clé OpenAI (NFR-1)."""

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        """Conserve l'ordre avec un score unitaire décroissant borné dans [0.0, 1.0]."""
        return [(p, max(0.0, 1.0 - (i * 0.001))) for i, p in enumerate(passages)]


class GraphitiGraphStore(GraphStore):
    """Magasin de graphe de connaissances s'appuyant sur Graphiti et Neo4j en local."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        driver: Optional[Any] = None,
        llm_client: Optional[Any] = None,
        embedder: Optional[Any] = None,
        cross_encoder: Optional[Any] = None,
        graphiti: Optional[Any] = None,
    ) -> None:
        """Initialise le magasin GraphitiGraphStore avec injection ou création des dépendances.

        Args:
            uri: URI Bolt Neo4j (ex: bolt://localhost:7687). Si omis, lit NEO4J_URI.
            user: Utilisateur Neo4j (défaut 'neo4j'). Si omis, lit NEO4J_USER.
            password: Mot de passe Neo4j. Si omis, lit NEO4J_PASSWORD.
            driver: Instance personnalisée ou mockée de Neo4jDriver.
            llm_client: Instance personnalisée ou mockée du client LLM (ex: MiroFishLLMClient).
            embedder: Instance personnalisée ou mockée de l'embedder (ex: SentenceTransformerEmbedder).
            cross_encoder: Instance personnalisée ou mockée du cross-encoder (ex: LocalPassthroughCrossEncoder).
            graphiti: Instance personnalisée ou mockée de Graphiti.
        """
        # 1. Enforcer l'interdiction de télémétrie posthog (AGENTS.md, config.py)
        if "GRAPHITI_TELEMETRY_ENABLED" not in os.environ:
            os.environ["GRAPHITI_TELEMETRY_ENABLED"] = (
                "true" if getattr(Config, "GRAPHITI_TELEMETRY_ENABLED", False) else "false"
            )

        # 2. Driver Neo4j
        if driver is not None:
            self._driver = driver
        else:
            resolved_uri = (
                uri
                or os.environ.get("NEO4J_URI")
                or getattr(Config, "NEO4J_URI", "bolt://localhost:7687")
            )
            resolved_user = (
                user
                or os.environ.get("NEO4J_USER")
                or getattr(Config, "NEO4J_USER", "neo4j")
            )
            resolved_password = (
                password
                or os.environ.get("NEO4J_PASSWORD")
                or getattr(Config, "NEO4J_PASSWORD", None)
            )

            if not resolved_password:
                raise GraphValidationError(
                    "NEO4J_PASSWORD est requis pour initialiser la connexion Neo4j dans GraphitiGraphStore. "
                    "Définissez-le dans votre fichier .env ou passez-le explicitement."
                )

            try:
                self._driver = Neo4jDriver(
                    uri=resolved_uri,
                    user=resolved_user,
                    password=resolved_password,
                )
            except Exception as exc:
                raise self._translate_error(exc, "initialisation du driver Neo4j") from exc

        # 3. Client LLM
        self._llm_client = llm_client if llm_client is not None else MiroFishLLMClient()

        # 4. Embedder
        self._embedder = (
            embedder if embedder is not None else SentenceTransformerEmbedder()
        )

        # 5. Cross-Encoder
        self._cross_encoder = (
            cross_encoder if cross_encoder is not None else LocalPassthroughCrossEncoder()
        )

        # 6. Instance Graphiti
        if graphiti is not None:
            self._graphiti = graphiti
        else:
            try:
                self._graphiti = Graphiti(
                    graph_driver=self._driver,
                    llm_client=self._llm_client,
                    embedder=self._embedder,
                    cross_encoder=self._cross_encoder,
                )
            except Exception as exc:
                raise self._translate_error(exc, "initialisation du moteur Graphiti") from exc

    @staticmethod
    def _translate_error(error: Exception, operation_name: str) -> GraphStoreError:
        """Traduit une exception Graphiti, Neo4j ou système vers la hiérarchie GraphStoreError."""
        if isinstance(error, GraphStoreError):
            return error

        err_type = type(error).__name__
        err_msg = str(error)

        if "AuthError" in err_type or "AuthenticationRateLimit" in err_type:
            return GraphConnectionError(
                f"Échec d'authentification Neo4j lors de {operation_name}: {err_msg}"
            )

        if "RateLimit" in err_type:
            return GraphConnectionError(
                f"Limite de requêtes atteinte (RateLimit) lors de {operation_name}: {err_msg}"
            )

        if any(
            conn_err in err_type
            for conn_err in (
                "ServiceUnavailable",
                "SessionExpired",
                "DriverError",
                "ConnectError",
                "NetworkError",
                "ConnectionError",
            )
        ):
            return GraphConnectionError(
                f"Échec de connexion Neo4j lors de {operation_name}: {err_msg}"
            )

        if isinstance(error, (TimeoutError, asyncio.TimeoutError)) or "Timeout" in err_type:
            return GraphTimeoutError(
                f"Délai d'attente dépassé lors de {operation_name}: {err_msg}"
            )

        if isinstance(error, (ValueError, TypeError)):
            return GraphValidationError(
                f"Paramètre invalide lors de {operation_name}: {err_msg}"
            )

        return GraphStoreError(f"Erreur inattendue lors de {operation_name}: {err_msg}")

    @contextmanager
    def _translate_errors(self, operation_name: str):
        """Gestionnaire de contexte traduisant systématiquement toutes les erreurs."""
        try:
            yield
        except Exception as exc:
            raise self._translate_error(exc, operation_name) from exc

    def _run_async(self, coro: Coroutine[Any, Any, T]) -> T:
        """Exécute une coroutine asynchrone de manière thread-safe et synchrone.

        Gère les cas sans boucle active (création via asyncio.run) ainsi que
        les cas sous boucle d'événements déjà active (délégation dans un ThreadPoolExecutor).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return asyncio.run(coro)

    # --- Propriétés de dépendances internes (utiles pour introspection et tests) ---

    @property
    def driver(self) -> Any:
        """Driver Neo4j sous-jacent."""
        return self._driver

    @property
    def llm_client(self) -> Any:
        """Client LLM sous-jacent."""
        return self._llm_client

    @property
    def embedder(self) -> Any:
        """Embedder sous-jacent."""
        return self._embedder

    @property
    def cross_encoder(self) -> Any:
        """Cross-encoder sous-jacent."""
        return self._cross_encoder

    @property
    def graphiti(self) -> Any:
        """Instance Graphiti sous-jacente."""
        return self._graphiti

    # --- Cycle de vie ---

    def create_graph(self, name: str, graph_id: Optional[str] = None) -> str:
        """Crée un graphe et retourne son identifiant durable.

        Note: L'implémentation complète fait l'objet de la Story 003-2.
        """
        if not name or not name.strip():
            raise GraphValidationError("Le nom du graphe ne peut pas être vide")
        if graph_id is not None and not graph_id.strip():
            raise GraphValidationError("graph_id ne peut pas être une chaîne vide")
        raise NotImplementedError(
            "create_graph pour GraphitiGraphStore fait l'objet de la Story 003-2."
        )

    def delete_graph(self, graph_id: str) -> None:
        """Supprime un graphe et l'ensemble de ses données associées.

        Note: L'implémentation complète fait l'objet de la Story 003-2.
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        raise NotImplementedError(
            "delete_graph pour GraphitiGraphStore fait l'objet de la Story 003-2."
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """Retourne les nœuds, arêtes et statistiques complètes du graphe pour l'API.

        Note: L'implémentation complète fait l'objet de la Story 003-3.
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        raise NotImplementedError(
            "get_graph_data pour GraphitiGraphStore fait l'objet de la Story 003-3."
        )

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        """Retourne un résumé synthétique (comptages et types d'entités).

        Note: L'implémentation complète fait l'objet de la Story 003-3.
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        raise NotImplementedError(
            "get_graph_info pour GraphitiGraphStore fait l'objet de la Story 003-3."
        )

    # --- Ontologie ---

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        """Définit ou synchronise l'ontologie des types d'entités du graphe (no-op en v1, ADR 0003).

        Note: L'implémentation complète fait l'objet de la Story 003-2.
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not isinstance(ontology, dict):
            raise GraphValidationError("L'ontologie doit être un dictionnaire")
        raise NotImplementedError(
            "set_ontology pour GraphitiGraphStore fait l'objet de la Story 003-2."
        )

    # --- Ingestion et épisodes ---

    def add_episode(
        self,
        graph_id: str,
        text: str,
        source_description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> EpisodeRecord:
        """Ajoute un épisode textuel unitaire au graphe.

        Note: L'implémentation complète fait l'objet de la Story 003-2.
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not text or not text.strip():
            raise GraphValidationError("Le contenu textuel de l'épisode est requis")
        raise NotImplementedError(
            "add_episode pour GraphitiGraphStore fait l'objet de la Story 003-2."
        )

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> BatchSubmissionRecord:
        """Ingère une liste de textes découpés par lots.

        Note: L'implémentation complète fait l'objet de la Story 003-2.
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not chunks:
            raise GraphValidationError("Au moins un fragment de texte est requis")
        if not isinstance(batch_size, int) or batch_size <= 0:
            raise GraphValidationError("batch_size doit être un entier strictement positif")
        raise NotImplementedError(
            "add_text_batch pour GraphitiGraphStore fait l'objet de la Story 003-2."
        )

    def wait_for_batch(
        self,
        batch: BatchSubmissionRecord,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        timeout: float = 600.0,
    ) -> bool:
        """Attend la fin du traitement asynchrone d'un lot d'ingestion.

        Note: L'implémentation complète fait l'objet de la Story 003-2.
        """
        if not batch or not getattr(batch, "batch_id", None):
            raise GraphValidationError("batch et batch_id sont requis")
        raise NotImplementedError(
            "wait_for_batch pour GraphitiGraphStore fait l'objet de la Story 003-2."
        )

    def wait_for_episodes(
        self,
        graph_id: str,
        episode_uuids: List[str],
        timeout: float = 600.0,
    ) -> bool:
        """Attend la fin du traitement pour une liste explicite d'épisodes.

        Note: L'implémentation complète fait l'objet de la Story 003-2.
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        raise NotImplementedError(
            "wait_for_episodes pour GraphitiGraphStore fait l'objet de la Story 003-2."
        )

    # --- Lecture et parcours ---

    def get_all_nodes(self, graph_id: str) -> List[GraphNode]:
        """Récupère tous les nœuds d'un graphe.

        Note: L'implémentation complète fait l'objet de la Story 003-3.
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        raise NotImplementedError(
            "get_all_nodes pour GraphitiGraphStore fait l'objet de la Story 003-3."
        )

    def get_all_edges(
        self, graph_id: str, include_temporal: bool = True
    ) -> List[GraphEdge]:
        """Récupère toutes les arêtes d'un graphe avec ou sans champs temporels.

        Note: L'implémentation complète fait l'objet de la Story 003-3.
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        raise NotImplementedError(
            "get_all_edges pour GraphitiGraphStore fait l'objet de la Story 003-3."
        )

    def get_node(self, graph_id: str, node_uuid: str) -> Optional[GraphNode]:
        """Récupère un nœud spécifique par son identifiant unique.

        Note: L'implémentation complète fait l'objet de la Story 003-3.
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not node_uuid or not node_uuid.strip():
            raise GraphValidationError("node_uuid est requis")
        raise NotImplementedError(
            "get_node pour GraphitiGraphStore fait l'objet de la Story 003-3."
        )

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[GraphEdge]:
        """Récupère toutes les arêtes connectées à un nœud (entrantes et sortantes).

        Note: L'implémentation complète fait l'objet de la Story 003-3.
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not node_uuid or not node_uuid.strip():
            raise GraphValidationError("node_uuid est requis")
        raise NotImplementedError(
            "get_node_edges pour GraphitiGraphStore fait l'objet de la Story 003-3."
        )

    # --- Recherche ---

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
        reranker: Optional[str] = None,
    ) -> GraphSearchResult:
        """Effectue une recherche sémantique / hybride sur les arêtes ou les nœuds.

        Note: L'implémentation complète fait l'objet de la Story 003-3.
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not query or not query.strip():
            raise GraphValidationError("Le texte de recherche query est requis")
        if not isinstance(limit, int) or limit <= 0:
            raise GraphValidationError("limit doit être un entier strictement positif")
        if scope not in ("edges", "nodes", "hybrid"):
            raise GraphValidationError(
                f"Périmètre de recherche invalide : '{scope}'. Valeurs acceptées : 'edges', 'nodes', 'hybrid'."
            )
        raise NotImplementedError(
            "search pour GraphitiGraphStore fait l'objet de la Story 003-3."
        )
