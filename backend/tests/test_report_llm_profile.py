"""Tests hermétiques pour Story 013-1 : Configuration LLM dédiée et support de l'effort.

Valide :
1. Le modèle ReportLLMProfile (immuabilité, validation, masquage des secrets, profils standards).
2. create_chat_completion avec paramètre reasoning_effort explicite sans altération d'os.environ.
3. LLMClient recevant un ReportLLMProfile ou reasoning_effort explicite et capturant usage.
4. antigravity_proxy._build_gemini_request traduisant reasoning_effort vers thinkingConfig.
5. ReportAgent et Report intégrant et persistant profile_id et llm_profile.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from app.models.report_llm_profile import (
    VALID_REASONING_EFFORTS,
    ReportLLMProfile,
)
from app.services.report_agent import Report, ReportAgent, ReportManager, ReportStatus
from app.utils.llm_client import LLMClient
from app.utils.openai_chat_compat import create_chat_completion


# ──────────────────────────────────────────────────────────────────────────────
# 1. Tests du modèle ReportLLMProfile
# ──────────────────────────────────────────────────────────────────────────────

def test_report_llm_profile_creation_and_validation():
    """Valide les contraintes de construction du profil."""
    # Profil valide
    prof = ReportLLMProfile(
        profile_id="test-high",
        model="gemini-3.8-flash",
        reasoning_effort="HIGH",
        temperature=0.4,
        max_tokens=8192,
    )
    assert prof.profile_id == "test-high"
    assert prof.model == "gemini-3.8-flash"
    assert prof.reasoning_effort == "high"  # Normalisé en minuscules
    assert prof.temperature == 0.4
    assert prof.max_tokens == 8192

    # Validation d'ID vide
    with pytest.raises(ValueError, match="profile_id"):
        ReportLLMProfile(profile_id="", model="gemini-3.8-flash")

    # Validation de modèle vide
    with pytest.raises(ValueError, match="model"):
        ReportLLMProfile(profile_id="test", model="")

    # Validation d'effort invalide
    with pytest.raises(ValueError, match="reasoning_effort invalide"):
        ReportLLMProfile(profile_id="test", model="gemini", reasoning_effort="extreme")


def test_report_llm_profile_to_dict_secret_masking():
    """Vérifie que les clés d'API et URLs privées sont masquées par défaut."""
    prof = ReportLLMProfile(
        profile_id="secure-prof",
        model="gemini-3.8-flash",
        api_key="sk-secret-key-12345",
        base_url="https://api.openai.com/v1",
    )

    masked = prof.to_dict(expose_secrets=False)
    assert "api_key" not in masked
    assert "base_url" not in masked
    assert masked.get("base_url_configured") is True
    assert masked["model"] == "gemini-3.8-flash"

    exposed = prof.to_dict(expose_secrets=True)
    assert exposed.get("api_key") == "sk-secret-key-12345"
    assert exposed.get("base_url") == "https://api.openai.com/v1"


def test_report_llm_profile_roundtrip():
    """Vérifie la désérialisation from_dict / to_dict."""
    data = {
        "profile_id": "flash-high",
        "model": "gemini-3.8-flash",
        "provider_id": "antigravity-local",
        "reasoning_effort": "high",
        "temperature": 0.2,
        "max_tokens": 4096,
        "max_total_cost_usd": 3.5,
        "max_wall_seconds": 600,
    }
    prof = ReportLLMProfile.from_dict(data)
    assert prof.profile_id == "flash-high"
    assert prof.reasoning_effort == "high"
    assert prof.max_total_cost_usd == 3.5
    assert prof.max_wall_seconds == 600


def test_report_llm_profile_standards_and_env():
    """Valide les catalogues prédéfinis de profils."""
    med = ReportLLMProfile.get_standard_profile("flash-medium")
    assert med is not None
    assert med.model == "gemini-3.8-flash"
    assert med.reasoning_effort == "medium"

    high = ReportLLMProfile.get_standard_profile("flash-high")
    assert high is not None
    assert high.reasoning_effort == "high"

    deepseek = ReportLLMProfile.get_standard_profile("deepseek-v4-pro")
    assert deepseek is not None
    assert deepseek.model == "deepseek-v4-pro"

    default_prof = ReportLLMProfile.default_from_env()
    assert default_prof is not None
    assert default_prof.profile_id == "env-default"


# ──────────────────────────────────────────────────────────────────────────────
# 2. Tests de create_chat_completion avec reasoning_effort explicite
# ──────────────────────────────────────────────────────────────────────────────

def test_create_chat_completion_explicit_reasoning_effort():
    """Vérifie que reasoning_effort explicite est injecté sans muter os.environ."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock()

    original_env = os.environ.get("LLM_REASONING_EFFORT")
    try:
        os.environ["LLM_REASONING_EFFORT"] = "low"

        # Appel avec override explicite "high"
        create_chat_completion(
            mock_client,
            model="gemini-3.8-flash",
            messages=[{"role": "user", "content": "hello"}],
            reasoning_effort="high",
        )

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["reasoning_effort"] == "high"
        # os.environ ne doit pas avoir bougé
        assert os.environ["LLM_REASONING_EFFORT"] == "low"

        # Appel sans override explicite -> repli sur os.environ
        create_chat_completion(
            mock_client,
            model="gemini-3.8-flash",
            messages=[{"role": "user", "content": "hello"}],
            reasoning_effort=None,
        )
        call_kwargs2 = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs2["reasoning_effort"] == "low"
    finally:
        if original_env is None:
            os.environ.pop("LLM_REASONING_EFFORT", None)
        else:
            os.environ["LLM_REASONING_EFFORT"] = original_env


# ──────────────────────────────────────────────────────────────────────────────
# 3. Tests de LLMClient avec profil et transmission d'effort
# ──────────────────────────────────────────────────────────────────────────────

def test_llm_client_with_profile():
    """Valide l'initialisation de LLMClient via ReportLLMProfile."""
    prof = ReportLLMProfile(
        profile_id="custom-job",
        model="gpt-6.1-sol",
        reasoning_effort="medium",
        api_key="sk-test-fake",
        temperature=0.1,
        max_tokens=2048,
    )

    client = LLMClient(profile=prof)
    assert client.model == "gpt-6.1-sol"
    assert client.reasoning_effort == "medium"
    assert client.profile == prof


@patch("app.utils.llm_client.create_chat_completion")
def test_llm_client_chat_forwards_effort_and_captures_usage(mock_create):
    """Vérifie que chat et chat_json transmettent reasoning_effort et capturent usage."""
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="Hello response"))]
    mock_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=150)
    mock_create.return_value = mock_resp

    prof = ReportLLMProfile(
        profile_id="test",
        model="gemini-3.8-flash",
        reasoning_effort="high",
        api_key="sk-test",
    )
    client = LLMClient(profile=prof)

    result = client.chat([{"role": "user", "content": "ping"}])
    assert result == "Hello response"
    assert client.last_usage is not None
    assert client.last_usage.total_tokens == 150

    # Vérification des kwargs envoyés à create_chat_completion
    assert mock_create.call_args[1]["reasoning_effort"] == "high"


# ──────────────────────────────────────────────────────────────────────────────
# 4. Tests d'antigravity_proxy : traduction de reasoning_effort en thinkingConfig
# ──────────────────────────────────────────────────────────────────────────────

def test_antigravity_proxy_build_gemini_request_translates_effort():
    """Vérifie qu'antigravity_proxy mappe reasoning_effort vers thinkingLevel."""
    # Importer le module proxy
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))
    try:
        import antigravity_proxy

        # Cas 1 : reasoning_effort = "high"
        body_high = {
            "model": "gemini-3.8-flash",
            "reasoning_effort": "high",
            "messages": [{"role": "user", "content": "hi"}],
        }
        env_high = antigravity_proxy._build_gemini_request(body_high, "gemini-3.8-flash-tiered")
        tc_high = env_high["request"].get("generationConfig", {}).get("thinkingConfig")
        assert tc_high is not None
        assert tc_high.get("thinkingLevel") == "HIGH"
        assert tc_high.get("includeThoughts") is False

        # Cas 2 : reasoning_effort = "medium"
        body_med = {
            "model": "gemini-3.8-flash",
            "reasoning_effort": "medium",
            "messages": [{"role": "user", "content": "hi"}],
        }
        env_med = antigravity_proxy._build_gemini_request(body_med, "gemini-3.8-flash-tiered")
        tc_med = env_med["request"].get("generationConfig", {}).get("thinkingConfig")
        assert tc_med is not None
        assert tc_med.get("thinkingLevel") == "MEDIUM"

        # Cas 3 : reasoning_effort = "low"
        body_low = {
            "model": "gemini-3.8-flash",
            "reasoning_effort": "low",
            "messages": [{"role": "user", "content": "hi"}],
        }
        env_low = antigravity_proxy._build_gemini_request(body_low, "gemini-3.8-flash-tiered")
        tc_low = env_low["request"].get("generationConfig", {}).get("thinkingConfig")
        assert tc_low is not None
        assert tc_low.get("thinkingLevel") == "LOW"

        # Cas 4 : aucun effort spécifié -> pas d'écrasement de thinkingConfig si non configuré
        body_none = {
            "model": "gemini-3.8-flash",
            "messages": [{"role": "user", "content": "hi"}],
        }
        env_none = antigravity_proxy._build_gemini_request(body_none, "gemini-3.8-flash-tiered")
        assert "thinkingConfig" not in env_none["request"].get("generationConfig", {})
    finally:
        sys.path.pop(0)


# ──────────────────────────────────────────────────────────────────────────────
# 5. Tests de ReportAgent et Report intégrant le profil
# ──────────────────────────────────────────────────────────────────────────────

def test_report_agent_initialization_with_profile():
    """Vérifie que ReportAgent initialise correctement son profil et son client."""
    prof = ReportLLMProfile(
        profile_id="report-candidate-high",
        model="gemini-3.8-flash",
        reasoning_effort="high",
        api_key="sk-test-fake",
    )

    agent = ReportAgent(
        graph_id="grp_test",
        simulation_id="sim_test",
        simulation_requirement="Test requirement",
        profile=prof,
    )

    assert agent.profile == prof
    assert agent.llm.model == "gemini-3.8-flash"
    assert agent.llm.reasoning_effort == "high"


def test_report_dataclass_and_manager_roundtrip():
    """Valide la persistance et restitution des métadonnées de profil dans Report."""
    prof_dict = {
        "profile_id": "flash-high",
        "model": "gemini-3.8-flash",
        "reasoning_effort": "high",
    }
    report = Report(
        report_id="rep_test_013",
        simulation_id="sim_test",
        graph_id="grp_test",
        simulation_requirement="Test requirement",
        status=ReportStatus.COMPLETED,
        profile_id="flash-high",
        llm_profile=prof_dict,
    )

    d = report.to_dict()
    assert d["profile_id"] == "flash-high"
    assert d["llm_profile"]["reasoning_effort"] == "high"
