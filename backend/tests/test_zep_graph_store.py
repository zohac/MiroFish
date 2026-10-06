"""Tests unitaires hermétiques pour ZepGraphStore.

Tous les appels au SDK Zep Cloud et au réseau sont rigoureusement mockés.
Aucune dépendance externe ni configuration .env réelle n'est requise.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, call, patch
import httpx
import pytest
from zep_cloud.core.api_error import ApiError as ZepApiError
from zep_cloud.errors.not_found_error import NotFoundError

from app.utils.graph_store import (
    BatchSubmissionRecord,
    EpisodeRecord,
    GraphConnectionError,
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphNotFoundError,
    GraphSearchResult,
    GraphStoreError,
    GraphTimeoutError,
    GraphValidationError,
    ZepGraphStore,
)


# --- Objets factices Zep pour simulation des réponses SDK ---


class DummyZepNode:
    def __init__(
        self,
        uuid_: str = "n-1",
        name: str = "Alice",
        labels: Optional[List[str]] = None,
        summary: str = "Chercheuse",
        attributes: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = "2026-10-06T10:00:00Z",
    ) -> None:
        self.uuid_ = uuid_
        self.name = name
        self.labels = labels if labels is not None else ["Entity", "Person"]
        self.summary = summary
        self.attributes = attributes if attributes is not None else {"field": "IA"}
        self.created_at = created_at


class DummyZepEdge:
    def __init__(
        self,
        uuid_: str = "e-1",
        name: str = "collaborates_with",
        fact: str = "Alice collabore avec Bob",
        source_node_uuid: str = "n-1",
        target_node_uuid: str = "n-2",
        fact_type: str = "collaboration",
        attributes: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = "2026-10-06T10:00:00Z",
        valid_at: Optional[str] = "2024-01-01T00:00:00Z",
        invalid_at: Optional[str] = None,
        expired_at: Optional[str] = None,
        episodes: Optional[List[str]] = None,
    ) -> None:
        self.uuid_ = uuid_
        self.name = name
        self.fact = fact
        self.source_node_uuid = source_node_uuid
        self.target_node_uuid = target_node_uuid
        self.fact_type = fact_type
        self.attributes = attributes if attributes is not None else {"role": "co-auteur"}
        self.created_at = created_at
        self.valid_at = valid_at
        self.invalid_at = invalid_at
        self.expired_at = expired_at
        self.episodes = episodes if episodes is not None else ["ep-1"]


class DummyZepEpisode:
    def __init__(
        self,
        uuid_: str = "ep-10",
        processed: bool = True,
        created_at: Optional[str] = "2026-10-06T10:00:00Z",
    ) -> None:
        self.uuid_ = uuid_
        self.processed = processed
        self.created_at = created_at


class DummyRawPage:
    def __init__(self, data: List[Any], next_cursor: Optional[str] = None) -> None:
        self.data = data
        self.headers = {"zep-next-cursor": next_cursor} if next_cursor else {}


@pytest.fixture
def mock_zep_client() -> MagicMock:
    """Fixture fournissant un mock complet du client Zep."""
    client = MagicMock()
    return client


# --- 1. Initialisation et configuration ---


def test_init_with_injected_client(mock_zep_client: MagicMock):
    """Vérifie l'injection de dépendance directe du client pour les tests."""
    store = ZepGraphStore(client=mock_zep_client)
    assert store._client is mock_zep_client


def test_init_without_api_key_raises_validation_error(monkeypatch: pytest.MonkeyPatch):
    """Vérifie que l'absence de clé API lève GraphValidationError."""
    monkeypatch.setattr("app.config.Config.ZEP_API_KEY", "")
    with pytest.raises(GraphValidationError) as exc:
        ZepGraphStore(api_key=None)
    assert "ZEP_API_KEY" in str(exc.value)



@patch("app.utils.graph_store.zep_store.get_zep_client")
def test_init_with_explicit_api_key(mock_get_client: MagicMock):
    """Vérifie la délégation à get_zep_client lorsque api_key est fournie."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    store = ZepGraphStore(api_key="test-key-123", timeout=45.0)
    mock_get_client.assert_called_once_with(api_key="test-key-123", timeout=45.0)
    assert store._client is mock_client


# --- 2. Cycle de vie : create_graph, delete_graph, get_graph_data, get_graph_info ---


def test_create_graph_success(mock_zep_client: MagicMock):
    """Vérifie la création réussie d'un graphe avec son identifiant cible."""
    store = ZepGraphStore(client=mock_zep_client)
    gid = store.create_graph(name="Graphe Alpha", graph_id="proj-alpha")
    assert gid == "proj-alpha"
    mock_zep_client.graph.create.assert_called_once_with(
        graph_id="proj-alpha",
        name="Graphe Alpha",
        description="MiroFish Social Simulation Graph",
    )


def test_create_graph_generates_id_if_none(mock_zep_client: MagicMock):
    """Vérifie la génération automatique d'un graph_id commençant par mirofish_."""
    store = ZepGraphStore(client=mock_zep_client)
    gid = store.create_graph(name="Graphe Beta")
    assert gid.startswith("mirofish_")
    assert mock_zep_client.graph.create.call_count == 1


def test_create_graph_empty_name_raises_validation_error(mock_zep_client: MagicMock):
    """Vérifie le rejet d'un nom de graphe vide."""
    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(GraphValidationError):
        store.create_graph(name="")


def test_create_graph_reconciliation_on_transient_error(mock_zep_client: MagicMock):
    """Vérifie la réconciliation via graph.get après un échec réseau réessayable sur create."""
    mock_zep_client.graph.create.side_effect = httpx.ConnectError("Connexion interrompue")
    mock_zep_client.graph.get.return_value = MagicMock(graph_id="proj-reconciled")

    store = ZepGraphStore(client=mock_zep_client)
    gid = store.create_graph(name="Graphe Reconcilié", graph_id="proj-reconciled")
    assert gid == "proj-reconciled"
    mock_zep_client.graph.get.assert_called_once_with("proj-reconciled")


def test_create_graph_reconciliation_failure_raises_connection_error(mock_zep_client: MagicMock):
    """Vérifie qu'un échec total de réconciliation lève GraphConnectionError."""
    mock_zep_client.graph.create.side_effect = httpx.ConnectError("Réseau indisponible")
    mock_zep_client.graph.get.side_effect = httpx.ConnectError("Toujours indisponible")

    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(GraphConnectionError):
        store.create_graph(name="Graphe Échoué", graph_id="proj-fail")


def test_delete_graph_success(mock_zep_client: MagicMock):
    """Vérifie la suppression d'un graphe."""
    store = ZepGraphStore(client=mock_zep_client)
    store.delete_graph("proj-delete")
    mock_zep_client.graph.delete.assert_called_once_with(graph_id="proj-delete")


def test_delete_graph_validation_error_on_empty_id(mock_zep_client: MagicMock):
    """Vérifie le rejet d'un graph_id vide pour delete_graph."""
    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(GraphValidationError):
        store.delete_graph("")


def test_delete_graph_translates_not_found(mock_zep_client: MagicMock):
    """Vérifie la traduction de 404 en GraphNotFoundError lors d'une suppression."""
    mock_zep_client.graph.delete.side_effect = NotFoundError("Graph not found")
    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(GraphNotFoundError):
        store.delete_graph("proj-inexistant")


def test_get_graph_data_success(mock_zep_client: MagicMock):
    """Vérifie que get_graph_data retourne la structure complète rétrocompatible."""
    node1 = DummyZepNode(uuid_="n-1", name="Alice", labels=["Entity", "Person"])
    node2 = DummyZepNode(uuid_="n-2", name="Bob", labels=["Entity", "Person"])
    edge1 = DummyZepEdge(
        uuid_="e-1",
        name="knows",
        fact="Alice connaît Bob",
        source_node_uuid="n-1",
        target_node_uuid="n-2",
    )

    mock_zep_client.graph.node.with_raw_response.get_by_graph_id.return_value = DummyRawPage([node1, node2])
    mock_zep_client.graph.edge.with_raw_response.get_by_graph_id.return_value = DummyRawPage([edge1])

    store = ZepGraphStore(client=mock_zep_client)
    data = store.get_graph_data("proj-data")

    assert data["graph_id"] == "proj-data"
    assert data["node_count"] == 2
    assert data["edge_count"] == 1
    assert data["statistics"] == {"node_count": 2, "edge_count": 1}

    # Nœuds
    assert len(data["nodes"]) == 2
    assert data["nodes"][0]["uuid"] == "n-1"
    assert data["nodes"][0]["name"] == "Alice"
    assert data["nodes"][0]["labels"] == ["Entity", "Person"]

    # Arêtes avec résolution des noms
    assert len(data["edges"]) == 1
    edge_data = data["edges"][0]
    assert edge_data["uuid"] == "e-1"
    assert edge_data["source_node_name"] == "Alice"
    assert edge_data["target_node_name"] == "Bob"
    assert edge_data["valid_at"] == "2024-01-01T00:00:00Z"
    assert edge_data["episodes"] == ["ep-1"]


def test_get_graph_info_computes_statistics_and_entity_types(mock_zep_client: MagicMock):
    """Vérifie le calcul synthétique de GraphInfo et le filtrage des labels."""
    node1 = DummyZepNode(uuid_="n-1", labels=["Entity", "Politician", "Minister"])
    node2 = DummyZepNode(uuid_="n-2", labels=["Entity", "Node", "Organization"])
    edge1 = DummyZepEdge(uuid_="e-1")

    mock_zep_client.graph.node.with_raw_response.get_by_graph_id.return_value = DummyRawPage([node1, node2])
    mock_zep_client.graph.edge.with_raw_response.get_by_graph_id.return_value = DummyRawPage([edge1])

    store = ZepGraphStore(client=mock_zep_client)
    info = store.get_graph_info("proj-info")

    assert isinstance(info, GraphInfo)
    assert info.graph_id == "proj-info"
    assert info.node_count == 2
    assert info.edge_count == 1
    # Doit exclure Entity et Node
    assert info.entity_types == ["Minister", "Organization", "Politician"]


# --- 3. Traduction d'erreurs ---


@pytest.mark.parametrize(
    "raised,expected_type",
    [
        (NotFoundError("Non trouvé"), GraphNotFoundError),
        (ZepApiError(status_code=404, body="Absent"), GraphNotFoundError),
        (ZepApiError(status_code=502, body="Bad Gateway"), GraphConnectionError),
        (ZepApiError(status_code=503, body="Unavailable"), GraphConnectionError),
        (ZepApiError(status_code=504, body="Gateway Timeout"), GraphConnectionError),
        (ZepApiError(status_code=408, body="Request Timeout"), GraphTimeoutError),
        (ZepApiError(status_code=400, body="Bad Request"), GraphValidationError),
        (ZepApiError(status_code=500, body="Internal Error"), GraphStoreError),
        (httpx.ConnectError("Connection refused"), GraphConnectionError),
        (httpx.NetworkError("Network down"), GraphConnectionError),
        (httpx.TimeoutException("Read timeout"), GraphTimeoutError),
        (TimeoutError("Python timeout"), GraphTimeoutError),
        (ValueError("Invalid argument"), GraphValidationError),
        (RuntimeError("Unexpected crash"), GraphStoreError),
    ],
)
def test_error_translation_table(mock_zep_client: MagicMock, raised: Exception, expected_type: type):
    """Valide l'ensemble de la table de correspondance des exceptions d'architecture §4."""
    mock_zep_client.graph.delete.side_effect = raised
    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(expected_type):
        store.delete_graph("proj-err")


# --- 4. Ingestion unitaire et par lots ---


def test_add_episode_success(mock_zep_client: MagicMock):
    """Vérifie l'ajout unitaire d'un épisode et la conversion en EpisodeRecord."""
    mock_zep_client.graph.add.return_value = DummyZepEpisode(uuid_="ep-42", processed=True)
    store = ZepGraphStore(client=mock_zep_client)

    rec = store.add_episode(
        graph_id="proj-ep",
        text="Texte de fait.",
        source_description="desc",
        metadata={"platform": "twitter"},
        created_at="2026-10-06T12:00:00Z",
    )
    assert isinstance(rec, EpisodeRecord)
    assert rec.uuid == "ep-42"
    assert rec.graph_id == "proj-ep"
    assert rec.processed is True
    mock_zep_client.graph.add.assert_called_once()


def test_add_episode_empty_text_raises_validation_error(mock_zep_client: MagicMock):
    """Vérifie le rejet d'un texte d'épisode vide."""
    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(GraphValidationError):
        store.add_episode(graph_id="proj-ep", text="   ")


def test_wait_for_episodes_success(mock_zep_client: MagicMock):
    """Vérifie l'attente du traitement des épisodes via polling."""
    mock_zep_client.graph.episode.get.side_effect = [
        DummyZepEpisode(uuid_="ep-1", processed=False),
        DummyZepEpisode(uuid_="ep-1", processed=True),
    ]
    store = ZepGraphStore(client=mock_zep_client)
    assert store.wait_for_episodes("proj-ep", ["ep-1"], timeout=10.0) is True


def test_wait_for_episodes_timeout(mock_zep_client: MagicMock):
    """Vérifie la levée de GraphTimeoutError en cas de dépassement du délai de polling."""
    mock_zep_client.graph.episode.get.return_value = DummyZepEpisode(uuid_="ep-slow", processed=False)
    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(GraphTimeoutError):
        store.wait_for_episodes("proj-ep", ["ep-slow"], timeout=0.01)


def test_add_text_batch_success(mock_zep_client: MagicMock):
    """Vérifie l'ingestion par lots, les callbacks et le retour de BatchSubmissionRecord."""
    mock_batch = MagicMock(batch_id="batch-123")
    mock_zep_client.batch.create.return_value = mock_batch

    item_ack1 = MagicMock(episode_uuid="ep-b1", sequence_index=0)
    item_ack2 = MagicMock(episode_uuid="ep-b2", sequence_index=1)
    mock_zep_client.batch.add.return_value = [item_ack1, item_ack2]
    mock_zep_client.batch.process.return_value = MagicMock()

    progress_log = []
    store = ZepGraphStore(client=mock_zep_client)
    batch_rec = store.add_text_batch(
        graph_id="proj-batch",
        chunks=["Fragment 1", "Fragment 2"],
        batch_size=350,
        progress_callback=lambda st, cur, tot: progress_log.append((st, cur, tot)),
    )

    assert isinstance(batch_rec, BatchSubmissionRecord)
    assert batch_rec.batch_id == "batch-123"
    assert batch_rec.item_count == 2
    assert batch_rec.episode_uuids == ["ep-b1", "ep-b2"]
    assert len(progress_log) == 1
    assert progress_log[0] == ("sending", 2, 2)
    mock_zep_client.batch.process.assert_called_once_with(batch_id="batch-123")


def test_add_text_batch_validation_limits(mock_zep_client: MagicMock):
    """Vérifie la validation stricte des limites d'ingestion par lots."""
    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(GraphValidationError):
        store.add_text_batch("g-1", chunks=[])
    with pytest.raises(GraphValidationError):
        store.add_text_batch("g-1", chunks=["a"], batch_size=0)
    with pytest.raises(GraphValidationError):
        store.add_text_batch("g-1", chunks=["a"], batch_size=351)
    with pytest.raises(GraphValidationError):
        store.add_text_batch("g-1", chunks=["x" * 10_001])


def test_wait_for_batch_success(mock_zep_client: MagicMock):
    """Vérifie l'attente avec succès d'un lot terminé."""
    summary_done = MagicMock(
        status="succeeded",
        progress=MagicMock(percent_complete=100.0),
    )
    mock_zep_client.batch.get.return_value = summary_done

    store = ZepGraphStore(client=mock_zep_client)
    batch = BatchSubmissionRecord(
        batch_id="b-1",
        operation_id="op-1",
        episode_uuids=["ep-1"],
        item_count=1,
    )
    calls = []
    res = store.wait_for_batch(batch, progress_callback=lambda st, r: calls.append((st, r)))
    assert res is True
    assert len(calls) >= 1
    assert calls[-1] == ("completed", 1.0)


def test_wait_for_batch_failure_status(mock_zep_client: MagicMock):
    """Vérifie qu'un statut terminal d'échec lève GraphStoreError."""
    summary_failed = MagicMock(
        status="failed",
        progress=MagicMock(percent_complete=50.0),
    )
    mock_zep_client.batch.get.return_value = summary_failed

    store = ZepGraphStore(client=mock_zep_client)
    batch = BatchSubmissionRecord(batch_id="b-fail", operation_id="op-1", episode_uuids=[], item_count=1)
    with pytest.raises(GraphStoreError) as exc:
        store.wait_for_batch(batch)
    assert "échec" in str(exc.value) or "failed" in str(exc.value)


def test_wait_for_batch_timeout(mock_zep_client: MagicMock):
    """Vérifie la levée de GraphTimeoutError si le lot dépasse le délai alloué."""
    mock_zep_client.batch.get.return_value = MagicMock(
        status="processing", progress=MagicMock(percent_complete=10.0)
    )
    store = ZepGraphStore(client=mock_zep_client)
    batch = BatchSubmissionRecord(batch_id="b-slow", operation_id="op-1", episode_uuids=[], item_count=1)
    with pytest.raises(GraphTimeoutError):
        store.wait_for_batch(batch, timeout=0.01)


def test_add_text_batch_reconciliation_on_transient_create_error(mock_zep_client: MagicMock):
    """Vérifie la réconciliation automatique lors d'une erreur réseau sur batch.create."""
    mock_zep_client.batch.create.side_effect = httpx.ConnectError("Connexion coupée")
    # Simulation de la réponse de list après réconciliation
    matching_batch = MagicMock(
        batch_id="batch-reconciled",
        metadata={
            "graph_id": "proj-reconcile-batch",
            "mirofish_operation_id": "op-hash",
        },
    )
    mock_zep_client.batch.list.return_value = MagicMock(batches=[matching_batch], next_cursor=None)
    mock_zep_client.batch.add.return_value = [MagicMock(episode_uuid="ep-rec", sequence_index=0)]
    mock_zep_client.batch.process.return_value = MagicMock()

    store = ZepGraphStore(client=mock_zep_client)
    # Patch de build_operation_id implicite via le hash
    with patch.object(
        store,
        "_find_batch_by_operation_id",
        return_value=matching_batch,
    ):
        batch_rec = store.add_text_batch("proj-reconcile-batch", ["Chunk 1"])
        assert batch_rec.batch_id == "batch-reconciled"


# --- 5. Lecture et parcours ---



def test_get_all_nodes(mock_zep_client: MagicMock):
    """Vérifie la récupération paginée de tous les nœuds."""
    n1 = DummyZepNode(uuid_="n-1", name="Alpha")
    mock_zep_client.graph.node.with_raw_response.get_by_graph_id.return_value = DummyRawPage([n1])

    store = ZepGraphStore(client=mock_zep_client)
    nodes = store.get_all_nodes("proj-nodes")
    assert len(nodes) == 1
    assert isinstance(nodes[0], GraphNode)
    assert nodes[0].uuid == "n-1"
    assert nodes[0].name == "Alpha"


def test_get_all_edges_with_and_without_temporal(mock_zep_client: MagicMock):
    """Vérifie la récupération de toutes les arêtes avec et sans métadonnées temporelles."""
    e1 = DummyZepEdge(
        uuid_="e-1",
        created_at="2026-10-06T10:00:00Z",
        valid_at="2020-01-01T00:00:00Z",
    )
    mock_zep_client.graph.edge.with_raw_response.get_by_graph_id.return_value = DummyRawPage([e1])

    store = ZepGraphStore(client=mock_zep_client)
    # Avec champs temporels
    edges_temp = store.get_all_edges("proj-edges", include_temporal=True)
    assert len(edges_temp) == 1
    assert edges_temp[0].valid_at == "2020-01-01T00:00:00Z"
    assert edges_temp[0].created_at == "2026-10-06T10:00:00Z"

    # Sans champs temporels
    edges_no_temp = store.get_all_edges("proj-edges", include_temporal=False)
    assert len(edges_no_temp) == 1
    assert edges_no_temp[0].valid_at is None
    assert edges_no_temp[0].created_at is None


def test_get_node_existing_enriches_related_edges(mock_zep_client: MagicMock):
    """Vérifie que get_node enrichit le nœud avec ses arêtes connectées."""
    dummy_node = DummyZepNode(uuid_="n-center", name="Center")
    dummy_edge = DummyZepEdge(uuid_="e-link", source_node_uuid="n-center", target_node_uuid="n-other")

    mock_zep_client.graph.node.get.return_value = dummy_node
    mock_zep_client.graph.node.get_edges.return_value = [dummy_edge]

    store = ZepGraphStore(client=mock_zep_client)
    node = store.get_node("proj-node", "n-center")

    assert node is not None
    assert node.uuid == "n-center"
    assert node.name == "Center"
    assert len(node.related_edges) == 1
    assert node.related_edges[0]["uuid"] == "e-link"


def test_get_node_not_found_returns_none(mock_zep_client: MagicMock):
    """Vérifie qu'un nœud inexistant (404) retourne None sans lever d'exception."""
    mock_zep_client.graph.node.get.side_effect = NotFoundError("Node missing")
    store = ZepGraphStore(client=mock_zep_client)
    node = store.get_node("proj-node", "n-missing")
    assert node is None


def test_get_node_edges_not_found_returns_empty_list(mock_zep_client: MagicMock):
    """Vérifie que get_node_edges sur un nœud 404 retourne une liste vide."""
    mock_zep_client.graph.node.get_edges.side_effect = NotFoundError("Edges missing")
    store = ZepGraphStore(client=mock_zep_client)
    edges = store.get_node_edges("proj-node", "n-missing")
    assert edges == []


# --- 6. Recherche sémantique ---


def test_search_scope_edges(mock_zep_client: MagicMock):
    """Vérifie la recherche sur les arêtes avec conversion en GraphSearchResult."""
    mock_edge = DummyZepEdge(uuid_="e-search", fact="Alice est directrice")
    mock_search_res = MagicMock(edges=[mock_edge], nodes=[])
    mock_zep_client.graph.search.return_value = mock_search_res

    store = ZepGraphStore(client=mock_zep_client)
    res = store.search("proj-search", query="directrice", limit=5, scope="edges", reranker="cross_encoder")

    assert isinstance(res, GraphSearchResult)
    assert res.query == "directrice"
    assert res.total_count == 1
    assert res.facts == ["Alice est directrice"]
    assert len(res.edges) == 1
    assert res.edges[0].uuid == "e-search"

    mock_zep_client.graph.search.assert_called_once_with(
        graph_id="proj-search",
        query="directrice",
        limit=5,
        scope="edges",
        reranker="cross_encoder",
    )


def test_search_scope_nodes(mock_zep_client: MagicMock):
    """Vérifie la recherche sur les nœuds."""
    mock_node = DummyZepNode(uuid_="n-search", name="Alice")
    mock_search_res = MagicMock(edges=[], nodes=[mock_node])
    mock_zep_client.graph.search.return_value = mock_search_res

    store = ZepGraphStore(client=mock_zep_client)
    res = store.search("proj-search", query="Alice", scope="nodes", reranker="rrf")

    assert res.total_count == 1
    assert len(res.nodes) == 1
    assert res.nodes[0].name == "Alice"
    assert res.facts == []


def test_search_scope_hybrid(mock_zep_client: MagicMock):
    """Vérifie la recherche hybride combinant nœuds et arêtes."""
    mock_edge = DummyZepEdge(uuid_="e-1", fact="Fait hybride")
    mock_node = DummyZepNode(uuid_="n-1", name="Nœud hybride")

    def mock_search_impl(**kwargs):
        if kwargs.get("scope") == "edges":
            return MagicMock(edges=[mock_edge], nodes=[])
        return MagicMock(edges=[], nodes=[mock_node])

    mock_zep_client.graph.search.side_effect = mock_search_impl

    store = ZepGraphStore(client=mock_zep_client)
    res = store.search("proj-search", query="hybride", scope="hybrid")

    assert len(res.facts) == 1
    assert len(res.edges) == 1
    assert len(res.nodes) == 1
    assert res.total_count == 2



def test_search_validation_errors(mock_zep_client: MagicMock):
    """Vérifie la validation des paramètres de requête, limite et scope."""
    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(GraphValidationError):
        store.search("g-1", query="")
    with pytest.raises(GraphValidationError):
        store.search("g-1", query="test", limit=0)
    with pytest.raises(GraphValidationError):
        store.search("g-1", query="test", scope="invalid_scope")


# --- 7. Ontologie ---


def test_set_ontology_success(mock_zep_client: MagicMock):
    """Vérifie la création dynamique des classes Pydantic et l'appel à set_ontology."""
    ontology = {
        "entity_types": [
            {
                "name": "Politician",
                "description": "Un représentant politique",
                "attributes": [{"name": "mandat", "description": "Mandat électoral"}],
            }
        ],
        "edge_types": [
            {
                "name": "allied_with",
                "description": "Alliance politique",
                "source_targets": [{"source": "Politician", "target": "Politician"}],
            }
        ],
    }

    store = ZepGraphStore(client=mock_zep_client)
    store.set_ontology("proj-onto", ontology)

    mock_zep_client.graph.set_ontology.assert_called_once()
    kwargs = mock_zep_client.graph.set_ontology.call_args[1]
    assert kwargs["graph_ids"] == ["proj-onto"]
    assert "Politician" in kwargs["entities"]
    assert "allied_with" in kwargs["edges"]


def test_set_ontology_invalid_payload(mock_zep_client: MagicMock):
    """Vérifie le rejet d'un payload d'ontologie invalide."""
    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(GraphValidationError):
        store.set_ontology("", {"entity_types": []})
    with pytest.raises(GraphValidationError):
        store.set_ontology("g-1", "not_a_dict")  # type: ignore


# --- 8. Tests complémentaires issus de la revue contradictoire (BMad) ---


def test_search_extracts_temporal_and_episode_fields(mock_zep_client: MagicMock):
    """Vérifie que search extrait et peuple fidèlement les champs temporels et épisodes sur GraphEdge."""
    mock_edge = DummyZepEdge(
        uuid_="e-temp",
        fact="Traité signé",
        created_at="2026-10-06T10:00:00Z",
        valid_at="2024-01-01T00:00:00Z",
        expired_at="2025-01-01T00:00:00Z",
        episodes=["ep-alpha", "ep-beta"],
    )
    mock_zep_client.graph.search.return_value = MagicMock(edges=[mock_edge], nodes=[])

    store = ZepGraphStore(client=mock_zep_client)
    res = store.search("proj-search", query="traité", scope="edges")

    assert len(res.edges) == 1
    edge = res.edges[0]
    assert edge.created_at == "2026-10-06T10:00:00Z"
    assert edge.valid_at == "2024-01-01T00:00:00Z"
    assert edge.expired_at == "2025-01-01T00:00:00Z"
    assert edge.is_expired is True
    assert edge.is_invalid is False
    assert edge.episodes == ["ep-alpha", "ep-beta"]


def test_search_extracts_node_created_at(mock_zep_client: MagicMock):
    """Vérifie que search extrait created_at lors de la recherche de nœuds."""
    mock_node = DummyZepNode(uuid_="n-temp", name="Bob", created_at="2026-10-06T09:00:00Z")
    mock_zep_client.graph.search.return_value = MagicMock(edges=[], nodes=[mock_node])

    store = ZepGraphStore(client=mock_zep_client)
    res = store.search("proj-search", query="Bob", scope="nodes")

    assert len(res.nodes) == 1
    assert res.nodes[0].created_at == "2026-10-06T09:00:00Z"


def test_set_ontology_with_string_lists_and_missing_names(mock_zep_client: MagicMock):
    """Vérifie le support des ontologies avec listes de chaînes et tolérance aux dictionnaires incomplets."""
    store = ZepGraphStore(client=mock_zep_client)
    compact_ontology = {
        "entity_types": ["Person", {"name": "Organization"}, {"invalid": "missing name"}],
        "edge_types": ["KNOWS", {"name": "ALLIED_WITH"}],
    }
    store.set_ontology("proj-compact", compact_ontology)

    mock_zep_client.graph.set_ontology.assert_called_once()
    kwargs = mock_zep_client.graph.set_ontology.call_args[1]
    assert "Person" in kwargs["entities"]
    assert "Organization" in kwargs["entities"]
    assert "KNOWS" in kwargs["edges"]
    assert "ALLIED_WITH" in kwargs["edges"]


def test_wait_for_episodes_validation_guards(mock_zep_client: MagicMock):
    """Vérifie la validation stricte de graph_id et timeout dans wait_for_episodes."""
    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(GraphValidationError) as exc1:
        store.wait_for_episodes("", ["ep-1"])
    assert "graph_id" in str(exc1.value)

    with pytest.raises(GraphValidationError) as exc2:
        store.wait_for_episodes("proj-1", ["ep-1"], timeout=0)
    assert "timeout" in str(exc2.value)


def test_wait_for_batch_validation_guards(mock_zep_client: MagicMock):
    """Vérifie la validation stricte de batch et timeout dans wait_for_batch."""
    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(GraphValidationError) as exc1:
        store.wait_for_batch(None)  # type: ignore
    assert "batch" in str(exc1.value)

    valid_batch = BatchSubmissionRecord(batch_id="b-1", operation_id="op-1", episode_uuids=[], item_count=1)
    with pytest.raises(GraphValidationError) as exc2:
        store.wait_for_batch(valid_batch, timeout=-10.0)
    assert "timeout" in str(exc2.value)


def test_get_node_edges_success_nominal(mock_zep_client: MagicMock):
    """Vérifie la récupération et le mapping nominal des arêtes d'un nœud existant."""
    raw_edge = DummyZepEdge(
        uuid_="e-nom",
        name="works_with",
        fact="Collaboration",
        source_node_uuid="n-1",
        target_node_uuid="n-2",
        valid_at="2024-01-01T00:00:00Z",
        episodes=["ep-1"],
    )
    mock_zep_client.graph.node.get_edges.return_value = [raw_edge]

    store = ZepGraphStore(client=mock_zep_client)
    edges = store.get_node_edges("proj-edges", "n-1")

    assert len(edges) == 1
    assert isinstance(edges[0], GraphEdge)
    assert edges[0].uuid == "e-nom"
    assert edges[0].fact == "Collaboration"
    assert edges[0].valid_at == "2024-01-01T00:00:00Z"
    assert edges[0].episodes == ["ep-1"]


@pytest.mark.parametrize(
    "method_name,args",
    [
        ("delete_graph", ("   ",)),
        ("get_graph_data", ("   ",)),
        ("get_graph_info", ("   ",)),
        ("set_ontology", ("   ", {"entity_types": []})),
        ("add_episode", ("   ", "texte")),
        ("add_text_batch", ("   ", ["chunk"])),
        ("get_all_nodes", ("   ",)),
        ("get_all_edges", ("   ",)),
        ("get_node", ("   ", "n-1")),
        ("get_node", ("proj-1", "   ")),
        ("get_node_edges", ("   ", "n-1")),
        ("get_node_edges", ("proj-1", "   ")),
        ("search", ("   ", "query")),
    ],
)
def test_whitespace_identifiers_raise_validation_error(
    mock_zep_client: MagicMock, method_name: str, args: tuple
):
    """Vérifie que les chaînes composées uniquement d'espaces sont rejetées comme identifiants."""
    store = ZepGraphStore(client=mock_zep_client)
    method = getattr(store, method_name)
    with pytest.raises(GraphValidationError):
        method(*args)


def test_translate_error_maps_type_error(mock_zep_client: MagicMock):
    """Vérifie qu'un TypeError est bien traduit en GraphValidationError."""
    mock_zep_client.graph.delete.side_effect = TypeError("Invalid parameter type")
    store = ZepGraphStore(client=mock_zep_client)
    with pytest.raises(GraphValidationError) as exc:
        store.delete_graph("proj-test")
    assert "Paramètre invalide" in str(exc.value)

