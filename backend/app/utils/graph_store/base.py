"""Interface abstraite GraphStore et modèles de données neutres."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


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
        """Retourne le type d'entité spécifique (hors Entity/Node génériques)."""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
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
    ) -> BatchSubmissionRecord:
        """Ingère une liste de textes découpés par lots.

        Args:
            graph_id: Identifiant unique du graphe cible.
            chunks: Liste ordonnée des fragments textuels à ingérer.
            batch_size: Taille maximale de chaque sous-lot.
            progress_callback: Callback facultatif (status, current, total).

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
