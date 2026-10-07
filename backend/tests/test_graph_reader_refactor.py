"""Tests unitaires du refactoring de la lecture du graphe (Story 002-5)."""

from typing import Any, Callable, Dict, List, Optional
import pytest

from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.zep_entity_reader import (
    EntityNode,
    FilteredEntities,
    ZepEntityReader,
)
from app.services.zep_tools import (
    EdgeInfo,
    NodeInfo,
    SearchResult,
    ZepToolsService,
)
from app.utils.graph_store.base import (
    BatchSubmissionRecord,
    EpisodeRecord,
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphSearchResult,
    GraphStore,
)
from app.utils.graph_store.errors import (
    GraphNotFoundError,
    GraphStoreError,
    GraphValidationError,
)


class MockReaderStore(GraphStore):
    """Store factice pour tester les flux de lecture et de recherche."""

    def __init__(self):
        self.calls: List[tuple[str, Dict[str, Any]]] = []
        self.nodes: Dict[str, List[GraphNode]] = {}
        self.edges: Dict[str, List[GraphEdge]] = {}

    def create_graph(self, name: str, graph_id: Optional[str] = None) -> str:
        return graph_id or "mock-graph"

    def delete_graph(self, graph_id: str) -> None:
        self.calls.append(("delete_graph", {"graph_id": graph_id}))

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        return {
            "graph_id": graph_id,
            "nodes": [n.to_dict() for n in self.nodes.get(graph_id, [])],
            "edges": [e.to_dict() for e in self.edges.get(graph_id, [])],
            "node_count": len(self.nodes.get(graph_id, [])),
            "edge_count": len(self.edges.get(graph_id, [])),
            "statistics": {
                "node_count": len(self.nodes.get(graph_id, [])),
                "edge_count": len(self.edges.get(graph_id, [])),
            },
        }

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        nodes = self.nodes.get(graph_id, [])
        edges = self.edges.get(graph_id, [])
        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=["Person", "Organization"],
        )

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        pass

    def add_episode(
        self,
        graph_id: str,
        text: str,
        source_description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> EpisodeRecord:
        return EpisodeRecord(uuid="ep-mock", graph_id=graph_id, processed=True)

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> BatchSubmissionRecord:
        return BatchSubmissionRecord(
            batch_id="batch-mock",
            operation_id="op-mock",
            episode_uuids=["ep-mock"],
            item_count=len(chunks),
        )

    def wait_for_batch(
        self,
        batch: BatchSubmissionRecord,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        timeout: float = 600.0,
    ) -> bool:
        return True

    def wait_for_episodes(
        self,
        graph_id: str,
        episode_uuids: List[str],
        timeout: float = 600.0,
    ) -> bool:
        return True

    def get_all_nodes(self, graph_id: str) -> List[GraphNode]:
        self.calls.append(("get_all_nodes", {"graph_id": graph_id}))
        return list(self.nodes.get(graph_id, []))

    def get_all_edges(
        self, graph_id: str, include_temporal: bool = True
    ) -> List[GraphEdge]:
        self.calls.append(("get_all_edges", {"graph_id": graph_id, "include_temporal": include_temporal}))
        return list(self.edges.get(graph_id, []))

    def get_node(self, graph_id: str, node_uuid: str) -> Optional[GraphNode]:
        self.calls.append(("get_node", {"graph_id": graph_id, "node_uuid": node_uuid}))
        if node_uuid == "missing-uuid":
            raise GraphNotFoundError(f"Node {node_uuid} introuvable")
        for node_list in self.nodes.values():
            for node in node_list:
                if node.uuid == node_uuid:
                    return node
        return None

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[GraphEdge]:
        self.calls.append(("get_node_edges", {"graph_id": graph_id, "node_uuid": node_uuid}))
        result = []
        for edge_list in self.edges.values():
            for edge in edge_list:
                if edge.source_node_uuid == node_uuid or edge.target_node_uuid == node_uuid:
                    result.append(edge)
        return result

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
        reranker: Optional[str] = None,
    ) -> GraphSearchResult:
        self.calls.append(("search", {"graph_id": graph_id, "query": query, "limit": limit, "scope": scope}))
        facts = [f"Fait lié à {query}"]
        nodes = list(self.nodes.get(graph_id, []))[:limit]
        edges = list(self.edges.get(graph_id, []))[:limit]
        return GraphSearchResult(
            facts=facts,
            nodes=nodes,
            edges=edges,
            query=query,
            total_count=len(facts),
        )


def test_zep_entity_reader_imports_are_decoupled_from_zep_cloud():
    """Vérifie que zep_entity_reader n'importe aucun symbole propriétaire au niveau module."""
    import app.services.zep_entity_reader as reader_module

    assert "get_zep_client" not in reader_module.__dict__
    assert "call_zep_read_with_retry" not in reader_module.__dict__
    assert "fetch_all_nodes" not in reader_module.__dict__
    assert "fetch_all_edges" not in reader_module.__dict__
    assert "NotFoundError" not in reader_module.__dict__


def test_oasis_profile_generator_imports_are_decoupled_from_utils_zep():
    """Vérifie que oasis_profile_generator n'importe plus de fonctions propriétaires de utils.zep."""
    import app.services.oasis_profile_generator as profile_module

    assert "call_zep_read_with_retry" not in profile_module.__dict__
    assert "get_zep_client" not in profile_module.__dict__
    assert "is_retryable_zep_error" not in profile_module.__dict__
    assert "normalize_zep_search_query" not in profile_module.__dict__


def test_zep_tools_imports_are_decoupled_from_zep_cloud():
    """Vérifie que zep_tools n'importe ni zep_cloud.NotFoundError ni utils.zep_paging au niveau module."""
    import app.services.zep_tools as tools_module

    assert "NotFoundError" not in tools_module.__dict__
    assert "fetch_all_nodes" not in tools_module.__dict__
    assert "fetch_all_edges" not in tools_module.__dict__
    assert "call_zep_read_with_retry" not in tools_module.__dict__
    assert "get_zep_client" not in tools_module.__dict__


def test_api_graph_imports_are_decoupled_from_zep_cloud():
    """Vérifie que api/graph.py n'importe plus NotFoundError de zep_cloud."""
    import app.api.graph as api_graph_module

    assert "NotFoundError" not in api_graph_module.__dict__


def test_zep_entity_reader_delegates_to_injected_store():
    """Vérifie que ZepEntityReader délègue la lecture de nœuds, d'arêtes et de voisinage au store."""
    store = MockReaderStore()
    node_alice = GraphNode(uuid="n-1", name="Alice", labels=["Person"], summary="Chercheuse IA")
    node_acme = GraphNode(uuid="n-2", name="Acme", labels=["Organization"], summary="Entreprise Tech")
    edge_works = GraphEdge(
        uuid="e-1",
        name="WORKS_AT",
        fact="Alice works at Acme",
        source_node_uuid="n-1",
        target_node_uuid="n-2",
    )
    store.nodes["graph-1"] = [node_alice, node_acme]
    store.edges["graph-1"] = [edge_works]

    reader = ZepEntityReader(store=store)

    # 1. Lecture de tous les nœuds
    nodes = reader.get_all_nodes("graph-1")
    assert len(nodes) == 2
    assert nodes[0]["name"] == "Alice"
    assert nodes[0]["labels"] == ["Person"]

    # 2. Lecture de toutes les arêtes
    edges = reader.get_all_edges("graph-1")
    assert len(edges) == 1
    assert edges[0]["fact"] == "Alice works at Acme"

    # 3. Voisinage avec graph_id (délégation directe au store)
    node_edges = reader.get_node_edges("n-1", graph_id="graph-1")
    assert len(node_edges) == 1
    assert node_edges[0]["uuid"] == "e-1"
    assert ("get_node_edges", {"graph_id": "graph-1", "node_uuid": "n-1"}) in store.calls

    # 4. Entité avec contexte complet
    entity = reader.get_entity_with_context("graph-1", "n-1")
    assert entity is not None
    assert entity.name == "Alice"
    assert entity.get_entity_type() == "Person"
    assert len(entity.related_edges) == 1
    assert entity.related_edges[0]["direction"] == "outgoing"
    assert len(entity.related_nodes) == 1
    assert entity.related_nodes[0]["name"] == "Acme"


def test_zep_entity_reader_handles_not_found_cleanly():
    """Vérifie que get_entity_with_context retourne None lors d'un GraphNotFoundError."""
    store = MockReaderStore()
    reader = ZepEntityReader(store=store)

    assert reader.get_entity_with_context("graph-1", "missing-uuid") is None


def test_zep_entity_reader_filter_defined_entities():
    """Vérifie le filtrage d'entités avec labels personnalisés."""
    store = MockReaderStore()
    node_generic = GraphNode(uuid="n-gen", name="Generic", labels=["Entity", "Node"])
    node_student = GraphNode(uuid="n-stu", name="Bob", labels=["Entity", "Student"])
    store.nodes["graph-filter"] = [node_generic, node_student]

    reader = ZepEntityReader(store=store)
    filtered = reader.filter_defined_entities("graph-filter")

    assert filtered.total_count == 2
    assert filtered.filtered_count == 1
    assert filtered.entities[0].name == "Bob"
    assert "Student" in filtered.entity_types


def test_zep_tools_service_delegates_to_injected_store():
    """Vérifie que ZepToolsService délègue recherche et lectures d'outils au GraphStore."""
    store = MockReaderStore()
    node_alice = GraphNode(uuid="n-1", name="Alice", labels=["Person"], summary="Chercheuse")
    edge_works = GraphEdge(
        uuid="e-1",
        name="WORKS_AT",
        fact="Alice works at Acme",
        source_node_uuid="n-1",
        target_node_uuid="n-2",
        source_node_name="Alice",
        target_node_name="Acme",
    )
    store.nodes["graph-tools"] = [node_alice]
    store.edges["graph-tools"] = [edge_works]

    service = ZepToolsService(store=store)

    # 1. Recherche
    res = service.search_graph("graph-tools", "Alice")
    assert isinstance(res, SearchResult)
    assert len(res.facts) > 0
    assert len(res.nodes) == 1

    # 1b. Recherche avec scope="both" normalisé en "hybrid"
    res_both = service.search_graph("graph-tools", "Alice", scope="both")
    assert isinstance(res_both, SearchResult)
    assert ("search", {"graph_id": "graph-tools", "query": "Alice", "limit": 10, "scope": "hybrid"}) in store.calls

    # 2. get_all_nodes
    nodes = service.get_all_nodes("graph-tools")
    assert len(nodes) == 1
    assert isinstance(nodes[0], NodeInfo)
    assert nodes[0].name == "Alice"

    # 3. get_all_edges
    edges = service.get_all_edges("graph-tools")
    assert len(edges) == 1
    assert isinstance(edges[0], EdgeInfo)
    assert edges[0].source_node_name == "Alice"

    # 4. get_node_detail
    detail = service.get_node_detail("n-1", graph_id="graph-tools")
    assert detail is not None
    assert detail.name == "Alice"

    # 5. get_node_detail non trouvé
    missing = service.get_node_detail("missing-uuid", graph_id="graph-tools")
    assert missing is None

    # 6. get_node_edges
    n_edges = service.get_node_edges("graph-tools", "n-1")
    assert len(n_edges) == 1


def test_oasis_profile_generator_search_delegates_to_injected_store():
    """Vérifie que OasisProfileGenerator._search_zep_for_entity délègue à store.search()."""
    store = MockReaderStore()
    node_target = GraphNode(uuid="n-target", name="Charlie", labels=["Student"], summary="Etudiant en info")
    node_related = GraphNode(uuid="n-rel", name="Univ", labels=["University"], summary="Université centrale")
    edge_study = GraphEdge(
        uuid="e-study",
        name="STUDIES_AT",
        fact="Charlie studies at Univ",
        source_node_uuid="n-target",
        target_node_uuid="n-rel",
    )
    store.nodes["graph-prof"] = [node_target, node_related]
    store.edges["graph-prof"] = [edge_study]

    generator = OasisProfileGenerator(
        api_key="fake-key",
        store=store,
        graph_id="graph-prof",
    )

    entity = EntityNode(
        uuid="n-target",
        name="Charlie",
        labels=["Student"],
        summary="Etudiant en info",
        attributes={},
    )

    results = generator._search_zep_for_entity(entity)
    assert "facts" in results
    assert "node_summaries" in results
    assert len(results["facts"]) > 0
    assert any("studies at Univ" in f or "Charlie" in f for f in results["facts"])


def test_oasis_profile_generator_resolves_store_override_without_zep_api_key():
    """Vérifie que OasisProfileGenerator résout correctement le store via override sans clé Zep."""
    from app.utils.graph_store.factory import override_graph_store

    store = MockReaderStore()
    with override_graph_store(store):
        generator = OasisProfileGenerator(api_key="fake-key", zep_api_key=None, graph_id="graph-prof")
        assert generator.store is store


def test_client_setters_support_direct_graph_store_injection():
    """Vérifie que client.setter affecte directement un GraphStore pour reader et tools."""
    store = MockReaderStore()
    reader = ZepEntityReader(store=store)
    tools = ZepToolsService(store=store)

    new_store = MockReaderStore()
    reader.client = new_store
    tools.client = new_store

    assert reader.store is new_store
    assert tools.store is new_store


def test_ast_decoupling_in_reader_and_tools():
    """Vérifie par analyse AST stricte l'absence d'import direct de zep_cloud ou utils.zep."""
    import ast
    from pathlib import Path

    base_dir = Path(__file__).resolve().parent.parent / "app"
    files_to_check = [
        base_dir / "services" / "zep_entity_reader.py",
        base_dir / "services" / "oasis_profile_generator.py",
        base_dir / "services" / "zep_tools.py",
        base_dir / "api" / "graph.py",
    ]
    forbidden_modules = {"zep_cloud", "app.utils.zep", "utils.zep", "app.utils.zep_paging", "utils.zep_paging"}
    for file_path in files_to_check:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_modules, f"{file_path.name} importe {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not any(mod == f or mod.startswith(f + ".") for f in forbidden_modules), (
                    f"{file_path.name} importe from {mod}"
                )

