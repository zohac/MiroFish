"""Implémentation ZepGraphStore encapsulant le SDK Zep Cloud."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import time
from typing import Any, Callable, Dict, List, Optional
import uuid
import warnings

import httpx
from pydantic import Field
from zep_cloud import BatchAddItem, EntityEdgeSourceTarget, NotFoundError
from zep_cloud.client import Zep
from zep_cloud.core.api_error import ApiError as ZepApiError
from zep_cloud.external_clients.ontology import (
    EdgeModel,
    EntityModel,
    EntityText,
)


from ..logger import get_logger
from ..ontology import (
    MAX_ONTOLOGY_TYPES,
    is_valid_ontology_name,
    normalize_ontology_attributes,
    normalize_ontology_source_targets,
    safe_ontology_attribute_name,
)
from .ontology_pydantic import valider_nom_de_type
from ..zep import (
    call_zep_read_with_retry,
    get_zep_client,
    is_retryable_zep_error,
    normalize_zep_search_limit,
    normalize_zep_search_query,
)
from ..zep_paging import fetch_all_edges, fetch_all_nodes
from .base import (
    AppliedOntology,
    BatchSubmissionRecord,
    EpisodeRecord,
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphSearchResult,
    GraphStore,
    ProvenanceOrigin,
    ProvenanceRecord,
    validate_chunk_metadata,
)
from .errors import (
    GraphConnectionError,
    GraphNotFoundError,
    GraphStoreError,
    GraphTimeoutError,
    GraphValidationError,
    OntologyValidationError,
)

logger = get_logger("mirofish.graph_store.zep")


def _declared_entity_type_names(ontology: Dict[str, Any]) -> List[str]:
    """Noms des types d'entité réellement transmis à Zep, dans l'ordre déclaré.

    Une entrée inutilisable — chaîne vide, dictionnaire sans nom — n'est jamais
    transmise, donc elle ne doit pas non plus figurer dans l'empreinte utilisée
    pour éviter de réappliquer une ontologie déjà posée (ADR 0014 §2).
    """
    return _declared_names(ontology.get("entity_types", []))


def _declared_edge_type_names(ontology: Dict[str, Any]) -> List[str]:
    """Noms des types de relation réellement transmis à Zep."""
    return _declared_names(ontology.get("edge_types", []))


def _declared_names(raw_types: Any) -> List[str]:
    """Noms exploits d'une liste de types, chaîne ou dictionnaire."""
    if not isinstance(raw_types, list):
        return []

    names: List[str] = []
    for type_def in raw_types[:MAX_ONTOLOGY_TYPES]:
        if isinstance(type_def, str):
            name = type_def.strip()
        elif isinstance(type_def, dict):
            name = str(type_def.get("name", "")).strip()
        else:
            continue
        if name:
            names.append(name)
    return names


class ZepGraphStore(GraphStore):
    """Magasin de graphe de connaissances s'appuyant sur l'infrastructure Zep Cloud."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        client: Optional[Zep] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """Initialise le magasin ZepGraphStore avec injection ou création du client.

        Args:
            api_key: Clé API Zep Cloud optionnelle (si omise, utilise Config.ZEP_API_KEY).
            client: Instance préconfigurée ou mockée de Zep (injection pour tests).
            timeout: Délai HTTP par requête en secondes.
        """
        if client is not None:
            self._client = client
        else:
            try:
                self._client = get_zep_client(api_key=api_key, timeout=timeout)
            except ValueError as exc:
                raise GraphValidationError(str(exc)) from exc
            except Exception as exc:
                raise GraphStoreError(f"Échec d'initialisation du client Zep : {exc}") from exc

        # Ontologies effectivement posées, par `graph_id` (ADR 0014 §2). Mémorisées
        # sur l'instance : Zep les applique de son côté, le store ne mémorise que
        # ce qu'il a transmis, pour ne pas réappliquer la même ontologie à chaque
        # fragment d'un lot.
        self._applied_ontologies: Dict[str, AppliedOntology] = {}

    @staticmethod
    def _translate_error(error: Exception, operation_name: str) -> GraphStoreError:
        """Traduit une exception Zep, HTTPX ou système vers la hiérarchie GraphStoreError."""
        if isinstance(error, GraphStoreError):
            return error

        if isinstance(error, NotFoundError):
            return GraphNotFoundError(f"Ressource introuvable lors de {operation_name}: {error}")

        if isinstance(error, ZepApiError):
            code = getattr(error, "status_code", None)
            if code == 404:
                return GraphNotFoundError(f"Ressource introuvable lors de {operation_name}: {error}")
            if code in (502, 503, 504):
                return GraphConnectionError(
                    f"Échec de connexion Zep Cloud (HTTP {code}) lors de {operation_name}: {error}"
                )
            if code == 408:
                return GraphTimeoutError(
                    f"Délai d'attente Zep dépassé (HTTP 408) lors de {operation_name}: {error}"
                )
            if code in (400, 422):
                return GraphValidationError(
                    f"Paramètres invalides pour Zep Cloud (HTTP {code}) lors de {operation_name}: {error}"
                )
            return GraphStoreError(
                f"Erreur API Zep Cloud (HTTP {code}) lors de {operation_name}: {error}"
            )

        if isinstance(error, (httpx.TimeoutException, TimeoutError)):
            return GraphTimeoutError(f"Délai d'attente dépassé lors de {operation_name}: {error}")

        if isinstance(error, (httpx.ConnectError, httpx.NetworkError, ConnectionError, OSError)):
            return GraphConnectionError(f"Erreur réseau Zep lors de {operation_name}: {error}")


        if isinstance(error, (ValueError, TypeError)):
            return GraphValidationError(f"Paramètre invalide lors de {operation_name}: {error}")

        return GraphStoreError(f"Erreur inattendue lors de {operation_name}: {error}")

    @contextmanager
    def _translate_errors(self, operation_name: str):
        """Gestionnaire de contexte traduisant systématiquement toutes les erreurs."""
        try:
            yield
        except Exception as exc:
            raise self._translate_error(exc, operation_name) from exc

    # --- Cycle de vie ---

    def create_graph(self, name: str, graph_id: Optional[str] = None) -> str:
        """Crée un graphe Zep avec réconciliation de création et tolérance aux pannes."""
        if not name or not name.strip():
            raise GraphValidationError("Le nom du graphe ne peut pas être vide")
        if graph_id is not None and not graph_id.strip():
            raise GraphValidationError("graph_id ne peut pas être une chaîne vide")

        target_graph_id = graph_id.strip() if graph_id else f"mirofish_{uuid.uuid4().hex[:16]}"
        with self._translate_errors(f"création du graphe {target_graph_id}"):
            try:
                self._client.graph.create(
                    graph_id=target_graph_id,
                    name=name,
                    description="MiroFish Social Simulation Graph",
                )
            except Exception as error:
                if not is_retryable_zep_error(error):
                    raise
                reconciliation_error = None
                for attempt in range(3):
                    try:
                        call_zep_read_with_retry(
                            lambda: self._client.graph.get(target_graph_id),
                            operation_name=f"reconcile graph create {target_graph_id}",
                        )
                        reconciliation_error = None
                        break
                    except (NotFoundError, ZepApiError) as nf:
                        status_code = getattr(nf, "status_code", None)
                        if isinstance(nf, NotFoundError) or status_code == 404:
                            reconciliation_error = nf
                            if attempt < 2:
                                time.sleep(attempt + 1)
                        else:
                            reconciliation_error = nf
                            break
                    except Exception as read_error:
                        reconciliation_error = read_error
                        break
                if reconciliation_error is not None:
                    raise error from reconciliation_error

            return target_graph_id

    def delete_graph(self, graph_id: str) -> None:
        """Supprime un graphe Zep Cloud."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        with self._translate_errors(f"suppression du graphe {graph_id}"):
            self._client.graph.delete(graph_id=graph_id)

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """Retourne la totalité des nœuds, arêtes et statistiques compatibles API/UI."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        with self._translate_errors(f"récupération des données du graphe {graph_id}"):
            nodes = fetch_all_nodes(self._client, graph_id)
            edges = fetch_all_edges(self._client, graph_id)

            node_map: Dict[str, str] = {}
            for node in nodes:
                node_uuid = getattr(node, "uuid_", None) or getattr(node, "uuid", "") or ""
                node_map[node_uuid] = getattr(node, "name", "") or ""

            nodes_data: List[Dict[str, Any]] = []
            for node in nodes:
                node_uuid = getattr(node, "uuid_", None) or getattr(node, "uuid", "") or ""
                created_at = getattr(node, "created_at", None)
                nodes_data.append(
                    {
                        "uuid": node_uuid,
                        "name": getattr(node, "name", "") or "",
                        "labels": list(getattr(node, "labels", []) or []),
                        "summary": getattr(node, "summary", "") or "",
                        "attributes": dict(getattr(node, "attributes", {}) or {}),
                        "created_at": str(created_at) if created_at else None,
                        "related_edges": [],
                        "related_nodes": [],
                    }
                )

            edges_data: List[Dict[str, Any]] = []
            for edge in edges:
                edge_uuid = getattr(edge, "uuid_", None) or getattr(edge, "uuid", "") or ""
                name_val = getattr(edge, "name", "") or ""
                fact_val = getattr(edge, "fact", "") or ""
                fact_type = getattr(edge, "fact_type", None) or name_val
                src_uuid = getattr(edge, "source_node_uuid", "") or ""
                tgt_uuid = getattr(edge, "target_node_uuid", "") or ""

                created_at = getattr(edge, "created_at", None)
                valid_at = getattr(edge, "valid_at", None)
                invalid_at = getattr(edge, "invalid_at", None)
                expired_at = getattr(edge, "expired_at", None)

                episodes = getattr(edge, "episodes", None) or getattr(edge, "episode_ids", None)
                if episodes and not isinstance(episodes, list):
                    episodes_list = [str(episodes)]
                elif episodes:
                    episodes_list = [str(e) for e in episodes]
                else:
                    episodes_list = []

                edges_data.append(
                    {
                        "uuid": edge_uuid,
                        "name": name_val,
                        "fact": fact_val,
                        "fact_type": fact_type,
                        "source_node_uuid": src_uuid,
                        "target_node_uuid": tgt_uuid,
                        "source_node_name": node_map.get(src_uuid, ""),
                        "target_node_name": node_map.get(tgt_uuid, ""),
                        "attributes": dict(getattr(edge, "attributes", {}) or {}),
                        "created_at": str(created_at) if created_at else None,
                        "valid_at": str(valid_at) if valid_at else None,
                        "invalid_at": str(invalid_at) if invalid_at else None,
                        "expired_at": str(expired_at) if expired_at else None,
                        "episodes": episodes_list,
                    }
                )

            return {
                "graph_id": graph_id,
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
        """Retourne les métadonnées et statistiques globales d'un graphe."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        with self._translate_errors(f"récupération des informations du graphe {graph_id}"):
            nodes = fetch_all_nodes(self._client, graph_id)
            edges = fetch_all_edges(self._client, graph_id)

            entity_types: set[str] = set()
            for node in nodes:
                labels = getattr(node, "labels", []) or []
                for label in labels:
                    if label and isinstance(label, str) and label not in ["Entity", "Node"]:
                        entity_types.add(label)

            return GraphInfo(
                graph_id=graph_id,
                node_count=len(nodes),
                edge_count=len(edges),
                entity_types=sorted(list(entity_types)),
            )

    # --- Ontologie ---

    def set_ontology(
        self, graph_id: str, ontology: Dict[str, Any], *, strict: bool = False
    ) -> None:
        """Configure l'ontologie des types d'entités et d'arêtes pour un graphe Zep.

        Zep Cloud applique l'ontologie **côté serveur** : il n'existe pas de
        paramètre d'ontologie par épisode. La seule façon d'en consommer une à
        l'écriture est donc de l'appliquer au graphe avant d'ajouter l'épisode —
        ce que fait `add_episode` quand une ontologie lui est confiée.

        `strict` est mémorisé et documenté, pas appliqué : le refus effectif d'un
        type hors ontologie est l'objet de la story 007-2 (ADR 0014).
        """
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not isinstance(ontology, dict):
            raise GraphValidationError("L'ontologie doit être un dictionnaire")
        target_graph_id = graph_id.strip()

        # La validation de noms et de cardinalité est **partagée** avec
        # GraphitiGraphStore : les deux implémentations doivent refuser la même
        # entrée pour la même raison (ADR 0014 §2). Zep n'écrit pas les mêmes
        # labels Cypher, mais un nom qui ne serait pas un identifiant produirait
        # chez lui la même erreur, en plus loin.
        entity_type_names = _declared_entity_type_names(ontology)
        edge_type_names = _declared_edge_type_names(ontology)
        if not entity_type_names and not edge_type_names:
            raise OntologyValidationError(
                "Ontologie refusée : aucun type d'entité ni type de relation "
                "exploitable"
            )

        with self._translate_errors(f"définition de l'ontologie pour {target_graph_id}"):
            warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

            entity_types: Dict[str, Any] = {}
            for entity_def in ontology.get("entity_types", [])[:MAX_ONTOLOGY_TYPES]:
                if isinstance(entity_def, str):
                    name = entity_def.strip()
                    if not name:
                        continue
                    description = f"A {name} entity."
                    raw_attrs = []
                elif isinstance(entity_def, dict):
                    name = str(entity_def.get("name", "")).strip()
                    if not name:
                        continue
                    description = entity_def.get("description", f"A {name} entity.")
                    raw_attrs = entity_def.get("attributes", [])
                else:
                    continue

                valider_nom_de_type(name, "type")

                attrs = {"__doc__": description}
                annotations: Dict[str, Any] = {}

                for normalized in normalize_ontology_attributes(raw_attrs):
                    attr_name = safe_ontology_attribute_name(normalized["name"])
                    if not is_valid_ontology_name(attr_name):
                        raise OntologyValidationError(
                            f"L'attribut '{normalized['name']}' du type '{name}' "
                            "n'est pas un identifiant valide"
                        )
                    attr_desc = normalized["description"]
                    attrs[attr_name] = Field(description=attr_desc, default=None)
                    annotations[attr_name] = Optional[EntityText]

                attrs["__annotations__"] = annotations
                entity_class = type(name, (EntityModel,), attrs)
                entity_class.__doc__ = description
                entity_types[name] = entity_class

            edge_definitions: Dict[str, Any] = {}
            for edge_def in ontology.get("edge_types", [])[:MAX_ONTOLOGY_TYPES]:
                if isinstance(edge_def, str):
                    name = edge_def.strip()
                    if not name:
                        continue
                    description = f"A {name} relationship."
                    raw_attrs = []
                    raw_source_targets = []
                elif isinstance(edge_def, dict):
                    name = str(edge_def.get("name", "")).strip()
                    if not name:
                        continue
                    description = edge_def.get("description", f"A {name} relationship.")
                    raw_attrs = edge_def.get("attributes", [])
                    raw_source_targets = edge_def.get("source_targets", [])
                else:
                    continue

                valider_nom_de_type(name, "relation")

                attrs = {"__doc__": description}
                annotations = {}

                for normalized in normalize_ontology_attributes(raw_attrs):
                    attr_name = safe_ontology_attribute_name(normalized["name"])
                    if not is_valid_ontology_name(attr_name):
                        raise OntologyValidationError(
                            f"L'attribut '{normalized['name']}' de la relation "
                            f"'{name}' n'est pas un identifiant valide"
                        )
                    attr_desc = normalized["description"]
                    attrs[attr_name] = Field(description=attr_desc, default=None)
                    annotations[attr_name] = Optional[str]

                attrs["__annotations__"] = annotations
                class_name = "".join(word.capitalize() for word in name.split("_"))
                edge_class = type(class_name, (EdgeModel,), attrs)
                edge_class.__doc__ = description

                source_targets: List[EntityEdgeSourceTarget] = []
                for st in normalize_ontology_source_targets(raw_source_targets):
                    source_targets.append(
                        EntityEdgeSourceTarget(
                            source=st.get("source", "Entity"),
                            target=st.get("target", "Entity"),
                        )
                    )

                if not source_targets:
                    source_targets.append(
                        EntityEdgeSourceTarget(source="Entity", target="Entity")
                    )

                edge_definitions[name] = (edge_class, source_targets)

            if entity_types or edge_definitions:
                self._client.graph.set_ontology(
                    graph_ids=[target_graph_id],
                    entities=entity_types,
                    edges=edge_definitions if edge_definitions else None,
                )
                self._applied_ontologies[target_graph_id] = AppliedOntology(
                    entity_type_names=tuple(entity_type_names),
                    edge_type_names=tuple(edge_type_names),
                    strict=bool(strict),
                )
                logger.debug(
                    "set_ontology : %d type(s) d'entité et %d type(s) de relation "
                    "posés sur le graphe Zep %s (strict=%s, ADR 0014)",
                    len(entity_type_names),
                    len(edge_type_names),
                    target_graph_id,
                    bool(strict),
                )

    def get_applied_ontology(self, graph_id: str) -> Optional[AppliedOntology]:
        """Ontologie en vigueur sur ce graphe Zep, décrite de façon neutre.

        Les noms sont conservés plutôt que les classes : Zep applique l'ontologie
        de son côté, le store n'a donc rien à construire pour la rappeler, et
        rien à refaire si le SDK change sa représentation interne (ADR 0014 §2).
        """
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        return self._applied_ontologies.get(graph_id.strip())

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
        """Ajoute un épisode textuel unitaire au graphe Zep.

        Zep n'a pas d'ontologie par épisode : si une ontologie est fournie ou
        déjà posée pour ce graphe, elle est appliquée au graphe **avant** l'ajout,
        pour que l'extraction distant s'exécute sous ces types (ADR 0014 §2).
        """
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not text or not text.strip():
            raise GraphValidationError("Le contenu textuel de l'épisode est requis")
        if metadata is not None and not isinstance(metadata, dict):
            raise GraphValidationError("metadata doit être un dictionnaire")

        target_graph_id = graph_id.strip()
        self._apply_ontology_for_episode(target_graph_id, ontology)

        with self._translate_errors(f"ajout d'épisode dans le graphe {target_graph_id}"):
            episode = self._client.graph.add(
                graph_id=target_graph_id,
                type="text",
                data=text,
                created_at=created_at,
                source_description=source_description or "MiroFish episode",
                metadata=metadata or {},
            )
            ep_uuid = getattr(episode, "uuid_", None) or getattr(episode, "uuid", None)
            if not ep_uuid:
                raise GraphStoreError("Zep n'a retourné aucun identifiant d'épisode")
            is_processed = bool(getattr(episode, "processed", False))
            ep_created_at = getattr(episode, "created_at", None)
            return EpisodeRecord(
                uuid=str(ep_uuid),
                graph_id=target_graph_id,
                processed=is_processed,
                created_at=str(ep_created_at) if ep_created_at else created_at,
            )

    def _apply_ontology_for_episode(
        self, graph_id: str, ontology: Optional[Dict[str, Any]]
    ) -> None:
        """Applique au graphe Zep l'ontologie effective de l'épisode à venir.

        Zep applique l'ontologie au graphe, pas à l'épisode : c'est donc le seul
        geste possible. Elle est appliquée une seule fois par ontologie distincte
        — un lot de fragments ne doit pas multiplier les appels distants, et
        l'idempotence de `set_ontology` côté Zep rend l'opération sans risque.
        """
        if ontology is None:
            return
        if not isinstance(ontology, dict):
            raise GraphValidationError("L'ontologie doit être un dictionnaire")

        # L'empreinte couvre les **relations** aussi : deux ontologies qui
        # déclarent les mêmes entités mais des relations différentes sont deux
        # ontologies, et ne pas les distinguer reviendrait à n'appliquer que la
        # première en silence.
        fingerprint = (
            tuple(_declared_entity_type_names(ontology)),
            tuple(_declared_edge_type_names(ontology)),
        )
        if fingerprint == ((), ()):
            return

        appliquee = self._applied_ontologies.get(graph_id)
        if appliquee is not None:
            courante = (appliquee.entity_type_names, appliquee.edge_type_names)
            if courante == fingerprint:
                return

        self.set_ontology(graph_id, ontology)

    def _find_batch_by_operation_id(
        self,
        graph_id: str,
        operation_id: str,
        *,
        max_attempts: int = 3,
    ) -> Any | None:
        """Retrouve un lot créé côté serveur lors d'une réponse de création ambiguë."""
        for attempt in range(1, max_attempts + 1):
            matches: List[Any] = []
            cursor: int | None = None
            seen_cursors: set[int] = set()
            while True:
                page = call_zep_read_with_retry(
                    lambda: self._client.batch.list(limit=100, cursor=cursor),
                    operation_name=f"reconcile batch create {operation_id}",
                )
                for batch in getattr(page, "batches", None) or []:
                    metadata = getattr(batch, "metadata", None) or {}
                    if (
                        metadata.get("mirofish_operation_id") == operation_id
                        and metadata.get("graph_id") == graph_id
                    ):
                        matches.append(batch)
                next_cursor = getattr(page, "next_cursor", None)
                if next_cursor is None:
                    break
                if next_cursor == cursor or next_cursor in seen_cursors:
                    raise RuntimeError("Zep batch list cursor did not advance")
                seen_cursors.add(next_cursor)
                cursor = next_cursor

            if len(matches) > 1:
                raise RuntimeError(
                    f"Plusieurs lots Zep correspondent à l'opération {operation_id}"
                )
            if matches:
                return matches[0]
            if attempt < max_attempts:
                time.sleep(attempt)
        return None

    def _list_batch_items(self, batch_id: str) -> List[Any]:
        """Liste exhaustivement les éléments d'un lot Zep par curseurs."""
        items: List[Any] = []
        cursor: int | None = None
        seen_cursors: set[int] = set()
        while True:
            page = call_zep_read_with_retry(
                lambda: self._client.batch.list_items(
                    batch_id=batch_id,
                    limit=100,
                    cursor=cursor,
                ),
                operation_name=f"list batch items {batch_id}",
            )
            items.extend(getattr(page, "items", None) or [])
            next_cursor = getattr(page, "next_cursor", None)
            if next_cursor is None:
                break
            if next_cursor == cursor or next_cursor in seen_cursors:
                raise RuntimeError(f"Zep batch {batch_id} item cursor did not advance")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        return items

    def _reconcile_batch_item_count(
        self,
        batch_id: str,
        expected_item_count: int,
        *,
        max_attempts: int = 3,
    ) -> List[Any]:
        """Attend la propagation d'éléments d'un lot Zep après un ajout ambigu."""
        items: List[Any] = []
        for attempt in range(1, max_attempts + 1):
            items = self._list_batch_items(batch_id)
            if len(items) >= expected_item_count:
                return items
            if attempt < max_attempts:
                time.sleep(attempt)
        return items

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        chunk_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> BatchSubmissionRecord:
        """Ingère des fragments textuels par lots via l'API Zep Batch."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not chunks:
            raise GraphValidationError("Au moins un fragment de texte est requis")
        if not 1 <= batch_size <= 350:
            raise GraphValidationError("batch_size doit être compris entre 1 et 350")
        if len(chunks) > 50_000:
            raise GraphValidationError("Un lot ne peut pas contenir plus de 50 000 éléments")
        oversized = [index for index, chunk in enumerate(chunks) if len(chunk) > 10_000]
        if oversized:
            raise GraphValidationError(
                f"Le fragment {oversized[0]} dépasse la limite de 10 000 caractères"
            )

        # Validation partagée avec Graphiti, avant toute écriture (ADR 0012 §1).
        metadata_entries = validate_chunk_metadata(chunks, chunk_metadata)

        total_chunks = len(chunks)
        operation_id = self._build_operation_id(graph_id, chunks, metadata_entries)

        with self._translate_errors(f"soumission par lot pour {graph_id}"):
            try:
                batch = self._client.batch.create(
                    metadata={
                        "mirofish_operation_id": operation_id,
                        "graph_id": graph_id,
                        "chunk_count": total_chunks,
                    }
                )
            except Exception as error:
                if not is_retryable_zep_error(error):
                    raise
                batch = self._find_batch_by_operation_id(graph_id, operation_id)
                if batch is None:
                    raise RuntimeError(
                        "Création de lot Zep non confirmée et aucun lot correspondant trouvé"
                    ) from error

            batch_id = getattr(batch, "batch_id", None)
            if not batch_id:
                raise GraphStoreError("L'API Zep Batch n'a retourné aucun batch_id")

            episode_uuids: List[str] = []
            for i in range(0, total_chunks, batch_size):
                batch_chunks = chunks[i : i + batch_size]
                current_count = i + len(batch_chunks)
                if progress_callback:
                    progress_callback("sending", current_count, total_chunks)

                items = [
                    self._build_batch_item(
                        graph_id=graph_id,
                        chunk=chunk,
                        operation_id=operation_id,
                        sequence_index=i + offset,
                        metadata_entry=(
                            metadata_entries[i + offset] if metadata_entries else None
                        ),
                    )
                    for offset, chunk in enumerate(batch_chunks)
                ]

                expected_item_count = i + len(items)
                try:
                    item_details = self._client.batch.add(
                        batch_id=batch_id,
                        items=items,
                    )
                except Exception as e:
                    if is_retryable_zep_error(e):
                        recovered_items = self._reconcile_batch_item_count(
                            batch_id,
                            expected_item_count,
                        )
                        recovered_indexes = {
                            getattr(item, "sequence_index", None)
                            for item in recovered_items
                        }
                        if (
                            len(recovered_items) == expected_item_count
                            and recovered_indexes == set(range(expected_item_count))
                        ):
                            item_details = recovered_items[i:expected_item_count]
                        else:
                            raise RuntimeError(
                                f"Échec non réconciliable de soumission d'éléments dans le lot {batch_id}"
                            ) from e
                    else:
                        raise RuntimeError(f"Échec d'ajout d'éléments dans le lot {batch_id}") from e

                if len(item_details or []) != len(items):
                    recovered_items = self._reconcile_batch_item_count(
                        batch_id,
                        expected_item_count,
                    )
                    recovered_indexes = {
                        getattr(item, "sequence_index", None)
                        for item in recovered_items
                    }
                    if (
                        len(recovered_items) == expected_item_count
                        and recovered_indexes == set(range(expected_item_count))
                    ):
                        item_details = recovered_items[i:expected_item_count]
                    else:
                        raise RuntimeError(
                            f"Lot Zep {batch_id} : {len(item_details or [])} sur {len(items)} éléments confirmés"
                        )

                for item in item_details:
                    ep_uuid = getattr(item, "episode_uuid", None)
                    if ep_uuid:
                        episode_uuids.append(ep_uuid)

            try:
                self._client.batch.process(batch_id=batch_id)
            except Exception as error:
                summary = call_zep_read_with_retry(
                    lambda: self._client.batch.get(batch_id=batch_id),
                    operation_name=f"reconcile batch {batch_id}",
                )
                if getattr(summary, "status", None) in {None, "draft"}:
                    raise RuntimeError(f"Traitement du lot Zep {batch_id} non confirmé") from error

            return BatchSubmissionRecord(
                batch_id=batch_id,
                operation_id=operation_id,
                episode_uuids=episode_uuids,
                item_count=total_chunks,
            )

    @staticmethod
    def _build_operation_id(
        graph_id: str,
        chunks: List[str],
        metadata_entries: List[Dict[str, Any]],
    ) -> str:
        """Identifiant déterministe d'opération.

        Sans provenance, le hachage est **inchangé** : un lot Zep déjà persisté
        dans `project.json` et repris après redémarrage reste reconnaissable
        (ADR 0012 §1). Avec provenance, les métadonnées entrent dans le hachage.
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

    @staticmethod
    def _build_batch_item(
        *,
        graph_id: str,
        chunk: str,
        operation_id: str,
        sequence_index: int,
        metadata_entry: Optional[Dict[str, Any]],
    ) -> "BatchAddItem":
        """Construit un élément de lot Zep, avec ou sans provenance.

        Les clés historiques (`chunk_index` global, `chunk_sha256`) sont
        conservées telles quelles : elles servent à la réconciliation. Avec
        provenance, `chunk_index` **local au document** est ajouté sous le nom
        `source_chunk_index`, pour que les deux index ne se confondent pas.
        """
        metadata: Dict[str, Any] = {
            "mirofish_operation_id": operation_id,
            "chunk_index": sequence_index,
            "chunk_sha256": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
        }
        source_description = "MiroFish source document chunk"

        if metadata_entry:
            for key, value in metadata_entry.items():
                if key == "chunk_index":
                    metadata["source_chunk_index"] = value
                    continue
                metadata[key] = value
            source_description = (
                f"{metadata_entry['source_filename']}#"
                f"{metadata_entry['chunk_index']} [{metadata_entry['source_role']}]"
            )

        return BatchAddItem(
            type="graph_episode",
            graph_id=graph_id,
            data=chunk,
            data_type="text",
            source_description=source_description,
            metadata=metadata,
        )

    # --- Provenance des faits ---

    def get_edge_provenance(self, graph_id: str, edge_uuid: str) -> List[ProvenanceRecord]:
        """Résout les origines documentaires d'une arête Zep, dans un graphe donné.

        Zep n'expose pas « get edge by uuid **dans** un graphe ». Lire l'arête
        à l'aveugle par UUID ferait fuiter une arête d'un autre graphe, donc la
        lecture passe par `get_by_graph_id` filtré sur les UUID (ADR 0012 §4).
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
            from zep_cloud import SearchFilters

            matches = call_zep_read_with_retry(
                lambda: self._client.graph.edge.get_by_graph_id(
                    graph_id=target_graph_id,
                    filters=SearchFilters(edge_uuids=[target_edge_uuid]),
                    limit=2,
                ),
                operation_name=f"get_edge_provenance {target_edge_uuid}",
            )
            edges = list(matches or [])
            if not edges:
                return []

            raw_refs = getattr(edges[0], "episodes", None) or []
            episode_uuids = [str(value) for value in raw_refs if value]
            if not episode_uuids:
                return []

            return [
                self._load_episode_record(episode_uuid)
                for episode_uuid in episode_uuids
            ]

    def _load_episode_record(self, episode_uuid: str) -> ProvenanceRecord:
        """Charge un épisode Zep et le classe selon son origine réelle.

        Seul un épisode réellement absent (`NotFoundError`) devient une référence
        non résolue. Une panne de lecture (réseau, authentification) **remonte**
        en `GraphStoreError` : l'appelant doit pouvoir distinguer « cette
        référence n'existe pas » d'une panne du store (ADR 0012 §3).

        L'isolation tient à l'appelant : `get_edge_provenance` n'énumère que les
        épisodes d'une arête obtenue par `get_by_graph_id(graph_id)`. Zep n'offre
        pas de « get episode **dans** un graphe », donc la borne de graphe vient
        de l'arête, et un épisode d'un autre graphe ne peut pas être atteint par
        ce chemin.
        """
        try:
            episode = call_zep_read_with_retry(
                lambda: self._client.graph.episode.get(episode_uuid),
                operation_name=f"get_episode {episode_uuid}",
            )
        except NotFoundError:
            return ProvenanceRecord(
                episode_uuid=episode_uuid,
                resolved=False,
                origin=ProvenanceOrigin.UNRESOLVED,
                missing_reason="Zep ne retourne aucun épisode pour cet UUID",
            )
        except ZepApiError as error:
            if getattr(error, "status_code", None) == 404:
                return ProvenanceRecord(
                    episode_uuid=episode_uuid,
                    resolved=False,
                    origin=ProvenanceOrigin.UNRESOLVED,
                    missing_reason="Zep ne retourne aucun épisode pour cet UUID (HTTP 404)",
                )
            raise

        raw_metadata = getattr(episode, "metadata", None) or {}
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        return self._classify_episode(episode_uuid, episode, metadata)

    @staticmethod
    def _classify_episode(
        episode_uuid: str,
        episode: Any,
        metadata: Dict[str, Any],
    ) -> ProvenanceRecord:
        """Classe un épisode Zep selon la même taxonomie que Graphiti."""

        def _str_or_none(value: Any) -> Any:
            if value is None:
                return None
            text = str(value)
            return text if text else None

        def _int_or_none(value: Any) -> Any:
            if value is None or isinstance(value, bool):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        document_id = _str_or_none(metadata.get("source_document_id"))
        simulation_id = _str_or_none(metadata.get("simulation_id"))

        if simulation_id:
            origin = ProvenanceOrigin.SIMULATION
        elif document_id:
            origin = ProvenanceOrigin.DOCUMENT
        else:
            origin = ProvenanceOrigin.LEGACY

        missing_reason = None
        if origin is ProvenanceOrigin.DOCUMENT:
            required = {
                "source_filename": _str_or_none(metadata.get("source_filename")),
                "source_role": _str_or_none(metadata.get("source_role")),
                "chunk_index": _int_or_none(
                    metadata.get("source_chunk_index", metadata.get("chunk_index"))
                ),
                "char_start": _int_or_none(metadata.get("char_start")),
                "char_end": _int_or_none(metadata.get("char_end")),
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
            source_filename=_str_or_none(metadata.get("source_filename")),
            source_role=_str_or_none(metadata.get("source_role")),
            chunk_index=_int_or_none(
                metadata.get("source_chunk_index", metadata.get("chunk_index"))
            ),
            char_start=_int_or_none(metadata.get("char_start")),
            char_end=_int_or_none(metadata.get("char_end")),
            page=_int_or_none(metadata.get("page")),
            section=_str_or_none(metadata.get("section")),
            content=_str_or_none(getattr(episode, "content", None)),
            simulation_id=simulation_id,
            platform=_str_or_none(metadata.get("platform")),
            missing_reason=missing_reason,
        )

    def wait_for_batch(
        self,
        batch: BatchSubmissionRecord,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        timeout: float = 600.0,
    ) -> bool:
        """Attend la finalisation d'un lot d'ingestion avec gestion du timeout."""
        if not batch or not getattr(batch, "batch_id", None):
            raise GraphValidationError("batch et batch_id sont requis")
        if timeout <= 0:
            raise GraphValidationError("timeout doit être strictement supérieur à 0")

        start_time = time.time()
        terminal_states = {"succeeded", "partial", "failed", "invalid", "canceled"}

        with self._translate_errors(f"attente du lot {batch.batch_id}"):
            while True:
                if time.time() - start_time > timeout:
                    raise GraphTimeoutError(
                        f"Le lot Zep {batch.batch_id} n'a pas terminé dans le délai imparti ({timeout}s)"
                    )

                summary = call_zep_read_with_retry(
                    lambda: self._client.batch.get(batch_id=batch.batch_id),
                    operation_name=f"poll batch {batch.batch_id}",
                )
                status = getattr(summary, "status", None)
                progress = getattr(summary, "progress", None)
                percent = float(getattr(progress, "percent_complete", 0) or 0) / 100.0
                ratio = min(max(percent, 0.0), 1.0)
                if progress_callback:
                    progress_callback(str(status or "processing"), ratio)

                if status in terminal_states:
                    break
                time.sleep(1)

            if status != "succeeded":
                raise GraphStoreError(
                    f"Le lot Zep {batch.batch_id} s'est terminé avec le statut d'échec '{status}'"
                )

            if progress_callback:
                progress_callback("completed", 1.0)
            return True

    def wait_for_episodes(
        self,
        graph_id: str,
        episode_uuids: List[str],
        timeout: float = 600.0,
    ) -> bool:
        """Attend le traitement individuel d'une liste d'épisodes."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if timeout <= 0:
            raise GraphValidationError("timeout doit être strictement supérieur à 0")
        if not episode_uuids:
            return True

        start_time = time.time()
        pending_episodes = set(episode_uuids)

        with self._translate_errors(f"attente des épisodes du graphe {graph_id}"):
            while pending_episodes:
                if time.time() - start_time > timeout:
                    raise GraphTimeoutError(
                        f"Délai d'attente d'ingestion des épisodes dépassé ({len(pending_episodes)} en attente)"
                    )

                for ep_uuid in list(pending_episodes):
                    episode = call_zep_read_with_retry(
                        lambda: self._client.graph.episode.get(uuid_=ep_uuid),
                        operation_name=f"poll episode {ep_uuid}",
                    )
                    if getattr(episode, "processed", False):
                        pending_episodes.remove(ep_uuid)

                if pending_episodes:
                    time.sleep(1)

            return True

    # --- Lecture et parcours ---

    def get_all_nodes(self, graph_id: str) -> List[GraphNode]:
        """Récupère tous les nœuds d'un graphe via pagination Zep."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        with self._translate_errors(f"récupération de tous les nœuds de {graph_id}"):
            raw_nodes = fetch_all_nodes(self._client, graph_id)
            nodes: List[GraphNode] = []
            for node in raw_nodes:
                uuid_val = getattr(node, "uuid_", None) or getattr(node, "uuid", "") or ""
                created_at = getattr(node, "created_at", None)
                nodes.append(
                    GraphNode(
                        uuid=uuid_val,
                        name=getattr(node, "name", "") or "",
                        labels=list(getattr(node, "labels", []) or []),
                        summary=getattr(node, "summary", "") or "",
                        attributes=dict(getattr(node, "attributes", {}) or {}),
                        created_at=str(created_at) if created_at else None,
                        related_edges=[],
                        related_nodes=[],
                    )
                )
            return nodes

    def get_all_edges(
        self, graph_id: str, include_temporal: bool = True
    ) -> List[GraphEdge]:
        """Récupère toutes les arêtes d'un graphe via pagination Zep."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        with self._translate_errors(f"récupération de toutes les arêtes de {graph_id}"):
            raw_edges = fetch_all_edges(self._client, graph_id)
            edges: List[GraphEdge] = []
            for edge in raw_edges:
                name_val = getattr(edge, "name", "") or ""
                episodes = getattr(edge, "episodes", None) or getattr(edge, "episode_ids", None)
                if episodes and not isinstance(episodes, list):
                    episodes_list = [str(episodes)]
                elif episodes:
                    episodes_list = [str(e) for e in episodes]
                else:
                    episodes_list = []

                created_at = getattr(edge, "created_at", None)
                valid_at = getattr(edge, "valid_at", None)
                invalid_at = getattr(edge, "invalid_at", None)
                expired_at = getattr(edge, "expired_at", None)

                edges.append(
                    GraphEdge(
                        uuid=getattr(edge, "uuid_", None) or getattr(edge, "uuid", "") or "",
                        name=name_val,
                        fact=getattr(edge, "fact", "") or "",
                        source_node_uuid=getattr(edge, "source_node_uuid", "") or "",
                        target_node_uuid=getattr(edge, "target_node_uuid", "") or "",
                        fact_type=getattr(edge, "fact_type", None) or name_val,
                        attributes=dict(getattr(edge, "attributes", {}) or {}),
                        episodes=episodes_list,
                        created_at=str(created_at) if (include_temporal and created_at) else None,
                        valid_at=str(valid_at) if (include_temporal and valid_at) else None,
                        invalid_at=str(invalid_at) if (include_temporal and invalid_at) else None,
                        expired_at=str(expired_at) if (include_temporal and expired_at) else None,
                    )
                )
            return edges

    def get_node(self, graph_id: str, node_uuid: str) -> Optional[GraphNode]:
        """Récupère un nœud spécifique et enrichit ses arêtes connectées."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not node_uuid or not node_uuid.strip():
            raise GraphValidationError("node_uuid est requis")

        try:
            node = call_zep_read_with_retry(
                lambda: self._client.graph.node.get(uuid_=node_uuid),
                operation_name=f"get node {node_uuid}",
            )
        except (NotFoundError, ZepApiError) as exc:
            status_code = getattr(exc, "status_code", None)
            if isinstance(exc, NotFoundError) or status_code == 404:
                return None
            raise self._translate_error(exc, f"récupération du nœud {node_uuid}") from exc
        except Exception as exc:
            raise self._translate_error(exc, f"récupération du nœud {node_uuid}") from exc

        if not node:
            return None

        # Arêtes connectées au nœud
        edges = self.get_node_edges(graph_id, node_uuid)
        related_edges = [e.to_dict() for e in edges]

        created_at = getattr(node, "created_at", None)
        return GraphNode(
            uuid=getattr(node, "uuid_", None) or getattr(node, "uuid", "") or node_uuid,
            name=getattr(node, "name", "") or "",
            labels=list(getattr(node, "labels", []) or []),
            summary=getattr(node, "summary", "") or "",
            attributes=dict(getattr(node, "attributes", {}) or {}),
            created_at=str(created_at) if created_at else None,
            related_edges=related_edges,
            related_nodes=[],
        )

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[GraphEdge]:
        """Récupère les arêtes connectées à un nœud spécifique."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        if not node_uuid or not node_uuid.strip():
            raise GraphValidationError("node_uuid est requis")

        with self._translate_errors(f"récupération des arêtes du nœud {node_uuid}"):
            try:
                raw_edges = call_zep_read_with_retry(
                    lambda: self._client.graph.node.get_edges(node_uuid=node_uuid),
                    operation_name=f"get node edges {node_uuid}",
                )
            except (NotFoundError, ZepApiError) as exc:
                status_code = getattr(exc, "status_code", None)
                if isinstance(exc, NotFoundError) or status_code == 404:
                    return []
                raise

            edges: List[GraphEdge] = []
            for edge in raw_edges or []:
                name_val = getattr(edge, "name", "") or ""
                episodes = getattr(edge, "episodes", None) or getattr(edge, "episode_ids", None)
                if episodes and not isinstance(episodes, list):
                    episodes_list = [str(episodes)]
                elif episodes:
                    episodes_list = [str(e) for e in episodes]
                else:
                    episodes_list = []

                created_at = getattr(edge, "created_at", None)
                valid_at = getattr(edge, "valid_at", None)
                invalid_at = getattr(edge, "invalid_at", None)
                expired_at = getattr(edge, "expired_at", None)

                edges.append(
                    GraphEdge(
                        uuid=getattr(edge, "uuid_", None) or getattr(edge, "uuid", "") or "",
                        name=name_val,
                        fact=getattr(edge, "fact", "") or "",
                        source_node_uuid=getattr(edge, "source_node_uuid", "") or "",
                        target_node_uuid=getattr(edge, "target_node_uuid", "") or "",
                        fact_type=getattr(edge, "fact_type", None) or name_val,
                        attributes=dict(getattr(edge, "attributes", {}) or {}),
                        episodes=episodes_list,
                        created_at=str(created_at) if created_at else None,
                        valid_at=str(valid_at) if valid_at else None,
                        invalid_at=str(invalid_at) if invalid_at else None,
                        expired_at=str(expired_at) if expired_at else None,
                    )
                )
            return edges

    # --- Recherche ---

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
        reranker: Optional[str] = None,
    ) -> GraphSearchResult:
        """Effectue une recherche sémantique ou hybride et retourne un GraphSearchResult neutre."""
        if not graph_id or not graph_id.strip():
            raise GraphValidationError("graph_id est requis")
        try:
            norm_query = normalize_zep_search_query(query)
            norm_limit = normalize_zep_search_limit(limit)
        except ValueError as exc:
            raise GraphValidationError(str(exc)) from exc

        if scope not in ("edges", "nodes", "hybrid"):
            raise GraphValidationError(
                f"Périmètre de recherche invalide : '{scope}'. Valeurs acceptées : 'edges', 'nodes', 'hybrid'."
            )

        with self._translate_errors(f"recherche sémantique dans {graph_id}"):
            facts: List[str] = []
            nodes: List[GraphNode] = []
            edges: List[GraphEdge] = []

            search_kwargs: Dict[str, Any] = {
                "graph_id": graph_id,
                "query": norm_query,
                "limit": norm_limit,
            }
            if reranker is not None and reranker.strip():
                search_kwargs["reranker"] = reranker.strip()

            if scope in ("edges", "hybrid"):
                edge_kwargs = dict(search_kwargs)
                edge_kwargs["scope"] = "edges"
                edge_res = call_zep_read_with_retry(
                    lambda: self._client.graph.search(**edge_kwargs),
                    operation_name=f"search edges in {graph_id}",
                )
                for raw_edge in getattr(edge_res, "edges", None) or []:
                    fact_val = getattr(raw_edge, "fact", "") or ""
                    if fact_val:
                        facts.append(fact_val)
                    name_val = getattr(raw_edge, "name", "") or ""
                    created_at = getattr(raw_edge, "created_at", None)
                    valid_at = getattr(raw_edge, "valid_at", None)
                    invalid_at = getattr(raw_edge, "invalid_at", None)
                    expired_at = getattr(raw_edge, "expired_at", None)
                    episodes = getattr(raw_edge, "episodes", None) or getattr(raw_edge, "episode_ids", None)
                    if episodes and not isinstance(episodes, list):
                        episodes_list = [str(episodes)]
                    elif episodes:
                        episodes_list = [str(e) for e in episodes]
                    else:
                        episodes_list = []

                    edges.append(
                        GraphEdge(
                            uuid=getattr(raw_edge, "uuid_", None) or getattr(raw_edge, "uuid", "") or "",
                            name=name_val,
                            fact=fact_val,
                            source_node_uuid=getattr(raw_edge, "source_node_uuid", "") or "",
                            target_node_uuid=getattr(raw_edge, "target_node_uuid", "") or "",
                            fact_type=getattr(raw_edge, "fact_type", None) or name_val,
                            attributes=dict(getattr(raw_edge, "attributes", {}) or {}),
                            episodes=episodes_list,
                            created_at=str(created_at) if created_at else None,
                            valid_at=str(valid_at) if valid_at else None,
                            invalid_at=str(invalid_at) if invalid_at else None,
                            expired_at=str(expired_at) if expired_at else None,
                        )
                    )

            if scope in ("nodes", "hybrid"):
                node_kwargs = dict(search_kwargs)
                node_kwargs["scope"] = "nodes"
                node_res = call_zep_read_with_retry(
                    lambda: self._client.graph.search(**node_kwargs),
                    operation_name=f"search nodes in {graph_id}",
                )
                for raw_node in getattr(node_res, "nodes", None) or []:
                    uuid_val = getattr(raw_node, "uuid_", None) or getattr(raw_node, "uuid", "") or ""
                    created_at = getattr(raw_node, "created_at", None)
                    nodes.append(
                        GraphNode(
                            uuid=uuid_val,
                            name=getattr(raw_node, "name", "") or "",
                            labels=list(getattr(raw_node, "labels", []) or []),
                            summary=getattr(raw_node, "summary", "") or "",
                            attributes=dict(getattr(raw_node, "attributes", {}) or {}),
                            created_at=str(created_at) if created_at else None,
                        )
                    )

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

