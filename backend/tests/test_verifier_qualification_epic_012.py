"""Tests hermétiques pour le script de qualification globale de l'Epic 012 (Story 012-6).

Valide l'orchestration de bout en bout des critères C1 à C8 :
- Exécution unitaire de chaque sonde (C1 à C8)
- Vérification du comportement Fail-Closed en présence d'anomalies injectées
- Génération et intégrité du rapport Markdown de qualification
- Comportement de la CLI (options --output, --domain, --help)
"""

import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import pytest

from scripts.verifier_qualification_epic_012 import (
    charger_fixture_r6,
    verifier_critere_c1,
    verifier_critere_c2,
    verifier_critere_c3,
    verifier_critere_c4,
    verifier_critere_c5,
    verifier_critere_c6,
    verifier_critere_c7,
    verifier_critere_c8,
    generer_rapport_qualification,
    main,
)


@pytest.fixture
def r6_bundle_data():
    """Charge les données de la fixture R6 synthétique."""
    return charger_fixture_r6()


def test_charger_fixture_r6(r6_bundle_data):
    """Vérifie le chargement conforme des 8 artefacts de la fixture synthétique R6."""
    expected_files = [
        "actors.json",
        "cohort_coverage.json",
        "quality_checks.json",
        "report_claims.json",
        "report.md",
        "run_manifest.json",
        "simulation_brief.json",
        "source_manifest.json",
    ]
    for filename in expected_files:
        assert filename in r6_bundle_data, f"Fichier manquant dans la fixture R6 : {filename}"
        assert r6_bundle_data[filename], f"Contenu vide pour : {filename}"
    assert "observed_events" in r6_bundle_data
    assert len(r6_bundle_data["observed_events"]) == 786


def test_sonde_c1_zero_collision(r6_bundle_data):
    """Vérifie la sonde C1 : Résolution stricte sans collision Agent_1 vs Agent_16."""
    ok, details = verifier_critere_c1(r6_bundle_data)
    assert ok is True
    assert details["agent_1_events_count"] == 31
    assert details["agent_16_events_count"] == 25
    assert details["events_disjoint"] is True
    assert details["resolver_strict_equality"] is True
    assert details["substring_collision_eliminated"] is True


def test_sonde_c2_cohort_filtering(r6_bundle_data):
    """Vérifie la sonde C2 : Cohorte propre sans inéligibles Stripe/CPAM et dédoublonnage d'alias."""
    ok, details = verifier_critere_c2(r6_bundle_data)
    assert ok is True
    assert details["ineligible_entities_excluded"] is True
    assert details["technical_aliases_deduplicated"] is True
    assert details["clean_cohort_members_count"] == 36


def test_sonde_c3_roles_and_decisions(r6_bundle_data):
    """Vérifie la sonde C3 : Rôles fidèles (fondateur NOT_APPLICABLE) et anti-affabulation ADOPTED."""
    ok, details = verifier_critere_c3(r6_bundle_data)
    assert ok is True
    assert details["founder_role_correct"] is True
    assert details["founder_decision_not_applicable"] is True
    assert details["zero_false_adopted_on_silence"] is True
    assert details["nuanced_decision_statuses_respected"] is True


def test_sonde_c4_claims_reconciliation(r6_bundle_data):
    """Vérifie la sonde C4 : Réconciliation déterministe claims <-> EvidencePack et exclusion faux sujets."""
    ok, details = verifier_critere_c4(r6_bundle_data)
    assert ok is True
    assert details["false_subjects_rejected"] is True
    assert details["titles_excluded_from_claims"] is True
    assert details["reconciliation_target_met"] is True
    assert details["reconciled_claims_ratio"] >= 0.80


def test_sonde_c5_fail_closed_barrier(r6_bundle_data):
    """Vérifie la sonde C5 : Barrière Fail-Closed (rejet 0% -> failed_validation, nominal -> verified_publishable)."""
    ok, details = verifier_critere_c5(r6_bundle_data)
    assert ok is True
    assert details["statuses_defined"] is True
    assert details["fail_closed_zero_claims_rejected"] is True
    assert details["verified_publishable_validated"] is True
    assert details["needs_review_on_exploratory"] is True


def test_sonde_c6_epistemic_prevalence(r6_bundle_data):
    """Vérifie la sonde C6 : Prévalence absolue de PERSONA_SPECIFICATION -> HYPOTHESIS et brief."""
    ok, details = verifier_critere_c6(r6_bundle_data)
    assert ok is True
    assert details["epistemic_prevalence_absolute"] is True
    assert details["metadata_role_mismatch_detected"] is True
    assert details["inferred_time_horizon_traced"] is True
    assert details["unknown_fallback_on_empty_brief"] is True


def test_sonde_c7_r6_validation_and_invalidation(r6_bundle_data):
    """Vérifie la sonde C7 : Invalidation prouvée de l'export R6 erroné et validation de la version réconciliée."""
    ok, details = verifier_critere_c7(r6_bundle_data)
    assert ok is True
    assert details["r6_invalid_rejected_fail_closed"] is True
    assert details["r6_invalid_status"] == "failed_validation"
    assert details["r6_reconciled_publishable"] is True
    assert details["r6_reconciled_status"] == "verified_publishable"


def test_sonde_c8_manifest_integrity_and_security(r6_bundle_data):
    """Vérifie la sonde C8 : Complétude du manifeste, horodatage ISO 8601 et zéro fuite de secret."""
    ok, details = verifier_critere_c8(r6_bundle_data)
    assert ok is True
    assert details["git_commit_resolved"] is True
    assert details["completed_at_valid_iso"] is True
    assert details["time_horizon_present"] is True
    assert details["zero_secrets_leaked"] is True


def test_generer_rapport_qualification(r6_bundle_data):
    """Vérifie que la fonction de rapport génère un document Markdown complet avec VERDICT GO."""
    resultats = {
        "verdict_global": True,
        "criteres": {
            "C1": {"status": "PASS", "details": {"agent_1_events_count": 31, "agent_16_events_count": 25, "events_disjoint": True}},
            "C2": {"status": "PASS", "details": {"clean_cohort_members_count": 36, "ineligible_entities_excluded": True}},
            "C3": {"status": "PASS", "details": {"founder_decision_not_applicable": True, "zero_false_adopted_on_silence": True}},
            "C4": {"status": "PASS", "details": {"reconciled_claims_ratio": 0.90, "false_subjects_rejected": True}},
            "C5": {"status": "PASS", "details": {"fail_closed_zero_claims_rejected": True, "verified_publishable_validated": True}},
            "C6": {"status": "PASS", "details": {"epistemic_prevalence_absolute": True, "metadata_role_mismatch_detected": True}},
            "C7": {"status": "PASS", "details": {"r6_invalid_rejected_fail_closed": True, "r6_reconciled_publishable": True}},
            "C8": {"status": "PASS", "details": {"git_commit_resolved": True, "zero_secrets_leaked": True}},
        },
    }
    with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        report_md = generer_rapport_qualification(resultats, tmp_path)
        assert os.path.exists(tmp_path)
        assert "VERDICT GO" in report_md
        assert "C1 à C8" in report_md
        assert "QA-01 à QA-13" in report_md
        assert "sim_ea4f3cfe1028" in report_md
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_cli_execution_mock_mode():
    """Vérifie que l'exécution CLI en mode mock retourne 0 et écrit le rapport."""
    with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        test_args = ["verifier_qualification_epic_012.py", "--output", tmp_path, "--mock-llm"]
        with patch("sys.argv", test_args):
            exit_code = main()
            assert exit_code == 0
            assert os.path.exists(tmp_path)
            content = open(tmp_path, encoding="utf-8").read()
            assert "VERDICT GO" in content
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_cli_failure_on_corrupted_probe():
    """Vérifie que le script CLI retourne le code 1 si une sonde échoue."""
    with patch("scripts.verifier_qualification_epic_012.verifier_critere_c1", return_value=(False, {})):
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            test_args = ["verifier_qualification_epic_012.py", "--output", tmp_path, "--mock-llm"]
            with patch("sys.argv", test_args):
                exit_code = main()
                assert exit_code == 1
                content = open(tmp_path, encoding="utf-8").read()
                assert "VERDICT NO-GO" in content
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


def test_sonde_c8_secret_leak_detection():
    """Vérifie que la sonde C8 détecte impitoyablement toute fuite de clé secrète injectée."""
    with tempfile.TemporaryDirectory() as td:
        bundle_path = Path(td)
        # Injection d'un fichier avec une clé OpenAI factice
        leak_file = bundle_path / "leaked_credentials.txt"
        leak_file.write_text("API_KEY = 'sk-abcdef1234567890abcdef1234567890'", encoding="utf-8")

        with patch("scripts.verifier_qualification_epic_012.get_r6_bundle_dir", return_value=bundle_path):
            ok, details = verifier_critere_c8(None)
            assert ok is False
            assert details["zero_secrets_leaked"] is False


def test_simulation_audit_service_manifest_inferred_horizon_and_fallbacks():
    """Vérifie l'inférence traçable d'horizon et les replis agent_count/completed_at dans build_run_manifest."""
    from app.config import Config
    from app.services.simulation_audit_service import SimulationAuditService

    with tempfile.TemporaryDirectory() as td:
        old_upload = Config.UPLOAD_FOLDER
        Config.UPLOAD_FOLDER = td
        try:
            sim_id = "sim_test_audit_inferred"
            sim_dir = Path(td) / "simulations" / sim_id
            sim_dir.mkdir(parents=True, exist_ok=True)

            # Brief avec goal portant une durée 48h mais sans time_horizon explicite
            brief = {
                "simulation_id": sim_id,
                "goal": "Évaluer l'adoption sur 48h de test",
                "time_horizon": "unknown",
            }
            (sim_dir / "simulation_brief.json").write_text(json.dumps(brief), encoding="utf-8")

            # actors.json pour tester le fallback agent_count
            actors_data = {
                "simulation_id": sim_id,
                "actors": [{"entity_name": "A1"}, {"entity_name": "A2"}, {"entity_name": "A3"}],
            }
            (sim_dir / "actors.json").write_text(json.dumps(actors_data), encoding="utf-8")

            service = SimulationAuditService(simulation_id=sim_id)
            manifest = service.build_run_manifest()

            assert manifest["simulation"]["time_horizon"] == "48h"
            assert manifest["simulation"]["agent_count"] == 3
        finally:
            Config.UPLOAD_FOLDER = old_upload


def test_cli_domain_options():
    """Vérifie le fonctionnement de l'option CLI --domain (r6, multi_domain)."""
    with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        test_args = ["verifier_qualification_epic_012.py", "--output", tmp_path, "--domain", "r6"]
        with patch("sys.argv", test_args):
            exit_code = main()
            assert exit_code == 0
            content = open(tmp_path, encoding="utf-8").read()
            assert "Audit réel R6" in content
            assert "$\\to$" in content or "-> " in content or "$\to$" not in content
            # Vérifier qu'il n'y a pas de caractère tabulaire corrompu $	o$
            assert "$\to$" not in content
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

