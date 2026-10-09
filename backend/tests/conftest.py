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
        monkeypatch.setattr(Config, "ZEP_API_KEY", "test-mock-zep-api-key-conftest")
    if not os.environ.get("ZEP_API_KEY"):
        monkeypatch.setenv("ZEP_API_KEY", "test-mock-zep-api-key-conftest")
