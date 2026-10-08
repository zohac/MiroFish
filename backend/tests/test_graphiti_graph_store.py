"""Tests unitaires hermétiques pour GraphitiGraphStore (Stories 003-1 et 003-2).

Valide l'instanciation, le respect du contrat d'interface GraphStore (14 méthodes),
la validation de configuration et d'environnement, le cross-encoder local,
la passerelle d'exécution synchrone/asynchrone thread-safe et la traduction des erreurs.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from inspect import signature
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from graphiti_core.nodes import EpisodeType

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

        # Non-string validation
        with pytest.raises(GraphValidationError):
            store_with_mocks.create_graph(name=123)  # type: ignore[arg-type]
        with pytest.raises(GraphValidationError):
            store_with_mocks.create_graph(name="test", graph_id=123)  # type: ignore[arg-type]
        with pytest.raises(GraphValidationError):
            store_with_mocks.delete_graph(graph_id=123)  # type: ignore[arg-type]
        with pytest.raises(GraphValidationError):
            store_with_mocks.add_episode(graph_id=123, text="sample")  # type: ignore[arg-type]
        with pytest.raises(GraphValidationError):
            store_with_mocks.add_episode(graph_id="g1", text=123)  # type: ignore[arg-type]

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

    def test_remaining_stubs_for_story_003_3_raise_not_implemented_error(self, store_with_mocks):
        """Les méthodes de lecture et recherche (Story 003-3) lèvent NotImplementedError explicite."""
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


class TestGraphitiGraphStoreLifecycle:
    """Tests unitaires du cycle de vie des graphes dans GraphitiGraphStore (Story 003-2)."""

    def test_create_graph_with_custom_id(self, store_with_mocks, mock_dependencies):
        """create_graph conserve un identifiant personnalisé et vérifie la connexion."""
        mock_dependencies["driver"].health_check = MagicMock()
        gid = store_with_mocks.create_graph(name="Simulation Climat", graph_id="sim-climat-01")
        assert gid == "sim-climat-01"
        mock_dependencies["driver"].health_check.assert_called_once()

    def test_create_graph_generates_id_when_none(self, store_with_mocks, mock_dependencies):
        """create_graph génère un identifiant formaté mirofish_<uuid> si graph_id est omis."""
        mock_dependencies["driver"].health_check = MagicMock()
        gid = store_with_mocks.create_graph(name="Simulation Auto")
        assert gid.startswith("mirofish_")
        assert len(gid) > len("mirofish_")
        mock_dependencies["driver"].health_check.assert_called_once()

    def test_create_graph_fallback_to_execute_query_when_no_health_check(
        self, store_with_mocks, mock_dependencies
    ):
        """create_graph utilise execute_query en repli si driver n'a pas health_check."""
        del mock_dependencies["driver"].health_check
        mock_dependencies["driver"].execute_query = MagicMock(return_value=[])
        gid = store_with_mocks.create_graph(name="Simulation Ping")
        assert gid.startswith("mirofish_")
        mock_dependencies["driver"].execute_query.assert_called_once_with(
            "RETURN 1 AS ping", params={}
        )

    def test_create_graph_connection_failure_raises_graph_connection_error(
        self, store_with_mocks, mock_dependencies
    ):
        """create_graph lève GraphConnectionError si le driver Neo4j signale une erreur de connexion."""
        mock_dependencies["driver"].health_check = MagicMock(
            side_effect=ConnectionError("Bolt unavailable")
        )
        with pytest.raises(GraphConnectionError) as exc_info:
            store_with_mocks.create_graph(name="Simulation Test")
        assert "Bolt unavailable" in str(exc_info.value)

    def test_delete_graph_executes_isolated_cypher_detach_delete(
        self, store_with_mocks, mock_dependencies
    ):
        """delete_graph exécute la suppression atomique ciblée par group_id (Critère C2)."""
        mock_dependencies["driver"].execute_query = MagicMock(return_value=[])
        store_with_mocks.delete_graph(graph_id="sim-target-42")

        mock_dependencies["driver"].execute_query.assert_called_once_with(
            "MATCH (n {group_id: $group_id}) DETACH DELETE n",
            params={"group_id": "sim-target-42"},
        )

    def test_delete_graph_driver_error_translated(
        self, store_with_mocks, mock_dependencies
    ):
        """delete_graph traduit les erreurs Neo4j en GraphStoreError."""
        mock_dependencies["driver"].execute_query = MagicMock(
            side_effect=RuntimeError("Cypher syntax error")
        )
        with pytest.raises(GraphStoreError) as exc_info:
            store_with_mocks.delete_graph(graph_id="sim-err")
        assert "Cypher syntax error" in str(exc_info.value)

    def test_set_ontology_noop_graceful(self, store_with_mocks):
        """set_ontology valide le dictionnaire et s'exécute en no-op gracieux (ADR 0003)."""
        res = store_with_mocks.set_ontology(
            graph_id="sim-onto",
            ontology={"entity_types": [{"name": "Person"}, {"name": "Institution"}]},
        )
        assert res is None


class TestGraphitiGraphStoreEpisodeIngestion:
    """Tests unitaires de l'ingestion unitaire d'épisodes dans GraphitiGraphStore (Story 003-2)."""

    def test_add_episode_success_with_iso_timestamp(
        self, store_with_mocks, mock_dependencies
    ):
        """add_episode convertit la date ISO, appelle Graphiti avec group_id et retourne EpisodeRecord."""
        fake_result = MagicMock()
        fake_result.episode = MagicMock(uuid="ep-uuid-123")
        mock_dependencies["graphiti"].add_episode = MagicMock(return_value=fake_result)

        record = store_with_mocks.add_episode(
            graph_id="sim-climat",
            text="Hausse de la température mondiale de 1.5°C observée.",
            source_description="Rapport GIEC",
            created_at="2026-10-06T12:00:00+00:00",
        )

        assert isinstance(record, EpisodeRecord)
        assert record.uuid == "ep-uuid-123"
        assert record.graph_id == "sim-climat"
        assert record.processed is True
        assert record.created_at == "2026-10-06T12:00:00+00:00"

        mock_dependencies["graphiti"].add_episode.assert_called_once()
        kwargs = mock_dependencies["graphiti"].add_episode.call_args.kwargs
        assert kwargs["group_id"] == "sim-climat"
        assert kwargs["episode_body"] == "Hausse de la température mondiale de 1.5°C observée."
        assert kwargs["source"] == EpisodeType.text
        assert kwargs["source_description"] == "Rapport GIEC"
        assert kwargs["reference_time"] == datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)

    def test_add_episode_success_with_iso_z_timestamp(
        self, store_with_mocks, mock_dependencies
    ):
        """add_episode gère les horodatages se terminant par 'Z'."""
        fake_result = MagicMock()
        fake_result.episode = MagicMock(uuid="ep-z-456")
        mock_dependencies["graphiti"].add_episode = MagicMock(return_value=fake_result)

        record = store_with_mocks.add_episode(
            graph_id="sim-z",
            text="Fait horodaté en Z.",
            created_at="2026-10-06T10:30:00Z",
        )
        assert record.uuid == "ep-z-456"
        kwargs = mock_dependencies["graphiti"].add_episode.call_args.kwargs
        assert kwargs["reference_time"] == datetime(2026, 10, 6, 10, 30, 0, tzinfo=timezone.utc)

    def test_add_episode_success_with_iso_lowercase_z_timestamp(
        self, store_with_mocks, mock_dependencies
    ):
        """add_episode gère les horodatages avec un suffixe minuscule 'z'."""
        fake_result = MagicMock()
        fake_result.episode = MagicMock(uuid="ep-z-lower")
        mock_dependencies["graphiti"].add_episode = MagicMock(return_value=fake_result)

        record = store_with_mocks.add_episode(
            graph_id="sim-z-lower",
            text="Fait horodaté en z minuscule.",
            created_at="2026-10-06T10:30:00z",
        )
        assert record.uuid == "ep-z-lower"
        kwargs = mock_dependencies["graphiti"].add_episode.call_args.kwargs
        assert kwargs["reference_time"] == datetime(2026, 10, 6, 10, 30, 0, tzinfo=timezone.utc)

    def test_add_episode_naive_iso_timestamp_gets_utc_tzinfo(
        self, store_with_mocks, mock_dependencies
    ):
        """add_episode assigne automatiquement timezone.utc si l'horodatage est naïf."""
        fake_result = MagicMock()
        fake_result.episode = MagicMock(uuid="ep-naive")
        mock_dependencies["graphiti"].add_episode = MagicMock(return_value=fake_result)

        record = store_with_mocks.add_episode(
            graph_id="sim-naive",
            text="Fait sans fuseau horaire.",
            created_at="2026-10-06T10:30:00",
        )
        assert record.uuid == "ep-naive"
        kwargs = mock_dependencies["graphiti"].add_episode.call_args.kwargs
        assert kwargs["reference_time"] == datetime(2026, 10, 6, 10, 30, 0, tzinfo=timezone.utc)

    def test_add_episode_default_utc_now_when_created_at_is_none(
        self, store_with_mocks, mock_dependencies
    ):
        """add_episode génère un timestamp UTC par défaut si created_at est omis."""
        fake_result = MagicMock(episode=MagicMock(uuid="ep-def-789"))
        mock_dependencies["graphiti"].add_episode = MagicMock(return_value=fake_result)

        t_before = datetime.now(timezone.utc)
        record = store_with_mocks.add_episode(
            graph_id="sim-now",
            text="Observation en temps réel.",
        )
        t_after = datetime.now(timezone.utc)

        assert record.uuid == "ep-def-789"
        kwargs = mock_dependencies["graphiti"].add_episode.call_args.kwargs
        ref_time = kwargs["reference_time"]
        assert t_before <= ref_time <= t_after

    def test_add_episode_invalid_timestamp_raises_validation_error(self, store_with_mocks):
        """add_episode lève GraphValidationError si created_at est mal formaté."""
        with pytest.raises(GraphValidationError) as exc:
            store_with_mocks.add_episode(
                graph_id="sim-err",
                text="Fait avec date invalide",
                created_at="date-non-valide-2026",
            )
        assert "created_at invalide" in str(exc.value)

    def test_add_episode_handles_direct_uuid_or_dict_result(
        self, store_with_mocks, mock_dependencies
    ):
        """add_episode extrait l'UUID que Graphiti retourne un objet ou un dict."""
        # Cas 1 : objet avec attribut uuid
        mock_dependencies["graphiti"].add_episode = MagicMock(
            return_value=MagicMock(uuid="direct-uuid-1", episode=None)
        )
        rec1 = store_with_mocks.add_episode(graph_id="sim-1", text="Fait 1")
        assert rec1.uuid == "direct-uuid-1"

        # Cas 2 : dict
        mock_dependencies["graphiti"].add_episode = MagicMock(
            return_value={"uuid": "dict-uuid-2"}
        )
        rec2 = store_with_mocks.add_episode(graph_id="sim-2", text="Fait 2")
        assert rec2.uuid == "dict-uuid-2"

    def test_add_episode_error_translation(
        self, store_with_mocks, mock_dependencies
    ):
        """add_episode traduit les erreurs Graphiti en GraphStoreError."""
        mock_dependencies["graphiti"].add_episode = MagicMock(
            side_effect=RuntimeError("Extraction failed")
        )
        with pytest.raises(GraphStoreError) as exc:
            store_with_mocks.add_episode(graph_id="sim-err", text="Fait en échec")
        assert "Extraction failed" in str(exc.value)


class TestGraphitiGraphStoreBatchIngestion:
    """Tests unitaires de l'ingestion par lots dans GraphitiGraphStore (Story 003-2)."""

    def test_add_text_batch_success_invokes_progress_callback(
        self, store_with_mocks, mock_dependencies
    ):
        """add_text_batch ingère séquentiellement les chunks et notifie progress_callback."""
        fake_result = MagicMock()
        fake_result.episode = MagicMock(uuid="ep-batch-1")
        mock_dependencies["graphiti"].add_episode = MagicMock(return_value=fake_result)

        progress_calls = []

        def callback(status: str, current: int, total: int):
            progress_calls.append((status, current, total))

        chunks = [
            "Premier paragraphe du document.",
            "Deuxième paragraphe d'analyse.",
            "Troisième section.",
        ]
        batch = store_with_mocks.add_text_batch(
            graph_id="sim-batch-01",
            chunks=chunks,
            batch_size=2,
            progress_callback=callback,
        )

        assert isinstance(batch, BatchSubmissionRecord)
        assert batch.item_count == 3
        assert len(batch.episode_uuids) == 3
        assert batch.batch_id.startswith("batch_")
        assert len(batch.operation_id) == 64  # SHA-256

        # Vérification du callback : processing et completed
        assert len(progress_calls) >= 4
        assert progress_calls[-1] == ("completed", 3, 3)

        # Vérification que add_episode a bien été appelé 3 fois avec group_id
        assert mock_dependencies["graphiti"].add_episode.call_count == 3
        for call in mock_dependencies["graphiti"].add_episode.call_args_list:
            assert call.kwargs["group_id"] == "sim-batch-01"

    def test_add_text_batch_invalid_chunks_raises_validation_error(self, store_with_mocks):
        """add_text_batch rejette les fragments vides ou non textuels."""
        with pytest.raises(GraphValidationError) as exc:
            store_with_mocks.add_text_batch(graph_id="sim-1", chunks=["Ok", "   ", "Aussi ok"])
        assert "ne peut pas être vide" in str(exc.value)

        with pytest.raises(GraphValidationError) as exc2:
            store_with_mocks.add_text_batch(graph_id="sim-1", chunks=["Ok", 123])  # type: ignore[list-item]
        assert "type invalide" in str(exc2.value)

    def test_add_text_batch_deterministic_operation_id(
        self, store_with_mocks, mock_dependencies
    ):
        """L'operation_id est déterministe pour le même contenu et même graphe."""
        fake_result = MagicMock(episode=MagicMock(uuid="ep-det"))
        mock_dependencies["graphiti"].add_episode = MagicMock(return_value=fake_result)

        chunks = ["Chunk A", "Chunk B"]
        b1 = store_with_mocks.add_text_batch(graph_id="sim-det", chunks=chunks)
        b2 = store_with_mocks.add_text_batch(graph_id="sim-det", chunks=chunks)
        assert b1.operation_id == b2.operation_id


class TestGraphitiGraphStoreWaitSynchronization:
    """Tests unitaires des méthodes wait_for_batch et wait_for_episodes (Story 003-2)."""

    def test_wait_for_batch_empty_episodes_returns_true(self, store_with_mocks):
        """wait_for_batch avec liste vide d'épisodes retourne immédiatement True."""
        batch = BatchSubmissionRecord(
            batch_id="b-empty",
            operation_id="op-empty",
            episode_uuids=[],
            item_count=0,
        )
        assert store_with_mocks.wait_for_batch(batch=batch) is True

    def test_wait_for_batch_success_when_all_persisted(
        self, store_with_mocks, mock_dependencies
    ):
        """wait_for_batch vérifie les UUIDs via Cypher et notifie le ratio de progression."""
        batch = BatchSubmissionRecord(
            batch_id="b-1",
            operation_id="op-1",
            episode_uuids=["ep-1", "ep-2"],
            item_count=2,
        )

        mock_dependencies["driver"].execute_query = MagicMock(
            return_value=[{"uuid": "ep-1"}, {"uuid": "ep-2"}]
        )

        progress_ratios = []

        def callback(status: str, ratio: float):
            progress_ratios.append((status, ratio))

        res = store_with_mocks.wait_for_batch(batch=batch, progress_callback=callback)
        assert res is True
        assert ("completed", 1.0) in progress_ratios

    def test_wait_for_batch_timeout_raises_graph_timeout_error(
        self, store_with_mocks, mock_dependencies
    ):
        """wait_for_batch lève GraphTimeoutError si des épisodes manquent à l'expiration du délai."""
        batch = BatchSubmissionRecord(
            batch_id="b-slow",
            operation_id="op-slow",
            episode_uuids=["ep-missing"],
            item_count=1,
        )
        mock_dependencies["driver"].execute_query = MagicMock(return_value=[])

        with pytest.raises(GraphTimeoutError) as exc:
            store_with_mocks.wait_for_batch(batch=batch, timeout=0.01)
        assert "n'a pas terminé dans le délai imparti" in str(exc.value)

    def test_wait_for_episodes_empty_returns_true(self, store_with_mocks):
        """wait_for_episodes avec liste vide retourne immédiatement True."""
        assert store_with_mocks.wait_for_episodes(graph_id="sim-1", episode_uuids=[]) is True

    def test_wait_for_episodes_success_with_strict_group_id(
        self, store_with_mocks, mock_dependencies
    ):
        """wait_for_episodes requiert et filtre explicitement par group_id (Critère C2)."""
        mock_dependencies["driver"].execute_query = MagicMock(
            return_value=[{"uuid": "ep-ok-1"}]
        )

        res = store_with_mocks.wait_for_episodes(
            graph_id="sim-scoped",
            episode_uuids=["ep-ok-1"],
            timeout=5.0,
        )
        assert res is True

        mock_dependencies["driver"].execute_query.assert_called_once()
        call_args = mock_dependencies["driver"].execute_query.call_args
        cypher = call_args[0][0]
        params = call_args[1]["params"]
        assert "group_id: $group_id" in cypher
        assert params["group_id"] == "sim-scoped"
        assert params["uuids"] == ["ep-ok-1"]

    def test_wait_for_episodes_timeout_raises_graph_timeout_error(
        self, store_with_mocks, mock_dependencies
    ):
        """wait_for_episodes lève GraphTimeoutError si les épisodes ne sont pas trouvés."""
        mock_dependencies["driver"].execute_query = MagicMock(return_value=[])

        with pytest.raises(GraphTimeoutError) as exc:
            store_with_mocks.wait_for_episodes(
                graph_id="sim-to",
                episode_uuids=["ep-unfound"],
                timeout=0.01,
            )
        assert "n'ont pas terminé dans le délai imparti" in str(exc.value)


class TestGraphitiStrictPartitioningIsolation:
    """Tests d'étanchéité absolue et de non-fuite entre graphes distincts (Critère C2, NFR-3)."""

    def test_delete_graph_strictly_scoped_to_target_group_id(
        self, store_with_mocks, mock_dependencies
    ):
        """delete_graph ne cible que le group_id passé et ne supprime jamais les autres graphes."""
        mock_dependencies["driver"].execute_query = MagicMock(return_value=[])

        store_with_mocks.delete_graph("project_alpha")
        params = mock_dependencies["driver"].execute_query.call_args.kwargs["params"]
        assert params["group_id"] == "project_alpha"
        assert params["group_id"] != "project_beta"

    def test_add_episode_always_binds_group_id(
        self, store_with_mocks, mock_dependencies
    ):
        """Chaque appel à add_episode transmet obligatoirement group_id à Graphiti."""
        mock_dependencies["graphiti"].add_episode = MagicMock(
            return_value=MagicMock(uuid="ep-1", episode=None)
        )

        store_with_mocks.add_episode("group_isolated_123", "Fait isolé.")
        kwargs = mock_dependencies["graphiti"].add_episode.call_args.kwargs
        assert kwargs["group_id"] == "group_isolated_123"

    def test_wait_for_episodes_scoped_to_target_group_id(
        self, store_with_mocks, mock_dependencies
    ):
        """wait_for_episodes filtre strictement sur group_id = graph_id en Cypher."""
        mock_dependencies["driver"].execute_query = MagicMock(return_value=[{"uuid": "ep-x"}])

        store_with_mocks.wait_for_episodes("group_A", ["ep-x"])
        params = mock_dependencies["driver"].execute_query.call_args.kwargs["params"]
        assert params["group_id"] == "group_A"
