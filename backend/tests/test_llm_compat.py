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


def test_lookalike_host_is_not_given_a_session_header():
    headers = llm_request_headers("https://notopencode.ai/v1")

    assert "x-opencode-session" not in headers


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("high", {"reasoning_effort": "high"}),
        ("  high  ", {"reasoning_effort": "high"}),
        ("", {}),
        ("   ", {}),
    ],
)
def test_completion_kwargs_follow_configured_effort(monkeypatch, value, expected):
    monkeypatch.setenv("LLM_REASONING_EFFORT", value)

    assert llm_completion_kwargs() == expected


def test_completion_kwargs_are_empty_when_effort_is_unset(monkeypatch):
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)

    assert llm_completion_kwargs() == {}