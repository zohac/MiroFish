"""Tests hermétiques pour le banc d'orchestration de qualification de l'Epic 007 (Story 007-7, AC1-AC9).

Vérifie :
- L'exécution isolée et déterministe de chaque sonde C1 à C8 ;
- Le formatage et la génération du rapport formel markdown ;
- La gestion des arguments CLI (--output, --mock-llm, --verbose) ;
- Le code de retour CLI (0 sur GO, 1 sur NO-GO).
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from scripts.verifier_qualification_epic_007 import (
    DeterministicClassifierLLM,
    generer_rapport_qualification,
    main,
    verifier_critere_c1,
    verifier_critere_c2,
    verifier_critere_c3,
    verifier_critere_c4,
    verifier_critere_c5,
    verifier_critere_c6,
    verifier_critere_c7,
    verifier_critere_c8,
)


def test_deterministic_classifier_llm():
    """Vérifie les retours déterministes du mock LLM."""
    mock_llm = DeterministicClassifierLLM()
    res1 = mock_llm.chat_json([{"content": "Capitaine Bunny"}])
    assert res1["role"] == "person"
    assert res1["status"] == "eligible"

    res2 = mock_llm.chat_json([{"content": "Conseil d'Administration"}])
    assert res2["role"] == "organization"
    assert res2["status"] == "eligible"

    res3 = mock_llm.chat_json([{"content": "Cratère Lunaire"}])
    assert res3["role"] == "concept"
    assert res3["status"] == "ineligible"


def test_verifier_critere_c1():
    """AC2 : Vérifie C1 (labels custom >= 80% sur 2 domaines)."""
    succes, details = verifier_critere_c1(mock_llm=True)
    assert succes is True
    assert details["telecom"]["ratio"] >= 80.0
    assert details["energie"]["ratio"] >= 80.0
    assert details["telecom"]["max_custom_labels"] <= 1
    assert details["energie"]["max_custom_labels"] <= 1


def test_verifier_critere_c2():
    """AC2 : Vérifie C2 (validation écriture & strict_ontology)."""
    succes, details = verifier_critere_c2()
    assert succes is True
    assert details["mode_permissif_warning"] is True
    assert details["mode_strict_rejet"] is True
    assert details["warnings_count"] == 1


def test_verifier_critere_c3():
    """AC3 : Vérifie C3 (régénération sous budget & déterminisme canonique)."""
    succes, details = verifier_critere_c3(mock_llm=True)
    assert succes is True
    assert details["identiques"] is True
    assert details["duree_max_s"] < details["seuil_hote_s"]
    assert details["audit_007_3_present"] is True


def test_verifier_critere_c4():
    """AC4 : Vérifie C4 (événement E1 ajout document < 5s & préservation labels)."""
    succes, details = verifier_critere_c4()
    assert succes is True
    assert details["duree_e1_s"] < 5.0
    assert details["labels_preserves"] is True
    assert details["nouveau_type_ajoute"] is True
    assert details["version_finale"] == 2


def test_verifier_critere_c5():
    """AC5 : Vérifie C5 (cohérence projet E5 & étanchéité multi-projets)."""
    succes, details = verifier_critere_c5()
    assert succes is True
    assert details["stabilite_meme_projet"] is True
    assert details["etancheite_inter_projets"] is True


def test_verifier_critere_c6():
    """AC6 : Vérifie C6 (composition ActorClassifier & court-circuit LLM)."""
    succes, details = verifier_critere_c6()
    assert succes is True
    assert details["court_circuit_ok"] is True
    assert details["cascade_fallback_ok"] is True
    assert details["acteurs_space_bunny"] == 8
    assert details["faux_acteurs"] == 0


def test_verifier_critere_c7():
    """AC7 : Vérifie C7 (audit rapport sous-section 6 & outil LLM get_applied_ontology)."""
    succes, details = verifier_critere_c7()
    assert succes is True
    assert details["section_audit_presente"] is True
    assert details["omission_conditionnelle_validee"] is True
    assert details["outil_llm_operationnel"] is True


def test_verifier_critere_c8_mocked():
    """AC8 : Vérifie C8 avec subprocess mocké pour vitesse d'exécution."""
    def _mock_subprocess_run(cmd, *args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stderr = ""
        if "docker" in cmd:
            mock_proc.stdout = "1534 passed, 3 deselected in 120s\n"
        else:
            mock_proc.stdout = "1549 passed in 250s\n"
        return mock_proc

    with patch("subprocess.run", side_effect=_mock_subprocess_run):
        succes, details = verifier_critere_c8()
        assert succes is True
        assert details["nfr5_conforme"] is True
        assert details["tests_passed"] == 1549
        assert details["docker_exit"] == 0


def test_generer_rapport_qualification(tmp_path):
    """AC9 : Vérifie la génération et le contenu du rapport Markdown formel."""
    out_file = tmp_path / "rapport-test.md"
    resultats_mock = {
        "C1": (True, {"telecom": {"ratio": 100.0, "labelled": 15, "total": 15}, "energie": {"ratio": 100.0, "labelled": 15, "total": 15}}),
        "C2": (True, {}),
        "C3": (True, {"seuil_hote_s": 30.0}),
        "C4": (True, {"duree_e1_s": 0.001}),
        "C5": (True, {}),
        "C6": (True, {}),
        "C7": (True, {}),
        "C8": (True, {"tests_passed": 1549}),
    }
    generer_rapport_qualification(resultats_mock, out_file)
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "VERDICT GO" in content
    assert "Rapport de Qualification Globale — Epic 007" in content
    assert "1549 tests réussis" in content


def test_main_cli_success(tmp_path, monkeypatch):
    """AC1 : Vérifie le code de retour CLI et les arguments standard."""
    out_file = tmp_path / "cli_report.md"
    test_args = [
        "verifier_qualification_epic_007.py",
        "--output", str(out_file),
        "--mock-llm",
    ]
    monkeypatch.setattr("sys.argv", test_args)

    with patch("scripts.verifier_qualification_epic_007.verifier_critere_c8") as mock_c8:
        mock_c8.return_value = (True, {"tests_passed": 1549, "docker_exit": 0, "host_summary": "1549 passed"})
        exit_code = main()
        assert exit_code == 0
        assert out_file.exists()


def test_main_cli_failure(tmp_path, monkeypatch):
    """AC1 : Vérifie le code de retour CLI 1 en cas d'échec d'un critère."""
    out_file = tmp_path / "cli_fail_report.md"
    test_args = [
        "verifier_qualification_epic_007.py",
        "--output", str(out_file),
        "--no-mock-llm",
    ]
    monkeypatch.setattr("sys.argv", test_args)

    with patch("scripts.verifier_qualification_epic_007.verifier_critere_c1") as mock_c1, \
         patch("scripts.verifier_qualification_epic_007.verifier_critere_c8") as mock_c8:
        mock_c1.return_value = (False, {
            "telecom": {"ratio": 40.0, "labelled": 4, "total": 10},
            "energie": {"ratio": 40.0, "labelled": 4, "total": 10},
        })
        mock_c8.return_value = (True, {"tests_passed": 1549, "docker_exit": 0, "host_summary": "1549 passed"})
        exit_code = main()
        assert exit_code == 1
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "VERDICT NO-GO" in content
