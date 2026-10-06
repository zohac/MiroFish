#!/usr/bin/env python3
"""Sonde de vérification du client LLM Graphiti (Story 001-3).

Ce script teste le client ``MiroFishLLMClient`` en conditions réelles ou simulées
afin de valider le critère de sortie C2 du PRD de l'epic 001 :
« 0 échec d'authentification (MissingSessionID) sur les appels LLM ».

Exécution :
    cd backend
    uv run python scripts/verifier_llm_graphiti.py
    uv run python scripts/verifier_llm_graphiti.py --mock
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

from pydantic import BaseModel, Field

# S'assurer que le package backend est dans le path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import Config  # noqa: E402
from app.utils.graphiti_llm_client import MiroFishLLMClient  # noqa: E402
from graphiti_core.prompts.models import Message  # noqa: E402


class EntiteEpreuve(BaseModel):
    """Schéma Pydantic d'extraction représentatif des besoins de Graphiti."""

    nom: str = Field(description="Nom de l'entité extraite")
    categorie: str = Field(description="Catégorie de l'entité (ex: Organisation, Personne, Concept)")
    description: str = Field(description="Brève description de l'entité dans le contexte")


class ResultatExtractionEpreuve(BaseModel):
    """Modèle racine structuré pour l'épreuve."""

    entites: List[EntiteEpreuve] = Field(default_factory=list, description="Liste des entités extraites")
    resume: str = Field(description="Résumé succinct du passage")


async def verifier_client_graphiti(mock: bool = False) -> int:
    """Exécute l'épreuve de compatibilité LLM Graphiti."""
    print("=" * 70)
    print("SONDE DE VÉRIFICATION DU CLIENT LLM GRAPHITI (STORY 001-3)")
    print("=" * 70)

    base_url = os.environ.get("LLM_BASE_URL") or Config.LLM_BASE_URL or "https://opencode.ai/zen/go/v1"
    model = os.environ.get("LLM_MODEL_NAME") or Config.LLM_MODEL_NAME or "space-bunny-free"
    api_key = os.environ.get("LLM_API_KEY") or Config.LLM_API_KEY

    print(f"URL cible      : {base_url}")
    print(f"Modèle         : {model}")
    print(f"Mode simulé    : {'Oui (--mock)' if mock else 'Non (appel réel)'}")

    if mock:
        # En mode simulé (--mock), on instancie MiroFishLLMClient normalement pour que
        # ses propres default_headers soient construits par sa logique d'initialisation,
        # puis on mocke uniquement chat.completions.create pour éviter tout appel réseau.
        if not api_key:
            os.environ.setdefault("LLM_API_KEY", "mock-epreuve-key")
        client = MiroFishLLMClient()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"entites": [{"nom": "Assemblée nationale", "categorie": "Organisation", '
            '"description": "Chambre parlementaire"}], "resume": "Extrait du rapport 2506."}'
        )
        mock_response.choices = [mock_choice]
        client.client.chat.completions.create = AsyncMock(return_value=mock_response)
    else:
        if not api_key:
            print("\n❌ ERREUR : Aucune clé LLM_API_KEY trouvée dans l'environnement ni dans .env.")
            print("Pour exécuter la sonde en mode simulation sans clé, utilisez : --mock")
            return 1
        client = MiroFishLLMClient()

    # 1. Contrôle des en-têtes
    print("\n--- 1. Contrôle des en-têtes injectés ---")
    headers = client.client.default_headers
    user_agent = headers.get("User-Agent")
    session_id = headers.get("x-opencode-session")

    print(f"User-Agent            : {user_agent}")
    print(f"x-opencode-session    : {session_id}")

    if not user_agent:
        print("❌ ÉCHEC : User-Agent manquant dans les en-têtes par défaut.")
        return 1

    if "opencode.ai" in (base_url or "").lower():
        if not session_id:
            print("❌ ÉCHEC : x-opencode-session manquant pour l'endpoint OpenCode Go !")
            return 1
        print("✓ En-tête x-opencode-session présent et conforme.")
    else:
        if session_id:
            print("⚠️ AVERTISSEMENT : x-opencode-session présent pour un endpoint non-OpenCode.")
        else:
            print("✓ En-tête de session absent (neutralité confirmée).")

    # 2. Contrôle du mode de sortie structurée
    print("\n--- 2. Contrôle du mode de sortie structurée ---")
    print(f"structured_output_mode : {client.structured_output_mode}")
    if client.structured_output_mode != "json_object":
        print("❌ ÉCHEC : structured_output_mode attendu 'json_object'.")
        return 1
    print("✓ Mode json_object actif par défaut.")

    # 3. Exercice d'un appel d'extraction structuré
    print("\n--- 3. Exécution d'un appel d'extraction d'épisode ---")
    texte_epreuve = (
        "L'Assemblée nationale a constitué le 14 mai 2024 une commission d'enquête "
        "sur les conditions d'attribution et de gestion des fréquences de la TNT."
    )
    messages = [
        Message(role="system", content="Tu es un extracteur d'entités pour un graphe de connaissances."),
        Message(role="user", content=f"Extrais les entités et résume ce texte :\n\n{texte_epreuve}"),
    ]

    t0 = time.perf_counter()
    try:
        reponse: Dict[str, Any] = await client.generate_response(
            messages,
            response_model=ResultatExtractionEpreuve,
        )
        duree = time.perf_counter() - t0
        print(f"✓ Réponse reçue en {duree:.2f}s")
        print(f"Contenu parsé : {reponse}")

        # Validation de forme
        if "entites" in reponse and "resume" in reponse:
            print("✓ Format JSON structuré validé avec succès.")
        else:
            print(f"⚠️ Avertissement : Clés attendues 'entites' et 'resume' non conformes : {reponse.keys()}")

    except Exception as exc:
        duree = time.perf_counter() - t0
        err_msg = str(exc)
        print(f"❌ Échec de l'appel LLM après {duree:.2f}s : {exc}")
        if "MissingSessionID" in err_msg or "400" in err_msg and "session" in err_msg.lower():
            print("🚨 ERREUR CRITIQUE : Échec d'authentification MissingSessionID détecté (Violation C2) !")
        return 1

    print("\n" + "=" * 70)
    print("RÉSULTAT : VERDICT C2 CONFORME — 0 échec MissingSessionID")
    print("=" * 70)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Vérification du client LLM Graphiti")
    parser.add_argument("--mock", action="store_true", help="Exécute l'épreuve avec un mock sans appel réseau")
    args = parser.parse_args()

    code = asyncio.run(verifier_client_graphiti(mock=args.mock))
    sys.exit(code)


if __name__ == "__main__":
    main()
