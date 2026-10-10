#!/usr/bin/env python3
"""Outil autonome de purge distante sécurisée de graphes Zep Cloud (Epic 006, Story 006-3).

Ce script permet de supprimer de manière contrôlée, confirmée et irréversible
les graphes de connaissances obsolètes ou déjà migrés sur le compte SaaS Zep Cloud.

Fonctionnalités :
1. Suppression ciblée d'un graphe unique (--graph-id) ou de l'ensemble du compte (--all).
2. Sécurité renforcée : double confirmation interactive (saisie obligatoire de l'identifiant
   du graphe ou de 'SUPPRIMER TOUT') ou flag explicite --yes en environnement automatisé/CI.
3. Mode simulation (--dry-run) : inventorie les cibles sans exécuter de suppression.
4. Mode hors-ligne (--mock) : exécution déterministe pour la CI sans compte Zep réel ni réseau.
5. Zéro secret : masquage strict de ZEP_API_KEY dans les sorties consoles et rapports.
6. Exports des comptes-rendus d'exécution aux formats Markdown et JSON.

Usage :
    # Mode démonstration / CI hors-ligne (déterministe)
    uv run python scripts/purger_graphes_zep.py --mock --yes

    # Simulation d'une purge d'un graphe sans exécution réelle
    uv run python scripts/purger_graphes_zep.py --graph-id "rapport_an_2506" --dry-run

    # Purge d'un graphe avec confirmation interactive
    uv run python scripts/purger_graphes_zep.py --graph-id "rapport_an_2506"

    # Purge d'un graphe en mode non-interactif / script
    uv run python scripts/purger_graphes_zep.py --graph-id "rapport_an_2506" --yes

    # Purge de TOUS les graphes avec export de rapport
    uv run python scripts/purger_graphes_zep.py --all --output-report purge.md --output-json purge.json

    # Mode silencieux
    uv run python scripts/purger_graphes_zep.py --mock --yes --quiet
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

# Configuration du PYTHONPATH et chargement de .env
_scripts_dir = Path(__file__).resolve().parent
_backend_dir = _scripts_dir.parent
_project_root = _backend_dir.parent
sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv

for _candidate in (_project_root / ".env", _backend_dir / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate)

from app.config import Config
from app.utils.logger import get_logger
from app.utils.zep import get_zep_client

logger = get_logger("mirofish.scripts.purger_graphes_zep")


# ==============================================================================
# 1. Masquage de Secret
# ==============================================================================


def masquer_secret(secret: Optional[str]) -> str:
    """Masque un token ou une clé API pour éviter toute fuite dans les logs et sorties."""
    if not secret:
        return "<non défini>"
    s = str(secret).strip()
    if not s:
        return "<non défini>"
    if len(s) <= 8:
        return "***"
    return f"{s[:3]}...{s[-2:]}"


def assainir_message_erreur(message: str, secrets: Optional[List[str]] = None) -> str:
    """Remplace toute occurrence de clés secrètes dans un message d'erreur."""
    result = str(message)
    if secrets:
        for sec in secrets:
            if sec and len(sec.strip()) >= 4:
                result = result.replace(sec.strip(), masquer_secret(sec))
    # Masque également les motifs de type clé zep (z_...)
    result = re.sub(r"z_[a-zA-Z0-9_\-]{8,}", "[CLE_ZEP_MASQUEE]", result)
    return result


# ==============================================================================
# 2. Dataclasses et Modèles de Données
# ==============================================================================


@dataclass
class PurgeTarget:
    """Cible identifiée pour la purge sur Zep Cloud."""

    graph_id: str
    name: str = ""
    node_count: int = 0
    edge_count: int = 0
    status: str = "PENDING"  # PENDING, PURGED, FAILED, SKIPPED_DRY_RUN

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'instance en dictionnaire sérialisable."""
        return asdict(self)


@dataclass
class PurgeResult:
    """Résultat de la tentative de purge pour un graphe."""

    graph_id: str
    status: str  # PURGED, FAILED, SKIPPED_DRY_RUN
    success: bool
    error_message: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'instance en dictionnaire sérialisable."""
        return asdict(self)


@dataclass
class PurgeReport:
    """Rapport global consolidé de l'opération de purge."""

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    total_targeted: int = 0
    total_purged: int = 0
    total_failed: int = 0
    total_skipped: int = 0
    dry_run: bool = False
    mock: bool = False
    results: List[PurgeResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convertit le rapport en dictionnaire sérialisable."""
        return {
            "timestamp": self.timestamp,
            "total_targeted": self.total_targeted,
            "total_purged": self.total_purged,
            "total_failed": self.total_failed,
            "total_skipped": self.total_skipped,
            "dry_run": self.dry_run,
            "mock": self.mock,
            "duration_seconds": round(self.duration_seconds, 3),
            "errors": self.errors,
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        """Sérialise le rapport au format JSON indenté."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Génère un rapport synthétique au format Markdown."""
        lines = [
            "# Rapport de Purge Zep Cloud (Story 006-3)",
            "",
            f"- **Date d'exécution** : `{self.timestamp}`",
            f"- **Mode** : `{'MOCK' if self.mock else ('DRY-RUN' if self.dry_run else 'REEL')}`",
            f"- **Graphes ciblés** : `{self.total_targeted}`",
            f"- **Graphes purgés** : `{self.total_purged}`",
            f"- **Graphes en échec** : `{self.total_failed}`",
            f"- **Graphes ignorés (dry-run)** : `{self.total_skipped}`",
            f"- **Durée totale** : `{self.duration_seconds:.2f} s`",
            "",
            "## Détail des opérations",
            "",
            "| Graphe ID | Statut | Succès | Durée (s) | Message / Erreur |",
            "|---|---|---|---|---|",
        ]

        if not self.results:
            lines.append("| *(aucun graphe ciblé)* | - | - | - | - |")
        else:
            for r in self.results:
                msg = (r.error_message or "").replace("|", "\\|")
                succ = "Oui" if r.success else "Non"
                lines.append(
                    f"| `{r.graph_id}` | `{r.status}` | {succ} | {r.duration_seconds:.2f} | {msg} |"
                )

        if self.errors:
            lines.extend([
                "",
                "## Erreurs globales",
                "",
            ])
            for err in self.errors:
                lines.append(f"- ⚠️ {err}")

        lines.append("")
        return "\n".join(lines)


# ==============================================================================
# 3. Logique d'inventaire et Orchestrateur de Purge
# ==============================================================================


class ZepPurgeManager:
    """Gestionnaire de suppression sécurisée des graphes hébergés sur Zep Cloud."""

    def __init__(self, zep_client: Optional[Any] = None, api_key: Optional[str] = None) -> None:
        self.zep_client = zep_client
        self.api_key = api_key

    def inventorier_cibles(
        self,
        graph_id: Optional[str] = None,
        purge_all: bool = False,
        mock_mode: bool = False,
    ) -> List[PurgeTarget]:
        """Établit la liste des cibles à purger selon les options demandées."""
        if mock_mode:
            if graph_id:
                return [PurgeTarget(graph_id=graph_id.strip(), name=f"Mock {graph_id}")]
            elif purge_all:
                return [
                    PurgeTarget(graph_id="mock_graphe_1", name="Mock Graphe 1", node_count=12, edge_count=8),
                    PurgeTarget(graph_id="mock_graphe_2", name="Mock Graphe 2", node_count=4, edge_count=3),
                    PurgeTarget(graph_id="mock_graphe_3", name="Mock Graphe 3", node_count=20, edge_count=15),
                ]
            else:
                return [PurgeTarget(graph_id="mock_graph_demo", name="Mock Demo Graph")]

        if graph_id:
            clean_id = graph_id.strip()
            return [PurgeTarget(graph_id=clean_id, name=clean_id)]

        if purge_all:
            if self.zep_client is None:
                raise ValueError("Client Zep Cloud non configuré pour inventorier l'ensemble des graphes.")
            return self._recuperer_tous_les_graphes_distants()

        return []

    def _recuperer_tous_les_graphes_distants(self) -> List[PurgeTarget]:
        """Interroge Zep Cloud pour lister l'intégralité des graphes du compte."""
        targets: List[PurgeTarget] = []
        page_number = 1
        page_size = 50

        while True:
            try:
                response = self.zep_client.graph.list_all(
                    page_number=page_number,
                    page_size=page_size,
                )
            except Exception as exc:
                err_msg = assainir_message_erreur(str(exc), [self.api_key] if self.api_key else None)
                logger.error("Erreur lors de la récupération de la liste des graphes Zep : %s", err_msg)
                raise RuntimeError(f"Impossible de lister les graphes Zep Cloud : {err_msg}") from exc

            graphs = getattr(response, "graphs", None)
            if graphs is None and isinstance(response, list):
                graphs = response
            elif graphs is None and isinstance(response, dict):
                graphs = response.get("graphs") or []

            if not graphs:
                break

            for g in graphs:
                g_id = ""
                g_name = ""
                if isinstance(g, dict):
                    g_id = g.get("graph_id") or g.get("id") or ""
                    g_name = g.get("name") or g_id
                else:
                    g_id = getattr(g, "graph_id", None) or getattr(g, "id", "") or ""
                    g_name = getattr(g, "name", "") or g_id

                if g_id:
                    targets.append(PurgeTarget(graph_id=str(g_id), name=str(g_name)))

            # Arrêt si moins d'éléments que la taille de page
            if len(graphs) < page_size:
                break
            page_number += 1

        return targets

    def purger_graphe(
        self,
        target: PurgeTarget,
        dry_run: bool = False,
        mock_mode: bool = False,
    ) -> PurgeResult:
        """Exécute la suppression d'un graphe donné ou simule l'action."""
        start_time = time.time()
        clean_id = target.graph_id.strip()

        # 1. Mode Dry-Run : pas d'exécution réseau
        if dry_run:
            duration = time.time() - start_time
            logger.info("[DRY-RUN] Suppression simulée pour le graphe '%s'.", clean_id)
            target.status = "SKIPPED_DRY_RUN"
            return PurgeResult(
                graph_id=clean_id,
                status="SKIPPED_DRY_RUN",
                success=True,
                error_message="Simulation dry-run (aucune suppression effectuée)",
                duration_seconds=duration,
            )

        # 2. Mode Mock : simulation déterministe
        if mock_mode:
            duration = time.time() - start_time
            logger.info("[MOCK] Suppression mockée réussie pour '%s'.", clean_id)
            target.status = "PURGED"
            return PurgeResult(
                graph_id=clean_id,
                status="PURGED",
                success=True,
                duration_seconds=duration,
            )

        # 3. Mode Réel : appel SDK Zep client.graph.delete
        if self.zep_client is None:
            duration = time.time() - start_time
            err = "Client Zep non configuré pour la suppression."
            target.status = "FAILED"
            return PurgeResult(
                graph_id=clean_id,
                status="FAILED",
                success=False,
                error_message=err,
                duration_seconds=duration,
            )

        try:
            logger.info("Suppression du graphe distant '%s' sur Zep Cloud...", clean_id)
            self.zep_client.graph.delete(graph_id=clean_id)
            duration = time.time() - start_time
            target.status = "PURGED"
            logger.info("✓ Graphe '%s' supprimé avec succès sur Zep Cloud.", clean_id)
            return PurgeResult(
                graph_id=clean_id,
                status="PURGED",
                success=True,
                duration_seconds=duration,
            )
        except Exception as exc:
            duration = time.time() - start_time
            raw_err = f"{type(exc).__name__}: {exc}"
            clean_err = assainir_message_erreur(raw_err, [self.api_key] if self.api_key else None)
            target.status = "FAILED"
            logger.error("Échec de suppression pour le graphe '%s' : %s", clean_id, clean_err)
            return PurgeResult(
                graph_id=clean_id,
                status="FAILED",
                success=False,
                error_message=clean_err,
                duration_seconds=duration,
            )

    def executer_purge(
        self,
        cibles: List[PurgeTarget],
        dry_run: bool = False,
        mock_mode: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> PurgeReport:
        """Orchestre la purge séquentielle d'une liste de cibles."""
        report = PurgeReport(
            total_targeted=len(cibles),
            dry_run=dry_run,
            mock=mock_mode,
        )
        start_time = time.time()

        for idx, cible in enumerate(cibles, start=1):
            if progress_callback:
                progress_callback(idx, len(cibles), cible.graph_id)

            res = self.purger_graphe(cible, dry_run=dry_run, mock_mode=mock_mode)
            report.results.append(res)

            if res.status == "PURGED":
                report.total_purged += 1
            elif res.status == "SKIPPED_DRY_RUN":
                report.total_skipped += 1
            else:
                report.total_failed += 1
                if res.error_message:
                    report.errors.append(f"Graphe {res.graph_id} : {res.error_message}")

        report.duration_seconds = time.time() - start_time
        return report


# ==============================================================================
# 4. Confirmation Interactive et Sécurité
# ==============================================================================


def demander_confirmation(
    cibles: List[PurgeTarget],
    force_yes: bool = False,
    is_interactive: Optional[bool] = None,
    input_func: Optional[Callable[[str], str]] = None,
) -> Tuple[bool, str]:
    """Valide les conditions de confirmation avant d'autoriser la purge destructive.

    Returns:
        (autorise, motif) : Booléen indiquant l'autorisation et message explicatif.
    """
    if not cibles:
        return True, "Aucune cible à supprimer."

    # 1. Flag --yes explicite
    if force_yes:
        logger.info("Confirmation automatique via le flag --yes.")
        return True, "Confirmation accordée via le flag --yes."

    # 2. Détection de l'interactivité stdin
    interactive = sys.stdin.isatty() if is_interactive is None else is_interactive
    ask = input_func or input

    if not interactive:
        err = (
            "Refus de sécurité : En mode non-interactif, vous devez spécifier "
            "le flag '--yes' pour confirmer la suppression définitive."
        )
        logger.warning(err)
        return False, err

    # 3. Confirmation interactive pour un graphe unique
    if len(cibles) == 1:
        target_id = cibles[0].graph_id
        prompt_msg = (
            f"\n⚠️  ATTENTION : La suppression sur Zep Cloud est DÉFINITIVE et IRRÉVERSIBLE.\n"
            f"Voulez-vous vraiment purger le graphe '{target_id}' ?\n"
            f"Pour confirmer, saisissez exactement l'identifiant '{target_id}' : "
        )
        try:
            saisie = ask(prompt_msg).strip()
        except (EOFError, KeyboardInterrupt):
            return False, "Saisie interrompue par l'utilisateur."

        if saisie == target_id:
            return True, f"Identifiant '{target_id}' confirmé avec succès."
        else:
            return False, f"Confirmation incorrecte (saisie : '{saisie}' != attendu : '{target_id}')."

    # 4. Confirmation interactive pour plusieurs graphes (--all)
    prompt_msg = (
        f"\n🚨 DANGER EXTRÊME : Vous êtes sur le point de purger {len(cibles)} graphe(s) sur Zep Cloud !\n"
        f"Cette opération détruira l'ensemble des connaissances distantes sans possibilité de récupération.\n"
        f"Pour confirmer la suppression TOTALE, saisissez exactement 'SUPPRIMER TOUT' : "
    )
    try:
        saisie = ask(prompt_msg).strip()
    except (EOFError, KeyboardInterrupt):
        return False, "Saisie interrompue par l'utilisateur."

    if saisie in ("SUPPRIMER TOUT", "DELETE ALL"):
        return True, "Confirmation collective accordée ('SUPPRIMER TOUT')."
    else:
        return False, f"Confirmation incorrecte (saisie : '{saisie}' != attendu : 'SUPPRIMER TOUT')."


# ==============================================================================
# 5. CLI et Parsing des Arguments
# ==============================================================================


def parser_arguments(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse et valide les arguments de ligne de commande."""
    parser = argparse.ArgumentParser(
        description="Outil autonome de purge distante sécurisée de graphes Zep Cloud (Epic 006, Story 006-3).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--graph-id",
        type=str,
        default=None,
        help="Identifiant du graphe Zep Cloud à purger (ex: 'rapport_an_2506').",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Cibler l'ensemble des graphes présents sur le compte Zep Cloud.",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Clé ZEP_API_KEY. Si omise, lue depuis l'environnement ou .env.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="Confirmer automatiquement la suppression sans invite interactive.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simuler l'opération : inventorie les cibles sans exécuter de suppression réelle.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Mode simulation déterministe hors-ligne (pour tests unitaires et CI).",
    )
    parser.add_argument(
        "--output-report",
        type=str,
        default=None,
        help="Chemin du fichier Markdown pour l'export du compte-rendu.",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Chemin du fichier JSON pour l'export des résultats structurés.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Mode silencieux, réduit les messages console au strict minimum.",
    )

    return parser.parse_args(args)


# ==============================================================================
# 6. Point d'Entrée Principal
# ==============================================================================


def main(cli_args: Optional[List[str]] = None) -> int:
    """Point d'entrée exécutable de l'outil de purge Zep Cloud."""
    args = parser_arguments(cli_args)

    if not args.quiet:
        print("=" * 72)
        print("  MiroFish — Outil de Purge Sécurisée Zep Cloud (Story 006-3)")
        print("=" * 72)

    # 1. Vérification des options mutuellement exclusives ou manquantes
    if args.graph_id and args.all:
        logger.error("Options incompatibles : --graph-id et --all ne peuvent pas être spécifiés simultanément.")
        print("Erreur : Spécifiez soit --graph-id soit --all, pas les deux.", file=sys.stderr)
        return 1

    if not args.graph_id and not args.all and not args.mock:
        logger.error("Aucune cible spécifiée : précisez --graph-id <ID> ou --all.")
        print("Erreur : Vous devez spécifier --graph-id <ID> ou --all.", file=sys.stderr)
        return 1

    # 2. Gestion de la clé Zep
    api_key: Optional[str] = None
    zep_client: Optional[Any] = None

    if not args.mock:
        api_key = args.api_key or os.environ.get("ZEP_API_KEY") or getattr(Config, "ZEP_API_KEY", None)
        if not api_key:
            logger.error("ZEP_API_KEY introuvable. Définissez-la dans .env ou via --api-key.")
            print("Erreur : Clé Zep manquante. Spécifiez --api-key ou définissez ZEP_API_KEY.", file=sys.stderr)
            return 1

        try:
            zep_client = get_zep_client(api_key=api_key)
        except Exception as exc:
            err_msg = assainir_message_erreur(str(exc), [api_key])
            logger.error("Impossible d'initialiser le client Zep : %s", err_msg)
            print(f"Erreur client Zep : {err_msg}", file=sys.stderr)
            return 1

    # 3. Initialisation du gestionnaire et inventaire des cibles
    manager = ZepPurgeManager(zep_client=zep_client, api_key=api_key)

    try:
        cibles = manager.inventorier_cibles(
            graph_id=args.graph_id,
            purge_all=args.all,
            mock_mode=args.mock,
        )
    except Exception as exc:
        err_msg = assainir_message_erreur(str(exc), [api_key] if api_key else None)
        logger.error("Échec de l'inventaire des cibles : %s", err_msg)
        print(f"Erreur d'inventaire : {err_msg}", file=sys.stderr)
        return 1

    if not cibles:
        if not args.quiet:
            print("Aucun graphe correspondant trouvé sur Zep Cloud. Rien à purger.")
        return 0

    if not args.quiet:
        print(f"\nCibles identifiées pour la purge ({len(cibles)} au total) :")
        for c in cibles:
            detail = f" (nœuds: {c.node_count}, arêtes: {c.edge_count})" if c.node_count else ""
            print(f"  - [{c.graph_id}] {c.name}{detail}")
        print()

    # 4. Mode simulation Dry-Run
    if args.dry_run:
        if not args.quiet:
            print("Mode simulation (--dry-run) actif : aucune suppression ne sera effectuée.\n")
        report = manager.executer_purge(cibles, dry_run=True, mock_mode=args.mock)
    else:
        # 5. Validation de sécurité / confirmation
        confirme, motif = demander_confirmation(cibles, force_yes=args.yes)
        if not confirme:
            logger.warning("Purge annulée : %s", motif)
            if not args.quiet:
                print(f"\n⛔ Opération annulée : {motif}")
            return 1 if "Refus de sécurité" in motif else 0

        if not args.quiet:
            print(f"\nExécution de la purge en cours...")

        def _cli_progress(curr: int, tot: int, gid: str) -> None:
            if not args.quiet:
                pct = (curr / tot * 100) if tot else 100
                print(f"  -> Purge [{curr}/{tot}] ({pct:.0f} %) : {gid}...", end="\r", flush=True)

        report = manager.executer_purge(
            cibles,
            dry_run=False,
            mock_mode=args.mock,
            progress_callback=_cli_progress,
        )
        if not args.quiet:
            print()

    # 6. Affichage du compte-rendu
    if not args.quiet:
        print("\n" + report.to_markdown())

    # 7. Exports optionnels
    if args.output_report:
        report_path = Path(args.output_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report.to_markdown(), encoding="utf-8")
        if not args.quiet:
            print(f"✓ Rapport Markdown exporté : {report_path}")

    if args.output_json:
        json_path = Path(args.output_json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(report.to_json(), encoding="utf-8")
        if not args.quiet:
            print(f"✓ Données JSON exportées : {json_path}")

    # Code retour : 0 si aucune erreur de suppression
    return 0 if report.total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
