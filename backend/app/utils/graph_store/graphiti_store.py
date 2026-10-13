"""Implémentation GraphitiGraphStore encapsulant Graphiti et Neo4j."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
import concurrent.futures
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import inspect
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar
import uuid

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.nodes import EpisodeType
from pydantic import BaseModel

from ...config import Config
from ..graphiti_embedder import SentenceTransformerEmbedder
from ..graphiti_llm_client import MiroFishLLMClient
from ..logger import get_logger
from .ontology_state import read_state, write_state, update_policy, delete_state
from .base import (
    AppliedOntology,
    BatchSubmissionRecord,
    EpisodeRecord,
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphSearchResult,
    GraphStore,
    GraphValidationWarning,
    ProvenanceOrigin,
    ProvenanceRecord,
    validate_chunk_metadata,
    FORBIDDEN_ANNOTATION_KEYS,
    _ANNOTATION_KEY_PATTERN,
)
from .errors import (
    GraphConnectionError,
    GraphNotFoundError,
    GraphStoreError,
    GraphTimeoutError,
    GraphValidationError,
)
from .ontology_pydantic import OntologyToPydantic

logger = get_logger("mirofish.graph_store.graphiti")

T = TypeVar("T")


@dataclass(frozen=True)
class _OntologyTraduite:
    """Ontologie en vigueur sur un graphe, avec ses classes Pydantic.

    Les classes sont **construites à la pose** et réutilisées telles quelles à
    chaque ingestion : les retraduire par fragment les rendrait dépendantes de
    l'ordre d'écriture, et une ontologie invalide échouerait au milieu d'un lot
    (ADR 0014, alternative « traduire à chaque ingestion »).
    """

    entity_types: Dict[str, type[BaseModel]]
    edge_types: Dict[str, type[BaseModel]]
    neutre: AppliedOntology


class LocalPassthroughCrossEncoder(CrossEncoderClient):
    """Cross-encoder local pass-through évitant tout appel externe ou clé OpenAI (NFR-1)."""

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        """Conserve l'ordre avec un score unitaire décroissant borné dans [0.0, 1.0]."""
        return [(p, max(0.0, 1.0 - (i * 0.001))) for i, p in enumerate(passages)]


class _ValidatingLLMClient:
    """Proxy du client LLM utilisé directement par les helpers Graphiti."""

    def __init__(self, client: Any, validator: Callable[..., Dict[str, Any]], group_id: str) -> None:
        self._client = client
        self._validator = validator
        self._group_id = group_id

    async def generate_response(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        response = await self._client.generate_response(*args, **kwargs)
        response_model = kwargs.get("response_model")
        if response_model is None and len(args) >= 2:
            response_model = args[1]
        return self._validator(response, response_model, self._group_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class _ValidatingClients:
    """Vue par requête des clients Graphiti avec contrôle de l'extraction brute."""

    def __init__(self, clients: Any, validator: Callable[..., Dict[str, Any]], group_id: str) -> None:
        self._clients = clients
        self._validator = validator
        self.llm_client = _ValidatingLLMClient(clients.llm_client, validator, group_id)

    async def generate_response(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        response = await self._clients.generate_response(*args, **kwargs)
        response_model = kwargs.get("response_model")
        if response_model is None and len(args) >= 2:
            response_model = args[1]
        group_id = kwargs.get("group_id")
        return self._validator(response, response_model, group_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._clients, name)


class _DowngradingSession:
    """Retire les anciens labels dans la transaction de sauvegarde du moteur."""

    def __init__(self, session: Any, graph_id: str, node_ids: list[str]) -> None:
        self._session = session
        self._graph_id = graph_id
        self._node_ids = node_ids

    async def execute_write(self, callback: Any, *args: Any, **kwargs: Any):
        async def write(tx):
            await tx.run(
                "MATCH (n:Entity {group_id: $graph_id}) "
                "WHERE n.uuid IN $node_ids "
                "REMOVE n:$(labels(n)) SET n:Entity",
                graph_id=self._graph_id, node_ids=self._node_ids,
            )
            return await callback(tx, *args, **kwargs)
        return await self._session.execute_write(write)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


class _DowngradingDriver:
    def __init__(self, driver: Any, graph_id: str, node_ids: list[str]) -> None:
        self._driver = driver
        self._graph_id = graph_id
        self._node_ids = node_ids

    def session(self, *args: Any, **kwargs: Any):
        return _DowngradingSession(self._driver.session(*args, **kwargs), self._graph_id, self._node_ids)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._driver, name)


class _PersistenceClients:
    def __init__(self, clients: Any, driver: Any) -> None:
        self._clients = clients
        self.driver = driver

    def __getattr__(self, name: str) -> Any:
        return getattr(self._clients, name)


class _OntologyValidatingGraphiti(Graphiti):
    """Graphiti avec frontières de validation avant `add_nodes_and_edges_bulk`."""

    def __init__(
        self,
        *,
        ontology_resolver: Callable[[str], Optional[_OntologyTraduite]],
        warning_callback: Callable[..., None],
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._ontology_resolver = ontology_resolver
        self._warning_callback = warning_callback
        self._request_ontology: ContextVar[Optional[_OntologyTraduite]] = ContextVar(
            "mirofish_request_ontology", default=None
        )

    async def add_episode(self, *args: Any, **kwargs: Any):
        request_ontology = kwargs.pop("_mirofish_ontology_validation", None)
        token = self._request_ontology.set(request_ontology)
        try:
            return await super().add_episode(*args, **kwargs)
        finally:
            self._request_ontology.reset(token)

    def _resolve_request_scope(self, group_id: Optional[str]):
        resolved_group, driver, clients = super()._resolve_request_scope(group_id)
        return resolved_group, driver, _ValidatingClients(clients, self._validate_response, resolved_group)

    def _effective_ontology(self, group_id: str) -> Optional[_OntologyTraduite]:
        request_ontology = getattr(self, "_request_ontology", None)
        return (request_ontology.get() if request_ontology is not None else None) or self._ontology_resolver(group_id)

    def _validate_response(
        self, response: Dict[str, Any], response_model: Any, group_id: Optional[str]
    ) -> Dict[str, Any]:
        if response_model is None or getattr(response_model, "__name__", "") != "ExtractedEntities":
            return response
        if not group_id:
            return response
        applied = self._effective_ontology(group_id)
        if applied is None or not applied.entity_types:
            return response

        allowed_count = len(applied.entity_types)
        extracted = response.get("extracted_entities")
        if not isinstance(extracted, list):
            raise GraphValidationError(
                f"Réponse ExtractedEntities invalide pour le graphe {group_id}"
            )
        normalized = dict(response)
        normalized["extracted_entities"] = [dict(item) for item in extracted]
        for item in normalized["extracted_entities"]:
            type_id = item.get("entity_type_id")
            if isinstance(type_id, bool) or not isinstance(type_id, int):
                raise GraphValidationError(
                    f"Type extrait invalide pour le graphe {group_id} : {type_id!r}"
                )
            if 1 <= type_id <= allowed_count:
                continue
            attempted = "Entity" if type_id == 0 else f"id={type_id}"
            message = (
                f"Type extrait hors ontologie pour le graphe {group_id} : {attempted}"
            )
            if applied.neutre.strict:
                raise GraphValidationError(message)
            self._warning_callback(
                group_id,
                attempted,
                None,
                "Graphiti.extract_nodes",
                message,
                "downgrade",
            )
            item["entity_type_id"] = 0
        return normalized

    async def _process_episode_data(self, *args: Any, **kwargs: Any):
        bound = inspect.signature(Graphiti._process_episode_data).bind(self, *args, **kwargs)
        nodes = bound.arguments["nodes"]
        group_id = bound.arguments["group_id"]
        applied = self._effective_ontology(group_id)
        downgraded_ids = []
        if applied is not None and applied.entity_types:
            allowed = set(applied.entity_types)
            technical = {"Entity", "Node"}
            for node in nodes:
                custom = list(dict.fromkeys(label for label in node.labels if label not in technical))
                unknown = [label for label in custom if label not in allowed]
                contradictory = len(custom) > 1
                generic = not custom
                invalid_attribute = generic and any(
                    node.attributes.get(key) not in (None, "", "Entity", "Node")
                    for key in ("entity_type", "type", "category")
                )
                invalid = unknown or contradictory or invalid_attribute
                if invalid or (generic and applied.neutre.strict):
                    attempted = ", ".join(custom) if custom else str(
                        node.attributes.get("entity_type") or node.attributes.get("type")
                        or node.attributes.get("category") or "Entity"
                    )
                    message = f"Type final hors ontologie ou contradictoire pour le graphe {group_id} : {attempted}"
                    if applied.neutre.strict:
                        raise GraphValidationError(message)
                    self._warning_callback(
                        group_id, attempted, node.uuid,
                        "Graphiti._process_episode_data", message, "downgrade",
                    )
                if invalid or generic:
                    node.labels = ["Entity"]
                    for key in ("entity_type", "type", "category"):
                        node.attributes.pop(key, None)
                    downgraded_ids.append(node.uuid)
        if downgraded_ids:
            clients = bound.arguments.get("clients") or self.clients
            bound.arguments["clients"] = _PersistenceClients(
                clients, _DowngradingDriver(clients.driver, group_id, downgraded_ids)
            )
        return await super()._process_episode_data(*bound.args[1:], **bound.kwargs)



class _AsyncLoopRunner:
    """Runner maintenant un event loop asyncio dédié dans un thread d'arrière-plan pour isoler les drivers asynchrones."""

    def __init__(self) -> None:
        import threading

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="GraphitiAsyncLoopRunner",
        )
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    def run(self, coro: Any) -> Any:
        if not inspect.isawaitable(coro):
            return coro
        if not self._loop.is_running():
            if inspect.iscoroutine(coro):
                coro.close()
            raise RuntimeError("Event loop is stopped or closed")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def stop(self) -> None:
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=1.0)


class GraphitiGraphStore(GraphStore):
    """Magasin de graphe de connaissances s'appuyant sur Graphiti et Neo4j en local."""

    supports_pre_persistence_ontology_validation = True

    # Clés réservées Neo4j / Graphiti à exclure des dictionnaires attributes (Patch 1)
    _NODE_SYSTEM_KEYS = {
        "uuid",
        "name",
        "name_embedding",
        "summary",
        "group_id",
        "created_at",
        "labels",
        "reference_time",
    }
    _EDGE_SYSTEM_KEYS = {
        "uuid",
        "source_uuid",
        "target_uuid",
        "source_node_uuid",
        "target_node_uuid",
        "name",
        "fact",
        "fact_type",
        "fact_embedding",
        "group_id",
        "episodes",
        "created_at",
        "valid_at",
        "invalid_at",
        "expired_at",
        "relation_type",
        "reference_time",
    }

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
        self._async_runner = _AsyncLoopRunner()
        self._owns_driver = driver is None
        self._closed = False

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

        # Ontologies effectivement posées, par `graph_id` (ADR 0014 §2).
        self._applied_ontologies: Dict[str, _OntologyTraduite] = {}
        self._ontology_states: Dict[str, Dict[str, Any]] = {}

        # 6. Instance Graphiti
        if graphiti is not None:
            self._graphiti = graphiti
        else:
            try:
                graphiti_kwargs = {
                    "graph_driver": self._driver,
                    "llm_client": self._llm_client,
                    "embedder": self._embedder,
                    "cross_encoder": self._cross_encoder,
                }
                if isinstance(Graphiti, type):
                    self._graphiti = _OntologyValidatingGraphiti(
                        **graphiti_kwargs,
                        ontology_resolver=lambda graph_id: self._applied_ontologies.get(graph_id),
                        warning_callback=self._record_warning,
                    )
                else:
                    self._graphiti = Graphiti(**graphiti_kwargs)
            except Exception as exc:
                raise self._translate_error(exc, "initialisation du moteur Graphiti") from exc

    def _record_warning(
        self,
        graph_id: str,
        attempted_type: str,
        node_uuid: Optional[str],
        source_call: str,
        message: str,
        policy: str,
    ) -> None:
        warning = GraphValidationWarning(
            graph_id=graph_id,
            attempted_type=attempted_type,
            node_uuid=node_uuid,
            source_call=source_call,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            policy=policy,
        )
        self._record_ontology_warning(warning)
        logger.warning(message)

    def close(self) -> None:
        """Ferme le driver possédé et le runner ; une dépendance injectée reste empruntée."""
        if getattr(self, "_closed", False):
            return
        self._closed = True
        try:
            if getattr(self, "_owns_driver", False) and hasattr(self, "_driver"):
                self._run_async(self._driver.close())
        finally:
            if hasattr(self, "_async_runner"):
                self._async_runner.stop()

    def __del__(self) -> None:
        """Nettoyage défensif lors du ramasse-miettes."""
        try:
            self.close()
        except Exception:
            pass

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

    def _run_async(self, coro: Any) -> Any:
        """Exécute une coroutine asynchrone de manière thread-safe et synchrone.

        Toutes les coroutines s'exécutent sur la boucle d'événements dédiée de l'instance,
        garantissant la stabilité du pool de connexions du driver Neo4j asynchrone.
        """
        if not inspect.isawaitable(coro):
            return coro

        try:
            return self._async_runner.run(coro)
        except Exception:
            if inspect.iscoroutine(coro):
                coro.close()
            raise

    async def _execute_cypher(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Exécute une requête Cypher via le driver en gérant l'asynchronisme de manière transparente."""
        res = self._driver.execute_query(query, params=params or {})
        if inspect.isawaitable(res):
            return await res
        return res

    async def _check_connection(self) -> None:
        """Contrôle la connectivité active vers Neo4j."""
        if hasattr(self._driver, "health_check"):
            res = self._driver.health_check()
            if inspect.isawaitable(res):
                await res
        elif hasattr(self._driver, "execute_query"):
            await self._execute_cypher("RETURN 1 AS ping")

    @staticmethod
    def _extract_records(res: Any) -> List[Any]:
        """Extrait la liste des enregistrements quel que soit le format renvoyé par le driver."""
        if res is None:
            return []
        if hasattr(res, "records"):
            return list(res.records)
        if isinstance(res, tuple) and len(res) >= 1 and isinstance(res[0], (list, tuple)):
            return list(res[0])
        if isinstance(res, list):
            return res
        return []

    @staticmethod
    def _get_record_field(record: Any, field_name: str, default: Any = None) -> Any:
        """Extrait un champ depuis un enregistrement Neo4j, dict ou mock."""
        if isinstance(record, dict):
            return record.get(field_name, default)
        if hasattr(record, "get"):
            return record.get(field_name, default)
        if hasattr(record, field_name):
            return getattr(record, field_name)
        try:
            return record[field_name]
        except Exception:
            return default

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
        """Crée un graphe logique et retourne son identifiant durable (group_id).

        Vérifie la disponibilité de la connexion Neo4j et retourne l'identifiant logique
        (généré au format 'mirofish_<uuid>' si omis).

        Quand un `graph_id` est explicitement fourni, l'ontologie appliquée
        mémorisée sous cette clé est effacée : un graphe « neuf » ne peut pas
        hériter d'une politique posée avant lui (ADR 0014 §2 ; bug de cycle de
        vie relecturé le 12 octobre 2026).
        """
        if not isinstance(name, str) or not name.strip():
            raise GraphValidationError("Le nom du graphe ne peut pas être vide")
        if graph_id is not None and (not isinstance(graph_id, str) or not graph_id.strip()):
            raise GraphValidationError("graph_id ne peut pas être une chaîne vide")

        target_graph_id = graph_id.strip() if graph_id else f"mirofish_{uuid.uuid4().hex[:16]}"
        with self._translate_errors(f"création du graphe {target_graph_id}"):
            self._run_async(self._check_connection())
            self._applied_ontologies.pop(target_graph_id, None)
            self._ontology_states.pop(target_graph_id, None)
            delete_state(target_graph_id, "graphiti")
            return target_graph_id

    def delete_graph(self, graph_id: str) -> None:
        """Supprime un graphe et l'ensemble de ses données associées de façon étanche.

        Supprime atomiquement par Cypher tous les nœuds et arêtes partitionnés sous le
        group_id spécifié, sans affecter aucun autre graphe (Critère C2).

        L'ontologie appliquée mémorisée est aussi purgée : un graphe supprimé
        puis recréé sous le même identifiant ne doit pas voir `get_applied
        _ontology` répondre sur un état mémoire antérieur (ADR 0014 §2 ; bug
        de cycle de vie relecturé le 12 octobre 2026).
        """
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        target_graph_id = graph_id.strip()
        with self._translate_errors(f"suppression du graphe {target_graph_id}"):
            self._run_async(
                self._execute_cypher(
                    "MATCH (n {group_id: $group_id}) DETACH DELETE n",
                    params={"group_id": target_graph_id},
                )
            )
        self._applied_ontologies.pop(target_graph_id, None)
        self._ontology_states.pop(target_graph_id, None)
        delete_state(target_graph_id, "graphiti")

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """Retourne les nœuds, arêtes et statistiques complètes du graphe pour l'API."""
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        target_graph_id = graph_id.strip()
        with self._translate_errors(f"récupération des données du graphe {target_graph_id}"):
            nodes = self.get_all_nodes(target_graph_id)
            edges = self.get_all_edges(target_graph_id, include_temporal=True)

            nodes_data = [self._sanitize_attribute_value(n.to_dict()) for n in nodes]
            edges_data = [self._sanitize_attribute_value(e.to_dict(include_temporal=True)) for e in edges]

            return {
                "graph_id": target_graph_id,
                "nodes": nodes_data,
                "edges": edges_data,
                "node_count": len(nodes_data),
                "edge_count": len(edges_data),
                "statistics": {
                    "node_count": len(nodes_data),
                    "edge_count": len(edges_data),
                },
            }

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        """Retourne un résumé synthétique (comptages et types d'entités)."""
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        target_graph_id = graph_id.strip()
        with self._translate_errors(f"récupération des informations du graphe {target_graph_id}"):
            nodes = self.get_all_nodes(target_graph_id)
            edges = self.get_all_edges(target_graph_id, include_temporal=False)

            entity_types: set[str] = set()
            for node in nodes:
                for label in node.labels:
                    if label and isinstance(label, str) and label not in ["Entity", "Node"]:
                        entity_types.add(label)

            return GraphInfo(
                graph_id=target_graph_id,
                node_count=len(nodes),
                edge_count=len(edges),
                entity_types=sorted(list(entity_types)),
            )

    # --- Ontologie ---

    def set_ontology(
        self, graph_id: str, ontology: Dict[str, Any], *, strict: bool = False
    ) -> None:
        """Pose l'ontologie du graphe et la retient pour les écritures suivantes.

        Traduit le dict en classes Pydantic **avant** toute mutation d'état : une
        ontologie refusée laisse l'instance exactement dans son état précédent,
        donc un graphe ne se retrouve jamais avec une ontologie à moitié appliquée
        (ADR 0014).

        La politique est persistée et relue avant chaque écriture ; la frontière
        de validation est exercée avant toute délégation de sauvegarde (007-2).
        """
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not isinstance(strict, bool):
            raise GraphValidationError("strict doit être un booléen")
        if not isinstance(ontology, dict):
            raise GraphValidationError("L'ontologie doit être un dictionnaire")
        target_graph_id = graph_id.strip()

        entity_types = OntologyToPydantic.from_dict(ontology)
        edge_types = OntologyToPydantic.edge_types_from_dict(ontology)
        neutre = AppliedOntology(
            entity_type_names=tuple(entity_types),
            edge_type_names=tuple(edge_types),
            strict=bool(strict),
        )

        write_state(target_graph_id, "graphiti", ontology, strict)
        self._ontology_states[target_graph_id] = {"ontology": ontology, "strict": strict}
        self._applied_ontologies[target_graph_id] = _OntologyTraduite(
            entity_types=entity_types, edge_types=edge_types, neutre=neutre
        )
        logger.debug(
            "set_ontology : %d type(s) d'entité et %d type(s) de relation posés "
            "sur le graphe %s (strict=%s, ADR 0014)",
            len(entity_types),
            len(edge_types),
            target_graph_id,
            bool(strict),
        )

    def get_applied_ontology(self, graph_id: str) -> Optional[AppliedOntology]:
        """Ontologie en vigueur sur ce graphe, décrite de façon neutre (ADR 0014 §2)."""
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        traduite = self._load_applied_ontology(graph_id.strip())
        return traduite.neutre if traduite is not None else None

    def update_ontology_policy(self, graph_id: str, strict: bool) -> None:
        update_policy(graph_id, "graphiti", strict)
        self._load_applied_ontology(graph_id.strip())

    def _load_applied_ontology(self, graph_id: str) -> Optional[_OntologyTraduite]:
        state = read_state(graph_id, "graphiti")
        if state is not None and state != self._ontology_states.get(graph_id):
            ontology = state["ontology"]
            entity_types = OntologyToPydantic.from_dict(ontology)
            edge_types = OntologyToPydantic.edge_types_from_dict(ontology)
            self._applied_ontologies[graph_id] = _OntologyTraduite(
                entity_types=entity_types,
                edge_types=edge_types,
                neutre=AppliedOntology(tuple(entity_types), tuple(edge_types), state["strict"]),
            )
            self._ontology_states[graph_id] = state
        elif state is None and graph_id in self._ontology_states:
            self._ontology_states.pop(graph_id, None)
            self._applied_ontologies.pop(graph_id, None)
        return self._applied_ontologies.get(graph_id)

    def _resolve_applied_ontology(
        self, graph_id: str, ontology: Optional[Dict[str, Any]]
    ) -> Optional[_OntologyTraduite]:
        """Ontologie effective d'une écriture : explicite, puis mémorisée.

        L'ontologie explicite est traduite à chaque appel : c'est le seul chemin
        qui permette à un appelant de poser, pour un épisode, une ontologie que
        `set_ontology` n'a jamais vue. Elle ne modifie **pas** l'ontologie
        mémorisée du graphe.

        `strict` est hérité de l'ontologie mémorisée du graphe quand une
        ontologie explicite est fournie : « la politique du graphe vaut tant
        qu'elle n'est pas changée » (ADR 0014). Sans graphe posé, défaut à
        `False`.
        """
        appliquee = self._load_applied_ontology(graph_id)
        if ontology is None:
            return appliquee

        entity_types = OntologyToPydantic.from_dict(ontology)
        edge_types = OntologyToPydantic.edge_types_from_dict(ontology)
        strict = appliquee.neutre.strict if appliquee is not None else False
        return _OntologyTraduite(
            entity_types=entity_types,
            edge_types=edge_types,
            neutre=AppliedOntology(
                entity_type_names=tuple(entity_types),
                edge_type_names=tuple(edge_types),
                strict=strict,
            ),
        )

    # --- Ingestion et épisodes ---

    def add_episode(
        self,
        graph_id: str,
        text: str,
        source_description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
        *,
        ontology: Optional[Dict[str, Any]] = None,
    ) -> EpisodeRecord:
        """Ajoute un épisode textuel unitaire au graphe avec partitionnement group_id.

        Les métadonnées sont **réellement persistées** sur `:Episodic` : Graphiti
        valide `episode_metadata` mais ne l'écrit pas dans sa requête de
        sauvegarde Neo4j, donc l'annotation est posée ici, par Cypher, sur l'UUID
        que Graphiti a réellement retourné (ADR 0012 §2).

        Si une ontologie est effective — passée explicitement ou posée par
        `set_ontology` sur ce `graph_id` — ses classes sont passées à Graphiti,
        qui en dérive le label Cypher de chaque nœud extrait (ADR 0014 §2).
        """
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not isinstance(text, str) or not text.strip():
            raise GraphValidationError("Le contenu textuel de l'épisode est requis")
        if metadata is not None and not isinstance(metadata, dict):
            raise GraphValidationError("metadata doit être un dictionnaire")

        target_graph_id = graph_id.strip()
        applied = self._resolve_applied_ontology(target_graph_id, ontology)
        with self._translate_errors(f"ajout d'épisode dans le graphe {target_graph_id}"):
            if created_at:
                try:
                    clean_ts = created_at.strip()
                    if clean_ts.endswith(("Z", "z")):
                        clean_ts = clean_ts[:-1] + "+00:00"
                    ref_time = datetime.fromisoformat(clean_ts)
                    if ref_time.tzinfo is None:
                        ref_time = ref_time.replace(tzinfo=timezone.utc)
                except Exception as exc:
                    raise GraphValidationError(
                        f"Horodatage created_at invalide : {created_at}"
                    ) from exc
            else:
                ref_time = datetime.now(timezone.utc)

            episode_name = (
                source_description.strip()
                if (source_description and source_description.strip())
                else f"Episode {uuid.uuid4().hex[:8]}"
            )
            src_desc = (
                source_description.strip()
                if (source_description and source_description.strip())
                else "MiroFish episode"
            )

            # Sans ontologie, l'appel est construit **exactement** comme avant :
            # c'est ce qui rend la rétrocompatibilité Epic 003-2 vérifiable
            # plutôt que déclarative (ADR 0014 §3).
            episode_kwargs: Dict[str, Any] = {
                "name": episode_name,
                "episode_body": text.strip(),
                "source": EpisodeType.text,
                "source_description": src_desc,
                "reference_time": ref_time,
                "group_id": target_graph_id,
            }
            if applied is not None and applied.entity_types:
                episode_kwargs["entity_types"] = dict(applied.entity_types)
            if applied is not None and applied.edge_types:
                episode_kwargs["edge_types"] = dict(applied.edge_types)
            if isinstance(self._graphiti, _OntologyValidatingGraphiti):
                episode_kwargs["_mirofish_ontology_validation"] = applied

            res = self._run_async(self._graphiti.add_episode(**episode_kwargs))

            ep_uuid = None
            if hasattr(res, "episode") and getattr(res, "episode") is not None:
                ep_obj = getattr(res, "episode")
                ep_uuid = getattr(ep_obj, "uuid", None)
            if not ep_uuid and hasattr(res, "uuid"):
                ep_uuid = getattr(res, "uuid")
            if not ep_uuid and isinstance(res, dict):
                ep_uuid = res.get("uuid")
            if not ep_uuid:
                # Plus de repli silencieux sur uuid4() : cet UUID serait
                # persisté nulle part et ne se résoudrait jamais (ADR 0012 §2).
                raise GraphStoreError(
                    "Graphiti n'a retourné aucun identifiant d'épisode ; "
                    "aucune valeur de repli n'est inventée, car elle ne "
                    "pointerait vers rien dans Neo4j"
                )

            episode_uuid = str(ep_uuid)

            if metadata:
                self._annotate_episode(target_graph_id, episode_uuid, metadata)

            return EpisodeRecord(
                uuid=episode_uuid,
                graph_id=target_graph_id,
                processed=True,
                created_at=ref_time.isoformat(),
            )

    def _annotate_episode(
        self,
        graph_id: str,
        episode_uuid: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Pose les métadonnées sur `:Episodic` et vérifie qu'une ligne a été touchée.

        Une annotation qui ne trouve pas son épisode est une erreur visible :
        l'ingestion ne doit jamais être déclarée réussie avec une provenance
        perdue en silence (ADR 0012 §2).

        Les noms de propriétés Cypher ne peuvent pas être paramétrés : chaque clé
        est donc validée comme identifiant et les clés que le store gère lui-même
        sont refusées, pour qu'une clé libre ne devienne pas une surface
        d'injection ou un écrasement de propriété.
        """
        payload: Dict[str, Any] = {}
        for key, value in metadata.items():
            if key in FORBIDDEN_ANNOTATION_KEYS:
                raise GraphValidationError(
                    f"La métadonnée '{key}' est interdite : elle est gérée par le store"
                )
            if not _ANNOTATION_KEY_PATTERN.match(key):
                raise GraphValidationError(
                    f"La métadonnée '{key}' n'est pas un nom de propriété valide"
                )
            if isinstance(value, (str, int, float, bool)) or value is None:
                payload[key] = value
            else:
                payload[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)

        if not payload:
            return

        assignments = ", ".join(f"e.{key} = ${key}" for key in payload)
        res = self._run_async(
            self._execute_cypher(
                f"""
                MATCH (e:Episodic {{uuid: $episode_uuid, group_id: $group_id}})
                SET {assignments}
                RETURN e.uuid AS uuid
                """,
                params={"episode_uuid": episode_uuid, "group_id": graph_id, **payload},
            )
        )
        records = self._extract_records(res)
        if not records:
            raise GraphStoreError(
                f"Aucune annotation appliquée à l'épisode {episode_uuid} dans le "
                f"graphe {graph_id} : l'ingestion n'est pas déclarée réussie"
            )

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        chunk_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> BatchSubmissionRecord:
        """Ingère une liste de textes découpés par lots avec suivi de progression."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not chunks:
            raise GraphValidationError("Au moins un fragment de texte est requis")
        if not isinstance(batch_size, int) or batch_size <= 0:
            raise GraphValidationError("batch_size doit être un entier strictement positif")

        target_graph_id = graph_id.strip()
        for idx, chunk in enumerate(chunks):
            if not isinstance(chunk, str) or not chunk.strip():
                raise GraphValidationError(
                    f"Le fragment d'index {idx} ne peut pas être vide ou de type invalide"
                )

        # Validation partagée, avant toute écriture (ADR 0012 §1).
        metadata_entries = validate_chunk_metadata(chunks, chunk_metadata)

        total_chunks = len(chunks)
        batch_id = f"batch_{uuid.uuid4().hex[:16]}"
        operation_id = self._build_operation_id(
            target_graph_id, chunks, metadata_entries
        )

        with self._translate_errors(f"ingestion par lots pour {target_graph_id}"):
            episode_uuids: List[str] = []
            for idx, chunk in enumerate(chunks, 1):
                if progress_callback:
                    progress_callback("processing", idx - 1, total_chunks)

                record = self.add_episode(
                    graph_id=target_graph_id,
                    text=chunk,
                    source_description=self._chunk_source_description(idx, metadata_entries, idx - 1),
                    metadata=metadata_entries[idx - 1] if metadata_entries else None,
                )
                episode_uuids.append(record.uuid)

                if progress_callback:
                    progress_callback("processing", idx, total_chunks)

            if progress_callback:
                progress_callback("completed", total_chunks, total_chunks)

            return BatchSubmissionRecord(
                batch_id=batch_id,
                operation_id=operation_id,
                episode_uuids=episode_uuids,
                item_count=total_chunks,
            )

    @staticmethod
    def _chunk_source_description(
        sequence: int,
        metadata_entries: List[Dict[str, Any]],
        index: int,
    ) -> str:
        """Description lisible de la source d'un fragment.

        Sans provenance, on garde `chunk_<n>` : c'est le comportement historique
        et plusieurs tests le vérifient. Avec provenance, la description nomme le
        document et l'index local — elle reste une description, jamais une
        sérialisation faisant autorité (ADR 0012 §1).
        """
        if not metadata_entries:
            return f"chunk_{sequence}"
        entry = metadata_entries[index]
        return (
            f"{entry['source_filename']}#{entry['chunk_index']}"
            f" [{entry['source_role']}]"
        )

    @staticmethod
    def _build_operation_id(
        graph_id: str,
        chunks: List[str],
        metadata_entries: List[Dict[str, Any]],
    ) -> str:
        """Identifiant déterministe d'opération.

        Sans provenance, le hachage est **inchangé** : un lot déjà persisté et
        repris après redémarrage reste reconnaissable. Avec provenance, les
        métadonnées entrent dans le hachage, pour que deux textes identiques
        issus de deux documents différents soient deux opérations distinctes
        (ADR 0012 §1).
        """
        payload_hash = hashlib.sha256("\0".join(chunks).encode("utf-8")).hexdigest()
        if metadata_entries:
            canonical = json.dumps(
                metadata_entries, ensure_ascii=False, sort_keys=True
            ).encode("utf-8")
            payload_hash = hashlib.sha256(
                payload_hash.encode("ascii") + b"\0" + canonical
            ).hexdigest()
        return hashlib.sha256(f"{graph_id}:{payload_hash}".encode("utf-8")).hexdigest()

    def wait_for_batch(
        self,
        batch: BatchSubmissionRecord,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        timeout: float = 600.0,
    ) -> bool:
        """Attend la fin du traitement d'un lot d'ingestion en vérifiant la persistance des épisodes."""
        if not batch or not getattr(batch, "batch_id", None):
            raise GraphValidationError("batch et batch_id sont requis")
        if timeout <= 0:
            raise GraphValidationError("timeout doit être strictement supérieur à 0")

        episode_uuids = getattr(batch, "episode_uuids", []) or []
        if not episode_uuids:
            if progress_callback:
                progress_callback("completed", 1.0)
            return True

        total_count = len(episode_uuids)
        pending_uuids = set(episode_uuids)
        start_time = time.time()

        with self._translate_errors(f"attente du lot {batch.batch_id}"):
            while pending_uuids:
                if time.time() - start_time > timeout:
                    raise GraphTimeoutError(
                        f"Le lot {batch.batch_id} n'a pas terminé dans le délai imparti ({timeout}s)"
                    )

                res = self._run_async(
                    self._execute_cypher(
                        """
                        MATCH (e:Episodic)
                        WHERE e.uuid IN $uuids
                        RETURN DISTINCT e.uuid AS uuid
                        """,
                        params={"uuids": list(pending_uuids)},
                    )
                )

                records = self._extract_records(res)
                for rec in records:
                    found_uuid = self._get_record_field(rec, "uuid")
                    if found_uuid in pending_uuids:
                        pending_uuids.remove(found_uuid)

                if progress_callback:
                    ratio = min(max((total_count - len(pending_uuids)) / total_count, 0.0), 1.0)
                    progress_callback("processing", ratio)

                if pending_uuids:
                    time.sleep(0.1)

            if progress_callback:
                progress_callback("completed", 1.0)
            return True

    def wait_for_episodes(
        self,
        graph_id: str,
        episode_uuids: List[str],
        timeout: float = 600.0,
    ) -> bool:
        """Attend la fin du traitement pour une liste explicite d'épisodes partitionnés."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if timeout <= 0:
            raise GraphValidationError("timeout doit être strictement supérieur à 0")
        if not episode_uuids:
            return True

        target_graph_id = graph_id.strip()
        pending_uuids = set(episode_uuids)
        start_time = time.time()

        with self._translate_errors(f"attente des épisodes pour {target_graph_id}"):
            while pending_uuids:
                if time.time() - start_time > timeout:
                    raise GraphTimeoutError(
                        f"Les épisodes {sorted(list(pending_uuids))} pour le graphe {target_graph_id} "
                        f"n'ont pas terminé dans le délai imparti ({timeout}s)"
                    )

                res = self._run_async(
                    self._execute_cypher(
                        """
                        MATCH (e:Episodic {group_id: $group_id})
                        WHERE e.uuid IN $uuids
                        RETURN DISTINCT e.uuid AS uuid
                        """,
                        params={"group_id": target_graph_id, "uuids": list(pending_uuids)},
                    )
                )

                records = self._extract_records(res)
                for rec in records:
                    found_uuid = self._get_record_field(rec, "uuid")
                    if found_uuid in pending_uuids:
                        pending_uuids.remove(found_uuid)

                if pending_uuids:
                    time.sleep(0.1)

            return True

    # --- Helpers de conversion Cypher -> DTO neutres ---

    @classmethod
    def _format_temporal(cls, val: Any) -> Optional[str]:
        """Convertit une valeur temporelle Cypher (DateTime, datetime) en chaîne ISO-8601."""
        if val is None:
            return None
        if hasattr(val, "isoformat") and callable(val.isoformat):
            return val.isoformat()
        return str(val)

    @classmethod
    def _sanitize_attribute_value(cls, val: Any) -> Any:
        """Convertit récursivement les types temporels en représentations JSON sérialisables."""
        if val is None:
            return None
        if hasattr(val, "isoformat") and callable(val.isoformat):
            return val.isoformat()
        if isinstance(val, dict):
            return {str(k): cls._sanitize_attribute_value(v) for k, v in val.items()}
        if isinstance(val, (list, tuple, set)):
            return [cls._sanitize_attribute_value(x) for x in val]
        return val

    @classmethod
    def _record_to_graph_node(cls, record: Any) -> GraphNode:
        """Convertit un enregistrement Cypher ou dictionnaire en GraphNode neutre."""
        uuid_val = cls._get_record_field(record, "uuid", "") or ""
        name_val = cls._get_record_field(record, "name", "") or ""
        summary_val = cls._get_record_field(record, "summary", "") or ""
        raw_labels = cls._get_record_field(record, "labels", []) or []
        labels_list = (
            [str(l) for l in raw_labels if l]
            if isinstance(raw_labels, (list, tuple, set))
            else []
        )
        raw_attrs = cls._get_record_field(record, "attributes", {}) or {}
        attributes = (
            {
                k: cls._sanitize_attribute_value(v)
                for k, v in raw_attrs.items()
                if k not in cls._NODE_SYSTEM_KEYS
            }
            if isinstance(raw_attrs, dict)
            else {}
        )
        raw_created_at = cls._get_record_field(record, "created_at", None)
        created_at_str = cls._format_temporal(raw_created_at)

        return GraphNode(
            uuid=str(uuid_val),
            name=str(name_val),
            labels=labels_list,
            summary=str(summary_val),
            attributes=attributes,
            created_at=created_at_str,
            related_edges=[],
            related_nodes=[],
        )

    @classmethod
    def _record_to_graph_edge(
        cls, record: Any, include_temporal: bool = True
    ) -> GraphEdge:
        """Convertit un enregistrement Cypher ou dictionnaire en GraphEdge neutre."""
        uuid_val = cls._get_record_field(record, "uuid", "") or ""
        src_uuid = cls._get_record_field(record, "source_node_uuid", "") or ""
        tgt_uuid = cls._get_record_field(record, "target_node_uuid", "") or ""
        src_name = cls._get_record_field(record, "source_node_name", "") or ""
        tgt_name = cls._get_record_field(record, "target_node_name", "") or ""
        rel_type = cls._get_record_field(record, "relation_type", "") or ""
        name_val = cls._get_record_field(record, "name", "") or rel_type or "RELATES_TO"
        fact_val = cls._get_record_field(record, "fact", "") or ""
        fact_type = cls._get_record_field(record, "fact_type", "") or name_val

        raw_episodes = cls._get_record_field(record, "episodes", [])
        if raw_episodes and isinstance(raw_episodes, (list, tuple, set)):
            episodes_list = [str(e) for e in raw_episodes]
        elif raw_episodes:
            episodes_list = [str(raw_episodes)]
        else:
            episodes_list = []

        raw_attrs = cls._get_record_field(record, "attributes", {}) or {}
        attributes = (
            {
                k: cls._sanitize_attribute_value(v)
                for k, v in raw_attrs.items()
                if k not in cls._EDGE_SYSTEM_KEYS
            }
            if isinstance(raw_attrs, dict)
            else {}
        )

        raw_created_at = cls._get_record_field(record, "created_at", None)
        raw_valid_at = cls._get_record_field(record, "valid_at", None)
        raw_invalid_at = cls._get_record_field(record, "invalid_at", None)
        raw_expired_at = cls._get_record_field(record, "expired_at", None)

        if include_temporal:
            created_at_str = cls._format_temporal(raw_created_at)
            valid_at_str = cls._format_temporal(raw_valid_at)
            invalid_at_str = cls._format_temporal(raw_invalid_at)
            expired_at_str = cls._format_temporal(raw_expired_at)
        else:
            created_at_str = None
            valid_at_str = None
            invalid_at_str = None
            expired_at_str = None

        return GraphEdge(
            uuid=str(uuid_val),
            name=str(name_val),
            fact=str(fact_val),
            source_node_uuid=str(src_uuid),
            target_node_uuid=str(tgt_uuid),
            fact_type=str(fact_type),
            source_node_name=str(src_name),
            target_node_name=str(tgt_name),
            attributes=attributes,
            episodes=episodes_list,
            created_at=created_at_str,
            valid_at=valid_at_str,
            invalid_at=invalid_at_str,
            expired_at=expired_at_str,
        )

    # --- Lecture et parcours ---

    def get_all_nodes(self, graph_id: str) -> List[GraphNode]:
        """Récupère tous les nœuds d'un graphe partitionné par group_id."""
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        target_graph_id = graph_id.strip()
        with self._translate_errors(f"récupération de tous les nœuds de {target_graph_id}"):
            res = self._run_async(
                self._execute_cypher(
                    """
                    MATCH (n:Entity)
                    WHERE n.group_id = $group_id
                    RETURN n.uuid AS uuid,
                           n.name AS name,
                           n.summary AS summary,
                           labels(n) AS labels,
                           n.created_at AS created_at,
                           properties(n) AS attributes
                    """,
                    params={"group_id": target_graph_id},
                )
            )
            records = self._extract_records(res)
            return [self._record_to_graph_node(rec) for rec in records]

    def get_all_edges(
        self, graph_id: str, include_temporal: bool = True
    ) -> List[GraphEdge]:
        """Récupère toutes les arêtes d'un graphe avec ou sans champs temporels."""
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        target_graph_id = graph_id.strip()
        with self._translate_errors(f"récupération de toutes les arêtes de {target_graph_id}"):
            res = self._run_async(
                self._execute_cypher(
                    """
                    MATCH (source:Entity)-[r]->(target:Entity)
                    WHERE source.group_id = $group_id
                      AND target.group_id = $group_id
                    RETURN r.uuid AS uuid,
                           source.uuid AS source_node_uuid,
                           target.uuid AS target_node_uuid,
                           source.name AS source_node_name,
                           target.name AS target_node_name,
                           type(r) AS relation_type,
                           r.name AS name,
                           r.fact AS fact,
                           coalesce(properties(r).fact_type, r.name, type(r), '') AS fact_type,
                           r.episodes AS episodes,
                           r.created_at AS created_at,
                           r.valid_at AS valid_at,
                           r.invalid_at AS invalid_at,
                           r.expired_at AS expired_at,
                           properties(r) AS attributes
                    """,
                    params={"group_id": target_graph_id},
                )
            )
            records = self._extract_records(res)
            return [
                self._record_to_graph_edge(rec, include_temporal=include_temporal)
                for rec in records
            ]

    def get_node(self, graph_id: str, node_uuid: str) -> Optional[GraphNode]:
        """Récupère un nœud spécifique par son identifiant unique et son voisinage."""
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not isinstance(node_uuid, str) or not node_uuid.strip():
            raise GraphValidationError("node_uuid est requis")
        target_graph_id = graph_id.strip()
        target_node_uuid = node_uuid.strip()
        with self._translate_errors(
            f"récupération du nœud {target_node_uuid} dans {target_graph_id}"
        ):
            res = self._run_async(
                self._execute_cypher(
                    """
                    MATCH (n:Entity {uuid: $node_uuid, group_id: $group_id})
                    RETURN n.uuid AS uuid,
                           n.name AS name,
                           n.summary AS summary,
                           labels(n) AS labels,
                           n.created_at AS created_at,
                           properties(n) AS attributes
                    """,
                    params={
                        "node_uuid": target_node_uuid,
                        "group_id": target_graph_id,
                    },
                )
            )
            records = self._extract_records(res)
            if not records:
                return None

            base_node = self._record_to_graph_node(records[0])
            edges = self.get_node_edges(target_graph_id, target_node_uuid)
            related_edges = [e.to_dict(include_temporal=True) for e in edges]

            return GraphNode(
                uuid=base_node.uuid,
                name=base_node.name,
                labels=base_node.labels,
                summary=base_node.summary,
                attributes=base_node.attributes,
                created_at=base_node.created_at,
                related_edges=related_edges,
                related_nodes=[],
            )

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[GraphEdge]:
        """Récupère toutes les arêtes connectées à un nœud (entrantes et sortantes)."""
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not isinstance(node_uuid, str) or not node_uuid.strip():
            raise GraphValidationError("node_uuid est requis")
        target_graph_id = graph_id.strip()
        target_node_uuid = node_uuid.strip()
        with self._translate_errors(
            f"récupération des arêtes du nœud {target_node_uuid} dans {target_graph_id}"
        ):
            res = self._run_async(
                self._execute_cypher(
                    """
                    MATCH (n:Entity {uuid: $node_uuid, group_id: $group_id})-[r]-(neighbor:Entity {group_id: $group_id})
                    RETURN DISTINCT r.uuid AS uuid,
                           startNode(r).uuid AS source_node_uuid,
                           endNode(r).uuid AS target_node_uuid,
                           startNode(r).name AS source_node_name,
                           endNode(r).name AS target_node_name,
                           type(r) AS relation_type,
                           r.name AS name,
                           r.fact AS fact,
                           coalesce(properties(r).fact_type, r.name, type(r), '') AS fact_type,
                           r.episodes AS episodes,
                           r.created_at AS created_at,
                           r.valid_at AS valid_at,
                           r.invalid_at AS invalid_at,
                           r.expired_at AS expired_at,
                           properties(r) AS attributes
                    """,
                    params={
                        "node_uuid": target_node_uuid,
                        "group_id": target_graph_id,
                    },
                )
            )
            records = self._extract_records(res)
            return [
                self._record_to_graph_edge(rec, include_temporal=True)
                for rec in records
            ]

    # --- Provenance des faits ---

    def get_edge_provenance(self, graph_id: str, edge_uuid: str) -> List[ProvenanceRecord]:
        """Résout les origines documentaires d'une arête, dans un graphe donné.

        La requête part de l'arête **dans le graphe cible** et résout ses
        références par `OPTIONAL MATCH` : une référence non résolue reste
        visible au lieu de disparaître du résultat (ADR 0012 §4).
        """
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not isinstance(edge_uuid, str) or not edge_uuid.strip():
            raise GraphValidationError("edge_uuid est requis")

        target_graph_id = graph_id.strip()
        target_edge_uuid = edge_uuid.strip()

        with self._translate_errors(
            f"lecture de la provenance de l'arête {target_edge_uuid}"
        ):
            res = self._run_async(
                self._execute_cypher(
                    """
                    MATCH (source:Entity {group_id: $group_id})-[r]->(target:Entity {group_id: $group_id})
                    WHERE r.group_id = $group_id AND r.uuid = $edge_uuid
                    RETURN coalesce(r.episodes, []) AS episode_uuids
                    """,
                    params={
                        "group_id": target_graph_id,
                        "edge_uuid": target_edge_uuid,
                    },
                )
            )
            edge_records = self._extract_records(res)
            if not edge_records:
                return []

            raw_refs = self._get_record_field(edge_records[0], "episode_uuids", []) or []
            if not isinstance(raw_refs, (list, tuple, set)):
                raw_refs = [raw_refs]
            episode_uuids = [str(value) for value in raw_refs if value]
            if not episode_uuids:
                return []

            resolved = self._resolve_episodes(target_graph_id, episode_uuids)
            return [
                self._to_provenance_record(episode_uuid, resolved.get(episode_uuid))
                for episode_uuid in episode_uuids
            ]

    def _resolve_episodes(
        self, graph_id: str, episode_uuids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Charge les épisodes d'un graphe, indexés par UUID.

        La résolution est bornée par `group_id` : un épisode d'un autre graphe
        est traité comme absent, jamais comme trouvé.
        """
        res = self._run_async(
            self._execute_cypher(
                """
                MATCH (e:Episodic {group_id: $group_id})
                WHERE e.uuid IN $uuids
                RETURN e.uuid AS uuid,
                       e.content AS content,
                       e.source_document_id AS source_document_id,
                       e.source_filename AS source_filename,
                       e.source_role AS source_role,
                       e.chunk_index AS chunk_index,
                       e.char_start AS char_start,
                       e.char_end AS char_end,
                       e.page AS page,
                       e.section AS section,
                       e.simulation_id AS simulation_id,
                       e.platform AS platform,
                       e.source AS source
                """,
                params={"group_id": graph_id, "uuids": list(episode_uuids)},
            )
        )
        records = self._extract_records(res)
        return {
            str(self._get_record_field(record, "uuid", "")): {
                "content": self._get_record_field(record, "content"),
                "source_document_id": self._get_record_field(
                    record, "source_document_id"
                ),
                "source_filename": self._get_record_field(record, "source_filename"),
                "source_role": self._get_record_field(record, "source_role"),
                "chunk_index": self._get_record_field(record, "chunk_index"),
                "char_start": self._get_record_field(record, "char_start"),
                "char_end": self._get_record_field(record, "char_end"),
                "page": self._get_record_field(record, "page"),
                "section": self._get_record_field(record, "section"),
                "simulation_id": self._get_record_field(record, "simulation_id"),
                "platform": self._get_record_field(record, "platform"),
                "source": self._get_record_field(record, "source"),
            }
            for record in records
            if self._get_record_field(record, "uuid")
        }

    @classmethod
    def _to_provenance_record(
        cls, episode_uuid: str, episode: Optional[Dict[str, Any]]
    ) -> ProvenanceRecord:
        """Classe une référence d'épisode selon son origine réelle.

        Quatre origines, jamais fusionnées : documentaire, simulée, héritée d'un
        graphe sans provenance, et non résolue (ADR 0012 §3).
        """
        if episode is None:
            return ProvenanceRecord(
                episode_uuid=episode_uuid,
                resolved=False,
                origin=ProvenanceOrigin.UNRESOLVED,
                missing_reason=(
                    "aucun épisode ne porte cet UUID dans le graphe demandé"
                ),
            )

        def _int_or_none(value: Any) -> Optional[int]:
            if isinstance(value, bool) or value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        def _str_or_none(value: Any) -> Optional[str]:
            if value is None:
                return None
            text = str(value)
            return text if text else None

        document_id = _str_or_none(episode.get("source_document_id"))
        simulation_id = _str_or_none(episode.get("simulation_id"))

        if simulation_id:
            origin = ProvenanceOrigin.SIMULATION
        elif document_id:
            origin = ProvenanceOrigin.DOCUMENT
        else:
            origin = ProvenanceOrigin.LEGACY

        missing_reason = None
        if origin is ProvenanceOrigin.DOCUMENT:
            # Une provenance documentaire incomplète n'est pas une provenance
            # complète : elle est signalée, pas complétée par invention.
            required = {
                "source_filename": _str_or_none(episode.get("source_filename")),
                "source_role": _str_or_none(episode.get("source_role")),
                "chunk_index": _int_or_none(episode.get("chunk_index")),
                "char_start": _int_or_none(episode.get("char_start")),
                "char_end": _int_or_none(episode.get("char_end")),
            }
            absent = [name for name, value in required.items() if value is None]
            if absent:
                missing_reason = (
                    "épisode documentaire incomplet, champs manquants : "
                    + ", ".join(sorted(absent))
                )
            elif required["char_end"] <= required["char_start"]:  # type: ignore[operator]
                missing_reason = (
                    f"positions incohérentes : char_end ({required['char_end']}) "
                    f"<= char_start ({required['char_start']})"
                )

        return ProvenanceRecord(
            episode_uuid=episode_uuid,
            resolved=True,
            origin=origin,
            source_document_id=document_id,
            source_filename=_str_or_none(episode.get("source_filename")),
            source_role=_str_or_none(episode.get("source_role")),
            chunk_index=_int_or_none(episode.get("chunk_index")),
            char_start=_int_or_none(episode.get("char_start")),
            char_end=_int_or_none(episode.get("char_end")),
            page=_int_or_none(episode.get("page")),
            section=_str_or_none(episode.get("section")),
            content=_str_or_none(episode.get("content")),
            simulation_id=simulation_id,
            platform=_str_or_none(episode.get("platform")),
            missing_reason=missing_reason,
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
        """Effectue une recherche sémantique / hybride sur les arêtes ou les nœuds."""
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not isinstance(query, str) or not query.strip():
            raise GraphValidationError("Le texte de recherche query est requis")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise GraphValidationError("limit doit être un entier strictement positif")
        if scope not in ("edges", "nodes", "hybrid"):
            raise GraphValidationError(
                f"Périmètre de recherche invalide : '{scope}'. Valeurs acceptées : 'edges', 'nodes', 'hybrid'."
            )

        target_graph_id = graph_id.strip()
        norm_query = query.strip()
        norm_limit = limit

        with self._translate_errors(f"recherche dans le graphe {target_graph_id}"):
            facts: List[str] = []
            edges: List[GraphEdge] = []
            nodes: List[GraphNode] = []

            # 1. Recherche d'arêtes / faits si scope in ("edges", "hybrid")
            if scope in ("edges", "hybrid"):
                raw_edges = self._run_async(
                    self._graphiti.search(
                        query=norm_query,
                        group_ids=[target_graph_id],
                        num_results=norm_limit,
                    )
                )
                raw_edge_list = self._extract_records(raw_edges)

                # Résolution des noms de nœuds associés si nécessaire
                node_uuids = set()
                for re in raw_edge_list:
                    src = self._get_record_field(re, "source_node_uuid") or getattr(
                        re, "source_node_uuid", None
                    )
                    tgt = self._get_record_field(re, "target_node_uuid") or getattr(
                        re, "target_node_uuid", None
                    )
                    if src:
                        node_uuids.add(str(src))
                    if tgt:
                        node_uuids.add(str(tgt))

                node_name_map: Dict[str, str] = {}
                if node_uuids:
                    res_names = self._run_async(
                        self._execute_cypher(
                            """
                            MATCH (n:Entity)
                            WHERE n.uuid IN $uuids AND n.group_id = $group_id
                            RETURN n.uuid AS uuid, n.name AS name
                            """,
                            params={"uuids": list(node_uuids), "group_id": target_graph_id},
                        )
                    )
                    for rec in self._extract_records(res_names):
                        u = self._get_record_field(rec, "uuid")
                        nm = self._get_record_field(rec, "name")
                        if u and nm:
                            node_name_map[str(u)] = str(nm)

                for re in raw_edge_list:
                    edge = self._record_to_graph_edge(re, include_temporal=True)
                    if (
                        (not edge.source_node_name and edge.source_node_uuid in node_name_map)
                        or (not edge.target_node_name and edge.target_node_uuid in node_name_map)
                    ):
                        edge = GraphEdge(
                            uuid=edge.uuid,
                            name=edge.name,
                            fact=edge.fact,
                            source_node_uuid=edge.source_node_uuid,
                            target_node_uuid=edge.target_node_uuid,
                            fact_type=edge.fact_type,
                            source_node_name=node_name_map.get(
                                edge.source_node_uuid, edge.source_node_name
                            ),
                            target_node_name=node_name_map.get(
                                edge.target_node_uuid, edge.target_node_name
                            ),
                            attributes=edge.attributes,
                            episodes=edge.episodes,
                            created_at=edge.created_at,
                            valid_at=edge.valid_at,
                            invalid_at=edge.invalid_at,
                            expired_at=edge.expired_at,
                        )

                    edges.append(edge)
                    if edge.fact:
                        facts.append(edge.fact)

            # 2. Recherche de nœuds si scope in ("nodes", "hybrid")
            if scope in ("nodes", "hybrid"):
                res_nodes = self._run_async(
                    self._execute_cypher(
                        """
                        MATCH (n:Entity {group_id: $group_id})
                        WHERE toLower(coalesce(n.name, '')) CONTAINS toLower($query)
                           OR toLower(coalesce(n.summary, '')) CONTAINS toLower($query)
                        RETURN n.uuid AS uuid,
                               n.name AS name,
                               n.summary AS summary,
                               labels(n) AS labels,
                               n.created_at AS created_at,
                               properties(n) AS attributes
                        LIMIT $limit
                        """,
                        params={
                            "group_id": target_graph_id,
                            "query": norm_query,
                            "limit": norm_limit,
                        },
                    )
                )
                records = self._extract_records(res_nodes)
                nodes = [self._record_to_graph_node(rec) for rec in records]

            # Calcul du total_count
            if scope == "hybrid":
                total_count = len(facts) + len(nodes)
            elif facts:
                total_count = len(facts)
            elif nodes:
                total_count = len(nodes)
            else:
                total_count = len(edges)

            return GraphSearchResult(
                facts=facts,
                nodes=nodes,
                edges=edges,
                query=norm_query,
                total_count=total_count,
            )
