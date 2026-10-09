"""Implémentation GraphitiGraphStore encapsulant Graphiti et Neo4j."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
import concurrent.futures
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import inspect
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar
import uuid

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.nodes import EpisodeType

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

    # Clés réservées Neo4j / Graphiti à exclure des dictionnaires attributes (Patch 1)
    _NODE_SYSTEM_KEYS = {
        "uuid",
        "name",
        "name_embedding",
        "summary",
        "group_id",
        "created_at",
        "labels",
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

    def close(self) -> None:
        """Libère les ressources du runner asynchrone."""
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
        """
        if not isinstance(name, str) or not name.strip():
            raise GraphValidationError("Le nom du graphe ne peut pas être vide")
        if graph_id is not None and (not isinstance(graph_id, str) or not graph_id.strip()):
            raise GraphValidationError("graph_id ne peut pas être une chaîne vide")

        target_graph_id = graph_id.strip() if graph_id else f"mirofish_{uuid.uuid4().hex[:16]}"
        with self._translate_errors(f"création du graphe {target_graph_id}"):
            self._run_async(self._check_connection())
            return target_graph_id

    def delete_graph(self, graph_id: str) -> None:
        """Supprime un graphe et l'ensemble de ses données associées de façon étanche.

        Supprime atomiquement par Cypher tous les nœuds et arêtes partitionnés sous le
        group_id spécifié, sans affecter aucun autre graphe (Critère C2).
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

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """Retourne les nœuds, arêtes et statistiques complètes du graphe pour l'API."""
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        target_graph_id = graph_id.strip()
        with self._translate_errors(f"récupération des données du graphe {target_graph_id}"):
            nodes = self.get_all_nodes(target_graph_id)
            edges = self.get_all_edges(target_graph_id, include_temporal=True)

            nodes_data = [n.to_dict() for n in nodes]
            edges_data = [e.to_dict(include_temporal=True) for e in edges]

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

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        """Définit ou synchronise l'ontologie des types d'entités du graphe (no-op en v1, ADR 0003)."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not isinstance(ontology, dict):
            raise GraphValidationError("L'ontologie doit être un dictionnaire")
        target_graph_id = graph_id.strip()
        logger.debug(
            "set_ontology appelé pour le graphe %s (no-op en v1 conformément à l'ADR 0003)",
            target_graph_id,
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
        """Ajoute un épisode textuel unitaire au graphe avec partitionnement group_id."""
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not isinstance(text, str) or not text.strip():
            raise GraphValidationError("Le contenu textuel de l'épisode est requis")
        if metadata is not None and not isinstance(metadata, dict):
            raise GraphValidationError("metadata doit être un dictionnaire")

        target_graph_id = graph_id.strip()
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

            res = self._run_async(
                self._graphiti.add_episode(
                    name=episode_name,
                    episode_body=text.strip(),
                    source=EpisodeType.text,
                    source_description=src_desc,
                    reference_time=ref_time,
                    group_id=target_graph_id,
                )
            )

            ep_uuid = None
            if hasattr(res, "episode") and getattr(res, "episode") is not None:
                ep_obj = getattr(res, "episode")
                ep_uuid = getattr(ep_obj, "uuid", None)
            if not ep_uuid and hasattr(res, "uuid"):
                ep_uuid = getattr(res, "uuid")
            if not ep_uuid and isinstance(res, dict):
                ep_uuid = res.get("uuid")
            if not ep_uuid:
                ep_uuid = uuid.uuid4().hex

            return EpisodeRecord(
                uuid=str(ep_uuid),
                graph_id=target_graph_id,
                processed=True,
                created_at=ref_time.isoformat(),
            )

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
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

        total_chunks = len(chunks)
        batch_id = f"batch_{uuid.uuid4().hex[:16]}"
        payload_hash = hashlib.sha256("\0".join(chunks).encode("utf-8")).hexdigest()
        operation_id = hashlib.sha256(
            f"{target_graph_id}:{payload_hash}".encode("utf-8")
        ).hexdigest()

        with self._translate_errors(f"ingestion par lots pour {target_graph_id}"):
            episode_uuids: List[str] = []
            for idx, chunk in enumerate(chunks, 1):
                if progress_callback:
                    progress_callback("processing", idx - 1, total_chunks)

                record = self.add_episode(
                    graph_id=target_graph_id,
                    text=chunk,
                    source_description=f"chunk_{idx}",
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
            {k: v for k, v in raw_attrs.items() if k not in cls._NODE_SYSTEM_KEYS}
            if isinstance(raw_attrs, dict)
            else {}
        )
        raw_created_at = cls._get_record_field(record, "created_at", None)
        created_at_str = str(raw_created_at) if raw_created_at is not None else None

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
            {k: v for k, v in raw_attrs.items() if k not in cls._EDGE_SYSTEM_KEYS}
            if isinstance(raw_attrs, dict)
            else {}
        )

        raw_created_at = cls._get_record_field(record, "created_at", None)
        raw_valid_at = cls._get_record_field(record, "valid_at", None)
        raw_invalid_at = cls._get_record_field(record, "invalid_at", None)
        raw_expired_at = cls._get_record_field(record, "expired_at", None)

        if include_temporal:
            created_at_str = str(raw_created_at) if raw_created_at is not None else None
            valid_at_str = str(raw_valid_at) if raw_valid_at is not None else None
            invalid_at_str = str(raw_invalid_at) if raw_invalid_at is not None else None
            expired_at_str = str(raw_expired_at) if raw_expired_at is not None else None
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
