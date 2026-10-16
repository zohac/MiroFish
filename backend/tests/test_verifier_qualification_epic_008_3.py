"""Tests hermétiques pour le banc d'orchestration de qualification de la Story 008-3.

Vérifie :
- L'exécution isolée et déterministe de chaque sonde AC1 à AC7 ;
- La génération du rapport formel markdown de qualification ;
- Le code de retour CLI (0 sur GO, 1 sur NO-GO).
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import pytest

from scripts.verifier_qualification_epic_008_3 import (
    generer_rapport_markdown,
    main,
    verifier_ac1_locale_canonique,
    verifier_ac2_propagation_sous_processus,
    verifier_ac4_contrats_techniques,
    verifier_ac5_personas_francais,
    verifier_ac7_rapport_francais,
)


def test_sonde_ac1_locale_canonique(tmp_path):
    """Vérifie l'évaluation de AC1 (persistance et normalisation)."""
    ok, details = verifier_ac1_locale_canonique(tmp_path)
    assert ok is True
    assert "RFC 7231" in details["normalisation"]
    assert "state.json" in details["persistance_disque"]


def test_sonde_ac2_propagation_sous_processus(tmp_path):
    """Vérifie l'évaluation de AC2 (propagation sous-processus et isolation de threads)."""
    ok, details = verifier_ac2_propagation_sous_processus(tmp_path)
    assert ok is True
    assert "thread_local" in details["isolation_threads"]
    assert "MIROFISH_SIMULATION_LOCALE='fr'" in details["env_subprocess"]


def test_sonde_ac4_contrats_techniques():
    """Vérifie l'évaluation de AC4 (invariance des contrats techniques)."""
    ok, details = verifier_ac4_contrats_techniques()
    assert ok is True
    assert "Invariants préservés" in details["cles_json"]


def test_sonde_ac5_personas_francais():
    """Vérifie l'évaluation de AC5 (personas et replis localisés en français)."""
    ok, details = verifier_ac5_personas_francais()
    assert ok is True
    assert "100% français" in details["personas_fallback"]
    assert "Consigne linguistique" in details["guidance_actions_oasis"]


def test_sonde_ac7_rapport_francais():
    """Vérifie l'évaluation de AC7 (rapport prédictif et ReACT en français)."""
    ok, details = verifier_ac7_rapport_francais()
    assert ok is True
    assert "JSON keys anglaises" in details["outline_planning"]
    assert "Rapport de prédiction et simulation" in details["outline_fallback"]
    assert "Observations, limites et forçage" in details["react_messages"]


def test_generer_rapport_markdown(tmp_path):
    """Vérifie le formatage du rapport formel markdown."""
    report_file = tmp_path / "rapport-test.md"
    dummy_results = {
        "AC1": (True, {"detail": "OK"}),
        "AC2": (True, {"detail": "OK"}),
    }
    generer_rapport_markdown(dummy_results, report_file)
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "# Rapport de qualification globale — Story 008-3 (VERDICT GO)" in content
    assert "AC1" in content
    assert "AC2" in content


def test_main_cli_execution(tmp_path, monkeypatch):
    """Vérifie l'exécution complète du script via CLI."""
    out_file = tmp_path / "qualif-report.md"
    monkeypatch.setattr("sys.argv", ["verifier_qualification_epic_008_3.py", "--output", str(out_file)])
    ret = main()
    assert ret == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "VERDICT GO" in content
