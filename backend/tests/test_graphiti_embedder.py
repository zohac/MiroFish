"""Tests unitaires hermétiques pour SentenceTransformerEmbedder (Story 001-4).

Conformément à AGENTS.md §2.2 :
- Aucun appel réseau réel (tous les modèles et inférences sont mockés ou testés avec des doubles factices).
- Pas d'accès disque intempestif ni dépendance à un secret d'environnement.
- Couverture complète des formats d'entrée, de la délégation asyncio et des types de retour.
"""

from __future__ import annotations

import asyncio
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.utils.graphiti_embedder import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    SentenceTransformerEmbedder,
    SentenceTransformerEmbedderConfig,
)
from app.utils.graphiti_llm_client import MiroFishLLMClient
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig


class FakeSentenceTransformer:
    """Double factice de SentenceTransformer pour tests déterministes et hors-ligne."""

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.call_count = 0
        self.last_texts: List[str] = []

    def encode(
        self,
        texts: List[str],
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
    ) -> np.ndarray:
        self.call_count += 1
        self.last_texts = texts
        # Générer des vecteurs pseudo-déterministes basés sur la longueur du texte
        arrays = []
        for text in texts:
            base_val = float(len(text) % 10) / 10.0
            vec = np.full((self.dim,), base_val, dtype=np.float32)
            if normalize_embeddings:
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
            arrays.append(vec)
        return np.array(arrays)


def test_embedder_config_defaults():
    """Vérifie les valeurs par défaut de SentenceTransformerEmbedderConfig."""
    config = SentenceTransformerEmbedderConfig()
    assert config.model_name == DEFAULT_EMBEDDING_MODEL
    assert config.embedding_dim == DEFAULT_EMBEDDING_DIM
    assert config.embedding_dim == 384
    assert config.device is None
    assert config.normalize_embeddings is True


def test_embedder_config_custom():
    """Vérifie la personnalisation des options de configuration."""
    config = SentenceTransformerEmbedderConfig(
        model_name="paraphrase-multilingual-MiniLM-L12-v2",
        device="cpu",
        normalize_embeddings=False,
    )
    assert config.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
    assert config.device == "cpu"
    assert config.normalize_embeddings is False
    assert config.embedding_dim == 384


def test_embedder_subclasses_embedder_client():
    """Vérifie que SentenceTransformerEmbedder implémente bien le contrat EmbedderClient."""
    embedder = SentenceTransformerEmbedder()
    assert isinstance(embedder, EmbedderClient)


def test_lazy_loading_and_model_injection():
    """Vérifie le chargement paresseux et la possibilité d'injecter un modèle préchargé."""
    # 1. Lazy loading par défaut
    embedder = SentenceTransformerEmbedder()
    assert embedder._model is None

    # 2. Injection directe
    fake_model = FakeSentenceTransformer()
    embedder_injected = SentenceTransformerEmbedder(model=fake_model)
    assert embedder_injected._model is fake_model
    assert embedder_injected._get_model() is fake_model


@pytest.mark.asyncio
async def test_create_with_single_str():
    """Vérifie que create(str) retourne un vecteur unique de dimension 384."""
    fake_model = FakeSentenceTransformer(dim=384)
    embedder = SentenceTransformerEmbedder(model=fake_model)

    vec = await embedder.create("Intelligence artificielle et démocratie")

    assert isinstance(vec, list)
    assert len(vec) == 384
    assert all(isinstance(x, float) for x in vec)
    assert fake_model.call_count == 1
    assert fake_model.last_texts == ["Intelligence artificielle et démocratie"]


@pytest.mark.asyncio
async def test_create_with_list_of_single_str():
    """Vérifie que create([text]) (format d'appel Graphiti) retourne le bon vecteur."""
    fake_model = FakeSentenceTransformer(dim=384)
    embedder = SentenceTransformerEmbedder(model=fake_model)

    vec = await embedder.create(["Assemblée nationale"])

    assert isinstance(vec, list)
    assert len(vec) == 384
    assert all(isinstance(x, float) for x in vec)
    assert fake_model.call_count == 1
    assert fake_model.last_texts == ["Assemblée nationale"]


@pytest.mark.asyncio
async def test_create_with_empty_and_iterable_inputs():
    """Vérifie la robustesse de create face à des entrées vides ou itérables atypiques."""
    fake_model = FakeSentenceTransformer(dim=384)
    embedder = SentenceTransformerEmbedder(model=fake_model)

    # Liste vide -> vecteur de zéros
    vec_empty = await embedder.create([])
    assert len(vec_empty) == 384
    assert all(x == 0.0 for x in vec_empty)

    # Tuple
    vec_tuple = await embedder.create(("Entité tuple",))
    assert len(vec_tuple) == 384
    assert fake_model.last_texts == ["Entité tuple"]


@pytest.mark.asyncio
async def test_create_batch_multiple_texts():
    """Vérifie l'encodage par lot de plusieurs entités/faits."""
    fake_model = FakeSentenceTransformer(dim=384)
    embedder = SentenceTransformerEmbedder(model=fake_model)

    texts = ["Entité Alpha", "Entité Bêta", "Fait Gamma", "Fait Delta"]
    batch_vecs = await embedder.create_batch(texts)

    assert isinstance(batch_vecs, list)
    assert len(batch_vecs) == 4
    for vec in batch_vecs:
        assert isinstance(vec, list)
        assert len(vec) == 384
        assert all(isinstance(x, float) for x in vec)

    assert fake_model.call_count == 1
    assert fake_model.last_texts == texts


@pytest.mark.asyncio
async def test_create_batch_empty():
    """Vérifie qu'un lot vide retourne immédiatement [] sans appel au modèle."""
    fake_model = FakeSentenceTransformer(dim=384)
    embedder = SentenceTransformerEmbedder(model=fake_model)

    res = await embedder.create_batch([])
    assert res == []
    assert fake_model.call_count == 0


@pytest.mark.asyncio
async def test_dimension_truncation_and_float_conversion():
    """Vérifie la troncature rigoureuse si le modèle renvoie une dimension plus large."""
    # Modèle renvoyant 768 dimensions alors que la config demande 384
    fake_model = FakeSentenceTransformer(dim=768)
    config = SentenceTransformerEmbedderConfig(embedding_dim=384)
    embedder = SentenceTransformerEmbedder(config=config, model=fake_model)

    vec = await embedder.create("Texte de test")
    assert len(vec) == 384
    assert all(isinstance(x, float) for x in vec)

    batch_vecs = await embedder.create_batch(["Texte 1", "Texte 2"])
    assert len(batch_vecs) == 2
    assert len(batch_vecs[0]) == 384
    assert len(batch_vecs[1]) == 384


@pytest.mark.asyncio
async def test_asyncio_to_thread_delegation():
    """Vérifie que l'encodage synchrone est bien délégué hors de la boucle événementielle."""
    fake_model = FakeSentenceTransformer(dim=384)
    embedder = SentenceTransformerEmbedder(model=fake_model)

    with patch("asyncio.to_thread", wraps=asyncio.to_thread) as mock_to_thread:
        await embedder.create("Délégation asyncio test")
        assert mock_to_thread.called
        assert mock_to_thread.call_args[0][0] == embedder._encode_sync

    with patch("asyncio.to_thread", wraps=asyncio.to_thread) as mock_to_thread:
        await embedder.create_batch(["Batch test 1", "Batch test 2"])
        assert mock_to_thread.called
        assert mock_to_thread.call_args[0][0] == embedder._encode_sync


def test_lazy_loading_import_sentence_transformers():
    """Vérifie que _get_model charge SentenceTransformer lorsque _model est None."""
    embedder = SentenceTransformerEmbedder()
    with patch("sentence_transformers.SentenceTransformer") as mock_st_cls:
        mock_instance = MagicMock()
        mock_st_cls.return_value = mock_instance

        model1 = embedder._get_model()
        model2 = embedder._get_model()

        assert model1 is mock_instance
        assert model2 is mock_instance
        # Vérifier qu'un seul chargement a eu lieu (singleton lazy)
        mock_st_cls.assert_called_once_with(
            model_name_or_path=DEFAULT_EMBEDDING_MODEL,
            device=None,
        )


def test_graphiti_integration_instantiation():
    """Vérifie que Graphiti s'instancie avec SentenceTransformerEmbedder sans clé OpenAI."""
    class DummyDriver(GraphDriver):
        async def build_indices_and_constraints(self, delete_existing: bool = False) -> None:
            pass

        async def delete_all_indexes(self) -> None:
            pass

        async def execute_query(self, query: str, **kwargs: Any) -> Any:
            return []

        async def session(self) -> Any:
            pass

        async def close(self) -> None:
            pass

        def clone(self) -> DummyDriver:
            return self

    class DummyCrossEncoder(CrossEncoderClient):
        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
            return [(p, 1.0) for p in passages]

    fake_model = FakeSentenceTransformer(dim=384)
    embedder = SentenceTransformerEmbedder(model=fake_model)
    llm_client = MiroFishLLMClient(
        config=LLMConfig(api_key="fake-key", base_url="https://api.opencode.ai/v1", model="space-bunny-free")
    )

    graphiti = Graphiti(
        graph_driver=DummyDriver(),
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=DummyCrossEncoder(),
    )

    assert graphiti.embedder is embedder
    assert graphiti.clients.embedder is embedder


@pytest.mark.asyncio
async def test_create_with_empty_or_whitespace_string():
    """Vérifie que les chaînes vides ou composées d'espaces renvoient un vecteur neutre de zéros."""
    fake_model = FakeSentenceTransformer(dim=384)
    embedder = SentenceTransformerEmbedder(model=fake_model)

    vec_empty = await embedder.create("")
    assert len(vec_empty) == 384
    assert all(x == 0.0 for x in vec_empty)

    vec_spaces = await embedder.create("   \t\n  ")
    assert len(vec_spaces) == 384
    assert all(x == 0.0 for x in vec_spaces)

    vec_list_spaces = await embedder.create(["   "])
    assert len(vec_list_spaces) == 384
    assert all(x == 0.0 for x in vec_list_spaces)
    # Aucun appel au modèle pour des chaînes vides
    assert fake_model.call_count == 0


@pytest.mark.asyncio
async def test_create_multiple_items_logs_warning(caplog):
    """Vérifie qu'un avertissement est émis si create() reçoit une liste de plusieurs éléments."""
    fake_model = FakeSentenceTransformer(dim=384)
    embedder = SentenceTransformerEmbedder(model=fake_model)

    with caplog.at_level("WARNING"):
        vec = await embedder.create(["Premier", "Second", "Troisième"])
        assert len(vec) == 384
        assert fake_model.last_texts == ["Premier"]
        assert "create() appelé avec plusieurs éléments (3)" in caplog.text


def test_encode_sync_insufficient_dimension_raises():
    """Vérifie qu'une exception ValueError est levée si le modèle renvoie une dimension insuffisante."""
    fake_model = FakeSentenceTransformer(dim=128)
    config = SentenceTransformerEmbedderConfig(embedding_dim=384)
    embedder = SentenceTransformerEmbedder(config=config, model=fake_model)

    with pytest.raises(ValueError, match="inférieure à la dimension configurée"):
        embedder._encode_sync(["Texte test"])


def test_get_model_dimension_mismatch_warning(caplog):
    """Vérifie qu'un avertissement est émis si la dimension native du modèle diffère de la config."""
    embedder = SentenceTransformerEmbedder(config=SentenceTransformerEmbedderConfig(embedding_dim=384))
    with patch("sentence_transformers.SentenceTransformer") as mock_st_cls:
        mock_instance = MagicMock()
        mock_instance.get_sentence_embedding_dimension.return_value = 768
        mock_st_cls.return_value = mock_instance

        with caplog.at_level("WARNING"):
            embedder._get_model()
            assert "diffère de la configuration (384)" in caplog.text


@pytest.mark.asyncio
async def test_sonde_verifier_embedder_mock():
    """Vérifie que la sonde scripts/verifier_embedder_graphiti.py s'exécute avec succès en mode mock."""
    from scripts.verifier_embedder_graphiti import tester_embedder_local

    succes = await tester_embedder_local(mock=True)
    assert succes is True

