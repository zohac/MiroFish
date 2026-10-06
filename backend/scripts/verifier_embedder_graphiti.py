#!/usr/bin/env python3
"""Sonde de vérification autonome de l'embedder local Sentence-Transformers pour Graphiti.

Ce script vérifie :
1. L'instanciation de SentenceTransformerEmbedder et son lazy loading.
2. L'encodage unitaire (create) sur différentes formes d'entrées (str, [str]).
3. L'encodage par lot (create_batch) sur un lot d'entités et faits types.
4. La conformité des dimensions (384) et des types (list[float]).
5. La latence moyenne d'inférence sur CPU/GPU.
6. L'intégration dans le constructeur Graphiti sans clé OpenAI.

Usage :
    cd backend && uv run python scripts/verifier_embedder_graphiti.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any, List
from unittest.mock import MagicMock

# S'assurer que le package app est accessible
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.graphiti_embedder import (
    DEFAULT_EMBEDDING_DIM,
    SentenceTransformerEmbedder,
    SentenceTransformerEmbedderConfig,
)
from app.utils.graphiti_llm_client import MiroFishLLMClient
from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig


class FakeSentenceTransformer:
    """Double factice déterministe pour vérification hors-ligne sans téléchargement réseau."""

    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIM):
        self.dim = dim

    def encode(
        self,
        texts: List[str],
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
    ) -> Any:
        import numpy as np

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


async def tester_embedder_local(mock: bool = False) -> bool:
    """Exécute la batterie de vérification de l'embedder local.

    Args:
        mock: Si True, utilise FakeSentenceTransformer sans téléchargement de poids.
    """
    print("=" * 60)
    print("Vérification de l'embedder local Sentence-Transformers (Story 001-4)")
    if mock:
        print("MODE MOCK ACTIVÉ : Exécution déterministe hors-ligne")
    print("=" * 60)

    # 1. Instanciation & Lazy loading
    print("\n1. Test d'instanciation et lazy loading...")
    config = SentenceTransformerEmbedderConfig()
    if mock:
        fake_model = FakeSentenceTransformer()
        embedder = SentenceTransformerEmbedder(config=config, model=fake_model)
        assert embedder._model is fake_model
        print("   ✓ Instanciation avec modèle factice injecté (mode mock)")
    else:
        embedder = SentenceTransformerEmbedder(config=config)
        assert embedder._model is None, "Le modèle ne doit pas être chargé à l'instanciation"
        print("   ✓ Instanciation sans chargement immédiat du modèle (lazy loading OK)")

    # 2. Encodage unitaire (create)
    print("\n2. Test de l'encodage unitaire (create)...")
    texte_test = "L'Assemblée nationale vote la proposition de loi sur l'intelligence artificielle."
    t0 = time.perf_counter()
    vec1 = await embedder.create(texte_test)
    t1 = time.perf_counter()
    latence_unitaire_init = (t1 - t0) * 1000

    assert isinstance(vec1, list), f"Le vecteur doit être une liste Python, obtenu: {type(vec1)}"
    assert len(vec1) == DEFAULT_EMBEDDING_DIM, f"Dimension attendue {DEFAULT_EMBEDDING_DIM}, obtenu {len(vec1)}"
    assert all(isinstance(x, float) for x in vec1), "Tous les éléments doivent être des flottants natifs"
    print(f"   ✓ Premier encodage (avec chargement du modèle) : {latence_unitaire_init:.2f} ms")
    print(f"   ✓ Dimensions : {len(vec1)}, Type des éléments : {type(vec1[0]).__name__}")

    # Test avec format liste d'un élément (appel typique Graphiti)
    t0 = time.perf_counter()
    vec2 = await embedder.create([texte_test])
    t1 = time.perf_counter()
    latence_unitaire_chaud = (t1 - t0) * 1000
    assert len(vec2) == DEFAULT_EMBEDDING_DIM, "Dimension incorrecte pour [str]"
    # Vérification de cohérence numérique (même texte -> même vecteur)
    diff_max = max(abs(a - b) for a, b in zip(vec1, vec2))
    assert diff_max < 1e-5, f"Écart numérique entre create(str) et create([str]) : {diff_max}"
    print(f"   ✓ Encodage à chaud : {latence_unitaire_chaud:.2f} ms (diff max create(str)/create([str]): {diff_max:.1e})")

    # 3. Encodage par lot (create_batch)
    print("\n3. Test de l'encodage par lot (create_batch)...")
    entites = [
        "Emmanuel Macron",
        "Assemblée nationale",
        "Commission européenne",
        "Intelligence artificielle",
        "Régulation algorithmique",
        "Énergie renouvelable",
        "Transition écologique",
        "Ministère de l'Économie",
    ]
    t0 = time.perf_counter()
    batch_vecs = await embedder.create_batch(entites)
    t1 = time.perf_counter()
    latence_batch = (t1 - t0) * 1000

    assert isinstance(batch_vecs, list), "Le résultat du batch doit être une liste"
    assert len(batch_vecs) == len(entites), f"Attendu {len(entites)} vecteurs, obtenu {len(batch_vecs)}"
    assert all(len(v) == DEFAULT_EMBEDDING_DIM for v in batch_vecs), "Toutes les dimensions du lot doivent valoir 384"
    latence_par_item = latence_batch / len(entites)
    print(f"   ✓ Lot de {len(entites)} entités encodé en {latence_batch:.2f} ms ({latence_par_item:.2f} ms/élément)")

    # Test lot vide
    empty_res = await embedder.create_batch([])
    assert empty_res == [], f"Un lot vide doit retourner [], obtenu {empty_res}"
    print("   ✓ Gestion de lot vide OK")

    # 4. Intégration conjointe avec Graphiti
    print("\n4. Test d'intégration avec Graphiti...")
    from graphiti_core.cross_encoder.client import CrossEncoderClient
    from graphiti_core.driver.driver import GraphDriver

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

    dummy_driver = DummyDriver()
    dummy_cross_encoder = DummyCrossEncoder()
    llm_client = MiroFishLLMClient(
        config=LLMConfig(api_key="fake-key", base_url="https://api.opencode.ai/v1", model="space-bunny-free")
    )
    graphiti = Graphiti(
        graph_driver=dummy_driver,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=dummy_cross_encoder,
    )
    assert graphiti.embedder is embedder, "L'embedder n'a pas été correctement assigné à l'instance Graphiti"
    assert graphiti.clients.embedder is embedder, "L'embedder de graphiti.clients doit correspondre"
    print("   ✓ Instanciation de Graphiti avec SentenceTransformerEmbedder réussie sans clé OpenAI")

    print("\n" + "=" * 60)
    print("VERDICT : TOUS LES CONTRÔLES EMBEDDER SONT CONFORMES (100 % LOCAL)")
    print("=" * 60)
    return True


def main() -> int:
    mock_mode = "--mock" in sys.argv
    try:
        succes = asyncio.run(tester_embedder_local(mock=mock_mode))
        return 0 if succes else 1
    except Exception as e:
        print(f"\n❌ ERREUR lors de la vérification de l'embedder : {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
