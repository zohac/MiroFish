"""Tests unitaires hermétiques pour GraphitiGraphStore (Story 003-1).

Valide l'instanciation, le respect du contrat d'interface GraphStore (14 méthodes),
la validation de configuration et d'environnement, le cross-encoder local,
la passerelle d'exécution synchrone/asynchrone thread-safe et la traduction des erreurs.
"""

from __future__ import annotations

import asyncio
from inspect import signature
from typing import Any
from unittest.mock import MagicMock, patch
import pytest

from app.config import Config
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
    get_graph_store,
    override_graph_store,
    set_graph_store_override,
)
from app.utils.graph_store.graphiti_store import (
    GraphitiGraphStore,
    LocalPassthroughCrossEncoder,
)


@pytest.fixture
def mock_dependencies():
    """Fournit un ensemble complet de doubles factices pour isoler GraphitiGraphStore."""
    driver = MagicMock()
    llm_client = MagicMock()
    embedder = MagicMock()
    cross_encoder = MagicMock()
    graphiti = MagicMock()
    return {
        "driver": driver,
        "llm_client": llm_client,
        "embedder": embedder,
        "cross_encoder": cross_encoder,
        "graphiti": graphiti,
    }


@pytest.fixture
def store_with_mocks(mock_dependencies):
    """Instancie un GraphitiGraphStore hermétique avec dépendances mockées."""
    return GraphitiGraphStore(
        driver=mock_dependencies["driver"],
        llm_client=mock_dependencies["llm_client"],
        embedder=mock_dependencies["embedder"],
        cross_encoder=mock_dependencies["cross_encoder"],
        graphiti=mock_dependencies["graphiti"],
    )


class TestGraphitiGraphStoreInstantiation:
    """Tests d'instanciation et d'injection de dépendances de GraphitiGraphStore."""

    def test_instantiation_with_injected_dependencies(self, mock_dependencies):
        """GraphitiGraphStore s'instancie avec des dépendances injectées sans toucher au réseau."""
        store = GraphitiGraphStore(**mock_dependencies)
        assert isinstance(store, GraphStore)
        assert isinstance(store, GraphitiGraphStore)
        assert store.driver is mock_dependencies["driver"]
        assert store.llm_client is mock_dependencies["llm_client"]
        assert store.embedder is mock_dependencies["embedder"]
        assert store.cross_encoder is mock_dependencies["cross_encoder"]
        assert store.graphiti is mock_dependencies["graphiti"]

    def test_missing_password_raises_graph_validation_error(self, monkeypatch):
        """Sans driver injecté et sans NEO4J_PASSWORD, lève GraphValidationError."""
        monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
        monkeypatch.setattr(Config, "NEO4J_PASSWORD", None, raising=False)

        with pytest.raises(GraphValidationError) as exc_info:
            GraphitiGraphStore(password=None)
        assert "NEO4J_PASSWORD" in str(exc_info.value)

    def test_instantiation_with_env_password_creates_neo4j_driver(self, monkeypatch):
        """Avec NEO4J_PASSWORD renseigné, Neo4jDriver est instancié avec les paramètres attendus."""
        monkeypatch.setenv("NEO4J_URI", "bolt://custom-neo4j:7687")
        monkeypatch.setenv("NEO4J_USER", "custom_user")
        monkeypatch.setenv("NEO4J_PASSWORD", "secret_pwd")

        with patch("app.utils.graph_store.graphiti_store.Neo4jDriver") as mock_driver_cls, \
             patch("app.utils.graph_store.graphiti_store.MiroFishLLMClient") as mock_llm_cls, \
             patch("app.utils.graph_store.graphiti_store.SentenceTransformerEmbedder") as mock_emb_cls, \
             patch("app.utils.graph_store.graphiti_store.Graphiti") as mock_graphiti_cls:

            store = GraphitiGraphStore()

            mock_driver_cls.assert_called_once_with(
                uri="bolt://custom-neo4j:7687",
                user="custom_user",
                password="secret_pwd",
            )
            mock_llm_cls.assert_called_once()
            mock_emb_cls.assert_called_once()
            mock_graphiti_cls.assert_called_once_with(
                graph_driver=mock_driver_cls.return_value,
                llm_client=mock_llm_cls.return_value,
                embedder=mock_emb_cls.return_value,
                cross_encoder=store.cross_encoder,
            )

    def test_driver_instantiation_error_translated(self, monkeypatch):
        """Une erreur lors de l'instanciation du driver est traduite en GraphConnectionError."""
        monkeypatch.setenv("NEO4J_PASSWORD", "secret")

        with patch("app.utils.graph_store.graphiti_store.Neo4jDriver", side_effect=ConnectionError("Host unreachable")):
            with pytest.raises(GraphConnectionError) as exc_info:
                GraphitiGraphStore()
            assert "Host unreachable" in str(exc_info.value)


class TestGraphitiGraphStoreContract:
    """Tests de conformité formelle au contrat d'interface GraphStore (14 méthodes)."""

    REQUIRED_METHODS = [
        "create_graph",
        "delete_graph",
        "get_graph_data",
        "get_graph_info",
        "set_ontology",
        "add_episode",
        "add_text_batch",
        "wait_for_batch",
        "wait_for_episodes",
        "get_all_nodes",
        "get_all_edges",
        "get_node",
        "get_node_edges",
        "search",
    ]

    def test_is_subclass_of_graph_store(self):
        """GraphitiGraphStore hérite de GraphStore."""
        assert issubclass(GraphitiGraphStore, GraphStore)

    def test_all_14_methods_declared(self):
        """Toutes les 14 méthodes obligatoires de GraphStore sont définies sur GraphitiGraphStore."""
        for method_name in self.REQUIRED_METHODS:
            assert hasattr(GraphitiGraphStore, method_name), f"Méthode manquante : {method_name}"
            method = getattr(GraphitiGraphStore, method_name)
            assert callable(method)

    def test_method_signatures_match_base_interface(self):
        """Les signatures des 14 méthodes correspondent exactement à l'interface abstraite GraphStore."""
        for method_name in self.REQUIRED_METHODS:
            base_sig = signature(getattr(GraphStore, method_name))
            impl_sig = signature(getattr(GraphitiGraphStore, method_name))
            assert list(base_sig.parameters.keys()) == list(impl_sig.parameters.keys()), (
                f"Différence de paramètres pour {method_name} : "
                f"attendu={list(base_sig.parameters.keys())}, reçu={list(impl_sig.parameters.keys())}"
            )

    def test_validation_on_empty_parameters(self, store_with_mocks):
        """La validation des entrées lève GraphValidationError avant toute logique métier."""
        # create_graph
        with pytest.raises(GraphValidationError):
            store_with_mocks.create_graph(name="")
        with pytest.raises(GraphValidationError):
            store_with_mocks.create_graph(name="test", graph_id="   ")

        # delete_graph
        with pytest.raises(GraphValidationError):
            store_with_mocks.delete_graph(graph_id="")

        # get_graph_data & get_graph_info
        with pytest.raises(GraphValidationError):
            store_with_mocks.get_graph_data(graph_id="")
        with pytest.raises(GraphValidationError):
            store_with_mocks.get_graph_info(graph_id="   ")

        # set_ontology
        with pytest.raises(GraphValidationError):
            store_with_mocks.set_ontology(graph_id="", ontology={})
        with pytest.raises(GraphValidationError):
            store_with_mocks.set_ontology(graph_id="g1", ontology="not-a-dict")  # type: ignore[arg-type]

        # add_episode
        with pytest.raises(GraphValidationError):
            store_with_mocks.add_episode(graph_id="", text="sample")
        with pytest.raises(GraphValidationError):
            store_with_mocks.add_episode(graph_id="g1", text="")

        # add_text_batch
        with pytest.raises(GraphValidationError):
            store_with_mocks.add_text_batch(graph_id="", chunks=["sample"])
        with pytest.raises(GraphValidationError):
            store_with_mocks.add_text_batch(graph_id="g1", chunks=[])
        with pytest.raises(GraphValidationError):
            store_with_mocks.add_text_batch(graph_id="g1", chunks=["sample"], batch_size=0)
        with pytest.raises(GraphValidationError):
            store_with_mocks.add_text_batch(graph_id="g1", chunks=["sample"], batch_size=-5)

        # wait_for_batch
        with pytest.raises(GraphValidationError):
            store_with_mocks.wait_for_batch(batch=None)  # type: ignore[arg-type]

        # wait_for_episodes
        with pytest.raises(GraphValidationError):
            store_with_mocks.wait_for_episodes(graph_id="", episode_uuids=["ep1"])

        # get_all_nodes & get_all_edges
        with pytest.raises(GraphValidationError):
            store_with_mocks.get_all_nodes(graph_id="")
        with pytest.raises(GraphValidationError):
            store_with_mocks.get_all_edges(graph_id="")

        # get_node & get_node_edges
        with pytest.raises(GraphValidationError):
            store_with_mocks.get_node(graph_id="", node_uuid="n1")
        with pytest.raises(GraphValidationError):
            store_with_mocks.get_node(graph_id="g1", node_uuid="")
        with pytest.raises(GraphValidationError):
            store_with_mocks.get_node_edges(graph_id="", node_uuid="n1")
        with pytest.raises(GraphValidationError):
            store_with_mocks.get_node_edges(graph_id="g1", node_uuid="")

        # search
        with pytest.raises(GraphValidationError):
            store_with_mocks.search(graph_id="", query="test")
        with pytest.raises(GraphValidationError):
            store_with_mocks.search(graph_id="g1", query="")
        with pytest.raises(GraphValidationError):
            store_with_mocks.search(graph_id="g1", query="   ")
        with pytest.raises(GraphValidationError):
            store_with_mocks.search(graph_id="g1", query="test", limit=0)
        with pytest.raises(GraphValidationError):
            store_with_mocks.search(graph_id="g1", query="test", limit=-1)
        with pytest.raises(GraphValidationError):
            store_with_mocks.search(graph_id="g1", query="test", scope="invalid_scope")

    def test_stubs_raise_not_implemented_error_with_story_reference(self, store_with_mocks):
        """Les méthodes stubbées pour les stories 003-2 et 003-3 lèvent NotImplementedError explicite."""
        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.create_graph(name="Graphe 1", graph_id="g-1")
        assert "003-2" in str(exc.value)

        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.delete_graph(graph_id="g-1")
        assert "003-2" in str(exc.value)

        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.set_ontology(graph_id="g-1", ontology={"entity_types": []})
        assert "003-2" in str(exc.value)

        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.add_episode(graph_id="g-1", text="Un fait.")
        assert "003-2" in str(exc.value)

        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.add_text_batch(graph_id="g-1", chunks=["Chunk 1"])
        assert "003-2" in str(exc.value)

        batch_record = BatchSubmissionRecord(
            batch_id="b-1",
            operation_id="op-1",
            episode_uuids=["ep-1"],
            item_count=1,
        )
        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.wait_for_batch(batch=batch_record)
        assert "003-2" in str(exc.value)

        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.wait_for_episodes(graph_id="g-1", episode_uuids=["ep-1"])
        assert "003-2" in str(exc.value)

        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.get_all_nodes(graph_id="g-1")
        assert "003-3" in str(exc.value)

        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.get_all_edges(graph_id="g-1")
        assert "003-3" in str(exc.value)

        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.get_node(graph_id="g-1", node_uuid="n-1")
        assert "003-3" in str(exc.value)

        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.get_node_edges(graph_id="g-1", node_uuid="n-1")
        assert "003-3" in str(exc.value)

        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.get_graph_data(graph_id="g-1")
        assert "003-3" in str(exc.value)

        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.get_graph_info(graph_id="g-1")
        assert "003-3" in str(exc.value)

        with pytest.raises(NotImplementedError) as exc:
            store_with_mocks.search(graph_id="g-1", query="test")
        assert "003-3" in str(exc.value)


class TestLocalPassthroughCrossEncoder:
    """Tests unitaires du cross-encoder local sans appel réseau."""

    @pytest.mark.asyncio
    async def test_rank_preserves_order_with_decreasing_scores(self):
        """rank conserve l'ordre initial des passages et applique des scores décroissants."""
        encoder = LocalPassthroughCrossEncoder()
        passages = ["Passage A", "Passage B", "Passage C"]
        results = await encoder.rank(query="requete test", passages=passages)

        assert len(results) == 3
        assert [p for p, _ in results] == passages
        scores = [s for _, s in results]
        assert scores[0] > scores[1] > scores[2]
        assert scores[0] == 1.0
        assert scores[1] == pytest.approx(0.999)
        assert scores[2] == pytest.approx(0.998)

    @pytest.mark.asyncio
    async def test_rank_empty_passages(self):
        """rank avec liste vide retourne une liste vide."""
        encoder = LocalPassthroughCrossEncoder()
        results = await encoder.rank(query="vide", passages=[])
        assert results == []

    @pytest.mark.asyncio
    async def test_rank_large_passages_keeps_non_negative_scores(self):
        """rank avec plus de 1000 passages borne les scores à zéro et reste décroissant."""
        encoder = LocalPassthroughCrossEncoder()
        passages = [f"Passage {i}" for i in range(1500)]
        results = await encoder.rank(query="test", passages=passages)
        assert len(results) == 1500
        for _, score in results:
            assert score >= 0.0
            assert score <= 1.0
        assert results[0][1] == 1.0
        assert results[1000][1] == 0.0
        assert results[1499][1] == 0.0


class TestGraphitiGraphStoreAsyncBridge:
    """Tests de robustesse de la passerelle synchrone / asynchrone _run_async."""

    def test_run_async_outside_event_loop(self, store_with_mocks):
        """_run_async fonctionne en environnement synchrone standard (sans boucle active)."""
        async def dummy_coro(value: int) -> int:
            await asyncio.sleep(0.001)
            return value * 2

        result = store_with_mocks._run_async(dummy_coro(21))
        assert result == 42

    @pytest.mark.asyncio
    async def test_run_async_inside_active_event_loop(self, store_with_mocks):
        """_run_async fonctionne lorsqu'une boucle d'événements tourne déjà sans lever RuntimeError."""
        async def inner_coro(msg: str) -> str:
            await asyncio.sleep(0.001)
            return f"Echo: {msg}"

        # Invoqué depuis une coroutine asynchrone (boucle active)
        result = store_with_mocks._run_async(inner_coro("Hello Async"))
        assert result == "Echo: Hello Async"

    def test_run_async_propagates_exceptions(self, store_with_mocks):
        """_run_async propage fidèlement les exceptions levées par la coroutine."""
        async def failing_coro():
            await asyncio.sleep(0.001)
            raise ValueError("Erreur asynchrone interne")

        with pytest.raises(ValueError) as exc:
            store_with_mocks._run_async(failing_coro())
        assert "Erreur asynchrone interne" in str(exc.value)


class TestGraphitiErrorTranslation:
    """Tests du traducteur d'erreurs _translate_error."""

    def test_translate_passthrough_graph_store_error(self, store_with_mocks):
        """Les exceptions dérivant déjà de GraphStoreError sont relayées telles quelles."""
        orig = GraphNotFoundError("Non trouvé")
        translated = store_with_mocks._translate_error(orig, "test")
        assert translated is orig

    def test_translate_auth_error(self, store_with_mocks):
        """Les erreurs d'authentification sont traduites en GraphConnectionError."""
        class Neo4jAuthError(Exception):
            pass

        exc = Neo4jAuthError("Invalid credentials for neo4j")
        translated = store_with_mocks._translate_error(exc, "connexion")
        assert isinstance(translated, GraphConnectionError)
        assert "authentification" in str(translated).lower()

    def test_translate_rate_limit_error(self, store_with_mocks):
        """Les erreurs de limitation de débit (RateLimitError) sont traduites en GraphConnectionError."""
        class OpenAIRateLimitError(Exception):
            pass

        exc = OpenAIRateLimitError("Rate limit exceeded. Please retry later.")
        translated = store_with_mocks._translate_error(exc, "completion LLM")
        assert isinstance(translated, GraphConnectionError)
        assert "RateLimit" in str(translated)

    def test_translate_connection_and_service_unavailable(self, store_with_mocks):
        """Les erreurs de service indisponible sont traduites en GraphConnectionError."""
        class ServiceUnavailable(Exception):
            pass

        exc = ServiceUnavailable("Could not connect to bolt://localhost:7687")
        translated = store_with_mocks._translate_error(exc, "connexion")
        assert isinstance(translated, GraphConnectionError)

    def test_translate_timeout_error(self, store_with_mocks):
        """Les erreurs de timeout sont traduites en GraphTimeoutError."""
        exc = TimeoutError("Request timed out after 30s")
        translated = store_with_mocks._translate_error(exc, "requete")
        assert isinstance(translated, GraphTimeoutError)

    def test_translate_validation_error(self, store_with_mocks):
        """ValueError et TypeError sont traduits en GraphValidationError."""
        exc = ValueError("Invalid parameter value")
        translated = store_with_mocks._translate_error(exc, "validation")
        assert isinstance(translated, GraphValidationError)

    def test_translate_unexpected_error(self, store_with_mocks):
        """Toute exception générique imprévue devient GraphStoreError."""
        exc = RuntimeError("System fault")
        translated = store_with_mocks._translate_error(exc, "operation")
        assert isinstance(translated, GraphStoreError)
        assert not isinstance(translated, (GraphConnectionError, GraphTimeoutError, GraphValidationError))


class TestGraphitiFactoryAndOverrideIntegration:
    """Tests d'intégration de GraphitiGraphStore avec la factory et le mécanisme d'override."""

    def test_factory_with_graphiti_override(self, store_with_mocks):
        """set_graph_store_override et override_graph_store fonctionnent avec GraphitiGraphStore."""
        assert get_graph_store(backend="cloud") is not store_with_mocks

        with override_graph_store(store_with_mocks):
            assert get_graph_store() is store_with_mocks
            assert get_graph_store(backend="cloud") is store_with_mocks
            assert get_graph_store(backend="graphiti") is store_with_mocks

        # Restauration après le contexte
        assert get_graph_store(backend="cloud") is not store_with_mocks
