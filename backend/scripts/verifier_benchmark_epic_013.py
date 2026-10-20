#!/usr/bin/env python3
"""Banc de benchmark contrôlé A/B du ReportAgent (Story 013-6, FR-10, C7).

Orchestre une campagne de comparaison contrôlée entre deux variantes de
rédaction du `ReportAgent` sur un **même jeu de preuves figées** :

  - pré-contrôle de l'empreinte SHA-256 des preuves (rejeu `replay_frozen`) ;
  - garde-fou de cohérence du graphe (le graphe n'est **pas** dans l'empreinte) ;
  - boucle de variantes, une par profil du catalogue et par répétition ;
  - relecture des artefacts produits et calcul d'une **grille de score fermée**
    et purement mécanique (`app/utils/report_benchmark_score.py`) ;
  - écriture d'une charge utile JSON, d'un rapport Markdown formel et du
    matériel de revue aveugle.

Invariants tenus par le banc :
  - il ne désigne jamais un modèle, un effort ou une variante comme gagnant ;
  - il ne corrige jamais le code vérificateur entre deux variantes ;
  - un dénominateur nul est un échec de couverture, jamais 100 % ;
  - une métrique absente vaut « indisponible », jamais 0 ;
  - aucun secret ne sort dans le rapport, le JSON ou la paire anonymisée.

Usage :
    cd backend && uv run python scripts/verifier_benchmark_epic_013.py \
        --dry-run --simulation-id sim_80a54d7bbd7b
    cd backend && uv run python scripts/verifier_benchmark_epic_013.py \
        --simulation-id sim_80a54d7bbd7b --profiles flash-medium,flash-high \
        --repetitions 1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# Configuration du PYTHONPATH et chargement de .env
_scripts_dir = Path(__file__).resolve().parent
_backend_dir = _scripts_dir.parent
_project_root = _backend_dir.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv

for _candidate in (_project_root / ".env", _backend_dir / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate)

from app.config import Config
from app.models.project import ProjectManager, ProjectStatus
from app.models.report_llm_profile import ReportLLMProfile
from app.models.report_usage import sanitize_usage_payload
from app.services.evidence_snapshot_service import (
    EvidenceSnapshotService,
    ReplayNotReproducibleError,
)
from app.services.report_agent import (
    ReportAgent,
    ReportManager,
    ReportStatus,
)
from app.services.simulation_manager import SimulationManager
from app.utils.graph_store.factory import get_graph_store, release_graph_store
from app.utils.report_benchmark_score import (
    COMPARABILITY_RULE,
    SCORE_GRID_METRICS,
    SCORE_GRID_VERSION,
    VERDICT_CONTROLEE,
    VERDICT_NON_CONTROLEE,
    evaluate_comparability,
    format_metric_value,
    metric_difference,
    score_report_artifacts,
)
from app.utils.zep_lifecycle import (
    graph_lifecycle_lock,
    register_graph_reader,
    unregister_graph_reader,
)

# ============================================================================
# Constantes de la campagne
# ============================================================================

#: Verdict de campagne : les preuves figées manquent ou sont vides.
VERDICT_NON_CONCLUANT_PREUVES = "non concluant — preuves insuffisantes"
#: Verdict de campagne : une variante a été écartée du comparatif.
VERDICT_NON_CONCLUANT_EXCLUSION = "non concluant — variante écartée"

#: Motifs de rejet du pré-contrôle d'environnement.
MOTIF_BACKEND_INATTENDU = "backend de graphe inattendu"

#: Étiquettes anonymes des variantes dans le matériel de revue aveugle.
LETTRES_VARIANTES = ("A", "B", "C", "D", "E", "F")

#: Marqueurs interdits dans le rapport de qualification : le rapport compare des
#: chiffres, il ne désigne jamais un modèle, un effort ou une variante comme
#: gagnant (AC9). La liste est testée par `test_rapport_ne_designe_aucun_gagnant`.
MARQUEURS_INTERDITS = (
    "gagnant",
    "gagnante",
    "vainqueur",
    "meilleur",
    "meilleure",
    "winner",
    "best",
    "supérieur",
    "superieure",
    "classement",
    "ranking",
    "recommandé",
    "recommandee",
    "recommandés",
    "recommandees",
    "palmarès",
    "palmares",
)

#: Fichiers d'artefacts attendus dans le dossier d'un rapport généré.
ARTEFACTS_ATTENDUS = (
    "meta.json",
    "full_report.md",
    "report_claims.json",
    "cohort_coverage.json",
    "quality_checks.json",
    "usage.json",
    "run_manifest.json",
)

#: Statuts de rapport qui signifient « la génération n'a pas abouti » : le
#: rapport est **partiel** (arrêt sur plafond, Plantage), donc il n'est pas
#: comparable à un rapport complet. La variante est écartée du comparatif
#: (revue BMAD du 20 octobre 2026).
STATUTS_GENERATION_INCOMPLETE = (ReportStatus.FAILED.value,)

#: Statut de rapport qui signifie « le rapport est complet, mais la barrière
#: de publication a refusé de le certifier ». Le rapport reste **comparable** :
#: le verdict de la barrière est une **mesure**, pas un défaut de mesure.
#: C'est un résultat que le banc doit publier, pas un motif d'exclusion.
STATUT_CERTIFICATION_REFUSEE = ReportStatus.FAILED_VALIDATION.value

#: Mode de rejeu de la campagne. La comparaison à preuves figées n'a de sens
#: qu'en `replay_frozen` : c'est une constante, pas une option (revue BMAD du
#: 20 octobre 2026 — un paramètre fantôme pouvait rendre le rapport faux).
MODE_REJEU = "replay_frozen"

#: Paire de profils de référence du critère de sortie C7 de l'Epic 013 :
#: `gemini-3.8-flash` en effort `medium` puis en effort `high`. Les
#: identifiants viennent du catalogue fermé (`ReportLLMProfile`), jamais d'une
#: liste écrite en dur dans le banc (NFR-1 de l'epic) : seul le *couple visé*
#: est nommé ici.
PROFILS_C7_REFERENCE = ("flash-medium", "flash-high")

#: Longueur maximale du message d'erreur retenu dans les artefacts produits.
#: Un message de fournisseur peut reprendre une URL de passerelle ou un
#: fragment de requête : on n'en garde que la tête, et le type d'exception.
LONGUEUR_MESSAGE_ERREUR = 200


def _description_erreur(erreur: Any) -> Optional[str]:
    """Décrit une erreur sans en divulguer le contenu brut.

    Le message d'une exception de fournisseur peut contenir une URL de
    passerelle, une URI de connexion porteuse d'identifiants, un extrait de
    requête ou un jeton. On ne conserve que le type de l'exception et la tête
    de son message, et on masque toute URI (revue BMAD du 20 octobre 2026).
    """
    if erreur is None:
        return None
    if isinstance(erreur, BaseException):
        prefixe = type(erreur).__name__
        message = str(erreur).strip()
    else:
        prefixe = "erreur"
        message = str(erreur).strip()
    if not message:
        return prefixe
    message = re.sub(r"[a-zA-Z][a-zA-Z0-9+.\-]*://\S+", "<uri masquée>", message)
    if len(message) > LONGUEUR_MESSAGE_ERREUR:
        message = message[:LONGUEUR_MESSAGE_ERREUR] + "…"
    return f"{prefixe}: {message}"


# ============================================================================
# Configuration
# ============================================================================


@dataclass
class ConfigurationCampagne:
    """Paramètres d'une campagne de benchmark."""

    simulation_id: str
    profils: Tuple[str, ...] = PROFILS_C7_REFERENCE
    repetitions: int = 1
    # Nombre maximum de générations par variante. Au-delà de 1, une variante
    # dont la génération a **levé** (erreur d'infrastructure : réponse amont
    # coupée, 502, timeout réseau) est relancée : une panne réseau n'est pas
    # un résultat. La relance est bornée, avec le même profil et le même jeu
    # de preuves, et elle est consignée dans la charge utile et le rapport.
    tentatives_max: int = 2
    backend_graphe_attendu: str = "graphiti"
    #: Surcharges d'injection pour les tests hermétiques.
    capture_empreinte: Optional[Callable[[str], Dict[str, Any]]] = None
    mesurer_graphe: Optional[Callable[[str], Dict[str, Any]]] = None
    generer_variante: Optional[Callable[..., Dict[str, Any]]] = None
    verifier_preconditions: Optional[Callable[[str], Tuple[bool, Dict[str, Any]]]] = None

    def __post_init__(self) -> None:
        if not str(self.simulation_id or "").strip():
            raise ValueError("simulation_id est obligatoire")
        if not self.profils:
            raise ValueError("au moins un profil de catalogue est nécessaire")
        if isinstance(self.repetitions, bool) or int(self.repetitions) < 1:
            raise ValueError("repetitions doit être un entier positif")
        self.repetitions = int(self.repetitions)
        if isinstance(self.tentatives_max, bool) or int(self.tentatives_max) < 1:
            raise ValueError("tentatives_max doit être un entier positif")
        self.tentatives_max = int(self.tentatives_max)

# ============================================================================
# Pré-contrôles
# ============================================================================


def verifier_backend_graphe(attendu: str) -> Tuple[bool, Dict[str, Any]]:
    """Vérifie que le backend de graphe résolu est celui attendu.

    Le banc refuse de s'exécuter sur un backend inattendu : les outils graphe
    du `ReportAgent` viseraient alors une passerelle absente, et les deux
    variantes seraient dégradées de façon non comparable (AC2, décision
    d'ingénierie n° 1).
    """
    brut = str(getattr(Config, "ZEP_BACKEND", "") or "").strip().lower()
    attendu_normalise = str(attendu or "").strip().lower()
    details: Dict[str, Any] = {
        "backend_resolu": brut or None,
        "backend_attendu": attendu_normalise,
        "motif": None,
    }
    if brut != attendu_normalise:
        details["motif"] = (
            f"{MOTIF_BACKEND_INATTENDU} : le graphe actif est '{brut or 'non résolu'}' "
            f"alors que le banc exige '{attendu_normalise}'. Les outils graphe du "
            "ReportAgent viseraient une passerelle absente : les deux variantes "
            "seraient dégradées de façon non comparable. Le banc s'exécute dans la "
            "stack Docker de référence (ZEP_BACKEND=graphiti, Neo4j local)."
        )
        return False, details
    return True, details


def verifier_preconditions(simulation_id: str) -> Tuple[bool, Dict[str, Any]]:
    """Reproduit les préconditions de l'API de génération de rapport.

    Le banc appelle `ReportAgent` en direct (l'API travaille dans un thread de
    fond et répond `task_id`), donc il doit reproduire lui-même les conditions
    que l'API vérifie : projet existant et `GRAPH_COMPLETED`, `graph_id` du
    projet conforme à celui de l'état, exigence de simulation non vide
    (décision d'ingénierie n° 11).
    """
    details: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "simulation_trouvee": False,
        "projet_trouve": False,
        "project_id": None,
        "projet_statut": None,
        "graph_id": None,
        "graph_id_concordant": False,
        "simulation_requirement": False,
        "locale": None,
        "motif": None,
    }

    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        details["motif"] = f"simulation '{simulation_id}' introuvable"
        return False, details
    details["simulation_trouvee"] = True
    details["locale"] = getattr(state, "locale", None)

    project = ProjectManager.get_project(getattr(state, "project_id", "") or "")
    if not project:
        details["motif"] = (
            f"projet '{getattr(state, 'project_id', '')}' introuvable pour la "
            f"simulation '{simulation_id}'"
        )
        return False, details
    details["projet_trouve"] = True
    details["project_id"] = getattr(project, "project_id", None)
    details["projet_statut"] = str(getattr(project.status, "value", project.status))

    if project.status != ProjectStatus.GRAPH_COMPLETED:
        details["motif"] = (
            f"le projet '{project.project_id}' n'est pas au statut "
            f"GRAPH_COMPLETED (statut actuel : {details['projet_statut']})"
        )
        return False, details

    graph_id = project.graph_id
    if not graph_id:
        details["motif"] = f"le projet '{project.project_id}' ne porte aucun graph_id"
        return False, details
    details["graph_id"] = graph_id

    state_graph_id = getattr(state, "graph_id", None)
    if state_graph_id and state_graph_id != graph_id:
        details["motif"] = (
            "la simulation référence un graphe plus ancien que celui du projet ; "
            "il faut la préparer à nouveau avant de générer un rapport"
        )
        return False, details
    details["graph_id_concordant"] = True

    if not project.simulation_requirement:
        details["motif"] = (
            f"le projet '{project.project_id}' ne porte aucune exigence de simulation"
        )
        return False, details
    details["simulation_requirement"] = True
    # L'exigence et la locale sont relues ici, et réutilisées telles quelles
    # par la campagne : le pré-contrôle est la source unique du contexte, et
    # le projet ne peut pas changer entre la validation et la génération
    # (revue BMAD du 20 octobre 2026).
    details["simulation_requirement_texte"] = project.simulation_requirement

    return True, details


def capturer_empreinte(simulation_id: str) -> Dict[str, Any]:
    """Capture l'empreinte SHA-256 des preuves figées de la simulation.

    Le mode strict est utilisé : une simulation sans preuve exploitable doit
    faire échouer le banc (AC1), pas produire un comparatif dégradé.
    """
    snapshot = EvidenceSnapshotService(simulation_id=simulation_id).capture_snapshot(
        strict=True
    )
    return {
        "snapshot_id": snapshot.snapshot_id,
        "sha256_hash": snapshot.sha256_hash,
        "total_events": snapshot.total_events,
        "total_actors": snapshot.total_actors,
        "has_archived_interviews": snapshot.has_archived_interviews,
        "file_hashes": dict(snapshot.file_hashes),
    }


def mesurer_graphe(graph_id: str) -> Dict[str, Any]:
    """Mesure l'état du graphe (cardinalités et empreinte du contenu).

    Le graphe n'est **pas** scellé par l'empreinte des preuves : `replay_frozen`
    ne gèle que les interactions OASIS live, les outils graphe interrogent
    toujours Neo4j. Cette mesure est donc le garde-fou de cohérence du comparatif
    (décision d'ingénierie n° 3).

    Les cardinalités ne suffisent pas : une écriture peut enrichir un nœud
    **existant** sans en créer (le « merge » de Graphiti met à jour le résumé
    et les attributs), et laisserait les comptes inchangés alors que les
    outils graphe liraient un contenu différent. On mesure donc aussi une
    **empreinte de contenu** : SHA-256 sur la liste triée des identifiants,
    noms et résumés des nœuds, et des identifiants et faits des arêtes
    (revue BMAD du 20 octobre 2026).
    """
    store = get_graph_store()
    try:
        noeuds = store.get_all_nodes(graph_id) or []
        aretes = store.get_all_edges(graph_id) or []
        empreintes = []
        for noeud in noeuds:
            empreintes.append(
                "N|{}|{}|{}".format(
                    getattr(noeud, "uuid", ""),
                    getattr(noeud, "name", ""),
                    getattr(noeud, "summary", "") or "",
                )
            )
        for arete in aretes:
            empreintes.append(
                "A|{}|{}|{}|{}".format(
                    getattr(arete, "uuid", ""),
                    getattr(arete, "source_name", "") or getattr(arete, "source", ""),
                    getattr(arete, "target_name", "") or getattr(arete, "target", ""),
                    getattr(arete, "fact", "") or "",
                )
            )
        empreintes.sort()
        empreinte_contenu = hashlib.sha256(
            "\n".join(empreintes).encode("utf-8")
        ).hexdigest()
        return {
            "graph_id": graph_id,
            "nodes": len(noeuds),
            "edges": len(aretes),
            "contenu_sha256": empreinte_contenu,
        }
    finally:
        release_graph_store(store)


# ============================================================================
# Génération d'une variante
# ============================================================================


def generer_variante(
    *,
    simulation_id: str,
    graph_id: str,
    simulation_requirement: str,
    locale: Optional[str],
    profile: ReportLLMProfile,
    report_id: str,
    report_folder: str,
) -> Dict[str, Any]:
    """Exécute une génération de rapport et renvoie son résumé.

    La génération est exécutée sous `graph_lifecycle_lock`, comme dans l'API :
    ce verrou empêche la suppression du graphe pendant la lecture. Le rapport
    est enregistré dans l'historique de la simulation, et le lecteur de graphe
    est désinscrit dans tous les cas.
    """
    started = time.monotonic()
    agent = ReportAgent(
        graph_id=graph_id,
        simulation_id=simulation_id,
        simulation_requirement=simulation_requirement,
        locale=locale,
        profile=profile,
        replay_mode=MODE_REJEU,
    )
    report = None
    with graph_lifecycle_lock(graph_id):
        register_graph_reader(graph_id, report_id)
        try:
            report = agent.generate_report(report_id=report_id)
            ReportManager.save_report(report)
        finally:
            unregister_graph_reader(graph_id, report_id)
    if report is None:  # pragma: no cover - garde défensive
        raise RuntimeError(
            f"la génération du rapport '{report_id}' n'a produit aucun rapport"
        )
    return {
        "report_id": report_id,
        "statut": str(getattr(report.status, "value", report.status)),
        "erreur": getattr(report, "error", None),
        "duree_secondes": round(time.monotonic() - started, 3),
        "report_folder": report_folder,
    }


def lire_artefacts(report_folder: str) -> Dict[str, Any]:
    """Relit les artefacts d'un rapport généré depuis son dossier.

    Un artefact absent ou illisible ne fait pas échouer la relecture : il est
    simplement marqué absent, et les métriques correspondantes seront
    « indisponibles » (AC8).
    """
    dossier = Path(report_folder)
    artefacts: Dict[str, Any] = {}

    for nom, cle in (
        ("meta.json", "meta"),
        ("report_claims.json", "report_claims"),
        ("cohort_coverage.json", "cohort_coverage"),
        ("quality_checks.json", "quality_checks"),
        ("usage.json", "usage"),
        ("run_manifest.json", "run_manifest"),
    ):
        chemin = dossier / nom
        if not chemin.exists():
            artefacts[cle] = None
            continue
        try:
            charge = json.loads(chemin.read_text(encoding="utf-8"))
            artefacts[cle] = charge if isinstance(charge, dict) else None
        except (OSError, ValueError):
            artefacts[cle] = None

    markdown = dossier / "full_report.md"
    if markdown.exists():
        try:
            artefacts["full_report"] = markdown.read_text(encoding="utf-8")
        except OSError:
            artefacts["full_report"] = None
    else:
        artefacts["full_report"] = None

    return artefacts


# ============================================================================
# Campagne
# ============================================================================


def _profil_du_catalogue(profile_id: str) -> ReportLLMProfile:
    """Résout un profil du catalogue fermé des profils LLM de rapport.

    La liste des profils n'est jamais écrite en dur dans le banc : elle vient
    de `ReportLLMProfile` (NFR-1 de l'epic).
    """
    profil = ReportLLMProfile.get_standard_profile(profile_id)
    if profil is None:
        connus = ", ".join(ReportLLMProfile.standard_profile_ids())
        raise ValueError(
            f"profil '{profile_id}' absent du catalogue (profils connus : {connus})"
        )
    return profil


def executer_precontrole(
    configuration: ConfigurationCampagne,
) -> Tuple[bool, Dict[str, Any]]:
    """Enchaîne les quatre pré-contrôles du banc.

    Renvoie ``(conforme, détails)``. Les détails portent toujours les mêmes
    clés, que le pré-contrôle passe ou échoue : un échec doit dire *pourquoi*,
    jamais laisser un trou dans le diagnostic.

    Les quatre contrôles sont, dans l'ordre : le backend de graphe résolu, les
    préconditions de génération, l'empreinte des preuves figées, et l'état du
    graphe. Le troisième et le quatrième sont ceux qui décident si un
    comparatif peut être établi.
    """
    capture = configuration.capture_empreinte or capturer_empreinte
    mesurer = configuration.mesurer_graphe or mesurer_graphe
    preconditions = configuration.verifier_preconditions or verifier_preconditions

    details: Dict[str, Any] = {
        "backend_graphe": {},
        "preconditions": {},
        "preuves": {},
        "graphe": {},
        "evidence": None,
        "graph_state": None,
        "conforme": False,
        "motif": None,
    }

    # ── 1. Backend de graphe ───────────────────────────────────────────
    backend_ok, backend_details = verifier_backend_graphe(
        configuration.backend_graphe_attendu
    )
    details["backend_graphe"] = backend_details
    if not backend_ok:
        details["motif"] = backend_details.get("motif")
        return False, details

    # ── 2. Préconditions de génération ─────────────────────────────────
    precond_ok, precond_details = preconditions(configuration.simulation_id)
    details["preconditions"] = precond_details
    if not precond_ok:
        details["motif"] = precond_details.get("motif")
        return False, details

    # ── 3. Empreinte des preuves figées ────────────────────────────────
    try:
        evidence = capture(configuration.simulation_id)
    except ReplayNotReproducibleError as erreur:
        motif = _description_erreur(erreur)
        details["preuves"] = {"conforme": False, "motif": motif}
        details["motif"] = motif
        return False, details
    except Exception as erreur:
        motif = _description_erreur(erreur)
        details["preuves"] = {"conforme": False, "motif": motif}
        details["motif"] = (
            "capture de l'empreinte des preuves impossible : " + str(motif)
        )
        return False, details

    details["evidence"] = evidence
    details["preuves"] = {
        "conforme": True,
        "sha256_hash": evidence.get("sha256_hash"),
        "total_events": evidence.get("total_events"),
        "total_actors": evidence.get("total_actors"),
    }

    # ── 4. État du graphe ──────────────────────────────────────────────
    graph_id = precond_details.get("graph_id") or ""
    try:
        graph_state = mesurer(graph_id)
    except Exception as erreur:
        motif = _description_erreur(erreur)
        details["graphe"] = {"conforme": False, "motif": motif}
        details["motif"] = (
            "mesure de l'état du graphe impossible : " + str(motif) + ". Sans "
            "cette mesure, le comparatif ne serait pas contrôlé : le graphe "
            "n'est pas scellé par l'empreinte des preuves."
        )
        return False, details

    details["graph_state"] = graph_state
    details["graphe"] = {"conforme": True, **graph_state}
    details["conforme"] = True
    return True, details


def executer_campagne(
    configuration: ConfigurationCampagne,
    precontrole: Optional[Tuple[bool, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Exécute une campagne complète et renvoie sa charge utile.

    La fonction n'écrit rien : elle renvoie un dictionnaire que l'appelant
    (le script ou un test) décide d'écrire sur disque. Toutes les dépendances
    externes sont injectables, ce qui rend la campagne testable sans réseau ni
    modèle.

    Args:
        configuration: paramètres de la campagne.
        precontrole: résultat d'un pré-contrôle déjà effectué. Quand il est
            fourni, il est réutilisé tel quel : une campagne ne doit pas
            capturer deux empreintes de référence différentes, sinon la
            console, la charge utile et le rapport ne porteraient pas la même
            (revue BMAD du 20 octobre 2026).
    """
    capture = configuration.capture_empreinte or capturer_empreinte
    mesurer = configuration.mesurer_graphe or mesurer_graphe
    generer = configuration.generer_variante or generer_variante

    depart = time.monotonic()
    payload: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "simulation_id": configuration.simulation_id,
        "replay_mode": MODE_REJEU,
        "score_grid_version": SCORE_GRID_VERSION,
        "repetitions": configuration.repetitions,
        "profils": list(configuration.profils),
        "precontrole": {},
        "evidence": None,
        "graph_state_reference": None,
        "variantes": [],
        "comparabilite": {},
        "verdict": None,
        "motif_verdict": None,
        "cout_estime_usd_total": None,
        "duree_murale_secondes": None,
        "backend_graphe": {},
    }

    # ── Pré-contrôle (environnement, préconditions, preuves, graphe) ───
    if precontrole is None:
        conforme, precontrole = executer_precontrole(configuration)
    else:
        conforme, precontrole = precontrole
    payload["precontrole"] = precontrole
    payload["backend_graphe"] = precontrole.get("backend_graphe", {})
    if not conforme:
        payload["verdict"] = VERDICT_NON_CONCLUANT_PREUVES
        payload["motif_verdict"] = precontrole.get("motif")
        payload["duree_murale_secondes"] = round(time.monotonic() - depart, 3)
        return payload

    evidence = precontrole.get("evidence") or {}
    graph_reference = precontrole.get("graph_state") or {}
    payload["evidence"] = evidence
    payload["graph_state_reference"] = graph_reference
    contexte = precontrole.get("preconditions") or {}
    graph_id = contexte.get("graph_id") or ""
    simulation_requirement = contexte.get("simulation_requirement_texte") or ""
    locale = contexte.get("locale")

    # ── Boucle de variantes ────────────────────────────────────────────
    cout_total = 0.0
    cout_connu = True
    etiquette = 0
    for profile_id in configuration.profils:
        profil = _profil_du_catalogue(profile_id)
        for repetition in range(1, configuration.repetitions + 1):
            lettre = (
                LETTRES_VARIANTES[etiquette]
                if etiquette < len(LETTRES_VARIANTES)
                else f"V{etiquette + 1}"
            )
            etiquette += 1
            report_id = f"report_{uuid.uuid4().hex[:12]}"
            # Le dossier du rapport est celui du gestionnaire : c'est la seule
            # source de vérité. Le reconstituer ici pourrait désigner un
            # dossier vide, dont les métriques seraient « indisponibles »
            # sans que personne ne s'en aperçoive (revue BMAD du 20 octobre
            # 2026).
            report_folder = ReportManager.get_report_folder(report_id)

            variante: Dict[str, Any] = {
                "etiquette": lettre,
                "profile_id": profile_id,
                "model": profil.model,
                "reasoning_effort": profil.reasoning_effort,
                "repetition": repetition,
                "report_id": report_id,
                "report_folder": report_folder,
                "statut": "non exécutée",
                "exclue": False,
                "certification_refusee": False,
                "tentatives": 0,
                "erreurs": [],
                "motif_exclusion": None,
                "evidence_sha256": None,
                "graph_state": None,
                "score": None,
                "duree_secondes": None,
                "cout_estime_usd": None,
                "stop_reason": None,
                "stop_message": None,
                "artefacts_manquants": [],
            }

            resume = None
            erreurs: List[str] = []
            while (
                resume is None
                and variante["tentatives"] < configuration.tentatives_max
            ):
                variante["tentatives"] += 1
                try:
                    resume = generer(
                        simulation_id=configuration.simulation_id,
                        graph_id=graph_id,
                        simulation_requirement=simulation_requirement,
                        locale=locale,
                        profile=profil,
                        report_id=report_id,
                        report_folder=report_folder,
                    )
                except Exception as erreur:
                    # Une erreur d'infrastructure (réponse amont coupée, 502,
                    # timeout réseau) n'est pas un résultat : la variante est
                    # relancée **une fois**, avec le même profil et le même
                    # jeu de preuves. La relance est bornée et consignée.
                    erreurs.append(_description_erreur(erreur) or "erreur inconnue")
                    if variante["tentatives"] >= configuration.tentatives_max:
                        break
                    print(
                        f"\n  [Variante {lettre}] La génération a échoué "
                        f"({erreurs[-1]}) ; nouvelle tentative "
                        f"({variante['tentatives'] + 1}/{configuration.tentatives_max})."
                    )
                    report_id = f"report_{uuid.uuid4().hex[:12]}"
                    report_folder = ReportManager.get_report_folder(report_id)
                    variante["report_id"] = report_id
                    variante["report_folder"] = report_folder

            variante["erreurs"] = erreurs
            if resume is None:
                variante["statut"] = "échec"
                variante["exclue"] = True
                variante["motif_exclusion"] = (
                    "la génération a échoué : " + "; ".join(erreurs)
                )
                # Le coût de la variante est inconnu : la campagne ne peut
                # plus annoncer un total de 0 $ (AC8).
                cout_connu = False
                payload["variantes"].append(variante)
                continue

            variante["statut"] = str(resume.get("statut") or "inconnu")
            variante["duree_secondes"] = resume.get("duree_secondes")
            variante["erreur"] = _description_erreur(resume.get("erreur"))

            artefacts = lire_artefacts(report_folder)
            variante["artefacts_manquants"] = [
                nom
                for nom in ARTEFACTS_ATTENDUS
                if not (Path(report_folder) / nom).exists()
            ]

            # Empreinte réelle de la variante : elle doit être strictement
            # égale à celle du pré-contrôle, et l'empreinte *stockée* dans les
            # artefacts doit elle aussi y correspondre (AC3).
            try:
                evidence_variante = capture(configuration.simulation_id)
            except Exception as erreur:
                evidence_variante = {
                    "sha256_hash": None,
                    "motif": "empreinte recontrôlée impossible : "
                    + _description_erreur(erreur),
                }
            variante["evidence_sha256"] = evidence_variante.get("sha256_hash")

            meta = artefacts.get("meta") or {}
            snapshot_meta = meta.get("evidence_snapshot")
            empreinte_stockee = (
                snapshot_meta.get("sha256_hash")
                if isinstance(snapshot_meta, dict)
                else None
            )
            variante["evidence_sha256_stockee"] = empreinte_stockee
            variante["evidence_snapshot_id"] = (
                snapshot_meta.get("snapshot_id")
                if isinstance(snapshot_meta, dict)
                else None
            )

            # ── Exclusion : rapport non achevé ─────────────────────────
            # Un rapport arrêté sur un plafond ou interrompu est **partiel** :
            # il ne peut pas être comparé à un rapport complet. En revanche,
            # un rapport complet refusé par la barrière de publication reste
            # comparable : son verdict de certification est une mesure.
            if variante["statut"] in STATUTS_GENERATION_INCOMPLETE:
                variante["exclue"] = True
                variante["motif_exclusion"] = (
                    f"la génération s'est terminée sur le statut "
                    f"'{variante['statut']}' : le rapport est partiel, il ne "
                    "peut pas être comparé à un rapport complet."
                )
            elif variante["statut"] == STATUT_CERTIFICATION_REFUSEE:
                variante["certification_refusee"] = True

            # ── Exclusion : dossier de rapport absent ───────────────────
            if not variante["exclue"] and not (
                Path(report_folder) / "full_report.md"
            ).exists():
                variante["exclue"] = True
                variante["motif_exclusion"] = (
                    "le dossier du rapport ne contient pas de rapport complet "
                    f"({report_folder}) : aucune mesure n'a pu être relevée."
                )

            # ── Exclusion : empreinte divergente ou absente ─────────────
            if not variante["exclue"]:
                if variante["evidence_sha256"] != evidence.get("sha256_hash"):
                    variante["exclue"] = True
                    variante["motif_exclusion"] = (
                        "l'empreinte des preuves a divergé pendant la "
                        f"génération (pré-contrôle {evidence.get('sha256_hash')} "
                        f"observée {variante['evidence_sha256']}) : les deux "
                        "variantes n'auraient pas été produites sur le même "
                        "jeu de preuves."
                    )
                elif not empreinte_stockee:
                    variante["exclue"] = True
                    variante["motif_exclusion"] = (
                        "le rapport ne porte aucune empreinte des preuves "
                        "(meta.json ou evidence_snapshot absent) : il ne peut "
                        "pas être rattaché au jeu de preuves rejoué."
                    )
                elif empreinte_stockee != variante["evidence_sha256"]:
                    variante["exclue"] = True
                    variante["motif_exclusion"] = (
                        "l'empreinte stockée dans les artefacts du rapport "
                        f"({empreinte_stockee}) diffère de l'empreinte "
                        f"recontrôlée ({variante['evidence_sha256']}) : le "
                        "rapport ne peut pas être rattaché au jeu de preuves "
                        "rejoué."
                    )

            # ── Exclusion : graphe modifié ou non mesurable ─────────────
            try:
                graph_variante = mesurer(graph_id)
                graph_mesure_ok = True
            except Exception as erreur:
                graph_variante = {"erreur": _description_erreur(erreur)}
                graph_mesure_ok = False
            variante["graph_state"] = graph_variante
            if not variante["exclue"] and not graph_mesure_ok:
                variante["exclue"] = True
                variante["motif_exclusion"] = (
                    "l'état du graphe n'a pas pu être mesuré après la "
                    f"génération ({graph_variante.get('erreur')}) : la "
                    "comparaison ne serait pas contrôlée."
                )
            elif not variante["exclue"] and graph_variante != graph_reference:
                variante["exclue"] = True
                variante["motif_exclusion"] = (
                    "l'état du graphe a changé pendant la génération "
                    f"({graph_reference} au pré-contrôle, {graph_variante} "
                    "après) : le graphe n'est pas scellé par l'empreinte des "
                    "preuves, la comparaison ne serait pas contrôlée."
                )

            # ── Score et télémétrie ────────────────────────────────────
            # Le dénominateur du taux d'adoption est publié par le modèle
            # métier (`CohortCoverageTable.to_dict`) : la règle d'éligibilité
            # reste écrite à un seul endroit, et le dénominateur est un fait
            # persisté, lisible par l'API, l'historique et la grille.
            score = score_report_artifacts(artefacts)
            variante["score"] = score
            usage = artefacts.get("usage") or {}
            variante["stop_reason"] = usage.get("stop_reason")
            variante["stop_message"] = usage.get("stop_message")
            variante["pricing_table_version"] = usage.get("pricing_table_version")
            cout = usage.get("estimated_cost_usd")
            variante["cout_estime_usd"] = cout
            if isinstance(cout, (int, float)) and not isinstance(cout, bool):
                cout_total += float(cout)
            else:
                cout_connu = False

            payload["variantes"].append(variante)

    # ── Comparabilité ──────────────────────────────────────────────────
    incluses = [v for v in payload["variantes"] if not v["exclue"]]
    if len(incluses) >= 2:
        comparabilite = evaluate_comparability(
            {
                "sha256": incluses[0].get("evidence_sha256"),
                "snapshot_id": incluses[0].get("evidence_snapshot_id"),
                "simulation_id": configuration.simulation_id,
            },
            {
                "sha256": incluses[1].get("evidence_sha256"),
                "snapshot_id": incluses[1].get("evidence_snapshot_id"),
                "simulation_id": configuration.simulation_id,
            },
        )
    else:
        comparabilite = {
            "regle": COMPARABILITY_RULE,
            "verdict": VERDICT_NON_CONTROLEE,
            "preuve_identite": None,
            "motif": (
                "moins de deux variantes exploitables : le comparatif ne peut "
                "pas être établi."
            ),
            "gauche_sha256": None,
            "droite_sha256": None,
            "gauche_snapshot_id": None,
            "droite_snapshot_id": None,
        }
    payload["comparabilite"] = comparabilite

    # ── Verdict de campagne ────────────────────────────────────────────
    ecartees = [v for v in payload["variantes"] if v["exclue"]]
    if ecartees:
        payload["verdict"] = VERDICT_NON_CONCLUANT_EXCLUSION
        payload["motif_verdict"] = (
            f"{len(ecartees)} variante(s) écartée(s) du comparatif : "
            + " ; ".join(
                f"{v.get('etiquette')} — {v.get('motif_exclusion')}" for v in ecartees
            )
        )
    elif comparabilite.get("verdict") == VERDICT_CONTROLEE:
        payload["verdict"] = VERDICT_CONTROLEE
        payload["motif_verdict"] = comparabilite.get("motif")
    else:
        payload["verdict"] = VERDICT_NON_CONTROLEE
        payload["motif_verdict"] = comparabilite.get("motif")

    payload["cout_estime_usd_total"] = round(cout_total, 8) if cout_connu else None
    payload["duree_murale_secondes"] = round(time.monotonic() - depart, 3)
    return payload


# ============================================================================
# Matériel de revue aveugle
# ============================================================================


def _detecter_declassement(markdown: Optional[str], profil: ReportLLMProfile) -> bool:
    """Indique si le corps du rapport trahit le profil qui l'a produit.

    La revue aveugle suppose que le lecteur ignore quelle variante est
    laquelle : si le corps du rapport mentionne le modèle ou l'effort, la
    correspondance doit être déclarée comme compromise plutôt que passée sous
    silence.

    Deux précautions (revue BMAD du 20 octobre 2026) :

      - le corps est **normalisé** (Unicode NFKD, séparateurs ramenés à un
        tiret, casse uniforme), pour qu'une reformulation du nom du modèle
        (« Gemini 3.8 Flash », « gemini_3_8_flash ») soit détectée aussi ;
      - l'effort n'est recherché qu'**accompagné d'un mot-clé** (« effort »,
        « reasoning », « profil ») : le mot anglais « high » est un mot
        courant, et le chercher seul déclasserait à tort des rapports
        parfaitement anonymes.
    """
    if not isinstance(markdown, str) or not markdown:
        return False
    corps = _normaliser_texte(markdown)
    modele = _normaliser_texte(str(profil.model))
    if modele and modele in corps:
        return True
    effort = profil.reasoning_effort
    if effort:
        motif_effort = re.compile(
            r"(?:effort|reasoning|profil|thinking)[^.;\n]{0,40}"
            + re.escape(_normaliser_texte(str(effort)))
        )
        if motif_effort.search(corps):
            return True
    return False


def _normaliser_texte(texte: str) -> str:
    """Normalise un texte pour une recherche de marqueur robuste.

    Unicode NFKD (accents retirés), casse uniforme, et tous les séparateurs
    (``-``, ``_``, ``.``, espace) ramenés à un tiret unique : « gemini-3.8-flash »,
    « Gemini 3.8 Flash » et « gemini_3_8_flash » deviennent la même chaîne.
    """
    if not isinstance(texte, str):
        return ""
    decomposee = unicodedata.normalize("NFKD", texte.lower())
    sans_accent = "".join(c for c in decomposee if not unicodedata.combining(c))
    return re.sub(r"[\s._/]+", "-", sans_accent).strip("-")


def _marqueurs_croises(
    markdown: Optional[str], profil: ReportLLMProfile, autres: Sequence[ReportLLMProfile]
) -> List[str]:
    """Repère les marqueurs d'un **autre** profil dans le corps du rapport.

    L'aveuglement est un constat de paire : si le corps d'une variante
    mentionne l'effort ou le modèle d'une autre variante, le lecteur en déduit
    quelle variante il relit. La correspondance est alors compromise même
    quand la variante elle-même ne se nomme pas (revue BMAD du 20 octobre
    2026).
    """
    if not isinstance(markdown, str) or not markdown:
        return []
    corps = _normaliser_texte(markdown)
    trouves: List[str] = []
    for autre in autres:
        if autre.profile_id == profil.profile_id:
            continue
        modele = _normaliser_texte(str(autre.model))
        if modele and modele in corps:
            trouves.append(f"{autre.profile_id} (modèle)")
            continue
        effort = autre.reasoning_effort
        if effort:
            motif = re.compile(
                r"(?:effort|reasoning|profil|thinking)[^.;\n]{0,40}"
                + re.escape(_normaliser_texte(str(effort)))
            )
            if motif.search(corps):
                trouves.append(f"{autre.profile_id} (effort)")
    return trouves


def ecrire_materiel_aveugle(
    dossier: Path,
    payload: Dict[str, Any],
    variantes: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Écrit la paire anonymisée, la grille de revue et la correspondance.

    La correspondance est écrite dans un **fichier distinct** de la grille : la
    règle de procédure impose de ne l'ouvrir qu'après remplissage de la grille.

    Deux précautions (revue BMAD du 20 octobre 2026) :

      - une variante **écartée** du comparatif ne reçoit pas l'en-tête
        « produit sur le même jeu de preuves » : cet énoncé serait faux, et
        l'évaluateur ne doit pas noter un rapport non comparable ;
      - le déclassement est détecté **de campagne** : un corps qui mentionne le
        modèle ou l'effort d'une autre variante trahit aussi la correspondance.
    """
    dossier.mkdir(parents=True, exist_ok=True)
    correspondance: Dict[str, Any] = {
        "campagne": dossier.name,
        "simulation_id": payload.get("simulation_id"),
        "regle": (
            "La correspondance ne s'ouvre qu'après remplissage complet de la "
            "grille de revue aveugle (grille-aveugle.md)."
        ),
        "procedure": (
            "Seuls les fichiers `variante-*.md` et `grille-aveugle.md` sont "
            "remis à l'évaluateur. `correspondance.json` et "
            "`mesure-benchmark-013.json` restent avec le responsable de "
            "campagne : ils portent la clé de l'aveuglement."
        ),
        "variantes": {},
        "declassement": {},
        "declassement_croise": {},
    }

    profils_campagne = []
    for variante in variantes:
        profil = ReportLLMProfile.get_standard_profile(
            str(variante.get("profile_id"))
        )
        if profil is not None and profil not in profils_campagne:
            profils_campagne.append(profil)

    for variante in variantes:
        lettre = str(variante.get("etiquette"))
        markdown = ""
        dossier_variante = str(variante.get("report_folder") or "")
        if dossier_variante:
            chemin = Path(dossier_variante) / "full_report.md"
            if chemin.exists():
                try:
                    markdown = chemin.read_text(encoding="utf-8")
                except OSError:
                    markdown = ""

        if variante.get("exclue"):
            entete = (
                f"> **Variante anonymisée {lettre} — ÉCARTÉE DU COMPARATIF.** "
                "Ce rapport ne peut pas être comparé à sa contrepartie : "
                f"{variante.get('motif_exclusion') or 'motif non communiqué'}. "
                "Il ne doit pas être noté.\n\n"
            )
        else:
            entete = (
                f"> **Variante anonymisée {lettre}** — rapport produit sur le "
                "même jeu de preuves figées que sa contrepartie. Le profil "
                "correspondant se trouve dans `correspondance.json`, qui ne "
                "doit pas être ouvert avant le remplissage de "
                "`grille-aveugle.md`.\n\n"
            )
        (dossier / f"variante-{lettre}.md").write_text(
            entete + markdown, encoding="utf-8"
        )

        profil = ReportLLMProfile.get_standard_profile(
            str(variante.get("profile_id"))
        )
        declassement = (
            _detecter_declassement(markdown, profil)
            if profil is not None
            else True
        )
        croises = (
            _marqueurs_croises(markdown, profil, profils_campagne)
            if profil is not None
            else []
        )
        correspondance["variantes"][lettre] = {
            "profile_id": variante.get("profile_id"),
            "model": variante.get("model"),
            "reasoning_effort": variante.get("reasoning_effort"),
            "report_id": variante.get("report_id"),
            "repetition": variante.get("repetition"),
            "exclue": variante.get("exclue"),
            "motif_exclusion": variante.get("motif_exclusion"),
        }
        correspondance["declassement"][lettre] = declassement
        correspondance["declassement_croise"][lettre] = croises

    (dossier / "correspondance.json").write_text(
        json.dumps(correspondance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (dossier / "grille-aveugle.md").write_text(
        _contenu_grille_aveugle(payload, variantes), encoding="utf-8"
    )
    return correspondance


def _contenu_grille_aveugle(
    payload: Dict[str, Any], variantes: Sequence[Dict[str, Any]]
) -> str:
    """Construit la grille de revue aveugle à remplir.

    Une colonne de note est créée **par variante** : avec plus de deux
    variantes (répétitions ou profils supplémentaires), une grille à deux
    colonnes laisserait la moitié du corpus sans case à remplir, et la règle
    « grille entièrement remplie » deviendrait impossible à satisfaire (revue
    BMAD du 20 octobre 2026).
    """
    notables = [v for v in variantes if not v.get("exclue")]
    retenues = notables or list(variantes)
    lettres = [str(v.get("etiquette")) for v in retenues] or ["A", "B"]
    entete_lettres = " | ".join(f"Note {lettre}" for lettre in lettres)
    criteres = [
        "Exactitude factuelle vérifiable",
        "Couverture de la cohorte",
        "Explicitation des limites et des objections",
        "Lisibilité et structure du rapport",
        "Respect des contraintes de publication",
    ]
    lignes = "\n".join(
        f"| {index} | {critere} | 0 à 5 | " + " | ".join("" for _ in lettres) + " | |"
        for index, critere in enumerate(criteres, start=1)
    )
    separation = "|---" * (4 + len(lettres)) + "|"
    ecartees = [str(v.get("etiquette")) for v in variantes if v.get("exclue")]
    mention_ecartees = (
        (
            "\n> Variantes écartées du comparatif (ne pas noter) : "
            + ", ".join(ecartees)
            + ".\n"
        )
        if ecartees
        else ""
    )
    return f"""# Grille de revue aveugle — campagne {payload.get('timestamp')}

> Campagne : `{payload.get('simulation_id')}` · Variantes notables : {', '.join(lettres)}
> Grille de score du banc : version `{payload.get('score_grid_version')}`.
{mention_ecartees}
## Règle de procédure (à lire avant de commencer)

1. Remplir **cette grille** avant d'ouvrir `correspondance.json`.
2. Ne pas ouvrir `correspondance.json` ni `mesure-benchmark-013.json` tant que
   la grille n'est pas entièrement remplie et datée.
3. Seuls `variante-*.md` et cette grille sont remis à l'évaluateur : les deux
   autres fichiers du dossier portent la clé de l'aveuglement et restent avec
   le responsable de campagne.
4. La correspondance associe chaque variante à son profil de génération ; elle
   ne sert qu'à **interpréter** des notes déjà portées, jamais à les produire.
5. Un évaluateur qui a déjà ouvert la correspondance ne peut plus produire une
   évaluation aveugle : il faut alors recommencer avec un autre évaluateur.

## Critères d'appréciation (à remplir)

| # | Critère | Échelle | {entete_lettres} | Commentaire |
{separation}
{lignes}

## Observations libres

<!-- Consigner ici les constats qualitatifs, sans mentionner d'effort ni de modèle. -->

---

## Validation de la procédure

- Grille remplie le : _(date et signature de l'évaluateur)_
- Correspondance ouverte le : _(date, une fois la grille remplie)_
"""


# ============================================================================
# Rapport Markdown formel
# ============================================================================


def _horodatage_du_payload(payload: Dict[str, Any]) -> str:
    """Horodatage de la campagne, lu dans la charge utile.

    Le rapport est ainsi une fonction **déterministe** de la charge utile :
    rejouer le constructeur sur le même JSON redonne le même fichier, à l'octet
    près. C'est ce qui rend l'artefact versionné vérifiable.
    """
    brut = str(payload.get("timestamp") or "").strip()
    if brut:
        try:
            moment = datetime.fromisoformat(brut.replace("Z", "+00:00"))
            return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except ValueError:
            return brut
    return "campagne non horodatée"


def _tableau_ecarts(variantes: Sequence[Dict[str, Any]]) -> str:
    """Construit le tableau des écarts bruts entre les deux variantes.

    L'écart est une **différence**, jamais une préférence : aucune colonne ne
    dit laquelle des deux variantes est meilleure (AC9). Le tableau est séparé
    du tableau des métriques, parce qu'une ligne à plusieurs valeurs dans un
    tableau à trois colonnes serait tronquée par le rendu Markdown.
    """
    incluses = [v for v in variantes if not v.get("exclue")]
    retenues = incluses or list(variantes)
    if len(retenues) != 2:
        return ""
    gauche = (retenues[0].get("score") or {}).get("metrics") or {}
    droite = (retenues[1].get("score") or {}).get("metrics") or {}
    lignes = [
        "| Métrique | Écart brut ("
        + str(retenues[1].get("etiquette"))
        + " − "
        + str(retenues[0].get("etiquette"))
        + ") |",
        "|---|---|",
    ]
    for nom in SCORE_GRID_METRICS:
        ecart = metric_difference(gauche.get(nom), droite.get(nom))
        if ecart is None:
            continue
        lignes.append(f"| `{nom}` | {ecart} |")
    return "\n".join(lignes)
def _tableau_metriques(
    variantes: Sequence[Dict[str, Any]],
) -> str:
    """Construit le tableau des métriques, une colonne par variante.

    Les variantes écartées du comparatif sont signalées dans l'en-tête de
    colonne et leurs valeurs ne sont pas publiées : un lecteur qui saute la
    section du verdict ne doit pas lire un comparatif chiffré entre deux
    rapports non comparables (revue BMAD du 20 octobre 2026).
    """
    if not variantes:
        return "_Aucune variante à comparer._"
    incluses = [v for v in variantes if not v.get("exclue")]
    retenues = incluses or list(variantes)
    entetes = []
    for variante in retenues:
        marque = " (écartée)" if variante.get("exclue") else ""
        entetes.append(f"{variante.get('etiquette')}{marque}")
    colonnes = " | ".join(entetes)
    sep = " | ".join("---" for _ in retenues)
    lignes = [f"| Métrique | {colonnes} |", f"|---|---|{sep}|"]
    for nom in SCORE_GRID_METRICS:
        valeurs = []
        for variante in retenues:
            if variante.get("exclue"):
                valeurs.append("hors comparatif")
                continue
            score = variante.get("score") or {}
            metriques = score.get("metrics") or {}
            valeurs.append(format_metric_value(metriques.get(nom)))
        lignes.append(f"| `{nom}` | " + " | ".join(valeurs) + " |")
    return "\n".join(lignes)


def ecrire_rapport_qualification(
    payload: Dict[str, Any],
    chemin_rapport: Path,
    dossier_campagne: Optional[Path] = None,
) -> Optional[str]:
    """Construit, contrôle puis écrit le rapport Markdown formel de la campagne.

    Point d'écriture **unique** : le contrôle des marqueurs de désignation
    (AC9) est fait sur le contenu construit, avant toute écriture. Un rapport
    non conforme n'est donc jamais laissé sur le disque (revue BMAD du
    20 octobre 2026 : le chemin de test et le chemin de production étaient
    deux fonctions différentes, et seul le second contrôlait).

    Returns:
        Le Markdown écrit, ou ``None`` si le rapport a été refusé.
    """
    markdown = construire_rapport_qualification(payload, dossier_campagne)
    marqueurs = marqueurs_interdits(markdown)
    if marqueurs:
        print(
            "\n  [ERREUR] Le rapport contient des marqueurs de désignation "
            f"interdits : {', '.join(marqueurs)}. Rien n'a été écrit."
        )
        return None
    chemin = Path(chemin_rapport)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(markdown, encoding="utf-8")
    return markdown


def marqueurs_interdits(markdown: str) -> List[str]:
    """Retourne les marqueurs de désignation présents dans un rapport."""
    if not isinstance(markdown, str):
        return []
    contenu = markdown.lower()
    return [marqueur for marqueur in MARQUEURS_INTERDITS if marqueur in contenu]


def construire_rapport_qualification(
    payload: Dict[str, Any],
    dossier_campagne: Optional[Path] = None,
) -> str:
    """Construit le contenu Markdown du rapport, sans l'écrire."""
    variantes = payload.get("variantes") or []
    incluses = [v for v in variantes if not v.get("exclue")]
    evidence = payload.get("evidence") or {}
    graph_ref = payload.get("graph_state_reference") or {}
    comparabilite = payload.get("comparabilite") or {}
    verdict = str(payload.get("verdict") or "verdict indéterminé")
    motif = payload.get("motif_verdict")

    lignes: List[str] = []
    lignes.append("# Rapport de qualification — banc de benchmark A/B du ReportAgent")
    lignes.append("")
    lignes.append(
        "> Généré par `backend/scripts/verifier_benchmark_epic_013.py` le "
        f"{_horodatage_du_payload(payload)}."
    )
    lignes.append(
        f"> Grille de score : version `{payload.get('score_grid_version')}` "
        f"({len(SCORE_GRID_METRICS)} métriques, grille fermée)."
    )
    lignes.append(
        f"> Simulation : `{payload.get('simulation_id')}` · mode de rejeu : "
        f"`{MODE_REJEU}` · répétitions par variante : "
        f"{payload.get('repetitions')}."
    )
    if dossier_campagne is not None:
        lignes.append(f"> Dossier de campagne : `{dossier_campagne.name}`.")
    lignes.append("")

    # ── 1. Verdict ──────────────────────────────────────────────────────
    lignes.append("## 1. Verdict de la campagne")
    lignes.append("")
    lignes.append(f"**{verdict}**")
    lignes.append("")
    if motif:
        lignes.append(f"Motif : {motif}")
        lignes.append("")
    lignes.append(
        "Ce verdict porte sur le **contrôle de la comparaison** (même jeu de "
        "preuves, même code vérificateur). Il ne conclut rien sur la qualité "
        "rédactionnelle d'une variante : cette appréciation appartient à la "
        "revue aveugle outillée par ce banc."
    )
    lignes.append("")

    # ── 2. Protocole ────────────────────────────────────────────────────
    lignes.append("## 2. Protocole appliqué")
    lignes.append("")
    lignes.append(
        f"- **Preuves figées** : empreinte SHA-256 "
        f"`{format_metric_value(evidence.get('sha256_hash'))}` "
        f"({format_metric_value(evidence.get('total_events'))} événements "
        f"observés, {format_metric_value(evidence.get('total_actors'))} acteurs, "
        "archives d'entretiens présentes : "
        f"{'oui' if evidence.get('has_archived_interviews') else 'non'})."
    )
    lignes.append(
        "- **Rejeu** : `replay_frozen` — les interactions OASIS live sont "
        "neutralisées, le paquet de preuves est celui scellé par l'empreinte."
    )
    lignes.append(
        "- **Profils** : issus du catalogue fermé des profils LLM de rapport "
        f"(`{'`, `'.join(payload.get('profils') or [])}`). Aucun profil n'est "
        "écrit en dur dans le banc."
    )
    lignes.append(
        f"- **Répétitions par variante** : {payload.get('repetitions')}."
    )
    tentatives = [
        int(v.get("tentatives") or 0) for v in variantes
    ]
    lignes.append(
        "- **Tentatives par variante** : "
        f"{max(tentatives) if tentatives else 0} au maximum. Une génération "
        "qui **lève** (erreur d'infrastructure : réponse amont coupée, 502, "
        "timeout réseau) est relancée une fois, avec le même profil et le "
        "même jeu de preuves : une panne réseau n'est pas un résultat. Les "
        "relances sont consignées variante par variante."
    )
    lignes.append(
        f"- **Grille de score** : version `{payload.get('score_grid_version')}`, "
        "fermée et purement mécanique. Elle ne contient aucun champ "
        "interprétatif et ne classe pas les variantes."
    )
    lignes.append(
        "- **Code vérificateur** : inchangé pendant toute la campagne. Toute "
        "modification entre deux variantes annulerait la comparaison."
    )
    lignes.append("")

    # ── 3. Contrôle d'environnement ─────────────────────────────────────
    lignes.append("## 3. Contrôle d'environnement")
    lignes.append("")
    backend = payload.get("backend_graphe") or {}
    lignes.append(
        f"- **Backend de graphe résolu** : `{backend.get('backend_resolu')}` "
        f"(attendu : `{backend.get('backend_attendu')}`). Les outils graphe du "
        "`ReportAgent` interrogent donc le Neo4j local, et non une passerelle "
        "distante."
    )
    lignes.append(
        "- **État du graphe au pré-contrôle** : "
        f"{format_metric_value(graph_ref.get('nodes'))} nœuds, "
        f"{format_metric_value(graph_ref.get('edges'))} arêtes."
    )
    etats = [
        v.get("graph_state")
        for v in variantes
        if isinstance(v.get("graph_state"), dict) and "erreur" not in v.get("graph_state")
    ]
    etats_erreur = [
        v for v in variantes if isinstance(v.get("graph_state"), dict)
        and "erreur" in v.get("graph_state")
    ]
    if not etats:
        etat_graphe = (
            "**non mesuré** — aucune variante n'a pu être mesurée, l'état du "
            "graphe à la fin de la campagne est inconnu."
        )
    elif all(etat == graph_ref for etat in etats):
        etat_graphe = (
            f"identique au pré-contrôle, mesuré sur {len(etats)} variante(s)."
        )
    else:
        etat_graphe = (
            f"**modifié** — mesuré sur {len(etats)} variante(s) : le comparatif "
            "ne peut pas être considéré comme contrôlé sur ce point."
        )
    if etats_erreur:
        etat_graphe += (
            f" {len(etats_erreur)} mesure(s) ont échoué et ne valent pas "
            "mesure : l'état du graphe n'y est pas connu."
        )
    lignes.append(
        "- **État du graphe à la fin de la campagne** : " + etat_graphe
    )
    lignes.append(
        "- **Rappel de protocole** : le graphe n'est **pas** scellé par "
        "l'empreinte des preuves. `replay_frozen` ne gèle que les interactions "
        "OASIS live ; les outils graphe interrogent toujours Neo4j. C'est le "
        "principal biais résiduel du protocole, et c'est la raison de ce "
        "garde-fou."
    )
    lignes.append("")

    # ── 4. Métriques ────────────────────────────────────────────────────
    lignes.append("## 4. Métriques par variante")
    lignes.append("")
    lignes.append(_tableau_metriques(variantes))
    lignes.append("")
    ecarts = _tableau_ecarts(variantes)
    if ecarts:
        lignes.append("**Écarts bruts**")
        lignes.append("")
        lignes.append(ecarts)
        lignes.append("")
    couverture = [
        (
            str(v.get("etiquette")),
            str((v.get("score") or {}).get("coverage_status") or "indisponible"),
        )
        for v in variantes
    ]
    lignes.append(
        "Statut de couverture : "
        + (
            " ; ".join(
                f"variante {etiquette} : {statut}"
                for etiquette, statut in couverture
            )
            if couverture
            else "indisponible — aucune variante n'a été mesurée."
        )
    )
    lignes.append("")
    lignes.append(
        "Un taux dont le dénominateur est connu et vaut zéro ne s'affiche pas : "
        "il est marqué « échec de couverture ». Il ne vaut jamais 100 %. Une "
        "métrique absente des artefacts s'affiche « indisponible », jamais 0."
    )
    lignes.append("")
    lignes.append("**Certification demandée par la barrière de publication**")
    lignes.append("")
    for variante in variantes:
        metriques = (variante.get("score") or {}).get("metrics") or {}
        statut = metriques.get("quality_publication_status")
        if variante.get("certification_refusee"):
            lignes.append(
                f"- Variante {variante.get('etiquette')} : certification "
                f"**refusée** (`{statut}`) — "
                f"{metriques.get('quality_failed_checks')} contrôle(s) "
                "critique(s) en échec. Le rapport est **complet** : ce verdict "
                "est une mesure du rapport, pas un défaut de la mesure."
            )
        elif variante.get("exclue"):
            lignes.append(
                f"- Variante {variante.get('etiquette')} : certification "
                f"indisponible (variante écartée du comparatif)."
            )
        else:
            lignes.append(
                f"- Variante {variante.get('etiquette')} : certification "
                f"`{statut}` — "
                f"{metriques.get('quality_failed_checks')} contrôle(s) en "
                f"échec, {metriques.get('quality_warning_checks')} "
                "avertissement(s)."
            )
    lignes.append("")

    # ── 5. Comparabilité ───────────────────────────────────────────────
    lignes.append("## 5. Comparabilité")
    lignes.append("")
    lignes.append(f"- **Règle appliquée** : {comparabilite.get('regle')}.")
    lignes.append(
        f"- **Verdict** : {format_metric_value(comparabilite.get('verdict'))}."
    )
    if comparabilite.get("motif"):
        motif = str(comparabilite.get("motif")).rstrip(". ")
        lignes.append(f"- **Motif** : {motif}.")
    lignes.append(
        f"- **Preuve d'identité** : `{comparabilite.get('preuve_identite') or 'aucune'}`."
    )
    lignes.append("")

    # ── 6. Coût, durée, budget ─────────────────────────────────────────
    lignes.append("## 6. Coût, durée et budget")
    lignes.append("")
    cout = payload.get("cout_estime_usd_total")
    versions_tarif = sorted(
        {
            str(v.get("pricing_table_version"))
            for v in variantes
            if v.get("pricing_table_version")
        }
    )
    version_tarif = versions_tarif[0] if len(versions_tarif) == 1 else "inconnue"
    lignes.append(
        "- **Coût facturable estimé** : "
        + (
            f"{cout} $ (estimation, grille tarifaire version "
            f"`{version_tarif}` — jamais une facture)."
            if isinstance(cout, (int, float)) and not isinstance(cout, bool)
            else "indisponible — au moins une variante n'a pas communiqué de "
            "coût mesuré."
        )
    )
    lignes.append(
        "- **Coût théorique** : somme des `usage_theoretical_cost_usd` publiés "
        "dans le tableau §4 (mêmes tokens valorisés au tarif du fournisseur, "
        "hors gratuité de la passerelle locale). C'est le montant qu'une "
        "campagne comparable coûterait sur une passerelle facturée."
    )
    lignes.append(
        f"- **Durée murale de campagne** : "
        + format_metric_value(payload.get("duree_murale_secondes"))
        + " s."
    )
    for variante in variantes:
        lignes.append(
            f"- Variante {variante.get('etiquette')} "
            f"(`{variante.get('profile_id')}`, répétition "
            f"{variante.get('repetition')}) : statut "
            f"`{variante.get('statut')}`, durée "
            + format_metric_value(variante.get("duree_secondes"))
            + " s, coût facturable estimé "
            + (
                f"{variante.get('cout_estime_usd')} $"
                if isinstance(variante.get("cout_estime_usd"), (int, float))
                and not isinstance(variante.get("cout_estime_usd"), bool)
                else "indisponible"
            )
            + "."
        )
        manquants = variante.get("artefacts_manquants") or []
        if manquants:
            lignes.append(
                f"  - Variante {variante.get('etiquette')} : artefacts "
                f"absents du dossier de rapport — {', '.join(manquants)}."
            )
        erreurs = variante.get("erreurs") or []
        if erreurs:
            lignes.append(
                f"  - Variante {variante.get('etiquette')} : "
                f"{variante.get('tentatives')} tentative(s) ; erreurs "
                "rencontrées — " + " ; ".join(str(e) for e in erreurs) + "."
            )
    lignes.append(
        "- **Plafonds** : chaque variante applique les plafonds de son profil "
        "(`max_total_cost_usd`, `max_wall_seconds`). Un plafond atteint produit "
        "un arrêt contrôlé, avec son code et son message ; le banc ne bascule "
        "jamais d'un modèle vers un autre et n'escalade jamais un effort."
    )
    arrets = [
        v
        for v in variantes
        if v.get("stop_reason") or v.get("stop_message")
    ]
    for variante in arrets:
        lignes.append(
            f"- Arrêt contrôlé sur la variante {variante.get('etiquette')} : "
            f"code `{variante.get('stop_reason')}`, message "
            f"« {variante.get('stop_message') or 'non communiqué'} »."
        )
    lignes.append("")

    # ── 7. Biais résiduels ──────────────────────────────────────────────
    lignes.append("## 7. Biais résiduels et limites")
    lignes.append("")
    lignes.append(
        "- **Le graphe n'est pas figé** : le jeu de preuves est scellé, le "
        "graphe ne l'est pas. Le garde-fou de cohérence le vérifie avant et "
        "après chaque variante, mais il ne peut pas exclure une variation "
        "minime et invisible du graphe."
    )
    lignes.append(
        "- **Une seule génération par variante** : une génération isolée ne "
        "permet pas de distinguer l'effet de l'effort de raisonnement de la "
        "variabilité stochastique du modèle. Les répétitions commandées par "
        "`--repetitions` sont le moyen de réduire cette variance ; leur "
        "nombre est indiqué ci-dessus."
    )
    lignes.append(
        "- **Effort effectif déclaré par le fournisseur** : l'effort retenu "
        "n'est déclaré effectif que si la réponse porte un objet d'usage. "
        "Sinon la valeur reste « inconnue »."
    )
    lignes.append(
        "- **Arbitrage qualitatif hors du banc** : la grille mesure des "
        "décomptes et des taux. Elle n'évalue pas la qualité rédactionnelle, "
        "qui relève de la revue aveugle."
    )
    lignes.append("")

    # ── 8. Domaines couverts et non couverts ───────────────────────────
    lignes.append("## 8. Domaines couverts et non couverts")
    lignes.append("")
    lignes.append("**Couverts par cette campagne**")
    lignes.append("")
    lignes.append(
        "- Le rejeu à preuves figées sur une simulation existante, sans "
        "relance d'OASIS ni reconstruction de graphe."
    )
    lignes.append(
        "- La consommation de tokens (entrée, sortie, réflexion, cache), la "
        "durée d'inférence et le coût estimé."
    )
    lignes.append(
        "- L'intégrité du registre des affirmations et la barrière de "
        "publication, lus dans les artefacts produits."
    )
    lignes.append(
        "- La couverture de cohorte et les statuts de décision."
    )
    lignes.append("")
    lignes.append("**Non couverts par cette campagne**")
    lignes.append("")
    lignes.append(
        "- La qualité rédactionnelle elle-même : elle est mesurée par la revue "
        "aveugle, dont le matériel est fourni à côté de ce rapport."
    )
    lignes.append(
        "- Les autres simulations, les autres domaines et les autres modèles : "
        "une campagne porte sur un seul jeu de preuves."
    )
    lignes.append(
        "- Le coût réel d'une facturation : les montants publiés sont des "
        "estimations issues de la grille tarifaire du dépôt."
    )
    lignes.append(
        "- La robustesse du rejeu face à une dérive du graphe : le banc la "
        "détecte et écarte la variante, il ne la répare pas."
    )
    lignes.append("")

    # ── 9. Matériel de revue aveugle ───────────────────────────────────
    lignes.append("## 9. Matériel de revue aveugle")
    lignes.append("")
    if dossier_campagne is not None:
        lignes.append(
            f"Le dossier de campagne `{dossier_campagne.name}` contient :"
        )
    else:
        lignes.append("Le dossier de campagne contient :")
    lignes.append("")
    lignes.append("- `variante-A.md` et `variante-B.md` : la paire anonymisée.")
    lignes.append("- `grille-aveugle.md` : la grille à remplir.")
    lignes.append(
        "- `correspondance.json` : l'association variante ↔ profil, dans un "
        "**fichier distinct**."
    )
    lignes.append("")
    lignes.append(
        "Règle de procédure : la correspondance ne s'ouvre qu'après remplissage "
        "complet de la grille. Le banc n'exécute pas cette revue : un agent ne "
        "peut pas être son propre juge aveugle."
    )
    lignes.append("")

    markdown = "\n".join(lignes).rstrip() + "\n"
    return markdown


# ============================================================================
# CLI
# ============================================================================


def _dossier_campagne_par_defaut() -> Path:
    """Dossier de campagne horodaté : une relance n'écrase pas la mesure."""
    base = (
        _project_root
        / "docs"
        / "plans"
        / "013-benchmark-llm-report-replay"
    )
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dossier = base / f"benchmark-013-{horodatage}"
    suffixe = 1
    while dossier.exists():
        suffixe += 1
        dossier = base / f"benchmark-013-{horodatage}-{suffixe}"
    return dossier


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Banc de benchmark contrôlé A/B du ReportAgent (Epic 013)."
    )
    parser.add_argument(
        "--simulation-id",
        required=True,
        help="Identifiant de la simulation dont les preuves sont rejouées",
    )
    parser.add_argument(
        "--profiles",
        default="flash-medium,flash-high",
        help=(
            "Profils du catalogue à comparer, séparés par des virgules "
            f"(catalogue : {', '.join(ReportLLMProfile.standard_profile_ids())})"
        ),
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="Nombre de générations par profil (1 par défaut)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            _project_root
            / "docs"
            / "plans"
            / "013-benchmark-llm-report-replay"
            / "rapport-qualification-epic-013.md"
        ),
        help="Chemin de sortie du rapport Markdown formel",
    )
    parser.add_argument(
        "--campaign-dir",
        type=Path,
        default=None,
        help=(
            "Dossier de campagne (charge utile JSON, paire anonymisée, grille, "
            "correspondance). Par défaut : benchmark-013-<horodatage> dans le "
            "dossier de plan de l'epic."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Pré-contrôle seul : affiche l'empreinte, l'état du graphe, les "
            "profils du catalogue et les plafonds, sans générer aucun rapport."
        ),
    )
    parser.add_argument(
        "--expected-graph-backend",
        default="graphiti",
        help="Backend de graphe attendu par le banc (défaut : graphiti)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Affichage détaillé des métriques d'exécution",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("      BANC DE BENCHMARK CONTRÔLÉ A/B — EPIC 013 (Story 013-6)          ")
    print(f"      Simulation : {args.simulation_id:<50}")
    print("=" * 80)

    profils = tuple(
        profil.strip() for profil in str(args.profiles).split(",") if profil.strip()
    )
    if not profils:
        print("Aucun profil demandé.")
        return 1
    inconnus = [
        profil
        for profil in profils
        if profil not in ReportLLMProfile.standard_profile_ids()
    ]
    if inconnus:
        print(
            "Profils absents du catalogue : "
            f"{', '.join(inconnus)} (catalogue : "
            f"{', '.join(ReportLLMProfile.standard_profile_ids())})."
        )
        return 1

    try:
        configuration = ConfigurationCampagne(
            simulation_id=args.simulation_id,
            profils=profils,
            repetitions=args.repetitions,
            backend_graphe_attendu=args.expected_graph_backend,
        )
    except ValueError as erreur:
        # Une configuration invalide est un refus lisible, jamais une traceback
        # Python dans la sortie d'un outillage de qualification.
        print(f"Configuration invalide : {erreur}")
        return 1

    # ── Pré-contrôle (environnement, préconditions, preuves, graphe) ───
    conforme, precontrole = executer_precontrole(configuration)
    backend_details = precontrole.get("backend_graphe") or {}
    print("\n--- [Pré-contrôle] Backend de graphe ---")
    print(f"  résolu   : {backend_details.get('backend_resolu')}")
    print(f"  attendu  : {backend_details.get('backend_attendu')}")

    precond_details = precontrole.get("preconditions") or {}
    if precond_details:
        print("\n--- [Pré-contrôle] Préconditions de génération ---")
        for cle in (
            "simulation_trouvee",
            "projet_trouve",
            "projet_statut",
            "graph_id",
            "graph_id_concordant",
            "simulation_requirement",
        ):
            print(f"  {cle:<24}: {precond_details.get(cle)}")

    preuves = precontrole.get("preuves") or {}
    print("\n--- [Pré-contrôle] Empreinte des preuves figées ---")
    if preuves.get("conforme"):
        evidence = precontrole.get("evidence") or {}
        print(f"  [OK=True] sha256      : {evidence.get('sha256_hash')}")
        print(f"            snapshot   : {evidence.get('snapshot_id')}")
        print(f"            événements : {evidence.get('total_events')}")
        print(f"            acteurs    : {evidence.get('total_actors')}")
    else:
        print(f"  [OK=False] {preuves.get('motif')}")

    graphe = precontrole.get("graphe") or {}
    print("\n--- [Pré-contrôle] État du graphe ---")
    if graphe.get("conforme"):
        print(
            f"  [OK=True] graphe {graphe.get('graph_id')} : "
            f"{graphe.get('nodes')} nœuds, {graphe.get('edges')} arêtes"
        )
    else:
        print(f"  [OK=False] {graphe.get('motif')}")

    if not conforme:
        print(f"\n  [OK=False] {precontrole.get('motif')}")
        print("\n>>> VERDICT FINAL : NON CONCLUANT (pré-contrôle non conforme)")
        print("=" * 80)
        return 1

    # ── Catalogue et plafonds ──────────────────────────────────────────
    print("\n--- [Pré-contrôle] Profils du catalogue et plafonds ---")
    for profile_id in profils:
        profil = ReportLLMProfile.get_standard_profile(profile_id)
        if profil is None:
            continue
        print(
            f"  {profile_id:<18} modèle={profil.model:<22} "
            f"effort={str(profil.reasoning_effort):<8} "
            f"plafond={profil.max_total_cost_usd} $ / "
            f"{profil.max_wall_seconds} s"
        )

    if args.dry_run:
        print("\n--- [Mode rehearsal] Aucune génération ---")
        print("  Aucun dossier de rapport n'a été créé.")
        print("\n>>> VERDICT FINAL : pré-contrôle conforme (aucune campagne exécutée)")
        print("=" * 80)
        return 0

    # ── Campagne ───────────────────────────────────────────────────────
    print(f"\n--- [Campagne] {len(profils)} profil(s) × {args.repetitions} répétition(s) ---")
    payload = executer_campagne(configuration, precontrole=(conforme, precontrole))
    for variante in payload.get("variantes", []):
        marque = "EXCLUE" if variante.get("exclue") else "incluse"
        print(
            f"  [variante {variante.get('etiquette')}] {variante.get('profile_id')} "
            f"×{variante.get('repetition')} → {variante.get('report_id')} "
            f"({variante.get('statut')}, {marque})"
        )
        if variante.get("motif_exclusion"):
            print(f"      motif : {variante.get('motif_exclusion')}")

    # ── Construction et contrôle du rapport, AVANT toute écriture ──────
    # Un rapport non conforme ne doit pas être laissé sur le disque.
    dossier_campagne = args.campaign_dir or _dossier_campagne_par_defaut()
    markdown = construire_rapport_qualification(
        payload, dossier_campagne=dossier_campagne
    )
    marqueurs = marqueurs_interdits(markdown)
    if marqueurs:
        print(
            "\n  [ERREUR] Le rapport contient des marqueurs de désignation "
            f"interdits : {', '.join(marqueurs)}. Rien n'a été écrit."
        )
        return 1

    # ── Écriture des artefacts ─────────────────────────────────────────
    dossier_campagne.mkdir(parents=True, exist_ok=True)

    charge = dict(payload)
    charge["dossier_campagne"] = str(dossier_campagne)
    # La charge utile passe par la barrière d'étanchéité du dépôt : ni clé,
    # ni URL de passerelle, ni prompt ne doivent y figurer (NFR-4).
    charge = sanitize_usage_payload(charge)
    (dossier_campagne / "mesure-benchmark-013.json").write_text(
        json.dumps(charge, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    correspondance = ecrire_materiel_aveugle(
        dossier_campagne, payload, payload.get("variantes", [])
    )
    declassement = [
        lettre
        for lettre, value in (correspondance.get("declassement") or {}).items()
        if value
    ]
    croises = [
        lettre
        for lettre, valeurs in (
            correspondance.get("declassement_croise") or {}
        ).items()
        if valeurs
    ]
    if declassement:
        print(
            "\n  [Avertissement] Le corps d'une variante anonymisée mentionne "
            f"son profil ({', '.join(declassement)}) : la revue aveugle est "
            "déclarée compromise pour ces variantes."
        )
    if croises:
        print(
            "\n  [Avertissement] Le corps d'une variante anonymisée mentionne "
            f"le profil d'une autre variante ({', '.join(croises)}) : la "
            "correspondance est compromise pour la paire."
        )

    chemin_rapport = Path(args.output)
    chemin_rapport.parent.mkdir(parents=True, exist_ok=True)
    chemin_rapport.write_text(markdown, encoding="utf-8")
    print(f"\n[OK] Charge utile machine : {dossier_campagne / 'mesure-benchmark-013.json'}")
    print(f"[OK] Rapport formel      : {args.output}")
    print(f"[OK] Matériel aveugle     : {dossier_campagne}")

    if args.verbose:
        print("\n[VERBOSE] Détails de la campagne :")
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    print("=" * 80)
    print(f">>> VERDICT FINAL : {payload.get('verdict')}")
    if payload.get("motif_verdict"):
        print(f"    Motif : {payload.get('motif_verdict')}")
    print("=" * 80)
    return 0 if payload.get("verdict") == VERDICT_CONTROLEE else 1


if __name__ == "__main__":
    sys.exit(main())
