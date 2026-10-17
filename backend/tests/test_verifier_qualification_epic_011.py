"""Tests hermétiques pour le banc d'orchestration de qualification de l'Epic 011 (Story 011-6, AC1 à AC12).

Vérifie :
- L'exécution isolée et déterministe de chaque sonde C1 à C11 ;
- Le formatage et la génération du rapport formel markdown avec VERDICT GO ;
- La gestion des arguments CLI (--output, --mock-llm, --domain, --verbose) ;
- Le code de retour CLI (0 sur GO, 1 sur NO-GO).
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from scripts.verifier_qualification_epic_011 import (
    charger_fixtures_domaines,
    generer_rapport_qualification,
    main,
    verifier_critere_c1,
    verifier_critere_c2_et_c3,
    verifier_critere_c4_et_c5,
    verifier_critere_c6,
    verifier_critere_c7_et_c8,
    verifier_critere_c9_et_c10,
    verifier_critere_c11_multi_domaines,
)


def test_charger_fixtures_domaines():
    """Vérifie le chargement exhaustif des 3 domaines requis pour l'évaluation."""
    domaines = charger_fixtures_domaines()
    assert len(domaines) == 3
    assert "keova" in domaines
    assert "public_policy" in domaines
    assert "telecom" in domaines

    # Vérification de structure
    for d_name in ("keova", "public_policy", "telecom"):
        data = domaines[d_name]
        assert "brief" in data
        assert "personas" in data
        assert "observed_actions" in data
        assert "citations" in data
        assert len(data["personas"]) == 4
        assert any(p.get("expected_silent") for p in data["personas"])


def test_verifier_critere_c1():
    """AC2 : Vérifie C1 (OASIS interactif post-rounds, interview_agents & clôture)."""
    succes, details = verifier_critere_c1(mock_llm=True)
    assert succes is True
    assert details["interactive_alive_verified"] is True
    assert details["interview_agents_success"] is True
    assert details["close_env_clean"] is True
    assert details["offline_fallback_ok"] is True


def test_verifier_critere_c2_et_c3():
    """AC3 : Vérifie C2 (traces réelles OasisLogReader) et C3 (Bouclier ToolShield)."""
    succes, details = verifier_critere_c2_et_c3()
    assert succes is True
    assert details["event_id_deterministic"] is True
    assert details["jsonl_and_sqlite_parsed"] is True
    assert details["tool_shield_interception_ok"] is True
    assert details["tool_shield_no_exception"] is True


def test_verifier_critere_c4_et_c5():
    """AC4 : Vérifie C4 (Anti-affabulation & ReportClaim) et C5 (Étanchéité épistémique)."""
    succes, details = verifier_critere_c4_et_c5()
    assert succes is True
    assert details["c4_intention_downgraded"] is True
    assert details["c4_verbatim_verified"] is True
    assert details["c4_forged_citation_rejected"] is True
    assert details["c5_persona_spec_isolated"] is True


def test_verifier_critere_c6():
    """AC5 : Vérifie C6 (Déterminisme d'assignation nominative Round 0)."""
    succes, details = verifier_critere_c6()
    assert succes is True
    assert details["matching_exact_rounds"] == details["total_trials"]
    assert details["zero_permutations"] is True


def test_verifier_critere_c7_et_c8():
    """AC6 & AC7 : Vérifie C7 (Tableau cohorte & silencieux) et C8 (Temps simulé & anti-fantômes)."""
    succes, details = verifier_critere_c7_et_c8()
    assert succes is True
    assert details["silent_agent_present_no_action"] is True
    assert details["silent_agent_cannot_act"] is True
    assert details["time_horizon_guard_downgrade"] is True
    assert details["ghost_metrics_neutralized"] is True


def test_verifier_critere_c9_et_c10():
    """AC8 & AC9 : Vérifie C9 (Quality Gate & anti-troncature) et C10 (Dossier d'Audit & SHA-256)."""
    succes, details = verifier_critere_c9_et_c10()
    assert succes is True
    assert details["section_guard_detects_truncation"] is True
    assert details["quality_gate_failed_validation"] is True
    assert details["audit_zip_all_files_present"] is True
    assert details["audit_zip_sha256_verified"] is True


def test_verifier_critere_c11_multi_domaines():
    """AC10 : Vérifie C11 (Épreuve multi-domaines sur les 3 fixtures)."""
    domaines = charger_fixtures_domaines()
    succes, details = verifier_critere_c11_multi_domaines(domaines)
    assert succes is True
    assert details["domains_tested"] == 3
    assert details["all_domains_passed"] is True
    assert details["domain_results"]["keova"]["verdict"] == "PASS"
    assert details["domain_results"]["public_policy"]["verdict"] == "PASS"
    assert details["domain_results"]["telecom"]["verdict"] == "PASS"


def test_verifier_critere_c11_echec_sur_domaine_incomplet():
    """AC10 : Vérifie qu'un nombre insuffisant de domaines fait échouer C11."""
    succes, details = verifier_critere_c11_multi_domaines({"keova": {}})
    assert succes is False
    assert details["all_domains_passed"] is False


def test_generer_rapport_qualification(tmp_path):
    """AC11 : Vérifie la génération Markdown du rapport formel de qualification."""
    report_file = tmp_path / "rapport-qualification-test.md"
    resultats = {
        "verdict_global": True,
        "criteres": {f"C{i}": {"status": "PASS"} for i in range(1, 12)},
    }
    generer_rapport_qualification(resultats, report_file)
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "# Rapport Formel de Qualification Globale — Epic 011" in content
    assert "VERDICT GO" in content
    assert "Tableau Récapitulatif des 11 Critères de Sortie" in content


def test_main_cli_execution(tmp_path, monkeypatch):
    """AC1 & AC12 : Vérifie le flux complet d'exécution CLI avec code retour 0."""
    out_file = tmp_path / "output_cli_report.md"
    test_args = [
        "verifier_qualification_epic_011.py",
        "--output",
        str(out_file),
        "--mock-llm",
    ]
    with patch("sys.argv", test_args):
        ret_code = main()
        assert ret_code == 0
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "VERDICT GO" in content


def test_main_cli_execution_single_domain(tmp_path):
    """Patch 1 & 4 : Vérifie l'exécution CLI ciblée sur un domaine unique (--domain keova)."""
    out_file = tmp_path / "output_single_domain.md"
    test_args = [
        "verifier_qualification_epic_011.py",
        "--domain",
        "keova",
        "--output",
        str(out_file),
        "--mock-llm",
    ]
    with patch("sys.argv", test_args):
        ret_code = main()
        assert ret_code == 0
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "VERDICT GO" in content
        assert "keova" in content


def test_main_cli_execution_verbose(tmp_path):
    """Patch 6 : Vérifie l'exécution CLI avec option --verbose."""
    out_file = tmp_path / "output_verbose.md"
    test_args = [
        "verifier_qualification_epic_011.py",
        "--output",
        str(out_file),
        "--mock-llm",
        "--verbose",
    ]
    with patch("sys.argv", test_args):
        ret_code = main()
        assert ret_code == 0
        assert out_file.exists()


def test_verifier_critere_c1_state_cleanup_on_error():
    """Patch 3 : Vérifie que SimulationRunner._run_states est nettoyé même si une erreur survient."""
    from app.services.simulation_runner import SimulationRunner

    with patch.object(SimulationRunner, "close_simulation_environment", side_effect=RuntimeError("Erreur simulée dans C1")):
        with pytest.raises(RuntimeError, match="Erreur simulée dans C1"):
            verifier_critere_c1(mock_llm=True)

    # Vérifie qu'aucun état orphelin 'sim_test_c1_lifecycle' n'a persisté
    assert "sim_test_c1_lifecycle" not in SimulationRunner._run_states
    assert "sim_test_c1_lifecycle" not in SimulationRunner._processes




def test_verifier_critere_c11_single_domain_expected_count():
    """Patch 1 : Vérifie verifier_critere_c11_multi_domaines avec expected_count=1."""
    domaines = {"keova": charger_fixtures_domaines()["keova"]}
    succes, details = verifier_critere_c11_multi_domaines(domaines, expected_count=1)
    assert succes is True
    assert details["domains_tested"] == 1
    assert details["all_domains_passed"] is True

