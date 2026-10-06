"""Embedder local Sentence-Transformers pour Graphiti.

Ce module fournit un client d'embeddings local dérivé de ``EmbedderClient``
de ``graphiti-core``, basé sur la bibliothèque ``sentence-transformers`` (fournie
par ``camel-oasis`` dans l'environnement MiroFish) :

1. Adaptateur local sans coût d'inférence marginal (0 €) et sans dépendance à une clé API cloud.
2. Modèle par défaut ``all-MiniLM-L6-v2`` produisant des vecteurs denses de 384 dimensions.
3. Inférence non-bloquante pour la boucle événementielle asyncio via ``asyncio.to_thread``.
4. Chargement paresseux (*lazy loading*) et thread-safe du modèle pour un démarrage rapide.
5. Support complet de l'encodage unitaire (``create``) et par lot (``create_batch``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
import logging
import threading
from typing import Any, List, Optional, Union

from pydantic import Field

from graphiti_core.embedder.client import EmbedderClient, EmbedderConfig

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIM = 384


class SentenceTransformerEmbedderConfig(EmbedderConfig):
    """Configuration de l'embedder local Sentence-Transformers."""

    model_name: str = DEFAULT_EMBEDDING_MODEL
    embedding_dim: int = Field(default=DEFAULT_EMBEDDING_DIM, frozen=True)
    device: Optional[str] = None
    normalize_embeddings: bool = True


class SentenceTransformerEmbedder(EmbedderClient):
    """Client d'embeddings local pour Graphiti utilisant SentenceTransformer."""

    def __init__(
        self,
        config: Optional[SentenceTransformerEmbedderConfig] = None,
        model: Optional[Any] = None,
    ):
        """Initialise l'embedder Sentence-Transformers.

        Args:
            config: Configuration de l'embedder (modèle, dimensions, device, normalisation).
                Si non fournie, utilise la configuration par défaut (all-MiniLM-L6-v2, 384 dim).
            model: Instance préchargée de SentenceTransformer (utile pour l'injection
                dans les tests unitaires sans téléchargement réseau). Si None, le modèle
                est chargé paresseusement lors du premier appel d'encodage.
        """
        if config is None:
            config = SentenceTransformerEmbedderConfig()
        self.config = config

        self._model = model
        self._lock = threading.Lock()

    def _get_model(self) -> Any:
        """Récupère l'instance du modèle, en effectuant un chargement paresseux thread-safe."""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    logger.info(
                        f"Chargement du modèle d'embedding local : {self.config.model_name}"
                    )
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(
                        model_name_or_path=self.config.model_name,
                        device=self.config.device,
                    )
                    if hasattr(self._model, "get_sentence_embedding_dimension"):
                        dim_model = self._model.get_sentence_embedding_dimension()
                        if dim_model and dim_model != self.config.embedding_dim:
                            logger.warning(
                                "La dimension du modèle SentenceTransformer (%d) "
                                "diffère de la configuration (%d)",
                                dim_model,
                                self.config.embedding_dim,
                            )
        return self._model

    def _encode_sync(self, texts: List[str]) -> List[List[float]]:
        """Encode une liste de textes en vecteurs d'embeddings (exécution synchrone)."""
        if not texts:
            return []

        model = self._get_model()
        embeddings = model.encode(
            texts,
            normalize_embeddings=self.config.normalize_embeddings,
            convert_to_numpy=True,
        )

        dim = self.config.embedding_dim
        # S'assurer que le résultat est converti en list[list[float]] natif Python
        if hasattr(embeddings, "tolist"):
            raw_list = embeddings.tolist()
            # Si le modèle a renvoyé un tableau 1D (un seul texte encodé directement)
            if raw_list and not isinstance(raw_list[0], list):
                raw_list = [raw_list]
        else:
            raw_list = [[float(x) for x in vec] for vec in embeddings]

        result: List[List[float]] = []
        for vec in raw_list:
            if len(vec) < dim:
                raise ValueError(
                    f"Dimension du vecteur produit ({len(vec)}) inférieure "
                    f"à la dimension configurée ({dim})"
                )
            result.append(vec[:dim])
        return result

    async def create(
        self, input_data: Union[str, List[str], Iterable[int], Iterable[Iterable[int]]]
    ) -> List[float]:
        """Génère le vecteur d'embedding pour une entrée textuelle unique.

        Compatible avec les signatures de Graphiti (``node.generate_name_embedding`` et
        ``edge.generate_embedding`` passent typiquement ``input_data=[text]``).

        Args:
            input_data: Texte unique (str) ou liste/itérable de textes/tokens.

        Returns:
            Vecteur d'embedding sous forme de liste de flottants de dimension ``embedding_dim``.
        """
        if isinstance(input_data, str):
            if not input_data.strip():
                return [0.0] * self.config.embedding_dim
            texts = [input_data]
        elif isinstance(input_data, (list, tuple)):
            if not input_data:
                return [0.0] * self.config.embedding_dim
            if len(input_data) > 1:
                logger.warning(
                    "SentenceTransformerEmbedder.create() appelé avec plusieurs éléments (%d), "
                    "seul le premier est vectorisé. Utilisez create_batch() pour vectoriser un lot.",
                    len(input_data),
                )
            first_item = input_data[0]
            if isinstance(first_item, str):
                if not first_item.strip():
                    return [0.0] * self.config.embedding_dim
                texts = [first_item]
            else:
                s = str(first_item)
                if not s.strip():
                    return [0.0] * self.config.embedding_dim
                texts = [s]
        elif isinstance(input_data, Iterable):
            items = list(input_data)
            if not items:
                return [0.0] * self.config.embedding_dim
            if len(items) > 1:
                logger.warning(
                    "SentenceTransformerEmbedder.create() appelé avec plusieurs éléments (%d), "
                    "seul le premier est vectorisé. Utilisez create_batch() pour vectoriser un lot.",
                    len(items),
                )
            s = str(items[0])
            if not s.strip():
                return [0.0] * self.config.embedding_dim
            texts = [s]
        else:
            s = str(input_data)
            if not s.strip():
                return [0.0] * self.config.embedding_dim
            texts = [s]

        vectors = await asyncio.to_thread(self._encode_sync, texts)
        if vectors:
            return vectors[0]
        return [0.0] * self.config.embedding_dim

    async def create_batch(self, input_data_list: List[str]) -> List[List[float]]:
        """Génère les vecteurs d'embeddings pour un lot de textes.

        Invoqué par Graphiti lors de la consolidation de nœuds et arêtes
        (``create_entity_node_embeddings`` et ``create_entity_edge_embeddings``).

        Args:
            input_data_list: Liste de chaînes de caractères à vectoriser.

        Returns:
            Liste de vecteurs d'embeddings.
        """
        if not input_data_list:
            return []

        texts = [str(t) for t in input_data_list]
        return await asyncio.to_thread(self._encode_sync, texts)
