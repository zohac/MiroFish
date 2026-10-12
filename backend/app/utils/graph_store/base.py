"""Interface abstraite GraphStore et modèles de données neutres."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import re
from typing import Any, Callable, Dict, List, Optional

from .errors import GraphValidationError


@dataclass(frozen=True)
class GraphNode:
    """Nœud de graphe de connaissances agnostique."""

    uuid: str
    name: str
    labels: List[str] = field(default_factory=list)
    summary: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convertit le nœud en dictionnaire sérialisable."""
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": list(self.labels),
            "summary": self.summary,
            "attributes": dict(self.attributes),
            "created_at": self.created_at,
            "related_edges": list(self.related_edges),
            "related_nodes": list(self.related_nodes),
        }

    def get_entity_type(self) -> Optional[str]:
        """Retourne le type d'entité résolu selon la chaîne de priorité :
        1. Labels spécifiques d'ontologie (hors 'Entity' et 'Node').
        2. Attributs explicites ('entity_type', 'type', 'category').
        3. Repli générique 'Entity' si le nœud porte le label 'Entity' ou 'Node'.
        4. None si aucun label ni attribut de type n'existe.
        """
        for label in self.labels:
            if label and isinstance(label, str) and label.strip() and label.strip() not in ["Entity", "Node"]:
                return label.strip()

        if self.attributes and isinstance(self.attributes, dict):
            attr_type = (
                self.attributes.get("entity_type")
                or self.attributes.get("type")
                or self.attributes.get("category")
            )
            if attr_type and isinstance(attr_type, str) and attr_type.strip():
                return attr_type.strip()

        if any(isinstance(l, str) and l.strip() in ["Entity", "Node"] for l in self.labels):
            return "Entity"

        return None

    def to_text(self) -> str:
        """Format textuel lisible pour injection dans les prompts LLM."""
        entity_type = self.get_entity_type() or "Entité"
        summary_str = f"\nRésumé : {self.summary}" if self.summary else ""
        return f"Entité : {self.name} (type : {entity_type}){summary_str}"


@dataclass(frozen=True)
class GraphEdge:
    """Arête de relation temporelle entre deux nœuds."""

    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    fact_type: str = ""
    source_node_name: str = ""
    target_node_name: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None
    episodes: List[str] = field(default_factory=list)

    def to_dict(self, include_temporal: bool = True) -> Dict[str, Any]:
        """Convertit l'arête en dictionnaire sérialisable."""
        data: Dict[str, Any] = {
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
            "fact_type": self.fact_type,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "source_node_name": self.source_node_name,
            "target_node_name": self.target_node_name,
            "attributes": dict(self.attributes),
            "episodes": list(self.episodes),
        }
        if include_temporal:
            data.update(
                {
                    "created_at": self.created_at,
                    "valid_at": self.valid_at,
                    "invalid_at": self.invalid_at,
                    "expired_at": self.expired_at,
                }
            )
        return data

    def to_text(self, include_temporal: bool = False) -> str:
        """Format textuel lisible pour injection dans les prompts LLM."""
        source = self.source_node_name or self.source_node_uuid[:8]
        target = self.target_node_name or self.target_node_uuid[:8]
        base_text = f"Relation : {source} --[{self.name}]--> {target}\nFait : {self.fact}"
        if include_temporal:
            valid_at = self.valid_at or "inconnue"
            invalid_at = self.invalid_at or "actuelle"
            base_text += f"\nValidité : {valid_at} -> {invalid_at}"
            if self.expired_at:
                base_text += f" (Expiré : {self.expired_at})"
        return base_text

    @property
    def is_expired(self) -> bool:
        """Indique si l'arête a expiré temporellement."""
        return self.expired_at is not None

    @property
    def is_invalid(self) -> bool:
        """Indique si l'arête a été invalidée."""
        return self.invalid_at is not None


@dataclass(frozen=True)
class GraphSearchResult:
    """Résultat unifié d'une recherche sémantique ou hybride."""

    facts: List[str]
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    query: str
    total_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Convertit le résultat de recherche en dictionnaire sérialisable."""
        return {
            "facts": list(self.facts),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "query": self.query,
            "total_count": self.total_count,
        }

    def to_text(self) -> str:
        """Format textuel lisible pour injection dans les prompts LLM."""
        parts = [f"Requête : {self.query}", f"{self.total_count} élément(s) pertinent(s)"]
        if self.facts:
            parts.append("\n### Faits extraits :")
            for idx, fact in enumerate(self.facts, 1):
                parts.append(f"{idx}. {fact}")
        elif self.nodes:
            parts.append("\n### Entités trouvées :")
            for idx, node in enumerate(self.nodes, 1):
                parts.append(f"{idx}. {node.to_text()}")
        elif self.edges:
            parts.append("\n### Relations trouvées :")
            for idx, edge in enumerate(self.edges, 1):
                parts.append(f"{idx}. {edge.to_text()}")
        return "\n".join(parts)


@dataclass(frozen=True)
class EpisodeRecord:
    """Enregistrement d'un épisode textuel ingéré."""

    uuid: str
    graph_id: str
    processed: bool = False
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'enregistrement d'épisode en dictionnaire."""
        return {
            "uuid": self.uuid,
            "graph_id": self.graph_id,
            "processed": self.processed,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class BatchSubmissionRecord:
    """Identité durable d'une opération d'ingestion par lots."""

    batch_id: str
    operation_id: str
    episode_uuids: List[str]
    item_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Convertit le résultat de soumission par lot en dictionnaire."""
        return {
            "batch_id": self.batch_id,
            "operation_id": self.operation_id,
            "episode_uuids": list(self.episode_uuids),
            "item_count": self.item_count,
        }


class ProvenanceOrigin(str):
    """Origines d'un épisode, distinctes et jamais fusionnées (ADR 0012 §3)."""

    DOCUMENT = "document"
    SIMULATION = "simulation"
    LEGACY = "legacy"
    UNRESOLVED = "unresolved"


#: Champs de métadonnées de fragment validés avant toute écriture (ADR 0012 §1).
REQUIRED_CHUNK_METADATA_FIELDS = (
    "source_document_id",
    "source_filename",
    "chunk_index",
    "char_start",
    "char_end",
    "source_role",
)

#: Champs facultatifs, avec leur type attendu quand ils sont présents.
OPTIONAL_CHUNK_METADATA_FIELDS: Dict[str, type] = {
    "page": int,
    "section": str,
}

#: Clés acceptées dans `chunk_metadata`. Toute autre clé est refusée : les noms
#: de propriétés Cypher ne peuvent pas être paramétrés, donc une clé libre est
#: une surface d'injection et une dérive du contrat (ADR 0012 §1).
ALLOWED_CHUNK_METADATA_FIELDS = frozenset(
    REQUIRED_CHUNK_METADATA_FIELDS + tuple(OPTIONAL_CHUNK_METADATA_FIELDS)
)

#: Clés de métadonnées que le store gère lui-même : les écrire écraserait une
#: propriété de Graphiti ou le partitionnement. `source` en fait partie :
#: `EpisodicNode.source` est un `EpisodeType`, et l'annoter corromprait
#: l'épisode. L'origine simulée se lit sur `simulation_id`, jamais sur `source`.
FORBIDDEN_ANNOTATION_KEYS = frozenset(
    {
        "uuid",
        "group_id",
        "content",
        "name",
        "source",
        "source_description",
        "valid_at",
        "created_at",
        "entity_edges",
        "labels",
        "episode_metadata",
        "reference_time",
    }
)

#: Un nom de propriété Neo4j est un identifiant : lettres, chiffres, `_`.
_ANNOTATION_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Rôles documentaires reconnus. La liste est explicite plutôt que déduite d'un
#: import de modèle : `base.py` ne connaît aucun service métier (AGENTS.md §2.1).
VALID_SOURCE_ROLES = (
    "facts",
    "scenario",
    "personas",
    "hypotheses",
    "constraints",
    "reference",
)


def validate_chunk_metadata(
    chunks: List[str],
    chunk_metadata: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Valide les métadonnées alignées avant toute écriture.

    Une seule implémentation pour les deux stores : c'est la seule façon qu'ils
    refusent la même entrée pour la même raison (ADR 0012 §1). Un refus lève
    ``GraphValidationError`` **avant** la première écriture — il n'existe aucun
    chemin produisant une ingestion partielle déclarée réussie.

    Args:
        chunks: Fragments.alignés sur ``chunk_metadata``.
        chunk_metadata: Une entrée par fragment, ou ``None``.

    Returns:
        La liste validée, ou une liste vide si aucune provenance n'est demandée.

    Raises:
        GraphValidationError: Désalignement, champ manquant, type invalide ou
            entrée non dictionnaire.
    """
    if chunk_metadata is None:
        return []

    if not isinstance(chunk_metadata, list):
        raise GraphValidationError(
            "chunk_metadata doit être une liste, une entrée par fragment"
        )

    if len(chunk_metadata) != len(chunks):
        raise GraphValidationError(
            f"chunk_metadata désaligné : {len(chunk_metadata)} entrées pour "
            f"{len(chunks)} fragments"
        )

    validated: List[Dict[str, Any]] = []
    for index, entry in enumerate(chunk_metadata):
        if not isinstance(entry, dict):
            raise GraphValidationError(
                f"chunk_metadata[{index}] doit être un dictionnaire, reçu "
                f"{type(entry).__name__}"
            )

        for field_name in REQUIRED_CHUNK_METADATA_FIELDS:
            if field_name not in entry:
                raise GraphValidationError(
                    f"chunk_metadata[{index}] ne porte pas le champ requis "
                    f"'{field_name}'"
                )

        unknown = set(entry) - ALLOWED_CHUNK_METADATA_FIELDS
        if unknown:
            raise GraphValidationError(
                f"chunk_metadata[{index}] porte des champs non reconnus : "
                f"{sorted(unknown)} ; champs acceptés : "
                f"{sorted(ALLOWED_CHUNK_METADATA_FIELDS)}"
            )

        for field_name in ("source_document_id", "source_filename"):
            value = entry[field_name]
            if not isinstance(value, str) or not value.strip():
                raise GraphValidationError(
                    f"chunk_metadata[{index}].{field_name} doit être une chaîne non vide"
                )

        for field_name in ("chunk_index", "char_start", "char_end"):
            value = entry[field_name]
            if isinstance(value, bool) or not isinstance(value, int):
                raise GraphValidationError(
                    f"chunk_metadata[{index}].{field_name} doit être un entier, "
                    f"reçu {type(value).__name__}"
                )

        if entry["chunk_index"] < 0:
            raise GraphValidationError(
                f"chunk_metadata[{index}].chunk_index doit être >= 0 (base 0, "
                "local au document)"
            )
        if entry["char_start"] < 0:
            raise GraphValidationError(
                f"chunk_metadata[{index}].char_start doit être >= 0"
            )
        if entry["char_end"] <= entry["char_start"]:
            raise GraphValidationError(
                f"chunk_metadata[{index}].char_end ({entry['char_end']}) doit être "
                f"strictement supérieur à char_start ({entry['char_start']})"
            )

        role = entry["source_role"]
        if not isinstance(role, str) or role not in VALID_SOURCE_ROLES:
            raise GraphValidationError(
                f"chunk_metadata[{index}].source_role doit être un rôle reconnu "
                f"{VALID_SOURCE_ROLES}, reçu {role!r}"
            )

        for field_name, expected_type in OPTIONAL_CHUNK_METADATA_FIELDS.items():
            if field_name not in entry or entry[field_name] is None:
                continue
            value = entry[field_name]
            if expected_type is int and isinstance(value, bool):
                raise GraphValidationError(
                    f"chunk_metadata[{index}].{field_name} doit être un entier"
                )
            if not isinstance(value, expected_type):
                raise GraphValidationError(
                    f"chunk_metadata[{index}].{field_name} doit être un "
                    f"{expected_type.__name__}, reçu {type(value).__name__}"
                )
        if entry.get("page") is not None and entry["page"] < 1:
            raise GraphValidationError(
                f"chunk_metadata[{index}].page doit être >= 1 quand elle est connue"
            )

        validated.append(dict(entry))

    return validated


@dataclass(frozen=True)
class ProvenanceRecord:
    """Origine d'une référence d'épisode, résolue ou non (ADR 0012 §3).

    Une référence non résolue n'est pas une exception : un graphe migré est un
    cas normal d'usage, et l'appelant doit pouvoir distinguer « pas d'épisode »
    d'une panne.
    """

    episode_uuid: str
    resolved: bool
    origin: str
    source_document_id: Optional[str] = None
    source_filename: Optional[str] = None
    source_role: Optional[str] = None
    chunk_index: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    page: Optional[int] = None
    section: Optional[str] = None
    content: Optional[str] = None
    simulation_id: Optional[str] = None
    platform: Optional[str] = None
    missing_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_uuid": self.episode_uuid,
            "resolved": self.resolved,
            "origin": self.origin,
            "source_document_id": self.source_document_id,
            "source_filename": self.source_filename,
            "source_role": self.source_role,
            "chunk_index": self.chunk_index,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "page": self.page,
            "section": self.section,
            "content": self.content,
            "simulation_id": self.simulation_id,
            "platform": self.platform,
            "missing_reason": self.missing_reason,
        }

    @property
    def is_documentary(self) -> bool:
        """Vrai si cette référence compte comme fait documentaire (C3).

        Une provenance **incomplète** (`missing_reason` renseigné) ne compte pas :
        l'ADR 0012 §5 exige document, fichier, rôle, index et positions pour
        qu'une référence soit résolue.
        """

        return (
            self.resolved
            and self.origin == ProvenanceOrigin.DOCUMENT
            and self.missing_reason is None
        )


@dataclass(frozen=True)
class GraphInfo:
    """Statistiques et métadonnées globales d'un graphe."""

    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convertit les métadonnées globales en dictionnaire."""
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": list(self.entity_types),
        }


class GraphStore(ABC):
    """Interface unifiée pour le magasin de graphe de connaissances temporel."""

    # --- Cycle de vie ---

    @abstractmethod
    def create_graph(self, name: str, graph_id: Optional[str] = None) -> str:
        """Crée un graphe et retourne son identifiant durable.

        Args:
            name: Nom d'affichage ou libellé du graphe.
            graph_id: Identifiant unique optionnel (ex: project_id). Si omis, généré.

        Returns:
            L'identifiant durable du graphe créé.
        """
        pass

    @abstractmethod
    def delete_graph(self, graph_id: str) -> None:
        """Supprime un graphe et l'ensemble de ses données associées.

        Args:
            graph_id: Identifiant unique du graphe à supprimer.
        """
        pass

    @abstractmethod
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """Retourne les nœuds, arêtes et statistiques complètes du graphe pour l'API.

        Garantit pour la rétrocompatibilité (api/graph.py et frontend) :
        - 'graph_id' : identifiant unique du graphe.
        - 'nodes' : liste des dictionnaires de nœuds sérialisés.
        - 'edges' : liste des dictionnaires d'arêtes sérialisées.
        - 'node_count' et 'edge_count' : comptages directs au premier niveau.
        - 'statistics' : dictionnaire {'node_count': int, 'edge_count': int}.

        Args:
            graph_id: Identifiant unique du graphe.

        Returns:
            Dictionnaire complet contenant 'graph_id', 'nodes', 'edges',
            'node_count', 'edge_count' et 'statistics'.
        """
        pass

    @abstractmethod
    def get_graph_info(self, graph_id: str) -> GraphInfo:
        """Retourne un résumé synthétique (comptages et types d'entités).

        Args:
            graph_id: Identifiant unique du graphe.

        Returns:
            Instance de GraphInfo avec les statistiques.
        """
        pass

    # --- Ontologie ---

    @abstractmethod
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        """Définit ou synchronise l'ontologie des types d'entités du graphe.

        Args:
            graph_id: Identifiant unique du graphe.
            ontology: Dictionnaire décrivant l'ontologie (ex: entity_types).
        """
        pass

    # --- Ingestion et épisodes ---

    @abstractmethod
    def add_episode(
        self,
        graph_id: str,
        text: str,
        source_description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> EpisodeRecord:
        """Ajoute un épisode textuel unitaire au graphe.

        Args:
            graph_id: Identifiant unique du graphe.
            text: Contenu textuel de l'épisode (fait, observation, message).
            source_description: Description facultative de la source (ex: 'turn_1').
            metadata: Métadonnées additionnelles facultatives.
            created_at: Horodatage optionnel au format ISO 8601.

        Returns:
            EpisodeRecord représentant l'épisode enregistré.
        """
        pass

    @abstractmethod
    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        chunk_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> BatchSubmissionRecord:
        """Ingère une liste de textes découpés par lots.

        Args:
            graph_id: Identifiant unique du graphe cible.
            chunks: Liste ordonnée des fragments textuels à ingérer.
            batch_size: Taille maximale de chaque sous-lot.
            progress_callback: Callback facultatif (status, current, total).
            chunk_metadata: Une entrée de métadonnées par fragment, dans le même
                ordre que `chunks` (ADR 0012 §1). `None` — le cas de tous les
                appelants existants — demande aucune provenance et conserve le
                comportement actuel. Une liste désalignée ou invalide lève
                `GraphValidationError` **avant** toute écriture.

        Returns:
            BatchSubmissionRecord contenant les identifiants d'opération et d'épisodes.
        """
        pass

    @abstractmethod
    def wait_for_batch(
        self,
        batch: BatchSubmissionRecord,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        timeout: float = 600.0,
    ) -> bool:
        """Attend la fin du traitement asynchrone d'un lot d'ingestion.

        Args:
            batch: Enregistrement de soumission retourné par add_text_batch.
            progress_callback: Callback facultatif (status, progress_ratio).
            timeout: Délai maximal d'attente en secondes.

        Returns:
            True si le traitement est terminé avec succès.

        Raises:
            GraphTimeoutError: Si le délai maximal d'attente expire avant traitement complet.
        """
        pass

    @abstractmethod
    def wait_for_episodes(
        self,
        graph_id: str,
        episode_uuids: List[str],
        timeout: float = 600.0,
    ) -> bool:
        """Attend la fin du traitement pour une liste explicite d'épisodes.

        Args:
            graph_id: Identifiant unique du graphe.
            episode_uuids: Liste des identifiants d'épisodes à surveiller.
            timeout: Délai maximal d'attente en secondes.

        Returns:
            True si tous les épisodes sont traités avec succès.

        Raises:
            GraphTimeoutError: Si le délai maximal d'attente expire avant traitement complet.
        """
        pass

    # --- Lecture et parcours ---

    @abstractmethod
    def get_all_nodes(self, graph_id: str) -> List[GraphNode]:
        """Récupère tous les nœuds d'un graphe.

        Args:
            graph_id: Identifiant unique du graphe.

        Returns:
            Liste de GraphNode.
        """
        pass

    @abstractmethod
    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[GraphEdge]:
        """Récupère toutes les arêtes d'un graphe avec ou sans champs temporels.

        Args:
            graph_id: Identifiant unique du graphe.
            include_temporal: Si True, inclut les métadonnées de validité temporelle.

        Returns:
            Liste de GraphEdge.
        """
        pass

    @abstractmethod
    def get_node(self, graph_id: str, node_uuid: str) -> Optional[GraphNode]:
        """Récupère un nœud spécifique par son identifiant unique.

        Args:
            graph_id: Identifiant unique du graphe.
            node_uuid: Identifiant unique du nœud.

        Returns:
            GraphNode ou None si introuvable.
        """
        pass

    @abstractmethod
    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[GraphEdge]:
        """Récupère toutes les arêtes connectées à un nœud (entrantes et sortantes).

        Args:
            graph_id: Identifiant unique du graphe.
            node_uuid: Identifiant unique du nœud.

        Returns:
            Liste de GraphEdge connectées.
        """
        pass

    # --- Provenance des faits ---

    @abstractmethod
    def get_edge_provenance(self, graph_id: str, edge_uuid: str) -> List[ProvenanceRecord]:
        """Résout les origines documentaires d'une arête, dans un graphe donné.

        Chaque référence de `r.episodes` est rendue telle qu'elle, qu'elle se
        résolve ou non : une liste vide, un épisode absent, une origine
        simulée, héritée ou inconnue sont **signés distinctement** et jamais
        inventés (ADR 0012 §3). La requête reste dans le store : aucun Cypher
        ne remonte dans les services (AGENTS.md §2.1).

        Args:
            graph_id: Identifiant unique du graphe cible. Toute résolution est
                bornée par ce `group_id` — une référence d'un autre graphe est
                `unresolved`.
            edge_uuid: Identifiant unique de l'arête.

        Returns:
            Une liste de `ProvenanceRecord` par référence d'épisode. Une arête
            sans aucun épisode retourne une liste vide, pas une exception.
        """
        pass

    def get_edges_provenance(
        self, graph_id: str, edge_uuids: List[str]
    ) -> Dict[str, List[ProvenanceRecord]]:
        """Résout la provenance de plusieurs arêtes en une seule passe.

        Implémentation par défaut : appels individuels à `get_edge_provenance`.
        Les stores qui ont une requête batch (UNWIND ou équivalent) peuvent la
        surcharger pour éviter l'effet N+1.

        Args:
            graph_id: Identifiant unique du graphe cible.
            edge_uuids: Liste d'UUIDs d'arêtes à résoudre.

        Returns:
            Dictionnaire `{edge_uuid: [ProvenanceRecord, ...]}` aligné sur la
            liste d'entrée : un UUID absent du résultat signifie « aucun
            enregistrement de provenance pour cette arête » (liste vide).
        """
        result: Dict[str, List[ProvenanceRecord]] = {}
        for uuid in edge_uuids:
            try:
                result[uuid] = list(self.get_edge_provenance(graph_id, uuid) or [])
            except Exception:
                result[uuid] = []
        return result

    def get_edge_by_uuid(
        self, graph_id: str, edge_uuid: str, include_temporal: bool = True
    ) -> Optional[GraphEdge]:
        """Lit une arête unique par son UUID.

        Implémentation par défaut : scan linéaire via `get_all_edges`. Les
        stores disposant d'un index direct (Cypher `MATCH (r) WHERE r.uuid = $uuid`)
        peuvent surcharger pour offrir un lookup O(1).

        Args:
            graph_id: Identifiant unique du graphe cible.
            edge_uuid: UUID de l'arête recherchée.
            include_temporal: Inclure les champs de temporalité.

        Returns:
            La `GraphEdge` correspondante, ou `None` si absente.
        """
        for edge in self.get_all_edges(graph_id, include_temporal=include_temporal):
            if edge.uuid == edge_uuid:
                return edge
        return None

    # --- Recherche ---

    @abstractmethod
    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
        reranker: Optional[str] = None,
    ) -> GraphSearchResult:
        """Effectue une recherche sémantique / hybride sur les arêtes ou les nœuds.

        Args:
            graph_id: Identifiant unique du graphe.
            query: Requête de recherche en langage naturel.
            limit: Nombre maximal de résultats souhaités.
            scope: Périmètre de recherche ('edges', 'nodes', 'hybrid').
            reranker: Stratégie de reranking optionnelle ('rrf', 'cross_encoder', None).

        Returns:
            GraphSearchResult structuré et neutre.
        """
        pass
