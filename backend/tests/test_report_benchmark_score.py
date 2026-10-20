"""Tests hermétiques du moteur de score du banc de benchmark (Story 013-6).

Couvre :
  - AC5 : grille fermée, versionnée, sans champ interprétatif.
  - AC6 : un dénominateur nul est un échec de couverture, jamais 100 %.
  - AC7 : verdict de comparabilité et son motif en toutes lettres.
  - AC8 : une métrique absente vaut ``None`` (« indisponible »), jamais 0.

Aucun test n'ouvre de fichier du dépôt en écriture, n'appelle le réseau ni un
modèle : le moteur de score est une fonction pure sur des dictionnaires.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils.report_benchmark_score import (
    ACTION_CLAIM_KIND,
    COMPARABILITY_RULE,
    COVERAGE_STATUS_ECHEC,
    COVERAGE_STATUS_INDISPONIBLE,
    COVERAGE_STATUS_MESUREE,
    SCORE_GRID_METRICS,
    SCORE_GRID_VERSION,
    VERDICT_CONTROLEE,
    VERDICT_NON_CONTROLEE,
    evaluate_comparability,
    format_metric_value,
    grid_metric_names,
    metric_difference,
    score_report_artifacts,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "qualification_epic_012" / "r6_bundle"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _artefacts_minimaux() -> dict:
    """Jeu d'artefacts minimal mais complet, fabriqué dans le test."""
    return {
        "report_claims": {
            "simulation_id": "sim_test",
            "claims": [
                {
                    "claim_id": "clm_1",
                    "text": "Une action observée",
                    "claim_kind": ACTION_CLAIM_KIND,
                    "verification_status": "VERIFIED",
                },
                {
                    "claim_id": "clm_2",
                    "text": "Une intention non prouvée",
                    "claim_kind": "REPORTED_INTENTION",
                    "verification_status": "UNSUPPORTED",
                },
                {
                    "claim_id": "clm_3",
                    "text": "Une déduction",
                    "claim_kind": "ANALYST_INFERENCE",
                    "verification_status": "CONTRADICTED",
                },
            ],
        },
        "quality_checks": {
            "total_checks": 5,
            "passed_checks": 3,
            "warning_checks": 2,
            "failed_checks": 0,
            "publication_status": "needs_review",
            "is_publishable": False,
        },
        "cohort_coverage": {
            "total_members": 18,
            "active_members": 17,
            "silent_members": 1,
            "adoption_rate": 0.0,
        },
        "usage": {
            "calls_count": 12,
            "prompt_tokens": 1000,
            "completion_tokens": 2000,
            "thinking_tokens": 300,
            "cached_tokens": 40,
            "total_tokens": 3000,
            "duration_seconds": 12.5,
            "wall_seconds": 30.25,
            "estimated_cost_usd": 0.0,
            "stop_reason": None,
            "stop_message": None,
            "calls": [
                {"call_index": 1, "finish_reason": "stop"},
                {"call_index": 2, "finish_reason": "length"},
                {"call_index": 3, "finish_reason": "stop"},
            ],
        },
        "full_report": "# Titre\n\nTexte.\n\n## Section\n\n```\n# pas un titre\n```\n",
    }


def _charger_fixture() -> dict:
    """Charge les artefacts réels du bundle R6 (lecture seule)."""
    return {
        "report_claims": json.loads(
            (FIXTURE_DIR / "report_claims.json").read_text(encoding="utf-8")
        ),
        "quality_checks": json.loads(
            (FIXTURE_DIR / "quality_checks.json").read_text(encoding="utf-8")
        ),
        "cohort_coverage": json.loads(
            (FIXTURE_DIR / "cohort_coverage.json").read_text(encoding="utf-8")
        ),
        "full_report": (FIXTURE_DIR / "report.md").read_text(encoding="utf-8"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# AC5 — grille fermée et versionnée
# ──────────────────────────────────────────────────────────────────────────────


def test_grille_expose_les_metriques_attendues():
    """La grille contient exactement les familles de métriques annoncées."""
    assert "claims_total" in SCORE_GRID_METRICS
    assert "claims_action_verification_rate" in SCORE_GRID_METRICS
    assert "quality_publication_status" in SCORE_GRID_METRICS
    assert "cohort_adoption_rate" in SCORE_GRID_METRICS
    assert "usage_estimated_cost_usd" in SCORE_GRID_METRICS
    assert "report_sections" in SCORE_GRID_METRICS
    assert len(SCORE_GRID_METRICS) == len(set(SCORE_GRID_METRICS))


def test_grille_est_stricte_fermee_et_sans_champ_interpretatif():
    """Le score ne publie rien hors grille, et aucun champ de classement."""
    score = score_report_artifacts(_artefacts_minimaux())
    assert set(score["metrics"]) == set(SCORE_GRID_METRICS)
    interdits = ("winner", "best", "gagnant", "rank", "classement", "score_total")
    for nom in score["metrics"]:
        assert not any(marqueur in nom.lower() for marqueur in interdits)


def test_version_de_grille_stable():
    """La version de grille est non vide et reportée dans le résultat."""
    assert isinstance(SCORE_GRID_VERSION, str) and SCORE_GRID_VERSION.strip()
    score = score_report_artifacts(_artefacts_minimaux())
    assert score["score_grid_version"] == SCORE_GRID_VERSION
    assert grid_metric_names() == SCORE_GRID_METRICS


# ──────────────────────────────────────────────────────────────────────────────
# Métriques par famille
# ──────────────────────────────────────────────────────────────────────────────


def test_metriques_de_claims_calculees_depuis_le_registre():
    """Les décomptes d'affirmations viennent de la liste du registre."""
    score = score_report_artifacts(_artefacts_minimaux())
    metriques = score["metrics"]
    assert metriques["claims_total"] == 3
    assert metriques["claims_verified"] == 1
    assert metriques["claims_unsupported"] == 1
    assert metriques["claims_contradicted"] == 1
    assert metriques["claims_action_total"] == 1
    assert metriques["claims_action_verified"] == 1
    assert metriques["claims_verification_ratio"] == pytest.approx(1 / 3, abs=1e-4)
    assert metriques["claims_action_verification_rate"] == pytest.approx(1.0)


def test_metriques_de_qualite_calculees_depuis_la_barriere():
    """Les compteurs de la barrière sont repris tels quels."""
    score = score_report_artifacts(_artefacts_minimaux())
    metriques = score["metrics"]
    assert metriques["quality_total_checks"] == 5
    assert metriques["quality_passed_checks"] == 3
    assert metriques["quality_warning_checks"] == 2
    assert metriques["quality_failed_checks"] == 0
    assert metriques["quality_publication_status"] == "needs_review"
    assert metriques["quality_is_publishable"] is False


def test_metriques_de_cohorte_calculees_depuis_la_table():
    """Les compteurs de cohorte sont repris tels quels."""
    score = score_report_artifacts(_artefacts_minimaux())
    metriques = score["metrics"]
    assert metriques["cohort_total_members"] == 18
    assert metriques["cohort_active_members"] == 17
    assert metriques["cohort_silent_members"] == 1
    assert metriques["cohort_adoption_rate"] == 0.0


def test_metriques_d_usage_calculees_depuis_la_telemetrie():
    """Les compteurs d'usage et les motifs de fin sont repris tels quels."""
    score = score_report_artifacts(_artefacts_minimaux())
    metriques = score["metrics"]
    assert metriques["usage_calls_count"] == 12
    assert metriques["usage_prompt_tokens"] == 1000
    assert metriques["usage_completion_tokens"] == 2000
    assert metriques["usage_thinking_tokens"] == 300
    assert metriques["usage_cached_tokens"] == 40
    assert metriques["usage_total_tokens"] == 3000
    assert metriques["usage_duration_seconds"] == pytest.approx(12.5)
    assert metriques["usage_wall_seconds"] == pytest.approx(30.25)
    assert metriques["usage_estimated_cost_usd"] == 0.0
    assert metriques["usage_finish_reasons"] == "stop, length"


def test_usage_indisponible_ne_publie_pas_de_zeros():
    """Sans objet d'usage fournisseur, les compteurs de tokens sont indisponibles."""
    artefacts = _artefacts_minimaux()
    artefacts["usage"] = {
        "usage_available": False,
        "calls_count": 7,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    score = score_report_artifacts(artefacts)
    metriques = score["metrics"]
    assert metriques["usage_prompt_tokens"] is None
    assert metriques["usage_completion_tokens"] is None
    assert metriques["usage_thinking_tokens"] is None
    assert metriques["usage_cached_tokens"] is None
    assert metriques["usage_total_tokens"] is None
    # Le nombre d'appels est un décompte réel : il reste disponible.
    assert metriques["usage_calls_count"] == 7


def test_cout_theorique_est_publie():
    """Le coût théorique (tarif fournisseur, hors gratuité de la passerelle) est publié."""
    artefacts = _artefacts_minimaux()
    artefacts["usage"]["theoretical_cost_usd"] = 0.7747425
    score = score_report_artifacts(artefacts)
    assert score["metrics"]["usage_theoretical_cost_usd"] == pytest.approx(0.7747425)
    # Le coût facturable reste distinct : une passerelle locale coûte 0 $.
    assert score["metrics"]["usage_estimated_cost_usd"] == 0.0


def test_taux_d_adoption_indefini_si_le_denominateur_est_nul():
    """Un dénominateur d'adoption nul donne un taux indéfini, pas 0 %."""
    artefacts = _artefacts_minimaux()
    artefacts["cohort_coverage"]["adoption_denominator"] = 0
    artefacts["cohort_coverage"]["adoption_rate"] = 0.0
    score = score_report_artifacts(artefacts)
    assert score["metrics"]["cohort_adoption_denominator"] == 0
    assert score["metrics"]["cohort_adoption_rate"] is None


def test_taux_d_adoption_publie_quand_le_denominateur_est_connu():
    """Un dénominateur connu et non nul publie le taux déclaré."""
    artefacts = _artefacts_minimaux()
    artefacts["cohort_coverage"]["adoption_denominator"] = 12
    score = score_report_artifacts(artefacts)
    assert score["metrics"]["cohort_adoption_denominator"] == 12
    assert score["metrics"]["cohort_adoption_rate"] == 0.0


def test_metriques_du_contenu_redige():
    """Le contenu rédigé est mesuré en caractères et en titres de section."""
    score = score_report_artifacts(_artefacts_minimaux())
    metriques = score["metrics"]
    assert metriques["report_characters"] == len(_artefacts_minimaux()["full_report"])
    # Le titre « # pas un titre » est dans un bloc de code : ce n'est pas une section.
    assert metriques["report_sections"] == 2


# ──────────────────────────────────────────────────────────────────────────────
# AC6 — dénominateur nul
# ──────────────────────────────────────────────────────────────────────────────


def test_denominateur_nul_vient_echec_de_couverture():
    """Zéro assertion d'action : taux ``None`` et échec de couverture."""
    artefacts = _artefacts_minimaux()
    artefacts["report_claims"]["claims"] = [
        {
            "claim_id": "clm_1",
            "text": "Une déduction",
            "claim_kind": "ANALYST_INFERENCE",
            "verification_status": "UNSUPPORTED",
        }
    ]
    score = score_report_artifacts(artefacts)
    assert score["metrics"]["claims_action_total"] == 0
    assert score["metrics"]["claims_action_verification_rate"] is None
    assert score["coverage_status"] == COVERAGE_STATUS_ECHEC


def test_taux_a_denominateur_nul_ne_vaut_jamais_cent_pour_cent():
    """Aucun taux à dénominateur nul ne devient 100 %."""
    artefacts = _artefacts_minimaux()
    artefacts["report_claims"]["claims"] = []
    score = score_report_artifacts(artefacts)
    assert score["metrics"]["claims_verification_ratio"] is None
    assert score["metrics"]["claims_action_verification_rate"] is None
    assert score["coverage_status"] == COVERAGE_STATUS_ECHEC


def test_couverture_mesuree_quand_le_denominateur_est_connu_et_positif():
    """Un dénominateur connu et non nul donne une couverture mesurée."""
    score = score_report_artifacts(_artefacts_minimaux())
    assert score["coverage_status"] == COVERAGE_STATUS_MESUREE


def test_couverture_indisponible_quand_le_registre_est_absent():
    """Sans registre d'affirmations, la couverture est indisponible."""
    score = score_report_artifacts({})
    assert score["coverage_status"] == COVERAGE_STATUS_INDISPONIBLE


# ──────────────────────────────────────────────────────────────────────────────
# AC8 — honnêteté de la sortie
# ──────────────────────────────────────────────────────────────────────────────


def test_metrique_absente_vaut_null_et_non_zero():
    """Un artefact absent donne des métriques indisponibles, jamais des zéros."""
    score = score_report_artifacts({})
    for nom in SCORE_GRID_METRICS:
        assert score["metrics"][nom] is None, nom
    assert "report_claims" in score["artefacts_absents"]
    assert "usage" in score["artefacts_absents"]
    assert "full_report" in score["artefacts_absents"]


def test_artefact_illisible_est_traite_comme_absent():
    """Un artefact qui n'est pas un dictionnaire ne casse pas le score."""
    score = score_report_artifacts({"report_claims": "pas un dictionnaire"})
    assert score["metrics"]["claims_total"] is None
    assert "report_claims" in score["artefacts_absents"]


def test_registre_sans_liste_declare_le_denominateur_inconnu():
    """Un registre sans liste d'affirmations ne permet pas de conclure sur la couverture."""
    score = score_report_artifacts(
        {"report_claims": {"total_claims": 12, "verified_claims": 3, "verification_ratio": 0.25}}
    )
    assert score["metrics"]["claims_total"] == 12
    assert score["metrics"]["claims_verification_ratio"] == pytest.approx(0.25)
    assert score["metrics"]["claims_action_total"] is None
    assert score["coverage_status"] == COVERAGE_STATUS_INDISPONIBLE


def test_formatage_des_metriques_absentes():
    """``None`` s'affiche « indisponible », jamais 0 ni chaîne vide."""
    assert format_metric_value(None) == "indisponible"
    assert format_metric_value(0) == "0"
    assert format_metric_value(0.5) == "0.5"
    assert format_metric_value(True) == "oui"
    assert format_metric_value(False) == "non"


def test_ecart_brut_ignore_une_donnee_absente():
    """L'écart brut est ``None`` si l'une des deux valeurs manque."""
    assert metric_difference(10, 4) == -6
    assert metric_difference(None, 4) is None
    assert metric_difference(10, None) is None


# ──────────────────────────────────────────────────────────────────────────────
# AC7 — comparabilité
# ──────────────────────────────────────────────────────────────────────────────


def test_verdict_de_comparabilite_et_son_motif():
    """Empreinte identique : comparaison contrôlée, motif en toutes lettres."""
    empreinte = "a" * 64
    verdict = evaluate_comparability(
        {"sha256": empreinte, "snapshot_id": "snap_1"},
        {"sha256": empreinte, "snapshot_id": "snap_2"},
    )
    assert verdict["verdict"] == VERDICT_CONTROLEE
    assert verdict["preuve_identite"] == "sha256"
    assert verdict["motif"]
    assert verdict["regle"] == COMPARABILITY_RULE


def test_empreintes_divergentes_donnent_un_verdict_non_controle():
    """Empreintes différentes : comparaison non contrôlée, avec le motif."""
    verdict = evaluate_comparability(
        {"sha256": "a" * 64, "snapshot_id": "snap_1"},
        {"sha256": "b" * 64, "snapshot_id": "snap_2"},
    )
    assert verdict["verdict"] == VERDICT_NON_CONTROLEE
    assert "SHA-256" in verdict["motif"]
    assert verdict["preuve_identite"] is None


def test_comparabilite_replie_sur_identifiant_instantane():
    """Sans empreinte des deux côtés, l'identifiant d'instantané sert de repli."""
    verdict = evaluate_comparability(
        {"snapshot_id": "snap_1"},
        {"snapshot_id": "snap_1"},
    )
    assert verdict["verdict"] == VERDICT_CONTROLEE
    assert verdict["preuve_identite"] == "snapshot_id"


def test_absence_totale_d_empreinte_donne_un_verdict_non_controle():
    """Ni empreinte ni instantané : la comparaison n'est pas contrôlée."""
    verdict = evaluate_comparability({}, {})
    assert verdict["verdict"] == VERDICT_NON_CONTROLEE
    assert verdict["motif"]


def test_instantane_absent_d_un_cote_donne_un_verdict_non_controle():
    """Un rapport sans instantané ne peut pas être comparé (règle de l'IHM)."""
    verdict = evaluate_comparability(
        {"sha256": "a" * 64, "snapshot_id": "snap_1"},
        {"sha256": "a" * 64},
    )
    assert verdict["verdict"] == VERDICT_NON_CONTROLEE
    assert "instantané" in verdict["motif"]


def test_simulations_differentes_donnent_un_verdict_non_controle():
    """Deux rapports sur deux simulations ne sont pas comparables (règle de l'IHM)."""
    verdict = evaluate_comparability(
        {"sha256": "a" * 64, "snapshot_id": "snap_1", "simulation_id": "sim_1"},
        {"sha256": "a" * 64, "snapshot_id": "snap_2", "simulation_id": "sim_2"},
    )
    assert verdict["verdict"] == VERDICT_NON_CONTROLEE
    assert "simulation" in verdict["motif"]


def test_empreinte_partielle_avec_instantane_different_donne_non_controle():
    """Une empreinte d'un seul côté ne suffit pas à conclure."""
    verdict = evaluate_comparability(
        {"sha256": "a" * 64, "snapshot_id": "snap_1"},
        {"snapshot_id": "snap_2"},
    )
    assert verdict["verdict"] == VERDICT_NON_CONTROLEE


# ──────────────────────────────────────────────────────────────────────────────
# Fixture réelle R6
# ──────────────────────────────────────────────────────────────────────────────


def test_score_sur_la_fixture_reelle_r6():
    """Le score du bundle R6 réel est cohérent avec ses artefacts."""
    score = score_report_artifacts(_charger_fixture())
    metriques = score["metrics"]
    assert metriques["claims_total"] == 258
    assert metriques["claims_verified"] == 0
    assert metriques["claims_unsupported"] == 241
    assert metriques["claims_contradicted"] == 17
    assert metriques["claims_verification_ratio"] == 0.0
    # Le bundle R6 ne contient aucune assertion d'action : la couverture est
    # donc en échec, et le taux d'action reste indisponible.
    assert metriques["claims_action_total"] == 0
    assert metriques["claims_action_verification_rate"] is None
    assert score["coverage_status"] == COVERAGE_STATUS_ECHEC
    # La fixture ne porte pas de télémétrie d'usage : elle est indisponible.
    assert metriques["usage_calls_count"] is None
    assert "usage" in score["artefacts_absents"]


def test_fixture_reelle_ne_contient_aucune_fuite_de_secret():
    """Les artefacts scorable ne contiennent ni clé ni jeton (NFR-4)."""
    artefacts = _charger_fixture()
    charge = json.dumps(artefacts, ensure_ascii=False)
    for motif in ("sk-", "ghp_", "bearer ", "api_key", "password"):
        assert motif not in charge.lower()
