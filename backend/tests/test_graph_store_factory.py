"""Tests unitaires hermétiques pour la factory GraphStore et la configuration ZEP_BACKEND.

Valide la résolution de priorité, l'aiguillage des backends, la tolérance à la casse,
la validation des entrées, le mécanisme d'override et l'adaptation de Config.validate().
"""

from typing import Any, Callable, Dict, List, Optional
import pytest

from app.config import Config
from app.utils.graph_store import (
    BatchSubmissionRecord,
    EpisodeRecord,
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphSearchResult,
    GraphStore,
    GraphValidationError,
    ZepGraphStore,
    get_graph_store,
    override_graph_store,
    set_graph_store_override,
)


class FakeGraphStore(GraphStore):
    """Implémentation factice de GraphStore pour les tests d'override."""

    def __init__(self, tag: str = "fake") -> None:
        self.tag = tag

    def create_graph(self, name: str, graph_id: Optional[str] = None) -> str:
        return f"{self.tag}-{graph_id or name}"

    def delete_graph(self, graph_id: str) -> None:
        pass

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        return {"graph_id": graph_id, "nodes": [], "edges": []}

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        return GraphInfo(graph_id=graph_id, node_count=0, edge_count=0, entity_types=[])

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
            batch_id="b-1",
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
        return []

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[GraphEdge]:
        return []

    def get_node(self, graph_id: str, node_uuid: str) -> Optional[GraphNode]:
        return None

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[GraphEdge]:
        return []

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
    ) -> GraphSearchResult:
        return GraphSearchResult(facts=[], nodes=[], edges=[], query=query, total_count=0)


@pytest.fixture(autouse=True)
def clean_factory_state(monkeypatch):
    """Réinitialise l'override global et l'environnement avant et après chaque test."""
    set_graph_store_override(None)
    monkeypatch.delenv("ZEP_BACKEND", raising=False)
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
    yield
    set_graph_store_override(None)


class TestGraphStoreFactoryResolution:
    """Tests d'aiguillage et de résolution de la factory get_graph_store."""

    def test_default_backend_returns_zep_graph_store(self, monkeypatch):
        """Par défaut (sans argument ni env), la factory retourne ZepGraphStore."""
        monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
        store = get_graph_store()
        assert isinstance(store, ZepGraphStore)

    def test_explicit_cloud_backend_argument(self):
        """Un argument backend='cloud' retourne ZepGraphStore."""
        store = get_graph_store(backend="cloud")
        assert isinstance(store, ZepGraphStore)

    def test_explicit_cloud_backend_case_insensitive_and_whitespace(self):
        """L'aiguillage est insensible à la casse et tolère les espaces superflus."""
        store_caps = get_graph_store(backend="  CLOUD  ")
        assert isinstance(store_caps, ZepGraphStore)

        store_mixed = get_graph_store(backend="Cloud")
        assert isinstance(store_mixed, ZepGraphStore)

    def test_explicit_api_key_forwarded_to_zep_store(self):
        """La clé API explicite est transmise au constructeur de ZepGraphStore."""
        custom_key = "test-custom-api-key-12345"
        from unittest.mock import patch

        with patch("app.utils.graph_store.factory.ZepGraphStore") as mock_zep_store:
            get_graph_store(backend="cloud", api_key=custom_key)
            mock_zep_store.assert_called_once_with(api_key=custom_key)

    def test_explicit_api_key_whitespace_trimmed(self):
        """Les espaces superflus autour de api_key sont nettoyés."""
        custom_key = "  test-custom-api-key-12345  "
        from unittest.mock import patch

        with patch("app.utils.graph_store.factory.ZepGraphStore") as mock_zep_store:
            get_graph_store(backend="cloud", api_key=custom_key)
            mock_zep_store.assert_called_once_with(api_key="test-custom-api-key-12345")

    def test_non_string_backend_raises_graph_validation_error(self):
        """Un type non chaîne passé à backend lève GraphValidationError."""
        with pytest.raises(GraphValidationError) as exc_info:
            get_graph_store(backend=123)  # type: ignore[arg-type]
        assert "invalide" in str(exc_info.value)

    def test_graphiti_backend_raises_not_implemented_error(self):
        """Le backend 'graphiti' lève NotImplementedError avec mention de l'Epic 003."""
        with pytest.raises(NotImplementedError) as exc_info:
            get_graph_store(backend="graphiti")
        assert "Epic 003" in str(exc_info.value)
        assert "graphiti" in str(exc_info.value).lower()

    def test_graphiti_backend_case_and_whitespace(self):
        """Le backend 'graphiti' fonctionne aussi avec majuscules et espaces."""
        with pytest.raises(NotImplementedError) as exc_info:
            get_graph_store(backend="  GRAPHITI  ")
        assert "Epic 003" in str(exc_info.value)

    @pytest.mark.parametrize("invalid_backend", ["neo4j", "memgraph", "redis", "unknown", "", "   "])
    def test_invalid_backend_raises_graph_validation_error(self, invalid_backend):
        """Tout backend non supporté ou vide lève GraphValidationError."""
        with pytest.raises(GraphValidationError) as exc_info:
            get_graph_store(backend=invalid_backend)
        assert "autorisées" in str(exc_info.value) or "invalide" in str(exc_info.value)


class TestGraphStorePriority:
    """Tests de la hiérarchie de priorité de résolution du backend."""

    def test_argument_overrides_config_and_env(self, monkeypatch):
        """L'argument explicite prévaut sur Config.ZEP_BACKEND et os.environ."""
        monkeypatch.setenv("ZEP_BACKEND", "invalid_backend")
        monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")

        # L'argument "cloud" doit primer sur "graphiti" et "invalid_backend"
        store = get_graph_store(backend="cloud")
        assert isinstance(store, ZepGraphStore)

    def test_config_overrides_env(self, monkeypatch):
        """Config.ZEP_BACKEND prévaut sur os.environ."""
        monkeypatch.setenv("ZEP_BACKEND", "invalid_env")
        monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")

        store = get_graph_store()
        assert isinstance(store, ZepGraphStore)

    def test_env_used_when_config_is_none(self, monkeypatch):
        """os.environ est utilisé quand Config.ZEP_BACKEND est None."""
        monkeypatch.setattr(Config, "ZEP_BACKEND", None)
        monkeypatch.setenv("ZEP_BACKEND", "graphiti")

        with pytest.raises(NotImplementedError):
            get_graph_store()


class TestGraphStoreOverride:
    """Tests du mécanisme d'override pour l'isolation des tests unitaires."""

    def test_set_graph_store_override_takes_precedence_over_all(self, monkeypatch):
        """L'override est prioritaire sur toute configuration ou argument."""
        fake_store = FakeGraphStore(tag="singleton-fake")
        set_graph_store_override(fake_store)

        monkeypatch.setenv("ZEP_BACKEND", "invalid_value")

        # Doit retourner fake_store même si backend="graphiti" est demandé
        resolved = get_graph_store(backend="graphiti")
        assert resolved is fake_store
        assert resolved.create_graph("test") == "singleton-fake-test"

    def test_set_graph_store_override_reset(self):
        """Passer None à set_graph_store_override restaure le comportement normal."""
        fake_store = FakeGraphStore()
        set_graph_store_override(fake_store)
        assert get_graph_store() is fake_store

        set_graph_store_override(None)
        assert isinstance(get_graph_store(), ZepGraphStore)

    def test_override_graph_store_context_manager(self):
        """override_graph_store injecte temporairement le store et restaure l'état initial."""
        assert isinstance(get_graph_store(), ZepGraphStore)

        fake_store = FakeGraphStore(tag="scoped-fake")
        with override_graph_store(fake_store) as ctx_store:
            assert ctx_store is fake_store
            assert get_graph_store() is fake_store

        # Restauration automatique
        assert isinstance(get_graph_store(), ZepGraphStore)

    def test_set_graph_store_override_invalid_type_raises_type_error(self):
        """Injecter un objet qui n'hérite pas de GraphStore lève TypeError."""
        with pytest.raises(TypeError) as exc_info:
            set_graph_store_override("not_a_graph_store")  # type: ignore[arg-type]
        assert "GraphStore" in str(exc_info.value)

    def test_override_graph_store_none_suspends_active_override(self):
        """override_graph_store(None) suspend temporairement un override actif."""
        fake_store = FakeGraphStore(tag="outer")
        set_graph_store_override(fake_store)
        assert get_graph_store() is fake_store

        with override_graph_store(None):
            # L'override est temporairement suspendu : retourne le store normal
            assert isinstance(get_graph_store(), ZepGraphStore)

        # L'override externe est restauré
        assert get_graph_store() is fake_store

    def test_override_graph_store_context_manager_on_exception(self):
        """override_graph_store restaure l'état initial même en cas d'exception levée."""
        fake_store = FakeGraphStore()
        try:
            with override_graph_store(fake_store):
                assert get_graph_store() is fake_store
                raise ValueError("Erreur simulée dans le test")
        except ValueError:
            pass

        assert isinstance(get_graph_store(), ZepGraphStore)

    def test_nested_override_graph_store(self):
        """Les gestionnaires de contexte d'override peuvent être imbriqués proprement."""
        store_outer = FakeGraphStore(tag="outer")
        store_inner = FakeGraphStore(tag="inner")

        with override_graph_store(store_outer):
            assert get_graph_store() is store_outer
            with override_graph_store(store_inner):
                assert get_graph_store() is store_inner
            assert get_graph_store() is store_outer

        assert isinstance(get_graph_store(), ZepGraphStore)


class TestConfigValidationWithZepBackend:
    """Tests d'adaptation de Config.validate() selon ZEP_BACKEND."""

    def test_config_validate_requires_zep_key_when_backend_cloud(self, monkeypatch):
        """En mode backend 'cloud', ZEP_API_KEY est obligatoire."""
        monkeypatch.setattr(Config, "LLM_API_KEY", "mock-llm-key")
        monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
        monkeypatch.setattr(Config, "ZEP_API_KEY", None)

        errors = Config.validate()
        assert any("ZEP_API_KEY" in err for err in errors)

    def test_config_validate_passes_when_backend_cloud_with_key(self, monkeypatch):
        """En mode backend 'cloud', aucune erreur si ZEP_API_KEY est fournie."""
        monkeypatch.setattr(Config, "LLM_API_KEY", "mock-llm-key")
        monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud")
        monkeypatch.setattr(Config, "ZEP_API_KEY", "mock-zep-key")

        errors = Config.validate()
        assert not errors

    def test_config_validate_does_not_require_zep_key_when_backend_graphiti(self, monkeypatch):
        """En mode backend 'graphiti', ZEP_API_KEY n'est plus exigée."""
        monkeypatch.setattr(Config, "LLM_API_KEY", "mock-llm-key")
        monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti")
        monkeypatch.setattr(Config, "ZEP_API_KEY", None)

        errors = Config.validate()
        assert not errors

    def test_config_validate_rejects_unsupported_backend(self, monkeypatch):
        """Config.validate() rejette un ZEP_BACKEND non supporté."""
        monkeypatch.setattr(Config, "LLM_API_KEY", "mock-llm-key")
        monkeypatch.setattr(Config, "ZEP_BACKEND", "neo4j")

        errors = Config.validate()
        assert any("ZEP_BACKEND 不受支持" in err for err in errors)

    def test_config_validate_rejects_empty_or_whitespace_backend(self, monkeypatch):
        """Config.validate() rejette un ZEP_BACKEND vide ou composé d'espaces."""
        monkeypatch.setattr(Config, "LLM_API_KEY", "mock-llm-key")
        monkeypatch.setattr(Config, "ZEP_BACKEND", "   ")

        errors = Config.validate()
        assert any("ZEP_BACKEND 无效配置" in err for err in errors)

    def test_config_validate_rejects_non_string_backend(self, monkeypatch):
        """Config.validate() rejette un ZEP_BACKEND de type non-chaîne."""
        monkeypatch.setattr(Config, "LLM_API_KEY", "mock-llm-key")
        monkeypatch.setattr(Config, "ZEP_BACKEND", 123)

        errors = Config.validate()
        assert any("ZEP_BACKEND 无效配置" in err for err in errors)


class TestGraphStorePackageExports:
    """Tests vérifiant l'exposition publique des symboles du package graph_store."""

    def test_factory_functions_exported_in_package(self):
        """get_graph_store, set_graph_store_override et override_graph_store sont exportés."""
        import app.utils.graph_store as gs

        assert hasattr(gs, "get_graph_store")
        assert hasattr(gs, "set_graph_store_override")
        assert hasattr(gs, "override_graph_store")
        assert "get_graph_store" in gs.__all__
        assert "set_graph_store_override" in gs.__all__
        assert "override_graph_store" in gs.__all__

    def test_invalid_backend_in_config_raises_graph_validation_error(self, monkeypatch):
        """Une valeur invalide dans Config.ZEP_BACKEND lève GraphValidationError."""
        monkeypatch.setattr(Config, "ZEP_BACKEND", "unsupported_storage")
        with pytest.raises(GraphValidationError) as exc_info:
            get_graph_store()
        assert "unsupported_storage" in str(exc_info.value)

    def test_invalid_backend_in_environ_raises_graph_validation_error(self, monkeypatch):
        """Une valeur invalide dans os.environ['ZEP_BACKEND'] lève GraphValidationError."""
        monkeypatch.setattr(Config, "ZEP_BACKEND", None)
        monkeypatch.setenv("ZEP_BACKEND", "unknown_provider")
        with pytest.raises(GraphValidationError) as exc_info:
            get_graph_store()
        assert "unknown_provider" in str(exc_info.value)
