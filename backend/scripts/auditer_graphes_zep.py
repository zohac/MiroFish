#!/usr/bin/env python3
"""Sonde d'audit et d'inventaire d'un compte Zep Cloud (Epic 006, Story 006-1).

Ce script inspecte un compte Zep Cloud afin de :
1. Recenser l'ensemble des graphes distants (graph_id / group_id).
2. Dénombrer de manière exhaustive les entités (nœuds), relations (arêtes) et épisodes.
3. Analyser la présence locale des documents sources associés dans uploads/documents/.
4. Établir une recommandation d'arbitrage (« Migrer vs Jeter vs Purger ») selon l'arbre de décision de l'Epic 006.
5. Exporter les résultats au format JSON normalisé et en rapport synthétique Markdown.

Usage :
    # Mode démonstration hors-ligne sans clé Zep (déterministe)
    uv run python scripts/auditer_graphes_zep.py --mock

    # Audit réel avec clé du fichier .env
    uv run python scripts/auditer_graphes_zep.py

    # Audit avec clé explicite et exports de fichiers
    uv run python scripts/auditer_graphes_zep.py --api-key "z_..." --output-json audit.json --output-report audit.md

    # Mode silencieux
    uv run python scripts/auditer_graphes_zep.py --mock --quiet --output-json audit.json
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
from typing import Any, Dict, List, Optional, Tuple
import unicodedata

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
from app.utils.zep import call_zep_read_with_retry, get_zep_client
from app.utils.zep_paging import fetch_all_edges, fetch_all_nodes

logger = get_logger("mirofish.scripts.audit_zep")

# Constantes d'arbitrage
ACTION_REBUILD_LOCAL = "REBUILD_LOCAL"
ACTION_MIGRATE = "MIGRATE"
ACTION_PURGE = "PURGE"

LABEL_REBUILD_LOCAL = "Jeter / Re-ingérer en local (0 €)"
LABEL_MIGRATE = "Migrer vers Neo4j local (ETL)"
LABEL_PURGE = "Purger le graphe distant"


@dataclass
class GraphSummary:
    """Synthèse d'un graphe distant audité."""

    graph_id: str
    name: str
    description: Optional[str] = None
    created_at: Optional[str] = None
    node_count: int = 0
    edge_count: int = 0
    episode_count: int = 0
    has_local_documents: bool = False
    local_document_matches: List[str] = field(default_factory=list)
    has_error: bool = False
    error_message: Optional[str] = None
    recommendation: str = ACTION_MIGRATE
    recommendation_label: str = LABEL_MIGRATE
    recommendation_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'instance en dictionnaire sérialisable."""
        return asdict(self)


@dataclass
class AuditReport:
    """Rapport global d'audit d'un compte Zep Cloud."""

    timestamp: str
    total_graphs: int
    total_nodes: int
    total_edges: int
    total_episodes: int
    graphs: List[GraphSummary]
    recommendations_breakdown: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convertit le rapport complet en dictionnaire."""
        return {
            "timestamp": self.timestamp,
            "total_graphs": self.total_graphs,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "total_episodes": self.total_episodes,
            "recommendations_breakdown": dict(self.recommendations_breakdown),
            "graphs": [g.to_dict() for g in self.graphs],
        }

    def to_json(self, indent: int = 2) -> str:
        """Exporte le rapport en JSON normalisé."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Génère une présentation synthétique et lisible en Markdown."""
        lines: List[str] = []
        lines.append(f"# Rapport d'audit Zep Cloud — {self.timestamp}")
        lines.append("")
        lines.append("## Synthèse globale")
        lines.append("")
        lines.append(f"- **Nombre total de graphes** : {self.total_graphs}")
        lines.append(f"- **Total des nœuds (entités)** : {self.total_nodes}")
        lines.append(f"- **Total des relations (arêtes)** : {self.total_edges}")
        lines.append(f"- **Total des épisodes** : {self.total_episodes}")
        lines.append("")
        lines.append("### Répartition des recommandations d'arbitrage")
        lines.append("")
        lines.append("| Action recommandée | Nombre de graphes | Proportion |")
        lines.append("|---|---|---|")
        for action, count in self.recommendations_breakdown.items():
            pct = (count / self.total_graphs * 100) if self.total_graphs > 0 else 0
            label = (
                LABEL_REBUILD_LOCAL
                if action == ACTION_REBUILD_LOCAL
                else LABEL_MIGRATE
                if action == ACTION_MIGRATE
                else LABEL_PURGE
            )
            lines.append(f"| **{label}** (`{action}`) | {count} | {pct:.1f} % |")
        lines.append("")
        lines.append("## Détail par graphe")
        lines.append("")
        if not self.graphs:
            lines.append("_Aucun graphe recensé sur ce compte Zep Cloud._")
            lines.append("")
            return "\n".join(lines)

        lines.append(
            "| Graph ID | Nom | Création | Nœuds | Arêtes | Épisodes | Documents locaux | Arbitrage | Motif |"
        )
        lines.append(
            "|---|---|---|---|---|---|---|---|---|"
        )
        for g in self.graphs:
            doc_str = (
                f"✅ Oui ({', '.join(g.local_document_matches)})"
                if g.has_local_documents
                else "❌ Non"
            )
            # Remplacement des sauts de ligne ou pipes dans les descriptions
            clean_name = g.name.replace("|", "-")
            clean_reason = g.recommendation_reason.replace("|", "-")
            created_str = g.created_at or "N/A"
            lines.append(
                f"| `{g.graph_id}` | {clean_name} | {created_str} | {g.node_count} | {g.edge_count} | {g.episode_count} | {doc_str} | **{g.recommendation_label}** | {clean_reason} |"
            )
        lines.append("")
        return "\n".join(lines)


def detecter_documents_locaux(
    graph_id: str,
    graph_name: str,
    episodes_descriptions: Optional[List[str]] = None,
    uploads_dir: Optional[Path] = None,
) -> Tuple[bool, List[str]]:
    """Détecte si des documents locaux dans uploads/documents correspondent à un graphe.

    Vérifie par correspondance de noms, de stems et de références documentaires.
    """
    if uploads_dir is None:
        uploads_dir = _backend_dir / "uploads" / "documents"

    if not uploads_dir.exists():
        return False, []

    # Extraction des fichiers existants dans le dossier
    fichiers_locaux = [
        f for f in uploads_dir.iterdir() if f.is_file() and not f.name.startswith(".")
    ]
    if not fichiers_locaux:
        return False, []

    matches: List[str] = []

    def normaliser(texte: str) -> str:
        decomposed = unicodedata.normalize("NFKD", texte)
        ascii_clean = "".join(c for c in decomposed if not unicodedata.combining(c))
        return re.sub(r"[^a-zA-Z0-9]", "", ascii_clean).lower()

    id_norm = normaliser(graph_id)
    name_norm = normaliser(graph_name)

    descriptions_norm = [
        normaliser(desc) for desc in (episodes_descriptions or []) if desc
    ]

    for f in fichiers_locaux:
        filename = f.name
        stem = f.stem
        filename_norm = normaliser(filename)
        stem_norm = normaliser(stem)

        # 1. Correspondance exacte ou inclusion significative
        is_match = False
        if stem_norm and (stem_norm in id_norm or stem_norm in name_norm):
            is_match = True
        elif id_norm and (id_norm in stem_norm or id_norm in filename_norm):
            is_match = True
        elif len(name_norm) >= 5 and (name_norm in filename_norm or filename_norm in name_norm):
            is_match = True
        else:
            # 2. Vérification dans les descriptions des épisodes
            for desc_norm in descriptions_norm:
                if stem_norm in desc_norm or filename_norm in desc_norm:
                    is_match = True
                    break

        if is_match and filename not in matches:
            matches.append(filename)

    return (len(matches) > 0), matches


def determiner_arbitrage(
    graph_id: str,
    name: str,
    node_count: int,
    edge_count: int,
    has_local_documents: bool,
    local_document_matches: List[str],
    has_error: bool = False,
    error_message: Optional[str] = None,
) -> Tuple[str, str, str]:
    """Applique l'arbre de décision formel « Migrer vs Jeter vs Purger » de l'Epic 006.

    Règles :
    0. Si une anomalie de lecture est survenue -> MIGRATE (sécurité : purge proscrite par précaution).
    1. Si le graphe est vide ou artefact de test éphémère -> PURGE.
    2. Si les documents sources sont présents localement -> REBUILD_LOCAL.
    3. Si le graphe est non vide et les documents sources sont absents -> MIGRATE.
    """
    # Règle 0 : Sécurité absolue en cas d'erreur partielle d'extraction
    if has_error:
        err_detail = f" ({error_message})" if error_message else ""
        return (
            ACTION_MIGRATE,
            LABEL_MIGRATE,
            f"Anomalie lors de l'extraction des métriques{err_detail}. Purge proscrite par précaution ; examen ou migration directe recommandé.",
        )

    # Règle 1 : Graphe vide ou artefact de test éphémère (détection stricte avec délimiteurs)
    ephemeral_pattern = re.compile(
        r"(?:^|[_\-\s])(test|tmp|sandbox|dummy|ephemeral)(?:[_\-\s]|$)",
        re.IGNORECASE,
    )
    is_ephemeral_name = bool(
        ephemeral_pattern.search(name) or ephemeral_pattern.search(graph_id)
    )

    if (node_count == 0 and edge_count == 0) or (is_ephemeral_name and node_count <= 2):
        return (
            ACTION_PURGE,
            LABEL_PURGE,
            "Graphe vide ou identifié comme artefact de test éphémère. Suppression recommandée pour clore le compte Zep Cloud.",
        )

    # Règle 2 : Documents sources présents localement
    if has_local_documents:
        docs_repr = ", ".join(local_document_matches)
        return (
            ACTION_REBUILD_LOCAL,
            LABEL_REBUILD_LOCAL,
            f"Documents sources locaux identifiés ({docs_repr}). Ré-ingestion locale recommandée avec Graphiti + Neo4j via le modèle gratuit space-bunny-free (coût marginal 0 €).",
        )

    # Règle 3 : Données orphelines sans document local
    return (
        ACTION_MIGRATE,
        LABEL_MIGRATE,
        "Données orphelines sans document source local disponible. Rapatriement structurel direct vers Neo4j local via migrer_zep_vers_graphiti.py requis pour éviter la perte des connaissances.",
    )


def generer_graphes_mock(uploads_dir: Optional[Path] = None) -> List[GraphSummary]:
    """Génère un jeu de données mocké représentatif pour tests et CI hors-ligne."""
    if uploads_dir is None:
        uploads_dir = _backend_dir / "uploads" / "documents"

    # Vérifie si le fichier de transition énergétique existe réellement dans uploads/documents
    rapport_pdf = "rapport-an-2506-territorialisation-transition-energetique.pdf"
    rapport_existant = (uploads_dir / rapport_pdf).exists()
    matches_graphe_1 = [rapport_pdf] if rapport_existant else ["rapport-an-2506-territorialisation.pdf"]

    mock_definitions = [
        {
            "graph_id": "mirofish_rapport_an_2506",
            "name": "Rapport AN 2506 — Territorialisation de la transition énergétique",
            "description": "Simulation sociale transition énergétique régionale",
            "created_at": "2026-09-15T10:30:00Z",
            "node_count": 49,
            "edge_count": 45,
            "episode_count": 30,
            "has_local_documents": True,
            "local_document_matches": matches_graphe_1,
        },
        {
            "graph_id": "mirofish_strategie_ia_2024",
            "name": "Stratégie Nationale IA 2024 (Documents archivés)",
            "description": "Graphe extrait depuis notes confidentielles non archivées",
            "created_at": "2026-08-10T14:15:00Z",
            "node_count": 82,
            "edge_count": 114,
            "episode_count": 50,
            "has_local_documents": False,
            "local_document_matches": [],
        },
        {
            "graph_id": "test_sandbox_ephemeral_dev",
            "name": "Test Sandbox Développeur Éphémère",
            "description": "Graphe de test d'ingestion ponctuel",
            "created_at": "2026-10-01T09:00:00Z",
            "node_count": 0,
            "edge_count": 0,
            "episode_count": 0,
            "has_local_documents": False,
            "local_document_matches": [],
        },
    ]

    summaries: List[GraphSummary] = []
    for item in mock_definitions:
        action, label, reason = determiner_arbitrage(
            graph_id=item["graph_id"],
            name=item["name"],
            node_count=item["node_count"],
            edge_count=item["edge_count"],
            has_local_documents=item["has_local_documents"],
            local_document_matches=item["local_document_matches"],
        )
        summaries.append(
            GraphSummary(
                graph_id=item["graph_id"],
                name=item["name"],
                description=item["description"],
                created_at=item["created_at"],
                node_count=item["node_count"],
                edge_count=item["edge_count"],
                episode_count=item["episode_count"],
                has_local_documents=item["has_local_documents"],
                local_document_matches=item["local_document_matches"],
                recommendation=action,
                recommendation_label=label,
                recommendation_reason=reason,
            )
        )
    return summaries


def auditer_compte_zep(
    api_key: Optional[str] = None,
    client: Any = None,
    mock: bool = False,
    uploads_dir: Optional[Path] = None,
) -> AuditReport:
    """Exécute l'audit complet du compte Zep Cloud et produit l'AuditReport."""
    now_iso = datetime.now(timezone.utc).isoformat()

    if mock:
        summaries = generer_graphes_mock(uploads_dir=uploads_dir)
    else:
        if client is None:
            # Récupération du client Zep avec la clé fournie ou configurée
            cle_effective = (api_key or Config.ZEP_API_KEY or "").strip()
            if not cle_effective:
                raise ValueError(
                    "Clé ZEP_API_KEY non configurée. "
                    "Veuillez spécifier --api-key ou définir ZEP_API_KEY dans votre fichier .env "
                    "(ou exécuter avec --mock pour un audit simulé déterministe)."
                )
            client = get_zep_client(api_key=cle_effective)

        # 1. Récupération de tous les graphes via pagination list_all
        graphes_distants: List[Any] = []
        page_number = 1
        page_size = 100

        while True:
            response = call_zep_read_with_retry(
                lambda: client.graph.list_all(page_number=page_number, page_size=page_size),
                operation_name=f"list_all page {page_number}",
            )
            page_graphs = getattr(response, "graphs", None) or []
            graphes_distants.extend(page_graphs)
            if not page_graphs or len(page_graphs) < page_size:
                break
            page_number += 1

        summaries = []
        for g in graphes_distants:
            graph_id = getattr(g, "graph_id", "") or ""
            name = getattr(g, "name", "") or graph_id
            description = getattr(g, "description", None)
            created_at = getattr(g, "created_at", None)

            # Extraction des nœuds et arêtes
            has_error = False
            error_messages: List[str] = []

            try:
                nodes = fetch_all_nodes(client, graph_id)
                node_count = len(nodes)
            except Exception as exc:
                logger.warning("Échec de récupération des nœuds pour %s: %s", graph_id, exc)
                node_count = 0
                has_error = True
                error_messages.append(f"nœuds: {exc}")

            try:
                edges = fetch_all_edges(client, graph_id)
                edge_count = len(edges)
            except Exception as exc:
                logger.warning("Échec de récupération des arêtes pour %s: %s", graph_id, exc)
                edge_count = 0
                has_error = True
                error_messages.append(f"arêtes: {exc}")

            # Extraction des épisodes
            episode_count = 0
            episodes_descriptions: List[str] = []
            try:
                ep_resp = call_zep_read_with_retry(
                    lambda: client.graph.episode.get_by_graph_id(graph_id=graph_id, lastn=1000),
                    operation_name=f"get episodes for graph {graph_id}",
                )
                ep_list = getattr(ep_resp, "episodes", None) or []
                episode_count = len(ep_list)
                for ep in ep_list:
                    desc = getattr(ep, "source_description", "")
                    if desc:
                        episodes_descriptions.append(str(desc))
            except Exception as exc:
                logger.warning("Échec de récupération des épisodes pour %s: %s", graph_id, exc)
                error_messages.append(f"épisodes: {exc}")

            error_msg_combined = "; ".join(error_messages) if error_messages else None

            has_local, matches = detecter_documents_locaux(
                graph_id=graph_id,
                graph_name=name,
                episodes_descriptions=episodes_descriptions,
                uploads_dir=uploads_dir,
            )

            rec_action, rec_label, rec_reason = determiner_arbitrage(
                graph_id=graph_id,
                name=name,
                node_count=node_count,
                edge_count=edge_count,
                has_local_documents=has_local,
                local_document_matches=matches,
                has_error=has_error,
                error_message=error_msg_combined,
            )

            summaries.append(
                GraphSummary(
                    graph_id=graph_id,
                    name=name,
                    description=description,
                    created_at=str(created_at) if created_at else None,
                    node_count=node_count,
                    edge_count=edge_count,
                    episode_count=episode_count,
                    has_local_documents=has_local,
                    local_document_matches=matches,
                    has_error=has_error,
                    error_message=error_msg_combined,
                    recommendation=rec_action,
                    recommendation_label=rec_label,
                    recommendation_reason=rec_reason,
                )
            )

    # Agrégation des métriques globales
    total_nodes = sum(s.node_count for s in summaries)
    total_edges = sum(s.edge_count for s in summaries)
    total_episodes = sum(s.episode_count for s in summaries)

    breakdown: Dict[str, int] = {
        ACTION_REBUILD_LOCAL: 0,
        ACTION_MIGRATE: 0,
        ACTION_PURGE: 0,
    }
    for s in summaries:
        breakdown[s.recommendation] = breakdown.get(s.recommendation, 0) + 1

    return AuditReport(
        timestamp=now_iso,
        total_graphs=len(summaries),
        total_nodes=total_nodes,
        total_edges=total_edges,
        total_episodes=total_episodes,
        graphs=summaries,
        recommendations_breakdown=breakdown,
    )


def parser_arguments(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        description="Outil d'audit et d'inventaire d'un compte Zep Cloud (Story 006-1)."
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=None,
        help="Clé API Zep Cloud (si omise, utilise ZEP_API_KEY depuis .env).",
    )
    parser.add_argument(
        "--output-json",
        dest="output_json",
        default=None,
        help="Chemin du fichier où exporter les résultats au format JSON.",
    )
    parser.add_argument(
        "--output-report",
        dest="output_report",
        default=None,
        help="Chemin du fichier où exporter le rapport synthétique en Markdown.",
    )
    parser.add_argument(
        "--uploads-dir",
        dest="uploads_dir",
        default=None,
        help="Chemin optionnel du dossier des documents locaux pour analyse de corrélation.",
    )
    parser.add_argument(
        "--mock",
        dest="mock",
        action="store_true",
        help="Active le mode simulation déterministe hors-ligne sans clé ni réseau.",
    )
    parser.add_argument(
        "--quiet",
        dest="quiet",
        action="store_true",
        help="Supprime l'affichage console du rapport.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Point d'entrée principal de la CLI."""
    args = parser_arguments(argv)

    uploads_dir = Path(args.uploads_dir) if args.uploads_dir else None

    try:
        report = auditer_compte_zep(
            api_key=args.api_key,
            mock=args.mock,
            uploads_dir=uploads_dir,
        )
    except Exception as exc:
        # Message sécurisé sans afficher de secret
        print(f"❌ Erreur lors de l'audit Zep Cloud : {exc}", file=sys.stderr)
        return 1

    # Affichage console sauf si mode silencieux
    if not args.quiet:
        print("=" * 70)
        print(" MiroFish — Audit et Inventaire de Compte Zep Cloud (Story 006-1)")
        print("=" * 70)
        print(f"Horodatage       : {report.timestamp}")
        print(f"Total Graphes    : {report.total_graphs}")
        print(f"Total Nœuds      : {report.total_nodes}")
        print(f"Total Arêtes     : {report.total_edges}")
        print(f"Total Épisodes   : {report.total_episodes}")
        print("-" * 70)
        print("Ventilation de l'arbitrage :")
        for action, count in report.recommendations_breakdown.items():
            label = (
                LABEL_REBUILD_LOCAL
                if action == ACTION_REBUILD_LOCAL
                else LABEL_MIGRATE
                if action == ACTION_MIGRATE
                else LABEL_PURGE
            )
            print(f"  • {label} [{action}]: {count}")
        print("-" * 70)
        print("\nDétail des graphes recensés :")
        for idx, g in enumerate(report.graphs, start=1):
            doc_info = (
                f"Oui ({', '.join(g.local_document_matches)})"
                if g.has_local_documents
                else "Non"
            )
            print(f"\n[{idx}] {g.name} (ID: {g.graph_id})")
            print(f"    Nœuds: {g.node_count} | Arêtes: {g.edge_count} | Épisodes: {g.episode_count}")
            print(f"    Documents locaux : {doc_info}")
            print(f"    Recommandation   : {g.recommendation_label}")
            print(f"    Justification    : {g.recommendation_reason}")
        print("\n" + "=" * 70)

    # Export JSON
    if args.output_json:
        try:
            target_json = Path(args.output_json)
            target_json.parent.mkdir(parents=True, exist_ok=True)
            target_json.write_text(report.to_json(), encoding="utf-8")
            if not args.quiet:
                print(f"✓ Rapport JSON exporté : {target_json}")
        except Exception as exc:
            print(f"❌ Échec d'écriture du fichier JSON {args.output_json} : {exc}", file=sys.stderr)
            return 1

    # Export Markdown
    if args.output_report:
        try:
            target_md = Path(args.output_report)
            target_md.parent.mkdir(parents=True, exist_ok=True)
            target_md.write_text(report.to_markdown(), encoding="utf-8")
            if not args.quiet:
                print(f"✓ Rapport Markdown exporté : {target_md}")
        except Exception as exc:
            print(f"❌ Échec d'écriture du fichier Markdown {args.output_report} : {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
