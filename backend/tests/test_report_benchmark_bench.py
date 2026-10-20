"""Tests hermétiques du banc de benchmark A/B (Story 013-6).

Couvre :
  - AC1 : refus du banc quand les preuves figées manquent, sans créer de rapport.
  - AC2 : ``--dry-run`` sans génération, et refus d'un backend de graphe inattendu.
  - AC3 : exclusion d'une variante à empreinte divergente ou à graphe modifié.
  - AC4 : deux variantes, deux dossiers complets, aucun écrasement.
  - AC9 : le rapport ne désigne aucun gagnant.
  - AC10 : matériel de revue aveugle écrit, correspondance dans un fichier distinct.
  - AC11 : arrêt contrôlé sur plafond, sans escalade de modèle.

Aucun test n'appelle le réseau ni un modèle : les quatre dépendances externes
du banc (empreinte, état du graphe, préconditions, génération) sont injectées.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from app.config import Config
from app.models.report_llm_profile import ReportLLMProfile
from app.services.evidence_snapshot_service import ReplayNotReproducibleError
from scripts import verifier_benchmark_epic_013 as banc
from scripts.verifier_benchmark_epic_013 import (
    ARTEFACTS_ATTENDUS,
    MARQUEURS_INTERDITS,
    VERDICT_CONTROLEE,
    VERDICT_NON_CONCLUANT_EXCLUSION,
    VERDICT_NON_CONCLUANT_PREUVES,
    ConfigurationCampagne,
    ecrire_materiel_aveugle,
    executer_campagne,
    ecrire_rapport_qualification,
)

EMPREINTE_SAINTE = "a" * 64
EMPREINTE_DIVERGENTE = "b" * 64
GRAPHE_SAIN = {"graph_id": "graphe_test", "nodes": 10, "edges": 12}
GRAPHE_CHANGE = {"graph_id": "graphe_test", "nodes": 11, "edges": 12}


# ──────────────────────────────────────────────────────────────────────────────
# Doubles de test
# ──────────────────────────────────────────────────────────────────────────────


class EtatFaux:
    """État partagé par les doubles : empreinte courante, état du graphe, journal."""

    def __init__(self) -> None:
        self.empreinte = EMPREINTE_SAINTE
        self.snapshot_id = "snap_faux_20260101"
        self.graph = dict(GRAPHE_SAIN)
        self.empreintes_par_appel: List[str] = []
        self.graphs_par_appel: List[Dict[str, Any]] = []
        self.appels_capture = 0
        self.appels_mesure = 0
        self.generations: List[Dict[str, Any]] = []

    def capture(self, simulation_id: str) -> Dict[str, Any]:
        self.appels_capture += 1
        if self.empreintes_par_appel:
            self.empreinte = self.empreintes_par_appel.pop(0)
        return {
            "snapshot_id": self.snapshot_id,
            "sha256_hash": self.empreinte,
            "total_events": 737,
            "total_actors": 41,
            "has_archived_interviews": False,
            "file_hashes": {},
        }

    def mesure(self, graph_id: str) -> Dict[str, Any]:
        self.appels_mesure += 1
        if self.graphs_par_appel:
            self.graph = self.graphs_par_appel.pop(0)
        return dict(self.graph)


class GenerateurFaux:
    """Générateur de rapport factice : écrit un dossier de rapport complet."""

    def __init__(
        self,
        etat: EtatFaux,
        stop_reason: Optional[str] = None,
        statut: str = "completed",
        avec_empreinte: bool = True,
        empreinte_stockee: Optional[str] = None,
        claims_corrompus: bool = False,
    ):
        self.etat = etat
        self.stop_reason = stop_reason
        self.statut = statut
        self.avec_empreinte = avec_empreinte
        self.empreinte_stockee = empreinte_stockee
        self.claims_corrompus = claims_corrompus

    def __call__(self, *, simulation_id, graph_id, simulation_requirement, locale,
                 profile, report_id, report_folder) -> Dict[str, Any]:
        self.etat.generations.append(
            {
                "report_id": report_id,
                "profile_id": profile.profile_id,
                "model": profile.model,
                "reasoning_effort": profile.reasoning_effort,
                "report_folder": report_folder,
            }
        )
        dossier = Path(report_folder)
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "full_report.md").write_text(
            f"# Rapport de la variante {profile.profile_id}\n\n"
            f"Effort retenu : {profile.reasoning_effort}.\n\n"
            "## Section\n\nTexte de la section.\n",
            encoding="utf-8",
        )
        snapshot = {}
        if self.avec_empreinte:
            snapshot = {
                "snapshot_id": self.etat.snapshot_id,
                "sha256_hash": (
                    self.etat.empreinte
                    if self.empreinte_stockee is None
                    else self.empreinte_stockee
                ),
            }
        (dossier / "meta.json").write_text(
            json.dumps(
                {
                    "report_id": report_id,
                    "simulation_id": simulation_id,
                    "graph_id": graph_id,
                    "status": self.statut,
                    "profile_id": profile.profile_id,
                    "replay_mode": "replay_frozen",
                    "evidence_snapshot": snapshot,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (dossier / "report_claims.json").write_text(
            '{"simulation_id": "sim_test", "claims": ['
            if self.claims_corrompus
            else json.dumps(
                {
                    "simulation_id": simulation_id,
                    "claims": [
                        {
                            "claim_id": "clm_1",
                            "text": "Une action observée",
                            "claim_kind": "OBSERVED_SOCIAL_ACTION",
                            "verification_status": "VERIFIED",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (dossier / "cohort_coverage.json").write_text(
            json.dumps(
                {
                    "simulation_id": simulation_id,
                    "total_members": 18,
                    "active_members": 17,
                    "silent_members": 1,
                    "adoption_rate": 0.0,
                    "adoption_denominator": 12,
                    "members": [
                        {
                            "persona_name": "Agent_1",
                            "scenario_role": "PROSPECT",
                            "decision_status": "REJECTED_EXPRESSED",
                        },
                        {
                            "persona_name": "Agent_2",
                            "scenario_role": "PROSPECT",
                            "decision_status": "ADOPTED_VERIFIED",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (dossier / "quality_checks.json").write_text(
            json.dumps(
                {
                    "simulation_id": simulation_id,
                    "report_id": report_id,
                    "total_checks": 5,
                    "passed_checks": 4,
                    "warning_checks": 1,
                    "failed_checks": 0,
                    "publication_status": "needs_review",
                    "is_publishable": False,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (dossier / "usage.json").write_text(
            json.dumps(
                {
                    "report_id": report_id,
                    "calls_count": 7,
                    "prompt_tokens": 100,
                    "completion_tokens": 200,
                    "thinking_tokens": 50,
                    "cached_tokens": 0,
                    "total_tokens": 300,
                    "duration_seconds": 12.0,
                    "wall_seconds": 20.0,
                    "estimated_cost_usd": 0.0,
                    "stop_reason": self.stop_reason,
                    "stop_message": (
                        "Plafond budgétaire atteint, arrêt contrôlé."
                        if self.stop_reason
                        else None
                    ),
                    "calls": [{"call_index": 1, "finish_reason": "stop"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (dossier / "run_manifest.json").write_text(
            json.dumps({"report_id": report_id, "simulation_id": simulation_id}),
            encoding="utf-8",
        )
        return {
            "report_id": report_id,
            "statut": self.statut,
            "erreur": None,
            "duree_secondes": 3.5,
            "report_folder": report_folder,
        }


def _generateur_qui_echoue(etat: EtatFaux, message: str = "échec simulé"):
    """Retourne un générateur qui lève : la variante ne produit aucun rapport."""

    def _generateur(**_kwargs):
        raise RuntimeError(message)

    return _generateur


def _preconditions_ok(_simulation_id: str):
    return True, {
        "simulation_id": _simulation_id,
        "simulation_trouvee": True,
        "projet_trouve": True,
        "project_id": "proj_test",
        "projet_statut": "graph_completed",
        "graph_id": "graphe_test",
        "graph_id_concordant": True,
        "simulation_requirement": True,
        "motif": None,
    }


class EtatSimule:
    """Faux état de simulation et faux projet, pour ne rien lire sur le disque."""

    class _State:
        project_id = "proj_test"
        graph_id = "graphe_test"
        locale = "fr"

    class _Projet:
        project_id = "proj_test"
        graph_id = "graphe_test"
        status = "graph_completed"
        simulation_requirement = "Exigence de simulation de test."

    @staticmethod
    def get_simulation(simulation_id):
        return EtatSimule._State()

    @staticmethod
    def get_project(project_id):
        return EtatSimule._Projet()


class _FauxSimulationManager:
    """Gestionnaire de simulation dont l'état peut être absent."""

    #: État simulé ; ``None`` pour une simulation inconnue.
    etat = None

    def get_simulation(self, simulation_id):
        return self.etat


class _FauxProjectManager:
    """Gestionnaire de projet dont le projet peut être absent."""

    #: Projet simulé ; ``None`` pour un projet absent.
    etat = None

    @staticmethod
    def get_project(project_id):
        return _FauxProjectManager.etat


@pytest.fixture()
def etat() -> EtatFaux:
    return EtatFaux()


@pytest.fixture()
def configuration(tmp_path, etat) -> ConfigurationCampagne:
    """Configuration de campagne entièrement injectée, sans réseau ni modèle."""
    return ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        repetitions=1,
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat),
        verifier_preconditions=_preconditions_ok,
    )


@pytest.fixture(autouse=True)
def _backend_graphite(monkeypatch):
    """Le banc exige le backend ``graphiti`` : on l'aligne sur le catalogue."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "graphiti", raising=False)


@pytest.fixture(autouse=True)
def _simulations_factices(monkeypatch):
    """Neutralise la lecture du disque pour l'état de simulation et le projet."""
    monkeypatch.setattr(banc, "SimulationManager", EtatSimule, raising=False)
    monkeypatch.setattr(banc, "ProjectManager", EtatSimule, raising=False)


# ──────────────────────────────────────────────────────────────────────────────
# AC1 — preuves insuffisantes
# ──────────────────────────────────────────────────────────────────────────────


def test_campagne_refusee_si_preuves_insuffisantes(tmp_path, monkeypatch, etat):
    """Des preuves figées manquantes arrêtent le banc avant toute génération."""
    racine_reports = Path(Config.UPLOAD_FOLDER) / "reports"

    def capture_echouante(simulation_id):
        raise ReplayNotReproducibleError(
            "REPLAY_NOT_REPRODUCIBLE: preuves obligatoires manquantes"
        )

    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        capture_empreinte=capture_echouante,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    assert payload["verdict"] == VERDICT_NON_CONCLUANT_PREUVES
    assert payload["variantes"] == []
    assert etat.generations == []
    assert not racine_reports.exists() or list(racine_reports.iterdir()) == []


def test_banc_refuse_un_backend_de_graphe_inattendu(configuration, monkeypatch):
    """Un backend de graphe inattendu fait refuser le banc."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud", raising=False)

    payload = executer_campagne(configuration)

    assert payload["verdict"] == VERDICT_NON_CONCLUANT_PREUVES
    assert "backend de graphe inattendu" in payload["motif_verdict"]
    assert payload["variantes"] == []


# ──────────────────────────────────────────────────────────────────────────────
# AC3 — exclusions
# ──────────────────────────────────────────────────────────────────────────────


def test_variante_exclue_si_empreinte_divergente(tmp_path, etat):
    """Une empreinte qui diverge pendant la campagne écarte la variante."""
    # Appel 1 : pré-contrôle. Appels 2 et 3 : recontrôle après chaque variante.
    etat.empreintes_par_appel = [EMPREINTE_SAINTE, EMPREINTE_DIVERGENTE]
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    premiere = payload["variantes"][0]
    assert premiere["exclue"] is True
    assert "divergé" in premiere["motif_exclusion"]
    assert payload["verdict"] == VERDICT_NON_CONCLUANT_EXCLUSION
    assert payload["comparabilite"]["verdict"] != VERDICT_CONTROLEE


def test_variante_exclue_si_le_graphe_a_change(tmp_path, etat):
    """Un graphe modifié pendant la campagne écarte la variante."""
    # Appel 1 : pré-contrôle. Appels 2 et 3 : mesure après chaque variante.
    etat.graphs_par_appel = [dict(GRAPHE_SAIN), dict(GRAPHE_CHANGE)]
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    premiere = payload["variantes"][0]
    assert premiere["exclue"] is True
    assert "graphe" in premiere["motif_exclusion"]
    assert premiere["graph_state"] == GRAPHE_CHANGE


# ──────────────────────────────────────────────────────────────────────────────
# AC4 — deux variantes, zéro écrasement
# ──────────────────────────────────────────────────────────────────────────────


def test_campagne_produit_deux_dossiers_complets_sans_ecrasement(tmp_path, configuration):
    """Chaque variante a son dossier complet, et le premier reste intact."""
    payload = executer_campagne(configuration)

    assert len(payload["variantes"]) == 2
    report_ids = [variante["report_id"] for variante in payload["variantes"]]
    assert len(set(report_ids)) == 2

    dossiers = []
    for variante in payload["variantes"]:
        dossier = Path(variante["report_folder"])
        dossiers.append(dossier)
        assert dossier.exists()
        for nom in ARTEFACTS_ATTENDUS:
            assert (dossier / nom).exists(), nom

    # Le dossier de la première variante est intact après la seconde.
    contenu_premier = (dossiers[0] / "full_report.md").read_text(encoding="utf-8")
    assert "flash-medium" in contenu_premier
    contenu_second = (dossiers[1] / "full_report.md").read_text(encoding="utf-8")
    assert "flash-high" in contenu_second
    assert (dossiers[0] / "full_report.md").read_text(encoding="utf-8") == contenu_premier


def test_campagne_controlee_publie_les_metriques_et_la_comparabilite(configuration):
    """Une campagne conforme publie la grille, la comparabilité et le verdict."""
    payload = executer_campagne(configuration)

    assert payload["verdict"] == VERDICT_CONTROLEE
    assert payload["comparabilite"]["preuve_identite"] == "sha256"
    assert payload["comparabilite"]["gauche_sha256"] == EMPREINTE_SAINTE
    for variante in payload["variantes"]:
        score = variante["score"]
        assert score["score_grid_version"]
        assert score["metrics"]["claims_total"] == 1
        assert score["metrics"]["claims_action_verification_rate"] == 1.0
        assert score["coverage_status"] == "mesurée"


def test_campagne_publie_l_empreinte_de_reference_et_l_etat_du_graphe(configuration):
    """La charge utile porte l'empreinte de référence et l'état du graphe."""
    payload = executer_campagne(configuration)

    assert payload["evidence"]["sha256_hash"] == EMPREINTE_SAINTE
    assert payload["evidence"]["total_events"] == 737
    assert payload["graph_state_reference"] == GRAPHE_SAIN


# ──────────────────────────────────────────────────────────────────────────────
# AC9 — aucun gagnant désigné
# ──────────────────────────────────────────────────────────────────────────────


def test_rapport_ne_designe_aucun_gagnant(tmp_path, configuration):
    """Le rapport produit ne contient aucun marqueur de désignation."""
    payload = executer_campagne(configuration)
    chemin = tmp_path / "rapport.md"

    markdown = ecrire_rapport_qualification(payload, chemin)

    assert chemin.exists()
    for marqueur in MARQUEURS_INTERDITS:
        assert marqueur not in markdown.lower(), marqueur


def test_rapport_declare_la_regle_de_comparabilite(tmp_path, configuration):
    """Le rapport énonce la règle appliquée et le verdict de comparabilité."""
    payload = executer_campagne(configuration)
    chemin = tmp_path / "rapport.md"

    markdown = ecrire_rapport_qualification(payload, chemin)

    assert "empreinte SHA-256" in markdown
    assert "identifiant d'instantané en repli" in markdown
    assert "Comparabilité" in markdown
    assert payload["score_grid_version"] in markdown
    # L'empreinte de référence et l'état du graphe sont publiés.
    assert EMPREINTE_SAINTE in markdown
    assert str(GRAPHE_SAIN["nodes"]) in markdown


# ──────────────────────────────────────────────────────────────────────────────
# AC10 — matériel de revue aveugle
# ──────────────────────────────────────────────────────────────────────────────


def test_materiel_aveugle_ecrit_avec_correspondance_separee(tmp_path, configuration):
    """La paire anonymisée, la grille et la correspondance sont écrits séparément."""
    payload = executer_campagne(configuration)
    dossier = tmp_path / "campagne"

    correspondance = ecrire_materiel_aveugle(dossier, payload, payload["variantes"])

    assert (dossier / "variante-A.md").exists()
    assert (dossier / "variante-B.md").exists()
    assert (dossier / "grille-aveugle.md").exists()
    assert (dossier / "correspondance.json").exists()
    assert (dossier / "grille-aveugle.md") != (dossier / "correspondance.json")

    grille = (dossier / "grille-aveugle.md").read_text(encoding="utf-8")
    assert "correspondance.json" in grille
    assert "Remplir" in grille

    charge = json.loads((dossier / "correspondance.json").read_text(encoding="utf-8"))
    assert charge["variantes"]["A"]["profile_id"] == "flash-medium"
    assert charge["variantes"]["B"]["profile_id"] == "flash-high"
    assert "regle" in charge


def test_materiel_aveugle_signale_un_corps_qui_trahit_le_profil(tmp_path, configuration):
    """Un corps de rapport qui mentionne le modèle est déclaré déclassé."""
    payload = executer_campagne(configuration)
    dossier = tmp_path / "campagne"

    correspondance = ecrire_materiel_aveugle(dossier, payload, payload["variantes"])

    # Le double factice écrit le nom du profil dans le corps du rapport.
    assert correspondance["declassement"]["A"] is True
    assert correspondance["declassement"]["B"] is True


def test_declassement_ne_declenche_pas_sur_un_mot_quelconque(tmp_path, etat):
    """Un mot qui contient l'effort, sans mot-clé, ne déclasse pas une variante."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium",),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat),
        verifier_preconditions=_preconditions_ok,
    )
    payload = executer_campagne(configuration)
    dossier = tmp_path / "campagne"

    # Le corps contient des mots qui *contiennent* l'effort, sans mot-clé.
    for variante in payload["variantes"]:
        chemin = Path(variante["report_folder"]) / "full_report.md"
        chemin.write_text(
            "# Rapport\n\nUne analyse high-level du marché, medium-sized.\n",
            encoding="utf-8",
        )

    correspondance = ecrire_materiel_aveugle(dossier, payload, payload["variantes"])

    assert correspondance["declassement"]["A"] is False


# ──────────────────────────────────────────────────────────────────────────────
# AC11 — arrêt contrôlé sur plafond, sans escalade
# ──────────────────────────────────────────────────────────────────────────────


def test_campagne_arretee_sur_plafond_sans_escalade(tmp_path, etat):
    """Un arrêt contrôlé est reporté avec son code et son message, sans escalade."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium",),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat, stop_reason="budget_exceeded"),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    variante = payload["variantes"][0]
    assert variante["stop_reason"] == "budget_exceeded"
    assert "Plafond" in (variante["stop_message"] or "")
    # Aucune escalade : un seul profil demandé, une seule génération.
    assert payload["profils"] == ["flash-medium"]
    assert len(etat.generations) == 1
    assert len(payload["variantes"]) == 1


# ──────────────────────────────────────────────────────────────────────────────
# AC2 — rehearsal sans génération
# ──────────────────────────────────────────────────────────────────────────────


def test_dry_run_ne_genere_aucun_rapport(tmp_path, monkeypatch, etat, capsys):
    """Le mode rehearsal affiche le pré-contrôle et ne crée aucun rapport."""
    racine = tmp_path / "reports"
    racine.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path), raising=False)
    monkeypatch.setattr(banc, "capturer_empreinte", etat.capture, raising=False)
    monkeypatch.setattr(banc, "mesurer_graphe", etat.mesure, raising=False)
    monkeypatch.setattr(banc, "verifier_preconditions", _preconditions_ok, raising=False)
    monkeypatch.setattr(
        sys_argv := __import__("sys"), "argv",
        [
            "verifier_benchmark_epic_013.py",
            "--dry-run",
            "--simulation-id",
            "sim_test",
        ],
    )

    code = banc.main()

    assert code == 0
    sortie = capsys.readouterr().out
    assert EMPREINTE_SAINTE in sortie
    assert "flash-medium" in sortie
    assert list(racine.iterdir()) == []
    assert etat.generations == []


def test_code_retour_1_quand_le_backend_de_graphe_est_inattendu(monkeypatch, capsys):
    """Le banc refuse de s'exécuter sur un backend de graphe inattendu."""
    monkeypatch.setattr(Config, "ZEP_BACKEND", "cloud", raising=False)
    monkeypatch.setattr(
        __import__("sys"), "argv",
        ["verifier_benchmark_epic_013.py", "--dry-run", "--simulation-id", "sim_test"],
    )

    code = banc.main()

    assert code == 1
    assert "NON CONCLUANT" in capsys.readouterr().out


def test_code_retour_1_pour_un_profil_absent_du_catalogue(monkeypatch):
    """Un profil absent du catalogue est refusé avant toute génération."""
    monkeypatch.setattr(
        __import__("sys"), "argv",
        [
            "verifier_benchmark_epic_013.py",
            "--simulation-id",
            "sim_test",
            "--profiles",
            "profil-inexistant",
        ],
    )

    code = banc.main()

    assert code == 1


# ──────────────────────────────────────────────────────────────────────────────
# Correctifs issus de la revue BMAD du 20 octobre 2026
# ──────────────────────────────────────────────────────────────────────────────


def test_variante_exclue_si_le_rapport_n_est_pas_acheve(tmp_path, etat):
    """Un rapport interrompu (plafond, plantage) est écarté du comparatif."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat, statut="failed"),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    for variante in payload["variantes"]:
        assert variante["exclue"] is True
        assert "failed" in variante["motif_exclusion"]


def test_variante_refusee_par_la_barriere_reste_comparable(tmp_path, etat):
    """Un rapport complet refusé par la barrière reste comparable et publié.

    Le verdict de certification est une **mesure** du rapport, pas un défaut
    de la mesure : écarter la variante perdrait l'information la plus
    interesting du benchmark (revue BMAD du 20 octobre 2026).
    """
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat, statut="failed_validation"),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    for variante in payload["variantes"]:
        assert variante["exclue"] is False
        assert variante["certification_refusee"] is True
    assert payload["verdict"] == VERDICT_CONTROLEE

    markdown = banc.construire_rapport_qualification(payload)
    assert "certification **refusée**" in markdown
    assert "rapport est **complet**" in markdown


def test_variante_exclue_si_le_rapport_ne_porte_aucune_empreinte(tmp_path, etat):
    """Un rapport sans empreinte des preuves ne peut pas être comparé."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat, avec_empreinte=False),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    for variante in payload["variantes"]:
        assert variante["exclue"] is True
        assert "aucune empreinte" in variante["motif_exclusion"]


def test_variante_exclue_si_le_graphe_na_pas_pu_etre_mesure(tmp_path, etat):
    """Un échec de mesure du graphe n'est pas un changement du graphe."""
    etat.graphs_par_appel = []

    def mesure_en_echec(graph_id):
        etat.appels_mesure += 1
        if etat.appels_mesure > 1:
            raise RuntimeError("Neo4j injoignable")
        return dict(GRAPHE_SAIN)

    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        capture_empreinte=etat.capture,
        mesurer_graphe=mesure_en_echec,
        generer_variante=GenerateurFaux(etat),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    premiere = payload["variantes"][0]
    assert premiere["exclue"] is True
    assert "n'a pas pu être mesuré" in premiere["motif_exclusion"]
    assert "a changé" not in premiere["motif_exclusion"]


def test_cout_total_inconnu_quand_une_variante_a_echoue(tmp_path, etat):
    """Un coût total inconnu ne s'affiche jamais 0 $."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium",),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=_generateur_qui_echoue(etat),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    assert payload["cout_estime_usd_total"] is None
    markdown = banc.construire_rapport_qualification(payload)
    assert "indisponible" in markdown
    assert "0.0 $ (estimation" not in markdown


def test_rapport_annonce_un_etat_du_graphe_non_mesure(tmp_path, etat):
    """Aucune variante mesurée : le rapport ne dit pas « identique »."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium",),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=_generateur_qui_echoue(etat),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)
    markdown = banc.construire_rapport_qualification(payload)

    assert "non mesuré" in markdown
    assert "identique au pré-contrôle" not in markdown


def test_duree_inconnue_saffiche_indisponible(tmp_path, configuration):
    """Une durée absente ne s'affiche jamais « None s »."""
    payload = executer_campagne(configuration)
    for variante in payload["variantes"]:
        variante["duree_secondes"] = None

    markdown = banc.construire_rapport_qualification(payload)

    assert "None s" not in markdown
    assert "indisponible s" in markdown


def test_grille_de_revue_a_une_colonne_par_variante(tmp_path, etat):
    """Avec quatre variantes, la grille propose quatre colonnes de note."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        repetitions=2,
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat),
        verifier_preconditions=_preconditions_ok,
    )
    payload = executer_campagne(configuration)
    dossier = tmp_path / "campagne"

    ecrire_materiel_aveugle(dossier, payload, payload["variantes"])
    grille = (dossier / "grille-aveugle.md").read_text(encoding="utf-8")

    for lettre in ("A", "B", "C", "D"):
        assert f"Note {lettre}" in grille


def test_variante_ecartee_nest_pas_vendue_comme_comparable(tmp_path, etat):
    """Une variante écartée ne reçoit pas l'en-tête « mêmes preuves »."""
    etat.empreintes_par_appel = [EMPREINTE_SAINTE, EMPREINTE_DIVERGENTE]
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat),
        verifier_preconditions=_preconditions_ok,
    )
    payload = executer_campagne(configuration)
    dossier = tmp_path / "campagne"

    ecrire_materiel_aveugle(dossier, payload, payload["variantes"])

    for variante in payload["variantes"]:
        contenu = (dossier / f"variante-{variante['etiquette']}.md").read_text(
            encoding="utf-8"
        )
        if variante["exclue"]:
            assert "ÉCARTÉE DU COMPARATIF" in contenu
            assert "rapport produit sur le même jeu de preuves" not in contenu
        else:
            assert "rapport produit sur le même jeu de preuves" in contenu


def test_tableau_des_metriques_exclut_les_variantes_ecartees(tmp_path, etat):
    """Les mesures d'une variante écartée ne sont pas publiées comme un comparatif."""
    etat.empreintes_par_appel = [EMPREINTE_SAINTE, EMPREINTE_DIVERGENTE]
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat),
        verifier_preconditions=_preconditions_ok,
    )
    payload = executer_campagne(configuration)

    markdown = banc.construire_rapport_qualification(payload)

    assert "hors comparatif" in markdown
    assert "(écartée)" in markdown


def test_declassement_detecte_un_modele_reformule(tmp_path, etat):
    """Un nom de modèle reformulé est détecté après normalisation."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium",),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat),
        verifier_preconditions=_preconditions_ok,
    )
    payload = executer_campagne(configuration)
    dossier = tmp_path / "campagne"

    for variante in payload["variantes"]:
        chemin = Path(variante["report_folder"]) / "full_report.md"
        chemin.write_text(
            "# Rapport\n\nProduit par Gemini 3.8 Flash pour cette campagne.\n",
            encoding="utf-8",
        )

    correspondance = ecrire_materiel_aveugle(dossier, payload, payload["variantes"])

    assert correspondance["declassement"]["A"] is True


def test_declassement_croise_detecte_le_profil_d_une_autre_variante(tmp_path, etat):
    """Un corps qui nomme l'effort d'une autre variante compromet la paire."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat),
        verifier_preconditions=_preconditions_ok,
    )
    payload = executer_campagne(configuration)
    dossier = tmp_path / "campagne"

    for variante in payload["variantes"]:
        chemin = Path(variante["report_folder"]) / "full_report.md"
        if variante["profile_id"] == "flash-medium":
            chemin.write_text(
                "# Rapport\n\nNous avons utilisé un effort de raisonnement high.\n",
                encoding="utf-8",
            )
        else:
            chemin.write_text("# Rapport\n\nAucun élément compromettant.\n", encoding="utf-8")

    correspondance = ecrire_materiel_aveugle(dossier, payload, payload["variantes"])

    assert correspondance["declassement_croise"]["A"] == ["flash-high (effort)"]
    assert correspondance["declassement_croise"]["B"] == []


def test_rapport_non_conforme_n_est_pas_ecrit(tmp_path, monkeypatch, configuration, capsys):
    """Un rapport porteur d'un marqueur interdit n'est pas laissé sur le disque."""
    rapport = tmp_path / "rapport.md"
    dossier = tmp_path / "campagne"
    monkeypatch.setattr(banc, "capturer_empreinte", configuration.capture_empreinte)
    monkeypatch.setattr(banc, "mesurer_graphe", configuration.mesurer_graphe)
    monkeypatch.setattr(banc, "verifier_preconditions", configuration.verifier_preconditions)
    monkeypatch.setattr(banc, "generer_variante", configuration.generer_variante)
    monkeypatch.setattr(
        __import__("sys"), "argv",
        [
            "verifier_benchmark_epic_013.py",
            "--simulation-id",
            "sim_test",
            "--output",
            str(rapport),
            "--campaign-dir",
            str(dossier),
        ],
    )

    def rapport_avec_gagnant(payload, dossier_campagne=None):
        return "# Rapport\n\nLe meilleur modèle.\n"

    monkeypatch.setattr(banc, "construire_rapport_qualification", rapport_avec_gagnant)

    code = banc.main()

    assert code == 1
    assert not rapport.exists()
    assert not dossier.exists()
    assert "Rien n'a été écrit" in capsys.readouterr().out


def test_variante_relancee_apres_une_erreur_d_infrastructure(tmp_path, etat):
    """Une panne réseau est relancée une fois, et la relance est consignée."""
    etat.generations.clear()
    appels = {"n": 0}

    def generateur_instable(**kwargs):
        appels["n"] += 1
        if appels["n"] == 1:
            raise RuntimeError(
                "Error code: 502 - Upstream call failed: Remote end closed connection"
            )
        return GenerateurFaux(etat)(**kwargs)

    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium",),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=generateur_instable,
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    variante = payload["variantes"][0]
    assert variante["tentatives"] == 2
    assert variante["exclue"] is False
    assert len(variante["erreurs"]) == 1
    assert "502" in variante["erreurs"][0]


def test_variante_definitivement_en_echec_est_ecartee(tmp_path, etat):
    """Après la relance, un échec persistant écarte la variante avec son motif."""
    def generateur_toujours_en_echec(**_kwargs):
        raise RuntimeError("Error code: 502 - Upstream call failed")

    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium",),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=generateur_toujours_en_echec,
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    variante = payload["variantes"][0]
    assert variante["tentatives"] == 2
    assert variante["exclue"] is True
    assert "502" in variante["motif_exclusion"]


def test_le_motif_precis_ne_sert_pas_apres_une_erreur_de_generation(tmp_path, etat):
    """Un rapport interrompu conserve le motif de son statut, pas celui du dossier."""
    def generateur_partiel(**kwargs):
        # Simule un rapport interrompu : le dossier existe, sans full_report.md.
        dossier = Path(kwargs["report_folder"])
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "meta.json").write_text("{}", encoding="utf-8")
        return {
            "report_id": kwargs["report_id"],
            "statut": "failed",
            "erreur": "arrêt sur plafond",
            "duree_secondes": 1.0,
            "report_folder": kwargs["report_folder"],
        }

    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium",),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=generateur_partiel,
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    variante = payload["variantes"][0]
    assert variante["exclue"] is True
    assert "failed" in variante["motif_exclusion"]
    assert "dossier du rapport" not in variante["motif_exclusion"]


def test_le_rapport_est_deterministe_pour_une_charge_utile_donnee(tmp_path, configuration):
    """Deux rendus de la même charge utile donnent le même rapport.

    Le rapport est ainsi rejouable à partir du seul JSON versionné : c'est ce
    qui rend l'artefact vérifiable par un tiers.
    """
    payload = executer_campagne(configuration)

    premier = banc.construire_rapport_qualification(payload)
    second = banc.construire_rapport_qualification(payload)

    assert premier == second
    # L'horodatage vient de la charge utile, pas de l'horloge du rendu.
    assert payload["timestamp"][:10] in premier


def test_le_tableau_des_ecarts_est_un_tableau_valide(tmp_path, configuration):
    """Le tableau des écarts a autant de colonnes que le tableau des métriques."""
    payload = executer_campagne(configuration)

    markdown = banc.construire_rapport_qualification(payload)

    assert "**Écarts bruts**" in markdown
    section = markdown.split("**Écarts bruts**", 1)[1]
    for ligne in section.split("\n"):
        if ligne.startswith("| `"):
            assert ligne.count("|") == 3, ligne


# ──────────────────────────────────────────────────────────────────────────────
# Couverture des chemins réels (revue BMAD du 20 octobre 2026)
# ──────────────────────────────────────────────────────────────────────────────


def test_main_ecrit_les_quatre_livrables(tmp_path, monkeypatch, configuration):
    """Le chemin d'écriture de la CLI produit les quatre livrables de campagne."""
    rapport = tmp_path / "rapport.md"
    dossier = tmp_path / "campagne"
    monkeypatch.setattr(banc, "capturer_empreinte", configuration.capture_empreinte)
    monkeypatch.setattr(banc, "mesurer_graphe", configuration.mesurer_graphe)
    monkeypatch.setattr(banc, "verifier_preconditions", configuration.verifier_preconditions)
    monkeypatch.setattr(banc, "generer_variante", configuration.generer_variante)
    monkeypatch.setattr(
        __import__("sys"), "argv",
        [
            "verifier_benchmark_epic_013.py",
            "--simulation-id",
            "sim_test",
            "--output",
            str(rapport),
            "--campaign-dir",
            str(dossier),
        ],
    )

    code = banc.main()

    assert code == 0
    assert rapport.exists()
    for nom in (
        "mesure-benchmark-013.json",
        "variante-A.md",
        "variante-B.md",
        "grille-aveugle.md",
        "correspondance.json",
    ):
        assert (dossier / nom).exists(), nom


def test_main_ne_publie_pas_une_url_de_passerelle(tmp_path, monkeypatch, configuration):
    """La charge utile produite par la CLI est passée par la barrière d'étanchéité."""
    dossier = tmp_path / "campagne"
    monkeypatch.setattr(banc, "capturer_empreinte", configuration.capture_empreinte)
    monkeypatch.setattr(banc, "mesurer_graphe", configuration.mesurer_graphe)
    monkeypatch.setattr(banc, "verifier_preconditions", configuration.verifier_preconditions)
    monkeypatch.setattr(banc, "generer_variante", configuration.generer_variante)
    monkeypatch.setattr(
        __import__("sys"), "argv",
        [
            "verifier_benchmark_epic_013.py",
            "--simulation-id",
            "sim_test",
            "--output",
            str(tmp_path / "rapport.md"),
            "--campaign-dir",
            str(dossier),
        ],
    )

    code = banc.main()

    assert code == 0
    charge = (dossier / "mesure-benchmark-013.json").read_text(encoding="utf-8")
    assert "http://" not in charge
    assert "18081" not in charge


def test_preconditions_refusent_un_projet_non_acheve(monkeypatch):
    """Un projet qui n'est pas au statut GRAPH_COMPLETED fait refuser le banc."""
    monkeypatch.setattr(
        banc, "verifier_preconditions",
        lambda _simulation_id: (False, {"motif": "projet non achevé"}),
    )
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        capture_empreinte=lambda _sim: {"sha256_hash": EMPREINTE_SAINTE},
        mesurer_graphe=lambda _gid: dict(GRAPHE_SAIN),
        generer_variante=GenerateurFaux(EtatFaux()),
        verifier_preconditions=lambda _sim: (False, {"motif": "projet non achevé"}),
    )

    payload = executer_campagne(configuration)

    assert payload["verdict"] == VERDICT_NON_CONCLUANT_PREUVES
    assert "projet non achevé" in payload["motif_verdict"]


def test_verifier_preconditions_refuse_une_simulation_inconnue(monkeypatch):
    """Une simulation inconnue est refusée avec un motif explicite."""
    monkeypatch.setattr(banc, "SimulationManager", _FauxSimulationManager)
    monkeypatch.setattr(banc, "ProjectManager", _FauxProjectManager)
    monkeypatch.setattr(_FauxSimulationManager, "etat", None)

    conforme, details = banc.verifier_preconditions("sim_inconnue")

    assert conforme is False
    assert "introuvable" in details["motif"]


def test_verifier_preconditions_refuse_un_projet_absent(monkeypatch):
    """Un projet absent est refusé avec un motif explicite."""
    monkeypatch.setattr(banc, "SimulationManager", _FauxSimulationManager)
    monkeypatch.setattr(banc, "ProjectManager", _FauxProjectManager)
    monkeypatch.setattr(_FauxSimulationManager, "etat", EtatSimule._State())
    monkeypatch.setattr(_FauxProjectManager, "etat", None)

    conforme, details = banc.verifier_preconditions("sim_test")

    assert conforme is False
    assert "introuvable" in details["motif"]


def test_variante_exclue_si_empreinte_stockee_diverge(tmp_path, etat):
    """Une empreinte stockée différente de l'empreinte recontrôlée écarte la variante."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium", "flash-high"),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat, empreinte_stockee="c" * 64),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    for variante in payload["variantes"]:
        assert variante["exclue"] is True
        assert "stockée dans les artefacts" in variante["motif_exclusion"]


def test_artefact_corrompu_est_traite_comme_absent(tmp_path, etat):
    """Un artefact JSON tronqué ne fait pas planter la campagne."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium",),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat, claims_corrompus=True),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    metriques = payload["variantes"][0]["score"]["metrics"]
    assert metriques["claims_total"] is None
    assert payload["variantes"][0]["score"]["coverage_status"] == "indisponible"


def test_capture_empreinte_exige_des_preuves_strictes():
    """La capture de l'empreinte refuse une simulation sans preuve exploitable."""
    with pytest.raises(ReplayNotReproducibleError):
        banc.capturer_empreinte("sim_inexistante_au_banc")


def test_generer_variante_desarme_le_lecteur_de_graphe(monkeypatch, tmp_path):
    """Le lecteur de graphe est désarmé même si la génération échoue."""
    desarmements = []

    monkeypatch.setattr(banc, "register_graph_reader", lambda g, r: None)
    monkeypatch.setattr(
        banc, "unregister_graph_reader", lambda g, r: desarmements.append(r)
    )

    class _AgentQuiEchoue:
        def __init__(self, **_kwargs):
            pass

        def generate_report(self, report_id=None):
            raise RuntimeError("échec de génération")

    monkeypatch.setattr(banc, "ReportAgent", _AgentQuiEchoue)

    with pytest.raises(RuntimeError):
        banc.generer_variante(
            simulation_id="sim_test",
            graph_id="graphe_test",
            simulation_requirement="exigence",
            locale="fr",
            profile=None,
            report_id="report_test",
            report_folder=str(tmp_path),
        )

    assert desarmements == ["report_test"]


def test_configuration_campagne_refuse_une_simulation_vide():
    """Une simulation vide est refusée à la construction."""
    with pytest.raises(ValueError):
        ConfigurationCampagne(simulation_id="  ")


def test_configuration_campagne_refuse_zero_repetition():
    """Zéro répétition est refusé à la construction."""
    with pytest.raises(ValueError):
        ConfigurationCampagne(simulation_id="sim_test", repetitions=0)


def test_cli_refuse_zero_repetition(monkeypatch, capsys):
    """La CLI traduit une configuration invalide en refus lisible, sans traceback."""
    monkeypatch.setattr(
        __import__("sys"), "argv",
        [
            "verifier_benchmark_epic_013.py",
            "--simulation-id",
            "sim_test",
            "--repetitions",
            "0",
        ],
    )

    code = banc.main()

    assert code == 1
    assert "repetitions" in capsys.readouterr().out


def test_profils_de_reference_visent_le_couple_attendu():
    """Les profils par défaut sont bien le couple modèle/effort du critère C7."""
    medium = ReportLLMProfile.get_standard_profile("flash-medium")
    high = ReportLLMProfile.get_standard_profile("flash-high")
    assert medium is not None and high is not None
    assert medium.model == "gemini-3.8-flash"
    assert medium.reasoning_effort == "medium"
    assert high.model == "gemini-3.8-flash"
    assert high.reasoning_effort == "high"
    assert banc.PROFILS_C7_REFERENCE == ("flash-medium", "flash-high")


def test_message_erreur_long_est_tronque():
    """Un message d'erreur de fournisseur est tronqué avant écriture."""
    message = "A" * 5000 + " sk-secret http://passerelle.local/v1"
    description = banc._description_erreur(RuntimeError(message))
    assert description is not None
    assert len(description) < 300
    assert "sk-secret" not in description
    assert "passerelle.local" not in description


def test_arret_controle_affiche_son_code_et_son_message(tmp_path, etat):
    """Le rapport affiche le code et le message d'un arrêt contrôlé."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium",),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=GenerateurFaux(etat, stop_reason="budget_exceeded"),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)
    markdown = banc.construire_rapport_qualification(payload)

    assert "budget_exceeded" in markdown
    assert "Plafond budgétaire atteint" in markdown


def test_metriques_de_cohorte_exposent_le_denominateur(tmp_path, configuration):
    """Le dénominateur du taux d'adoption est publié par le modèle métier."""
    payload = executer_campagne(configuration)

    metriques = payload["variantes"][0]["score"]["metrics"]
    assert metriques["cohort_adoption_denominator"] == 12
    assert metriques["cohort_adoption_rate"] == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Intégrité du dépôt produit par le banc
# ──────────────────────────────────────────────────────────────────────────────


def test_artefacts_produits_ne_contiennent_aucun_secret(tmp_path, configuration):
    """Aucun secret ne figure dans la charge utile ni dans le rapport."""
    payload = executer_campagne(configuration)
    dossier = tmp_path / "campagne"
    dossier.mkdir(parents=True, exist_ok=True)
    ecrire_materiel_aveugle(dossier, payload, payload["variantes"])
    chemin = tmp_path / "rapport.md"
    ecrire_rapport_qualification(payload, chemin)

    charge = (dossier / "mesure-benchmark-013.json")
    charge.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    for fichier in sorted(dossier.iterdir()) + [chemin]:
        contenu = fichier.read_text(encoding="utf-8").lower()
        for motif in ("sk-", "ghp_", "bearer ", "api_key", "password", "authorization"):
            assert motif not in contenu, f"{fichier.name} : {motif}"


def test_artefacts_produits_ne_contiennent_aucune_url_de_passerelle(tmp_path, configuration):
    """Aucune URL de passerelle ne figure dans les artefacts produits."""
    payload = executer_campagne(configuration)
    dossier = tmp_path / "campagne"
    dossier.mkdir(parents=True, exist_ok=True)
    ecrire_materiel_aveugle(dossier, payload, payload["variantes"])
    chemin = tmp_path / "rapport.md"
    ecrire_rapport_qualification(payload, chemin)

    for fichier in sorted(dossier.iterdir()) + [chemin]:
        contenu = fichier.read_text(encoding="utf-8").lower()
        for motif in ("http://", "https://", "18081", "18080", "base_url", "endpoint"):
            assert motif not in contenu, f"{fichier.name} : {motif}"


def test_erreur_de_fournisseur_ne_divulgue_pas_son_url(tmp_path, etat):
    """Un message d'erreur de fournisseur est neutralisé avant écriture."""
    configuration = ConfigurationCampagne(
        simulation_id="sim_test",
        profils=("flash-medium",),
        capture_empreinte=etat.capture,
        mesurer_graphe=etat.mesure,
        generer_variante=_generateur_qui_echoue(
            etat, "RuntimeError: appel à http://host.docker.internal:18081/v1 refusé"
        ),
        verifier_preconditions=_preconditions_ok,
    )

    payload = executer_campagne(configuration)

    motif = payload["variantes"][0]["motif_exclusion"]
    assert "18081" not in motif
    assert "uri masquée" in motif
