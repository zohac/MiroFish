"""Tests unitaires hermétiques pour l'adaptation du chemin de lecture aux entités Graphiti (Story 003-4).

Vérifie :
1. La résolution ordonnée de get_entity_type sur EntityNode et GraphNode.
2. Le filtrage agnostique dans filter_defined_entities (non-rejet des entités :Entity).
3. Le support de defined_entity_types avec et sans filtre.
4. get_entities_by_type et get_entity_with_context pour les graphes Graphiti.
5. L'intégration avec simulation_config_generator et oasis_profile_generator.
"""

from typing import Any, Callable, Dict, List, Optional
import pytest

from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.simulation_config_generator import SimulationConfigGenerator
from app.services.zep_entity_reader import (
    EntityNode,
    FilteredEntities,
    ZepEntityReader,
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
from app.utils.graph_store.errors import GraphNotFoundError


class MockGraphitiStore(GraphStore):
    """Store factice simulant un graphe Graphiti local."""

    def __init__(self):
        self.nodes: Dict[str, List[GraphNode]] = {}
        self.edges: Dict[str, List[GraphEdge]] = {}

    def create_graph(self, name: str, graph_id: Optional[str] = None) -> str:
        return graph_id or "test-graph"

    def delete_graph(self, graph_id: str) -> None:
        pass

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        nodes = self.nodes.get(graph_id, [])
        edges = self.edges.get(graph_id, [])
        return {
            "graph_id": graph_id,
            "nodes": [n.to_dict() for n in nodes],
            "edges": [e.to_dict() for e in edges],
            "node_count": len(nodes),
            "edge_count": len(edges),
            "statistics": {"node_count": len(nodes), "edge_count": len(edges)},
        }

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        nodes = self.nodes.get(graph_id, [])
        edges = self.edges.get(graph_id, [])
        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=["Entity"],
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
        return EpisodeRecord(uuid="ep-1", graph_id=graph_id, processed=True)

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 350,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> BatchSubmissionRecord:
        return BatchSubmissionRecord(
            batch_id="batch-1",
            operation_id="op-1",
            episode_uuids=["ep-1"],
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
        return list(self.nodes.get(graph_id, []))

    def get_all_edges(
        self, graph_id: str, include_temporal: bool = True
    ) -> List[GraphEdge]:
        return list(self.edges.get(graph_id, []))

    def get_node(self, graph_id: str, node_uuid: str) -> Optional[GraphNode]:
        for node in self.nodes.get(graph_id, []):
            if node.uuid == node_uuid:
                return node
        raise GraphNotFoundError(f"Node {node_uuid} non trouvé")

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[GraphEdge]:
        result = []
        for edge in self.edges.get(graph_id, []):
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
        return GraphSearchResult(
            facts=[],
            nodes=self.nodes.get(graph_id, [])[:limit],
            edges=self.edges.get(graph_id, [])[:limit],
            query=query,
            total_count=0,
        )


# ============================================================================
# Tests unitaires de la chaîne de résolution de get_entity_type
# ============================================================================


def test_entity_node_get_entity_type_resolution_order():
    """Vérifie la chaîne de priorité de get_entity_type sur EntityNode."""
    # 1. Custom label prioritaire
    node_custom = EntityNode(
        uuid="n-1",
        name="Alice",
        labels=["Entity", "Node", "Politician"],
        summary="Députée",
        attributes={"entity_type": "Student"},
    )
    assert node_custom.get_entity_type() == "Politician"

    # 2. Attribut explicite entity_type
    node_attr_entity_type = EntityNode(
        uuid="n-2",
        name="Bob",
        labels=["Entity"],
        summary="Étudiant",
        attributes={"entity_type": "Student"},
    )
    assert node_attr_entity_type.get_entity_type() == "Student"

    # 3. Attribut explicite type
    node_attr_type = EntityNode(
        uuid="n-3",
        name="Acme",
        labels=["Entity"],
        summary="Entreprise",
        attributes={"type": "Company"},
    )
    assert node_attr_type.get_entity_type() == "Company"

    # 4. Attribut explicite category
    node_attr_cat = EntityNode(
        uuid="n-4",
        name="Greenpeace",
        labels=["Entity"],
        summary="ONG",
        attributes={"category": "NGO"},
    )
    assert node_attr_cat.get_entity_type() == "NGO"

    # 5. Repli générique Entity si label Entity ou Node présent
    node_graphiti = EntityNode(
        uuid="n-5",
        name="Charlie",
        labels=["Entity"],
        summary="Citoyen",
        attributes={},
    )
    assert node_graphiti.get_entity_type() == "Entity"

    node_just_node = EntityNode(
        uuid="n-6",
        name="Objet",
        labels=["Node"],
        summary="Élément",
        attributes={},
    )
    assert node_just_node.get_entity_type() == "Entity"

    # 6. None si aucun label ni attribut
    node_empty = EntityNode(
        uuid="n-7",
        name="Inconnu",
        labels=[],
        summary="",
        attributes={},
    )
    assert node_empty.get_entity_type() is None


def test_graph_node_get_entity_type_resolution_order():
    """Vérifie la chaîne de priorité de get_entity_type sur GraphNode."""
    # Custom label
    gn_custom = GraphNode(uuid="g-1", name="Alice", labels=["Entity", "Journalist"])
    assert gn_custom.get_entity_type() == "Journalist"

    # Attributs
    gn_attr = GraphNode(
        uuid="g-2",
        name="TechCorp",
        labels=["Entity"],
        attributes={"entity_type": "Corporation"},
    )
    assert gn_attr.get_entity_type() == "Corporation"

    # Repli Entity
    gn_generic = GraphNode(uuid="g-3", name="Citoyen", labels=["Entity"])
    assert gn_generic.get_entity_type() == "Entity"

    # Vide
    gn_empty = GraphNode(uuid="g-4", name="Vide", labels=[])
    assert gn_empty.get_entity_type() is None


# ============================================================================
# Tests unitaires du filtrage agnostique filter_defined_entities
# ============================================================================


def test_filter_defined_entities_graphiti_pure():
    """Critère C4 : Un graphe Graphiti avec label unique :Entity retourne toutes les entités exploitables."""
    store = MockGraphitiStore()
    graph_id = "graph-graphiti-pure"
    store.nodes[graph_id] = [
        GraphNode(uuid="g-1", name="Alice", labels=["Entity"], summary="Porte-parole"),
        GraphNode(uuid="g-2", name="Bob", labels=["Entity"], summary="Manifestant"),
        GraphNode(uuid="g-3", name="Syndicat", labels=["Entity"], summary="Organisation"),
    ]
    store.edges[graph_id] = [
        GraphEdge(
            uuid="e-1",
            name="SUPPORTS",
            fact="Bob supports Syndicat",
            source_node_uuid="g-2",
            target_node_uuid="g-3",
        )
    ]

    reader = ZepEntityReader(store=store)

    # 1. Sans filtre de type -> 100 % des nœuds retenus
    result = reader.filter_defined_entities(graph_id)
    assert result.total_count == 3
    assert result.filtered_count == 3
    assert len(result.entities) == 3
    assert result.entity_types == {"Entity"}
    names = {e.name for e in result.entities}
    assert names == {"Alice", "Bob", "Syndicat"}

    # Vérification de l'enrichissement par arêtes
    bob = next(e for e in result.entities if e.name == "Bob")
    assert len(bob.related_edges) == 1
    assert bob.related_edges[0]["edge_name"] == "SUPPORTS"
    assert bob.related_edges[0]["direction"] == "outgoing"
    assert len(bob.related_nodes) == 1
    assert bob.related_nodes[0]["name"] == "Syndicat"

    # 2. Avec defined_entity_types=["Entity"] -> 100 % des nœuds retenus
    res_entity = reader.filter_defined_entities(
        graph_id, defined_entity_types=["Entity"]
    )
    assert res_entity.filtered_count == 3

    # 3. Avec defined_entity_types ciblant un type absent -> 0 nœud
    res_politician = reader.filter_defined_entities(
        graph_id, defined_entity_types=["Politician"]
    )
    assert res_politician.filtered_count == 0


def test_filter_defined_entities_mixed_graph():
    """Vérifie le filtrage sur un graphe mixte contenant labels Zep, labels Graphiti et attributs."""
    store = MockGraphitiStore()
    graph_id = "graph-mixed"
    store.nodes[graph_id] = [
        # Nœud Graphiti standard
        GraphNode(uuid="n-1", name="Citoyen 1", labels=["Entity"], summary="Habitant"),
        # Nœud Zep avec labels custom
        GraphNode(
            uuid="n-2",
            name="Ministre",
            labels=["Entity", "Politician", "Executive"],
            summary="Ministre de l'Intérieur",
        ),
        # Nœud Graphiti enrichi par attribut
        GraphNode(
            uuid="n-3",
            name="Action Climat",
            labels=["Entity"],
            attributes={"category": "Movement"},
            summary="Collectif écologiste",
        ),
        # Nœud sans type identifiable (doit être ignoré)
        GraphNode(uuid="n-4", name="Nœud Invalide", labels=[], attributes={}),
    ]

    reader = ZepEntityReader(store=store)

    # 1. Sans filtre -> retient n-1, n-2, n-3 et ignore n-4
    result_all = reader.filter_defined_entities(graph_id)
    assert result_all.total_count == 4
    assert result_all.filtered_count == 3
    assert result_all.entity_types == {"Entity", "Politician", "Movement"}
    names = {e.name for e in result_all.entities}
    assert names == {"Citoyen 1", "Ministre", "Action Climat"}

    # 2. Avec defined_entity_types=["Politician", "Movement"]
    result_subset = reader.filter_defined_entities(
        graph_id, defined_entity_types=["Politician", "Movement"]
    )
    assert result_subset.filtered_count == 2
    assert {e.name for e in result_subset.entities} == {"Ministre", "Action Climat"}

    # 3. Avec defined_entity_types=["Executive"] (second label de n-2)
    result_exec = reader.filter_defined_entities(
        graph_id, defined_entity_types=["Executive"]
    )
    assert result_exec.filtered_count == 1
    assert result_exec.entities[0].name == "Ministre"


def test_filter_defined_entities_enrich_flag():
    """Vérifie le respect du paramètre enrich_with_edges=False."""
    store = MockGraphitiStore()
    graph_id = "graph-no-enrich"
    store.nodes[graph_id] = [
        GraphNode(uuid="n-1", name="Alice", labels=["Entity"], summary="Porte-parole"),
        GraphNode(uuid="n-2", name="Bob", labels=["Entity"], summary="Manifestant"),
    ]
    store.edges[graph_id] = [
        GraphEdge(
            uuid="e-1",
            name="KNOWS",
            fact="Alice knows Bob",
            source_node_uuid="n-1",
            target_node_uuid="n-2",
        )
    ]

    reader = ZepEntityReader(store=store)
    result = reader.filter_defined_entities(graph_id, enrich_with_edges=False)

    assert result.filtered_count == 2
    for entity in result.entities:
        assert entity.related_edges == []
        assert entity.related_nodes == []


# ============================================================================
# Tests unitaires de get_entities_by_type et get_entity_with_context
# ============================================================================


def test_get_entities_by_type_graphiti():
    """Vérifie get_entities_by_type avec type générique 'Entity' et type spécifique."""
    store = MockGraphitiStore()
    graph_id = "graph-by-type"
    store.nodes[graph_id] = [
        GraphNode(uuid="n-1", name="Alice", labels=["Entity"]),
        GraphNode(uuid="n-2", name="Bob", labels=["Entity", "Student"]),
    ]

    reader = ZepEntityReader(store=store)

    # Extraction par type "Entity"
    entities_gen = reader.get_entities_by_type(graph_id, "Entity")
    assert len(entities_gen) >= 1
    assert any(e.name == "Alice" for e in entities_gen)

    # Extraction par type "Student"
    entities_stu = reader.get_entities_by_type(graph_id, "Student")
    assert len(entities_stu) == 1
    assert entities_stu[0].name == "Bob"


def test_get_entity_with_context_graphiti():
    """Vérifie que get_entity_with_context construit un EntityNode complet avec relations bidirectionnelles."""
    store = MockGraphitiStore()
    graph_id = "graph-context"
    node_alice = GraphNode(uuid="n-1", name="Alice", labels=["Entity"], summary="Leader")
    node_bob = GraphNode(uuid="n-2", name="Bob", labels=["Entity"], summary="Membre")
    node_orga = GraphNode(uuid="n-3", name="Orga", labels=["Entity"], summary="Collectif")

    edge_outgoing = GraphEdge(
        uuid="e-1",
        name="MANAGES",
        fact="Alice manages Bob",
        source_node_uuid="n-1",
        target_node_uuid="n-2",
    )
    edge_incoming = GraphEdge(
        uuid="e-2",
        name="MEMBER_OF",
        fact="Orga includes Alice",
        source_node_uuid="n-3",
        target_node_uuid="n-1",
    )

    store.nodes[graph_id] = [node_alice, node_bob, node_orga]
    store.edges[graph_id] = [edge_outgoing, edge_incoming]

    reader = ZepEntityReader(store=store)
    entity = reader.get_entity_with_context(graph_id, "n-1")

    assert entity is not None
    assert entity.uuid == "n-1"
    assert entity.name == "Alice"
    assert entity.get_entity_type() == "Entity"
    assert len(entity.related_edges) == 2

    # Vérification des directions
    out_edge = next(e for e in entity.related_edges if e["direction"] == "outgoing")
    assert out_edge["edge_name"] == "MANAGES"
    assert out_edge["target_node_uuid"] == "n-2"

    in_edge = next(e for e in entity.related_edges if e["direction"] == "incoming")
    assert in_edge["edge_name"] == "MEMBER_OF"
    assert in_edge["source_node_uuid"] == "n-3"

    # Vérification des nœuds liés
    related_names = {rn["name"] for rn in entity.related_nodes}
    assert related_names == {"Bob", "Orga"}


# ============================================================================
# Tests d'intégration avec les consommateurs en aval
# ============================================================================


def test_simulation_config_generator_summarize_entities_with_generic_graphiti():
    """Vérifie que simulation_config_generator traite les entités génériques sans Unknown ni erreur."""
    entities = [
        EntityNode(
            uuid="n-1",
            name="Alice",
            labels=["Entity"],
            summary="Représentante syndicale engagée",
            attributes={},
        ),
        EntityNode(
            uuid="n-2",
            name="Bob",
            labels=["Entity"],
            summary="Employé du secteur tertiaire",
            attributes={},
        ),
    ]

    generator = SimulationConfigGenerator(api_key="fake-key")
    summary = generator._summarize_entities(entities)

    assert "### Entity (2个)" in summary
    assert "Alice: Représentante syndicale engagée" in summary
    assert "Bob: Employé du secteur tertiaire" in summary


def test_oasis_profile_generator_rule_based_fallback_with_generic_graphiti():
    """Vérifie que oasis_profile_generator génère des profils pour des entités typées 'Entity'."""
    store = MockGraphitiStore()
    generator = OasisProfileGenerator(
        api_key="fake-key",
        store=store,
        graph_id="graph-oasis",
    )

    entity = EntityNode(
        uuid="n-1",
        name="Valérie",
        labels=["Entity"],
        summary="Écologiste active sur les réseaux",
        attributes={},
    )

    profile = generator.generate_profile_from_entity(
        entity=entity,
        user_id=1,
        use_llm=False,  # Test rule-based hermétique
    )

    assert profile is not None
    assert profile.user_id == 1
    assert profile.name == "Valérie"
    assert profile.persona is not None
    assert len(profile.persona) > 0


def test_filter_defined_entities_handles_none_values_and_empty_labels():
    """Vérifie la robustesse face aux champs None et labels avec espaces/vides (Patch BMad)."""
    store = MockGraphitiStore()
    graph_id = "graph-null-safety"

    # Dictionnaire brut simulant des données désérialisées avec valeurs None
    raw_node_none = {
        "uuid": "n-none",
        "name": "Nœud Null",
        "labels": None,
        "attributes": None,
        "summary": None,
    }
    # Dictionnaire brut avec labels contenant des espaces ou chaînes vides
    raw_node_whitespace = {
        "uuid": "n-ws",
        "name": "Nœud Espaces",
        "labels": ["", "  ", "  Acteur  ", "Entity"],
        "attributes": {"entity_type": "  Specialiste  "},
        "summary": "Résumé valide",
    }
    # Nœud sans custom labels avec attribut vide
    raw_node_generic_safe = {
        "uuid": "n-gen",
        "name": "Nœud Générique",
        "labels": ["Entity"],
        "attributes": None,
        "summary": "Entité sans attributs",
    }

    # Injecte directement ces dictionnaires dans le store
    class RawStore(MockGraphitiStore):
        def get_all_nodes(self, gid: str) -> List[Any]:
            return [raw_node_none, raw_node_whitespace, raw_node_generic_safe]

    reader = ZepEntityReader(store=RawStore())
    result = reader.filter_defined_entities(graph_id, enrich_with_edges=False)

    # raw_node_none : aucun type candidat (labels=None, attributes=None) -> ignoré proprement
    # raw_node_whitespace : custom label 'Acteur' résolu après strip()
    # raw_node_generic_safe : type 'Entity' résolu
    assert result.total_count == 3
    assert result.filtered_count == 2
    assert "Acteur" in result.entity_types
    assert "Entity" in result.entity_types

    entity_ws = next(e for e in result.entities if e.name == "Nœud Espaces")
    assert entity_ws.get_entity_type() == "Acteur"

