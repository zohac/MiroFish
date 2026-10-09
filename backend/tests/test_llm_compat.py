import pytest

from app.utils.llm_compat import (
    llm_completion_kwargs,
    llm_request_headers,
)


def test_headers_identify_the_client_on_any_provider():
    headers = llm_request_headers("https://api.openai.com/v1")

    assert headers["User-Agent"] == "mirofish/0.1.0"
    assert "x-opencode-session" not in headers


@pytest.mark.parametrize(
    "base_url",
    [
        "https://opencode.ai/zen/go/v1",
        "https://opencode.ai/zen/v1",
        "https://OPENCODE.AI/zen/go/v1",
    ],
)
def test_session_header_is_sent_to_opencode_gateways(base_url, monkeypatch):
    monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)

    headers = llm_request_headers(base_url)

    assert headers["x-opencode-session"]


def test_explicit_session_id_wins(monkeypatch):
    monkeypatch.setenv("OPENCODE_SESSION_ID", "my-session")

    headers = llm_request_headers("https://opencode.ai/zen/go/v1")

    assert headers["x-opencode-session"] == "my-session"


def test_session_id_is_stable_across_calls(monkeypatch):
    monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)

    first = llm_request_headers("https://opencode.ai/zen/go/v1")
    second = llm_request_headers("https://opencode.ai/zen/go/v1")

    assert first["x-opencode-session"] == second["x-opencode-session"]


def test_subdomain_of_opencode_is_treated_as_a_gateway():
    headers = llm_request_headers("https://zen.opencode.ai/v1")

    assert "x-opencode-session" in headers


@pytest.mark.parametrize(
    "provider_url",
    [
        "https://api.openai.com/v1",
        "https://api.deepseek.com/v1",
        "https://api.groq.com/openai/v1",
        "https://api.mistral.ai/v1",
        "http://localhost:11434/v1",
        "http://127.0.0.1:8000/v1",
    ],
)
def test_fournisseurs_tiers_ont_user_agent_sans_session_opencode(provider_url):
    """Vérifie la neutralité stricte envers les fournisseurs payants ou locaux."""
    headers = llm_request_headers(provider_url)

    assert headers["User-Agent"] == "mirofish/0.1.0"
    assert "x-opencode-session" not in headers


def test_url_sans_scheme_opencode_injecte_session():
    """Vérifie qu'une URL sans https:// vers OpenCode est correctement identifiée."""
    headers = llm_request_headers("opencode.ai/zen/go/v1")
    assert "x-opencode-session" in headers


def test_url_sans_scheme_tiers_reste_neutre():
    """Vérifie qu'une URL sans https:// vers un tiers ne reçoit aucun en-tête OpenCode."""
    headers = llm_request_headers("api.deepseek.com/v1")
    assert "x-opencode-session" not in headers


def test_completion_kwargs_avec_effort_explicite():
    """Vérifie qu'un niveau d'effort passé explicitement en argument l'emporte."""
    assert llm_completion_kwargs("low") == {"reasoning_effort": "low"}
    assert llm_completion_kwargs("  medium  ") == {"reasoning_effort": "medium"}
    assert llm_completion_kwargs("") == {}


def test_completion_kwargs_vide_quand_env_vide(monkeypatch):
    """Vérifie que sans variable d'environnement, aucun effort n'est émis."""
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    assert llm_completion_kwargs() == {}


def test_config_expose_llm_reasoning_effort():
    """Vérifie que la classe Config expose formellement l'attribut LLM_REASONING_EFFORT."""
    from app.config import Config

    assert hasattr(Config, "LLM_REASONING_EFFORT")
    assert isinstance(Config.LLM_REASONING_EFFORT, str)