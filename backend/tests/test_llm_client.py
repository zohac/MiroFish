"""Tests unitaires hermétiques pour LLMClient (Story 004-1).

Ces tests vérifient :
- L'instanciation de LLMClient avec des paramètres explicites ou issus de Config/.env
- La présence d'en-tête de session uniquement lorsque l'endpoint est OpenCode Go
- La neutralité stricte sur les endpoints tiers (OpenAI, DeepSeek, Groq, Ollama local)
- La levée d'erreur si aucune clé n'est fournie
"""

from unittest.mock import MagicMock, patch
import pytest

from app.config import Config
from app.utils.llm_client import LLMClient


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch):
    """Garantit un environnement hermétique sans secrets réels."""
    monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-key-env")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-4o-mini")


def test_llm_client_initialisation_par_defaut():
    """Vérifie l'initialisation de LLMClient depuis Config."""
    client = LLMClient()
    assert client.api_key == "test-key-env"
    assert client.base_url == "https://api.openai.com/v1"
    assert client.model == "gpt-4o-mini"
    # Fournisseur OpenAI par défaut : aucun en-tête OpenCode
    assert "x-opencode-session" not in client.client.default_headers
    assert client.client.default_headers.get("User-Agent") == "mirofish/0.1.0"


def test_llm_client_avec_endpoint_opencode(monkeypatch):
    """Vérifie que LLMClient injecte l'en-tête de session quand l'endpoint est OpenCode."""
    monkeypatch.setenv("LLM_BASE_URL", "https://opencode.ai/zen/go/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "space-bunny-free")

    client = LLMClient()
    assert client.base_url == "https://opencode.ai/zen/go/v1"
    assert client.model == "space-bunny-free"
    assert "x-opencode-session" in client.client.default_headers


def test_llm_client_avec_arguments_explicites():
    """Vérifie que les arguments explicites priment sur Config/env."""
    client = LLMClient(
        api_key="custom-key",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
    )
    assert client.api_key == "custom-key"
    assert client.base_url == "https://api.deepseek.com/v1"
    assert client.model == "deepseek-chat"
    assert "x-opencode-session" not in client.client.default_headers


def test_llm_client_sans_api_key_leve_erreur(monkeypatch):
    """Vérifie qu'une exception claire est levée en l'absence de LLM_API_KEY."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(Config, "LLM_API_KEY", None)

    with pytest.raises(ValueError, match="LLM_API_KEY"):
        LLMClient(api_key=None)
