"""Tests unitaires hermétiques du contrat d'interface GraphStore, des modèles et des exceptions."""

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import pytest

from app.utils.graph_store import (
    BatchSubmissionRecord,
    EpisodeRecord,
    GraphConnectionError,
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphNotFoundError,
    GraphSearchResult,
    GraphStore,
    GraphStoreError,
    GraphTimeoutError,
    GraphValidationError,
)


class FakeGraphStore(GraphStore):
    """Implémentation factice en mémoire complète pour valider le contrat GraphStore."""

    def __init__(self) -> None:
        self.graphs: Dict[str, Dict[str, Any]] = {}
        self.nodes: Dict[str, Dict[str, GraphNode]] = {}
        self.edges: Dict[str, Dict[str, GraphEdge]] = {}
        self.ontologies: Dict[str, Dict[str, Any]] = {}
        self.episodes: Dict[str, List[EpisodeRecord]] = {}

    def create_graph(self, name: str, graph_id: Optional[str] = None) -> str:
        gid = graph_id or f"graph-{len(self.graphs) + 1}"
        self.graphs[gid] = {"name": name, "graph_id": gid}
        self.nodes[gid] = {}
        self.edges[gid] = {}
        self.episodes[gid] = []
        return gid

    def delete_graph(self, graph_id: str) -> None:
        if graph_id not in self.graphs:
            raise GraphNotFoundError(f"Graphe '{graph_id}' introuvable.")
        del self.graphs[graph_id]
        self.nodes.pop(graph_id, None)
        self.edges.pop(graph_id, None)
        self.ontologies.pop(graph_id, None)
        self.episodes.pop(graph_id, None)

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        if graph_id not in self.graphs:
            raise GraphNotFoundError(f"Graphe '{graph_id}' introuvable.")
        nodes_list = [n.to_dict() for n in self.nodes.get(graph_id, {}).values()]
        edges_list = [e.to_dict() for e in self.edges.get(graph_id, {}).values()]
        return {
            "graph_id": graph_id,
            "nodes": nodes_list,
            "edges": edges_list,
            "node_count": len(nodes_list),
            "edge_count": len(edges_list),
            "statistics": {
                "node_count": len(nodes_list),
                "edge_count": len(edges_list),
            },
        }

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        if graph_id not in self.graphs:
            raise GraphNotFoundError(f"Graphe '{graph_id}' introuvable.")
        nodes = list(self.nodes.get(graph_id, {}).values())
        edges = list(self.edges.get(graph_id, {}).values())
        entity_types = sorted(
            list(
                {
                    etype
                    for n in nodes
                    for etype in [n.get_entity_type()]
                    if etype is not None
                }
            )
        )
        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=entity_types,
        )

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        if graph_id not in self.graphs:
            raise GraphNotFoundError(f"Graphe '{graph_id}' introuvable.")
        self.ontologies[graph_id] = dict(ontology)

    def add_episode(
        self,
        graph_id: str,
        text: str,
        source_description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> EpisodeRecord:
        if graph_id not in self.graphs:
            raise GraphNotFoundError(f"Graphe '{graph_id}' introuvable.")
        ep_uuid = f"ep-{len(self.episodes[graph_id]) + 1}"
        record = EpisodeRecord(
            uuid=ep_uuid,
            graph_id=graph_id,
            processed=True,
            created_at=created_at or "2026-10-06T12:00:00Z",
        )
        self.episodes[graph_id].append(record)
        return record

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> BatchSubmissionRecord:
        if graph_id not in self.graphs:
            raise GraphNotFoundError(f"Graphe '{graph_id}' introuvable.")
        ep_uuids = []
        for idx, chunk in enumerate(chunks):
            ep = self.add_episode(graph_id, chunk, source_description=f"chunk_{idx}")
            ep_uuids.append(ep.uuid)
            if progress_callback:
                progress_callback("processing", idx + 1, len(chunks))
        return BatchSubmissionRecord(
            batch_id=f"batch-{graph_id}",
            operation_id="op-123",
            episode_uuids=ep_uuids,
            item_count=len(chunks),
        )

    def wait_for_batch(
        self,
        batch: BatchSubmissionRecord,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        timeout: float = 600.0,
    ) -> bool:
        if progress_callback:
            progress_callback("completed", 1.0)
        return True

    def wait_for_episodes(
        self,
        graph_id: str,
        episode_uuids: List[str],
        timeout: float = 600.0,
    ) -> bool:
        if graph_id not in self.graphs:
            raise GraphNotFoundError(f"Graphe '{graph_id}' introuvable.")
        return True

    def get_all_nodes(self, graph_id: str) -> List[GraphNode]:
        if graph_id not in self.graphs:
            raise GraphNotFoundError(f"Graphe '{graph_id}' introuvable.")
        return list(self.nodes.get(graph_id, {}).values())

    def get_all_edges(
        self, graph_id: str, include_temporal: bool = True
    ) -> List[GraphEdge]:
        if graph_id not in self.graphs:
            raise GraphNotFoundError(f"Graphe '{graph_id}' introuvable.")
        return list(self.edges.get(graph_id, {}).values())

    def get_node(self, graph_id: str, node_uuid: str) -> Optional[GraphNode]:
        if graph_id not in self.graphs:
            raise GraphNotFoundError(f"Graphe '{graph_id}' introuvable.")
        return self.nodes.get(graph_id, {}).get(node_uuid)

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[GraphEdge]:
        if graph_id not in self.graphs:
            raise GraphNotFoundError(f"Graphe '{graph_id}' introuvable.")
        return [
            e
            for e in self.edges.get(graph_id, {}).values()
            if e.source_node_uuid == node_uuid or e.target_node_uuid == node_uuid
        ]

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
        reranker: Optional[str] = None,
    ) -> GraphSearchResult:
        if graph_id not in self.graphs:
            raise GraphNotFoundError(f"Graphe '{graph_id}' introuvable.")
        matching_edges = [
            e
            for e in self.edges.get(graph_id, {}).values()
            if query.lower() in e.fact.lower() or query.lower() in e.name.lower()
        ][:limit]
        facts = [e.fact for e in matching_edges]
        return GraphSearchResult(
            facts=facts,
            nodes=[],
            edges=matching_edges,
            query=query,
            total_count=len(matching_edges),
        )


def test_cannot_instantiate_abstract_graph_store():
    """Vérifie que GraphStore est une ABC pure avec 14 méthodes abstraites non instanciable directement."""
    with pytest.raises(TypeError) as exc_info:
        GraphStore()  # type: ignore

    msg = str(exc_info.value)
    assert "Can't instantiate abstract class GraphStore" in msg
    # Vérifier la présence de plusieurs méthodes abstraites obligatoires dans le message d'erreur
    for method in ["create_graph", "delete_graph", "get_graph_data", "add_episode", "search"]:
        assert method in msg


def test_fake_graph_store_full_lifecycle():
    """Valide l'exécution complète d'un scénario de cycle de vie via FakeGraphStore."""
    store = FakeGraphStore()
    gid = store.create_graph(name="Projet Test", graph_id="proj-001")
    assert gid == "proj-001"

    # Ontologie
    store.set_ontology(gid, {"entity_types": ["Person", "Organization"]})
    assert store.ontologies[gid]["entity_types"] == ["Person", "Organization"]

    # Ingestion unitaire
    ep = store.add_episode(gid, text="Alice est présidente de Foo Corp.", created_at="2026-10-06T10:00:00Z")
    assert ep.uuid == "ep-1"
    assert ep.processed is True

    # Ingestion par lots
    progress_calls = []
    batch = store.add_text_batch(
        gid,
        chunks=["Texte A", "Texte B"],
        progress_callback=lambda st, cur, tot: progress_calls.append((st, cur, tot)),
    )
    assert batch.item_count == 2
    assert len(batch.episode_uuids) == 2
    assert len(progress_calls) == 2

    assert store.wait_for_batch(batch) is True
    assert store.wait_for_episodes(gid, batch.episode_uuids) is True

    # Remplissage de nœuds et arêtes pour lecture
    n1 = GraphNode(uuid="node-1", name="Alice", labels=["Entity", "Person"], summary="Présidente")
    n2 = GraphNode(uuid="node-2", name="Foo Corp", labels=["Entity", "Organization"])
    edge1 = GraphEdge(
        uuid="edge-1",
        name="presides",
        fact="Alice préside Foo Corp.",
        source_node_uuid="node-1",
        target_node_uuid="node-2",
        source_node_name="Alice",
        target_node_name="Foo Corp",
    )
    store.nodes[gid]["node-1"] = n1
    store.nodes[gid]["node-2"] = n2
    store.edges[gid]["edge-1"] = edge1

    # Lectures et parcours
    assert len(store.get_all_nodes(gid)) == 2
    assert len(store.get_all_edges(gid)) == 1
    assert store.get_node(gid, "node-1") == n1
    assert store.get_node(gid, "node-999") is None
    assert len(store.get_node_edges(gid, "node-1")) == 1
    assert len(store.get_node_edges(gid, "node-2")) == 1

    # GraphInfo & GraphData
    info = store.get_graph_info(gid)
    assert info.graph_id == "proj-001"
    assert info.node_count == 2
    assert info.edge_count == 1
    assert info.entity_types == ["Organization", "Person"]

    data = store.get_graph_data(gid)
    assert data["graph_id"] == "proj-001"
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["node_count"] == 2
    assert data["edge_count"] == 1
    assert data["statistics"]["node_count"] == 2
    assert data["statistics"]["edge_count"] == 1

    # Recherche (avec reranker optionnel)
    sr = store.search(gid, query="préside", reranker="rrf")
    assert sr.total_count == 1
    assert sr.facts == ["Alice préside Foo Corp."]
    assert len(sr.edges) == 1

    # Suppression
    store.delete_graph(gid)
    with pytest.raises(GraphNotFoundError):
        store.get_graph_info(gid)


def test_graph_node_model():
    """Valide le modèle neutre GraphNode, son immutabilité et ses méthodes."""
    node = GraphNode(
        uuid="n-123",
        name="Jean Dupont",
        labels=["Entity", "Politician", "Minister"],
        summary="Ministre des finances",
        attributes={"age": 52},
        created_at="2026-10-06T10:00:00Z",
        related_edges=[{"uuid": "e-1", "name": "appointed_by"}],
        related_nodes=[{"uuid": "n-456", "name": "President"}],
    )

    # Immutabilité (frozen=True)
    with pytest.raises(FrozenInstanceError):
        node.name = "Jean Modifié"  # type: ignore

    # get_entity_type extrait le premier label spécifique, ou attribut, ou Entity par défaut
    assert node.get_entity_type() == "Politician"

    generic_node = GraphNode(uuid="n-generic", name="Inconnu", labels=["Entity", "Node"])
    assert generic_node.get_entity_type() == "Entity"

    attr_node = GraphNode(uuid="n-attr", name="Acteur", labels=["Entity"], attributes={"entity_type": "Student"})
    assert attr_node.get_entity_type() == "Student"

    empty_node = GraphNode(uuid="n-empty", name="Vide")
    assert empty_node.get_entity_type() is None

    # to_dict
    d = node.to_dict()
    assert d["uuid"] == "n-123"
    assert d["name"] == "Jean Dupont"
    assert d["labels"] == ["Entity", "Politician", "Minister"]
    assert d["summary"] == "Ministre des finances"
    assert d["attributes"] == {"age": 52}
    assert d["created_at"] == "2026-10-06T10:00:00Z"
    assert d["related_edges"] == [{"uuid": "e-1", "name": "appointed_by"}]
    assert d["related_nodes"] == [{"uuid": "n-456", "name": "President"}]

    # to_text
    text = node.to_text()
    assert "Entité : Jean Dupont (type : Politician)" in text
    assert "Résumé : Ministre des finances" in text


def test_graph_edge_model():
    """Valide le modèle neutre GraphEdge, son immutabilité et ses propriétés temporelles."""
    edge = GraphEdge(
        uuid="e-001",
        name="works_at",
        fact="Bob travaille chez Acme Corp depuis 2020.",
        source_node_uuid="n-1",
        target_node_uuid="n-2",
        fact_type="employment",
        source_node_name="Bob",
        target_node_name="Acme Corp",
        attributes={"confidence": 0.95},
        created_at="2026-10-06T10:00:00Z",
        valid_at="2020-01-01T00:00:00Z",
        invalid_at=None,
        expired_at="2025-01-01T00:00:00Z",
        episodes=["ep-1", "ep-2"],
    )

    # Immutabilité
    with pytest.raises(FrozenInstanceError):
        edge.fact = "Nouveau fait"  # type: ignore

    # @property is_expired et is_invalid (accès sans parenthèses)
    assert edge.is_expired is True
    assert edge.is_invalid is False

    invalid_edge = GraphEdge(
        uuid="e-002",
        name="error_fact",
        fact="Information erronée",
        source_node_uuid="n-1",
        target_node_uuid="n-2",
        invalid_at="2026-10-06T10:30:00Z",
    )
    assert invalid_edge.is_invalid is True
    assert invalid_edge.is_expired is False

    # to_text
    edge_text = edge.to_text(include_temporal=False)
    assert "Relation : Bob --[works_at]--> Acme Corp" in edge_text
    assert "Fait : Bob travaille chez Acme Corp depuis 2020." in edge_text
    assert "Validité :" not in edge_text

    edge_text_temporal = edge.to_text(include_temporal=True)
    assert "Validité : 2020-01-01T00:00:00Z -> actuelle" in edge_text_temporal
    assert "(Expiré : 2025-01-01T00:00:00Z)" in edge_text_temporal

    # to_dict avec et sans champs temporels
    d_full = edge.to_dict(include_temporal=True)
    assert d_full["uuid"] == "e-001"
    assert d_full["created_at"] == "2026-10-06T10:00:00Z"
    assert d_full["valid_at"] == "2020-01-01T00:00:00Z"
    assert d_full["expired_at"] == "2025-01-01T00:00:00Z"
    assert d_full["invalid_at"] is None
    assert d_full["episodes"] == ["ep-1", "ep-2"]

    d_no_temp = edge.to_dict(include_temporal=False)
    assert "valid_at" not in d_no_temp
    assert "expired_at" not in d_no_temp
    assert "invalid_at" not in d_no_temp
    assert "created_at" not in d_no_temp
    assert d_no_temp["uuid"] == "e-001"


def test_graph_search_result_model():
    """Valide GraphSearchResult, sa conversion to_dict et son rendu to_text pour prompts."""
    node = GraphNode(uuid="n-1", name="Alpha", labels=["Entity", "Company"])
    edge = GraphEdge(
        uuid="e-1",
        name="rel",
        fact="Alpha est lié à Beta.",
        source_node_uuid="n-1",
        target_node_uuid="n-2",
    )
    sr = GraphSearchResult(
        facts=["Alpha est lié à Beta.", "Alpha a été fondé en 2020."],
        nodes=[node],
        edges=[edge],
        query="Alpha",
        total_count=2,
    )

    # Immutabilité
    with pytest.raises(FrozenInstanceError):
        sr.query = "Autre"  # type: ignore

    d = sr.to_dict()
    assert d["query"] == "Alpha"
    assert d["total_count"] == 2
    assert len(d["facts"]) == 2
    assert len(d["nodes"]) == 1
    assert len(d["edges"]) == 1

    text = sr.to_text()
    assert "Requête : Alpha" in text
    assert "2 élément(s) pertinent(s)" in text
    assert "### Faits extraits :" in text
    assert "1. Alpha est lié à Beta." in text
    assert "2. Alpha a été fondé en 2020." in text

    # Recherche sans faits mais avec nœuds (scope='nodes')
    sr_nodes_only = GraphSearchResult(
        facts=[],
        nodes=[node],
        edges=[],
        query="Alpha",
        total_count=1,
    )
    text_nodes = sr_nodes_only.to_text()
    assert "### Entités trouvées :" in text_nodes
    assert "1. Entité : Alpha (type : Company)" in text_nodes

    # Sans faits ni nœuds
    sr_empty = GraphSearchResult(facts=[], nodes=[], edges=[], query="Inconnu", total_count=0)
    text_empty = sr_empty.to_text()
    assert "Requête : Inconnu" in text_empty
    assert "0 élément(s) pertinent(s)" in text_empty
    assert "### Faits extraits :" not in text_empty
    assert "### Entités trouvées :" not in text_empty


def test_auxiliary_records():
    """Valide EpisodeRecord, BatchSubmissionRecord et GraphInfo."""
    ep = EpisodeRecord(uuid="ep-10", graph_id="g-1", processed=True, created_at="2026-10-06T10:00:00Z")
    assert ep.to_dict() == {
        "uuid": "ep-10",
        "graph_id": "g-1",
        "processed": True,
        "created_at": "2026-10-06T10:00:00Z",
    }
    with pytest.raises(FrozenInstanceError):
        ep.processed = False  # type: ignore

    batch = BatchSubmissionRecord(
        batch_id="b-99",
        operation_id="op-88",
        episode_uuids=["ep-1", "ep-2"],
        item_count=2,
    )
    assert batch.to_dict() == {
        "batch_id": "b-99",
        "operation_id": "op-88",
        "episode_uuids": ["ep-1", "ep-2"],
        "item_count": 2,
    }
    with pytest.raises(FrozenInstanceError):
        batch.item_count = 5  # type: ignore

    info = GraphInfo(graph_id="g-1", node_count=10, edge_count=25, entity_types=["Person"])
    assert info.to_dict() == {
        "graph_id": "g-1",
        "node_count": 10,
        "edge_count": 25,
        "entity_types": ["Person"],
    }
    with pytest.raises(FrozenInstanceError):
        info.node_count = 11  # type: ignore


def test_exception_hierarchy():
    """Valide la hiérarchie d'héritage des exceptions GraphStoreError."""
    assert issubclass(GraphNotFoundError, GraphStoreError)
    assert issubclass(GraphConnectionError, GraphStoreError)
    assert issubclass(GraphTimeoutError, GraphStoreError)
    assert issubclass(GraphValidationError, GraphStoreError)
    assert issubclass(GraphStoreError, Exception)

    # Capture polymorphique
    try:
        raise GraphNotFoundError("Graphe introuvable")
    except GraphStoreError as exc:
        assert isinstance(exc, GraphNotFoundError)
        assert str(exc) == "Graphe introuvable"


def test_architectural_purity_no_zep_imports_in_base_modules():
    """Vérifie par analyse AST qu'aucun import zep_cloud n'existe dans base.py, errors.py et __init__.py."""
    package_dir = Path(__file__).parent.parent / "app" / "utils" / "graph_store"
    base_files_to_check = [
        package_dir / "base.py",
        package_dir / "errors.py",
    ]

    for file_path in base_files_to_check:
        assert file_path.exists(), f"Le fichier {file_path} doit exister."
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "zep" not in alias.name.lower(), (
                        f"Import Zep interdit dans {file_path.name}: import {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert "zep" not in mod.lower(), (
                    f"Import Zep interdit dans {file_path.name}: from {mod} import ..."
                )

    # Vérification que __init__.py n'importe pas directement le SDK zep_cloud
    init_file = package_dir / "__init__.py"
    assert init_file.exists()
    tree = ast.parse(init_file.read_text(encoding="utf-8"), filename=str(init_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "zep_cloud" not in alias.name.lower(), (
                    f"Import zep_cloud direct interdit dans __init__.py: import {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "zep_cloud" not in mod.lower(), (
                f"Import zep_cloud direct interdit dans __init__.py: from {mod} import ..."
            )

