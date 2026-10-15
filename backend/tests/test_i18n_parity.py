"""Unit tests for i18n parity and French locale integration (Story 008-1)."""

import json
import os
import re
import pytest
from flask import Flask

from app.utils.locale import (
    _translations,
    _languages,
    get_locale,
    set_locale,
    normalize_locale,
    t,
    get_language_instruction,
)

LOCALES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "locales")
)


def _flatten_keys(d, prefix=""):
    """Recursively flatten dictionary keys to dot-notation."""
    res = {}
    for k, v in d.items():
        curr = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            res.update(_flatten_keys(v, curr))
        else:
            res[curr] = v
    return res


def test_fr_json_exists_and_valid():
    """Verify that locales/fr.json exists and is valid JSON."""
    fr_path = os.path.join(LOCALES_DIR, "fr.json")
    assert os.path.isfile(fr_path), f"fr.json not found at {fr_path}"
    with open(fr_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert len(data) > 0


def test_en_fr_key_parity():
    """Verify strict 100% key parity between en.json and fr.json (0 missing, 0 extra)."""
    en_path = os.path.join(LOCALES_DIR, "en.json")
    fr_path = os.path.join(LOCALES_DIR, "fr.json")

    with open(en_path, "r", encoding="utf-8") as f:
        en_data = json.load(f)
    with open(fr_path, "r", encoding="utf-8") as f:
        fr_data = json.load(f)

    en_keys = _flatten_keys(en_data)
    fr_keys = _flatten_keys(fr_data)

    missing_in_fr = set(en_keys.keys()) - set(fr_keys.keys())
    extra_in_fr = set(fr_keys.keys()) - set(en_keys.keys())

    assert not missing_in_fr, f"Keys missing in fr.json: {missing_in_fr}"
    assert not extra_in_fr, f"Extraneous keys in fr.json: {extra_in_fr}"
    assert len(en_keys) == len(fr_keys)
    assert len(fr_keys) == 679


def test_en_fr_placeholder_parity():
    """Verify that every named variable placeholder {var} matches between en.json and fr.json."""
    en_path = os.path.join(LOCALES_DIR, "en.json")
    fr_path = os.path.join(LOCALES_DIR, "fr.json")

    with open(en_path, "r", encoding="utf-8") as f:
        en_data = json.load(f)
    with open(fr_path, "r", encoding="utf-8") as f:
        fr_data = json.load(f)

    en_keys = _flatten_keys(en_data)
    fr_keys = _flatten_keys(fr_data)

    ph_pattern = re.compile(r"\{([a-zA-Z0-9_]+)\}")
    mismatches = []

    for k in en_keys:
        en_val = en_keys[k]
        fr_val = fr_keys[k]
        if isinstance(en_val, str) and isinstance(fr_val, str):
            en_ph = set(ph_pattern.findall(en_val))
            fr_ph = set(ph_pattern.findall(fr_val))
            if en_ph != fr_ph:
                mismatches.append((k, en_ph, fr_ph, en_val, fr_val))

    assert not mismatches, f"Placeholder mismatches detected: {mismatches}"


def test_backend_locale_loading():
    """Verify that backend _translations and _languages recognize French."""
    assert "fr" in _translations, "fr locale is not loaded into _translations"
    assert "fr" in _languages, "fr is not defined in languages.json"
    assert _languages["fr"]["label"] == "Français"
    assert _languages["fr"]["llmInstruction"] == "Veuillez répondre en français."


def test_normalize_locale():
    """Verify normalize_locale correctly parses various RFC 7231 locale inputs."""
    assert normalize_locale("fr") == "fr"
    assert normalize_locale("fr-FR") == "fr"
    assert normalize_locale("fr-BE") == "fr"
    assert normalize_locale("fr-CA,fr;q=0.9,en;q=0.8") == "fr"
    assert normalize_locale("en-US,en;q=0.9") == "en"
    assert normalize_locale("zh-CN,zh;q=0.9") == "zh"
    assert normalize_locale(None) == "zh"
    assert normalize_locale("") == "zh"
    assert normalize_locale("unknown-LANGUAGE") == "zh"


def test_set_locale_and_translation():
    """Verify set_locale('fr') correctly affects t() and get_language_instruction()."""
    set_locale("fr")
    assert get_locale() == "fr"
    assert t("common.confirm") == "Confirmer"
    assert t("common.cancel") == "Annuler"
    assert t("step1.createSimulationFailed", error="test_err") == (
        "Échec de la création de la simulation : test_err"
    )
    assert get_language_instruction() == "Veuillez répondre en français."

    # Reset back to zh
    set_locale("zh")
    assert get_locale() == "zh"
    assert t("common.confirm") == "确认"


def test_flask_request_accept_language_header():
    """Verify get_locale() and t() in Flask request context with Accept-Language header."""
    app = Flask(__name__)

    with app.test_request_context(headers={"Accept-Language": "fr-FR,fr;q=0.9"}):
        assert get_locale() == "fr"
        assert t("common.close") == "Fermer"
        assert t("history.title") == "Historique des simulations"
        assert get_language_instruction() == "Veuillez répondre en français."

    with app.test_request_context(headers={"Accept-Language": "en-US,en;q=0.8"}):
        assert get_locale() == "en"
        assert t("common.close") == "Close"
        assert get_language_instruction() == "Please respond in English."

    with app.test_request_context(headers={"Accept-Language": "zh-CN,zh;q=0.9"}):
        assert get_locale() == "zh"
        assert t("common.close") == "关闭"
        assert get_language_instruction() == "请使用中文回答。"
