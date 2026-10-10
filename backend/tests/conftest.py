"""Configuration pytest globale et fixtures d'hermétisme (AGENTS.md §2.2).

Garantit qu'aucun test ne dépend de la présence d'un fichier .env local
et qu'une clé API Zep factice par défaut est disponible si aucune n'est configurée,
assurant ainsi un comportement identique entre la machine locale et l'environnement CI.
"""

import os
import pytest
from app.config import Config


@pytest.fixture(autouse=True)
def hermetic_env_defaults(monkeypatch):
    """Garantit des valeurs par défaut pour les clés nécessaires aux constructeurs."""
    if not getattr(Config, "ZEP_API_KEY", None):
        monkeypatch.setattr(Config, "ZEP_API_KEY", "test-mock-zep-api-key-conftest", raising=False)
    if not os.environ.get("ZEP_API_KEY"):
        monkeypatch.setenv("ZEP_API_KEY", "test-mock-zep-api-key-conftest")
    if not getattr(Config, "LLM_API_KEY", None):
        monkeypatch.setattr(Config, "LLM_API_KEY", "test-mock-llm-api-key-conftest", raising=False)
    if not os.environ.get("LLM_API_KEY"):
        monkeypatch.setenv("LLM_API_KEY", "test-mock-llm-api-key-conftest")
    if not os.environ.get("OPENAI_API_KEY"):
        monkeypatch.setenv("OPENAI_API_KEY", "test-mock-openai-api-key-conftest")
    if not getattr(Config, "NEO4J_PASSWORD", None):
        monkeypatch.setattr(Config, "NEO4J_PASSWORD", "test-mock-neo4j-password-conftest", raising=False)
    if not os.environ.get("NEO4J_PASSWORD"):
        monkeypatch.setenv("NEO4J_PASSWORD", "test-mock-neo4j-password-conftest")
    if not os.environ.get("NEO4J_URI"):
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    if not os.environ.get("NEO4J_USER"):
        monkeypatch.setenv("NEO4J_USER", "neo4j")
