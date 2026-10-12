"""Tests unitaires pour le transport de la provenance dans ZepToolsService (Story 009-4, AC1, AC2)."""

from unittest.mock import MagicMock
import pytest

from app.models.source_document import (
    DocumentRole,
    InformationOrigin,
    classify_provenance_records,
    classify_record_origin,
)
from app.services.zep_tools import EdgeInfo, InsightForgeResult, SearchResult, ZepToolsService
from app.utils.graph_store import (
    GraphEdge,
    GraphNode,
    GraphSearchResult,
    ProvenanceOrigin,
    ProvenanceRecord,
)


def test_edge_info_provenance_serialization():
    """Vérifie que EdgeInfo transporte et sérialise la provenance et les 5 origines (AC1, AC2)."""
    rec_doc = ProvenanceRecord(
        episode_uuid="ep_1",
        resolved=True,
        origin=ProvenanceOrigin.DOCUMENT,
        source_document_id="doc_123",
        source_filename="rapport_an.pdf",
        source_role=DocumentRole.FACTS.value,
        chunk_index=2,
        char_start=150,
        char_end=280,
    )
    rec_sim = ProvenanceRecord(
        episode_uuid="ep_2",
        resolved=True,
        origin=ProvenanceOrigin.SIMULATION,
        simulation_id="sim_456",
        platform="twitter",
    )

    edge_info = EdgeInfo(
        uuid="edge_abc",
        name="CRITIQUE",
        fact="L'opposition critique la gestion du budget",
        source_node_uuid="node_1",
        target_node_uuid="node_2",
        source_node_name="Député X",
        target_node_name="Gouvernement",
        episodes=["ep_1", "ep_2"],
        provenance=[rec_doc, rec_sim],
        origin="documentary",
        origins=["documentary", "simulation"],
        source_document_id="doc_123",
        source_filename="rapport_an.pdf",
        source_role=DocumentRole.FACTS.value,
        chunk_index=2,
        char_start=150,
        char_end=280,
    )

    d = edge_info.to_dict()
    assert d["uuid"] == "edge_abc"
    assert d["origin"] == "documentary"
    assert "documentary" in d["origins"]
    assert "simulation" in d["origins"]
    assert len(d["provenance"]) == 2
    assert d["source_filename"] == "rapport_an.pdf"
    assert d["char_start"] == 150
    assert d["char_end"] == 280

    text = edge_info.to_text(include_temporal=False, include_provenance=True)
    assert "来源: [documentary] rapport_an.pdf (pos: 150-280)" in text


def test_search_result_and_insight_forge_provenance():
    """Vérifie que SearchResult et InsightForgeResult portent la provenance (AC1)."""
    rec = ProvenanceRecord(
        episode_uuid="ep_1",
        resolved=True,
        origin=ProvenanceOrigin.DOCUMENT,
        source_document_id="doc_1",
        source_filename="doc.txt",
        source_role="facts",
        chunk_index=0,
        char_start=0,
        char_end=50,
    )
    res = SearchResult(
        facts=["Fait 1"],
        edges=[{"uuid": "e1", "origin": "documentary"}],
        nodes=[{"uuid": "n1"}],
        query="budget",
        total_count=1,
        provenance=[rec],
        origin="documentary",
        origins=["documentary"],
    )

    d = res.to_dict()
    assert d["origin"] == "documentary"
    assert len(d["provenance"]) == 1
    assert d["provenance"][0]["source_filename"] == "doc.txt"

    forge = InsightForgeResult(
        query="analyse",
        simulation_requirement="contexte",
        sub_queries=["q1"],
        semantic_facts=["Fait A"],
        edges=[{"uuid": "e1"}],
        provenance=[rec],
        origin="documentary",
        origins=["documentary"],
        total_facts=1,
    )
    fd = forge.to_dict()
    assert fd["origin"] == "documentary"
    assert len(fd["provenance"]) == 1
    assert len(fd["edges"]) == 1


def test_classify_provenance_5_origins_and_multi_sources():
    """Vérifie la typologie stricte des 5 origines et la préservation multi-sources (AC2)."""
    # 1. Documentary
    r_doc = ProvenanceRecord(
        episode_uuid="e1",
        resolved=True,
        origin=ProvenanceOrigin.DOCUMENT,
        source_document_id="d1",
        source_filename="doc.pdf",
        source_role=DocumentRole.FACTS.value,
        chunk_index=0,
        char_start=0,
        char_end=10,
    )
    assert classify_record_origin(r_doc) == InformationOrigin.DOCUMENTARY

    # 2. Hypothesis / scenario
    r_hyp = ProvenanceRecord(
        episode_uuid="e2",
        resolved=True,
        origin=ProvenanceOrigin.DOCUMENT,
        source_document_id="d2",
        source_filename="brief.txt",
        source_role=DocumentRole.HYPOTHESES.value,
        chunk_index=0,
        char_start=0,
        char_end=10,
    )
    assert classify_record_origin(r_hyp) == InformationOrigin.HYPOTHESIS

    # 3. Simulation
    r_sim = ProvenanceRecord(
        episode_uuid="e3",
        resolved=True,
        origin=ProvenanceOrigin.SIMULATION,
        simulation_id="sim_1",
    )
    assert classify_record_origin(r_sim) == InformationOrigin.SIMULATION

    # 4. Unknown / legacy / unresolved
    r_leg = ProvenanceRecord(
        episode_uuid="e4",
        resolved=True,
        origin=ProvenanceOrigin.LEGACY,
    )
    assert classify_record_origin(r_leg) == InformationOrigin.UNKNOWN

    r_unres = ProvenanceRecord(
        episode_uuid="e5",
        resolved=False,
        origin=ProvenanceOrigin.UNRESOLVED,
    )
    assert classify_record_origin(r_unres) == InformationOrigin.UNKNOWN

    # Multi-sources : une relation soutenue par un doc ET une simulation conserve les deux origines
    primary, distinct = classify_provenance_records([r_doc, r_sim])
    assert primary == InformationOrigin.DOCUMENTARY
    assert set(distinct) == {InformationOrigin.DOCUMENTARY, InformationOrigin.SIMULATION}


def test_zep_tools_service_resolves_edge_provenance_and_detail():
    """Vérifie que ZepToolsService résout la provenance via GraphStore (AC1)."""
    mock_store = MagicMock()
    mock_edge = GraphEdge(
        uuid="edge_xyz",
        name="ANNONCE",
        fact="Le ministère annonce une réforme",
        source_node_uuid="node_gov",
        target_node_uuid="node_ref",
        source_node_name="Ministère",
        target_node_name="Réforme",
        episodes=["ep_rec_1"],
    )

    prov_record = ProvenanceRecord(
        episode_uuid="ep_rec_1",
        resolved=True,
        origin=ProvenanceOrigin.DOCUMENT,
        source_document_id="doc_loi",
        source_filename="projet_loi.pdf",
        source_role="facts",
        chunk_index=1,
        char_start=100,
        char_end=250,
    )

    mock_store.get_all_edges.return_value = [mock_edge]
    mock_store.get_node_edges.return_value = [mock_edge]
    mock_store.get_edge_provenance.return_value = [prov_record]
    mock_store.get_edges_provenance.return_value = {"edge_xyz": [prov_record]}
    # `get_edge_by_uuid` retourne l'arête ou None selon l'UUID demandé.
    def _lookup_edge(gid, eid, include_temporal=True):
        return mock_edge if eid == "edge_xyz" else None
    mock_store.get_edge_by_uuid.side_effect = _lookup_edge

    service = ZepToolsService(store=mock_store)

    # 1. get_node_edges
    edges = service.get_node_edges("graph_test", "node_gov")
    assert len(edges) == 1
    assert edges[0].uuid == "edge_xyz"
    assert edges[0].origin == "documentary"
    assert edges[0].source_filename == "projet_loi.pdf"
    assert edges[0].char_start == 100
    assert edges[0].char_end == 250
    mock_store.get_edge_provenance.assert_called_with("graph_test", "edge_xyz")

    # 2. get_edge_detail
    detail = service.get_edge_detail("graph_test", "edge_xyz")
    assert detail is not None
    assert detail.uuid == "edge_xyz"
    assert detail.source_document_id == "doc_loi"
    assert detail.origin == "documentary"
    assert detail.episodes == ["ep_rec_1"]

    # Inexistant
    assert service.get_edge_detail("graph_test", "edge_non_existent") is None


def test_zep_tools_search_graph_enriches_provenance():
    """Vérifie que search_graph enrichit les arêtes avec la provenance (AC1)."""
    mock_store = MagicMock()
    mock_edge = GraphEdge(
        uuid="edge_s1",
        name="PARTICIPE",
        fact="L'université participe à l'étude",
        source_node_uuid="univ_1",
        target_node_uuid="etude_1",
        episodes=["ep_univ"],
    )
    mock_node = GraphNode(uuid="univ_1", name="Université", labels=["Organization"], summary="Univ")

    prov_record = ProvenanceRecord(
        episode_uuid="ep_univ",
        resolved=True,
        origin=ProvenanceOrigin.DOCUMENT,
        source_document_id="doc_univ",
        source_filename="etude.pdf",
        source_role="facts",
        chunk_index=3,
        char_start=300,
        char_end=420,
    )

    mock_search_res = GraphSearchResult(
        facts=["L'université participe à l'étude"],
        edges=[mock_edge],
        nodes=[mock_node],
        query="université",
        total_count=1,
    )
    mock_store.search.return_value = mock_search_res
    mock_store.get_edge_provenance.return_value = [prov_record]
    mock_store.get_edges_provenance.return_value = {"edge_s1": [prov_record]}

    service = ZepToolsService(store=mock_store)
    res = service.search_graph("graph_test", "université", limit=5)

    assert res.total_count == 2
    assert res.origin == "documentary"
    assert len(res.provenance) == 1
    assert len(res.edges) == 1
    assert res.edges[0]["source_filename"] == "etude.pdf"
    assert res.edges[0]["char_start"] == 300
    assert res.edges[0]["origin"] == "documentary"


def test_classify_record_origin_uses_source_filename_on_objects():
    """Vérifie que la détection documentaire fonctionne pour les `ProvenanceRecord` (objet)."""
    rec_with_source_filename = ProvenanceRecord(
        episode_uuid="ep_doc",
        resolved=True,
        origin=ProvenanceOrigin.DOCUMENT,
        source_filename="document.txt",
        char_start=10,
        char_end=20,
        # Pas de `filename` (qui était cherché à tort) ni d'`is_documentary`
    )
    # Avant le fix, le fallback par coordonnées ne se déclenchait que via
    # `filename` (champ inexistant sur l'objet) et laissait la trace comme
    # `unknown`. Avec le fix, le champ `source_filename` est aussi reconnu.
    assert classify_record_origin(rec_with_source_filename) == InformationOrigin.DOCUMENTARY


def test_zep_tools_uses_batch_provenance_to_avoid_n_plus_1():
    """Vérifie que `search_graph` et `get_all_edges` font UN appel batch, pas N."""
    from app.utils.graph_store import (
        GraphEdge,
        GraphNode,
        GraphSearchResult,
        ProvenanceOrigin,
        ProvenanceRecord,
    )

    mock_store = MagicMock()
    # Plusieurs arêtes retournées par le store
    edges = [
        GraphEdge(
            uuid=f"edge_{i}",
            name="LINK",
            fact=f"Fait {i}",
            source_node_uuid="n1",
            target_node_uuid="n2",
            episodes=[f"ep_{i}"],
        )
        for i in range(3)
    ]
    mock_store.search.return_value = GraphSearchResult(
        facts=["Fait 0", "Fait 1", "Fait 2"],
        edges=edges,
        nodes=[],
        query="q",
        total_count=3,
    )
    mock_store.get_edges_provenance.return_value = {f"edge_{i}": [] for i in range(3)}
    mock_store.get_all_edges.return_value = edges

    service = ZepToolsService(store=mock_store)

    # search_graph : UN appel à get_edges_provenance, jamais à get_edge_provenance
    service.search_graph("graph_x", "q", limit=5)
    assert mock_store.get_edges_provenance.call_count == 1
    assert mock_store.get_edge_provenance.call_count == 0

    # get_all_edges : idem
    mock_store.get_edges_provenance.reset_mock()
    mock_store.get_edge_provenance.reset_mock()
    service.get_all_edges("graph_x")
    assert mock_store.get_edges_provenance.call_count == 1
    assert mock_store.get_edge_provenance.call_count == 0


def test_zep_tools_get_edge_detail_uses_get_edge_by_uuid():
    """Vérifie que `get_edge_detail` passe par `get_edge_by_uuid` (O(1) potentiel) et pas un scan."""
    from app.utils.graph_store import GraphEdge

    mock_store = MagicMock()
    target = GraphEdge(
        uuid="edge_target",
        name="LINK",
        fact="Fait ciblé",
        source_node_uuid="n1",
        target_node_uuid="n2",
        episodes=[],
    )
    mock_store.get_edge_by_uuid.return_value = target
    mock_store.get_edges_provenance.return_value = {"edge_target": []}

    service = ZepToolsService(store=mock_store)
    info = service.get_edge_detail("graph_x", "edge_target")
    assert info is not None
    assert info.uuid == "edge_target"
    mock_store.get_edge_by_uuid.assert_called_with("graph_x", "edge_target", include_temporal=True)
    # get_all_edges ne doit pas être appelé pour un lookup ciblé
    mock_store.get_all_edges.assert_not_called()
