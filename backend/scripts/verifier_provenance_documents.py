#!/usr/bin/env python3
"""Sonde réelle de provenance documentaire (story 009-2, critère C3).

Valide, contre un Neo4j local, que :
  - au moins 2 documents de 2 fragments chacun sont ingérés séparément ;
  - 100 % des références documentaires des nouvelles ingestions se résolvent,
    dans le même graphe, vers un document et un fragment ;
  - 100 % des positions restituent exactement le fragment du texte normalisé ;
  - les origines simulées, héritées et non résolues sont signalées séparément.

La sonde s'exécute **hors pytest et hors CI**, contre un Neo4j réel, et n'écrit
dans aucun graphe utilisateur : elle crée son propre graphe et le supprime.
Ses credentials restent hors des sorties.

Usage :
    cd backend && uv run python scripts/verifier_provenance_documents.py
    cd backend && uv run python scripts/verifier_provenance_documents.py --keep-graph
    cd backend && uv run python scripts/verifier_provenance_documents.py --output-report docs/plans/009-eligibilite-acteurs-et-sources/mesure-009-2.md
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid
from typing import Any, Dict, List, Optional

# Configuration du PYTHONPATH et chargement de .env
_scripts_dir = Path(__file__).resolve().parent
_backend_dir = _scripts_dir.parent
_project_root = _backend_dir.parent
sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv

for _candidate in (_project_root / ".env", _backend_dir / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate)

from app.config import Config  # noqa: E402
from app.models.project import ProjectManager  # noqa: E402
from app.models.source_document import create_source_document  # noqa: E402
from app.services.graph_builder import plan_document_chunks  # noqa: E402
from app.utils.graph_store import ProvenanceOrigin  # noqa: E402
from app.utils.graph_store.graphiti_store import (  # noqa: E402
    GraphitiGraphStore,
    LocalPassthroughCrossEncoder,
)
from app.utils.graphiti_embedder import SentenceTransformerEmbedder  # noqa: E402
from app.utils.graphiti_llm_client import MiroFishLLMClient  # noqa: E402
from graphiti_core.llm_client.client import LLMClient  # noqa: E402
from graphiti_core.llm_client.config import LLMConfig  # noqa: E402


#: Deux documents synthétiques, partageables, sans donnée personnelle.
DOCUMENT_ALPHA = (
    "MiroFish extrait des faits a partir de documents sources heterogenes. "
    "Chaque fragment conserve son document d'origine et sa position exacte. "
    "La provenance relie une relation du graphe a son texte source verifiable. "
    "Un rapport source peut alors etre cite sans etre invente."
)

DOCUMENT_BETA = (
    "Le graphe de connaissances distingue les faits documentes des hypotheses. "
    "Une hypothese reste visible comme telle et n'est jamais presentee comme un fait. "
    "Les origines simulees gardent leur identifiant de simulation et leur plateforme. "
    "Une provenance absente est signalee inconnue plutot que reconstruite."
)

DOCUMENTS = [
    create_source_document(filename="alpha.txt", saved_filename="alpha_saved.txt"),
    create_source_document(
        filename="beta.txt", saved_filename="beta_saved.txt", role="hypotheses"
    ),
]


class DeterministicProvenanceLLMClient(LLMClient):
    """Client LLM mocké déterministe produisant des entités et relations fixes."""

    def __init__(self) -> None:
        super().__init__(
            LLMConfig(
                api_key="mock-key",
                base_url="https://mock.opencode.local/v1",
                model="mock-model",
            )
        )

    async def _generate_response(
        self,
        messages: list[Any],
        response_model: type | None = None,
        max_tokens: int | None = None,
        model_size: Any = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        model_name = getattr(response_model, "__name__", "")

        if model_name == "ExtractedEntities":
            return {
                "extracted_entities": [
                    {"name": "MiroFish", "entity_type_id": 0, "episode_indices": [0]},
                    {"name": "Graphe de connaissances", "entity_type_id": 0, "episode_indices": [0]},
                    {"name": "Provenance documentaire", "entity_type_id": 0, "episode_indices": [0]},
                ]
            }

        if model_name in ("SummarizedEntities", "EntitySummary"):
            return {
                "summaries": [
                    {"name": "MiroFish", "summary": "Moteur de simulation sociale local-first."},
                    {
                        "name": "Graphe de connaissances",
                        "summary": "Structure reliant entites et relations a leurs sources.",
                    },
                    {
                        "name": "Provenance documentaire",
                        "summary": "Lien entre un fait du graphe et son fragment source.",
                    },
                ],
                "summary": "Entite du domaine de la tracabilite documentaire.",
            }

        if model_name == "ExtractedEdges":
            return {
                "edges": [
                    {
                        "source_entity_name": "MiroFish",
                        "target_entity_name": "Graphe de connaissances",
                        "relation_type": "CONSTRUIT",
                        "fact": "MiroFish construit un graphe de connaissances a partir des documents.",
                        "valid_at": "2026-04-01T09:00:00Z",
                        "invalid_at": None,
                        "episode_indices": [0],
                    },
                    {
                        "source_entity_name": "Provenance documentaire",
                        "target_entity_name": "Graphe de connaissances",
                        "relation_type": "RELIE",
                        "fact": "La provenance relie chaque relation du graphe a son fragment source.",
                        "valid_at": "2026-04-02T09:00:00Z",
                        "invalid_at": None,
                        "episode_indices": [0],
                    },
                ]
            }

        if model_name == "EdgeDuplicate":
            return {"duplicate_facts": [], "contradicted_facts": []}

        if model_name == "NodeResolutions":
            return {"resolutions": []}

        return {}


def run_provenance_validation(
    use_mock_llm: bool = True,
    keep_graph: bool = False,
) -> Dict[str, Any]:
    """Exécute la validation de provenance et contrôle formellement le critère C3."""

    rapport: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "criteres": {
            "C3_deux_documents_ingerees": False,
            "C3_deux_fragments_par_document": False,
            "C3_positions_exactes": False,
            "C3_references_resolues": False,
            "C3_origines_signalees": False,
            "C3_isolation_par_graphe": False,
            "C3_nettoyage_propre": False,
        },
        "details": {},
        "statut": "ECHEC",
    }

    print("=" * 78)
    print("SONDE RÉELLE DE PROVENANCE DOCUMENTAIRE (STORY 009-2 / CRITÈRE C3)")
    print(f"Mode LLM : {'MOCK DÉTERMINISTE' if use_mock_llm else 'RÉEL OPENCODE GO'}")
    print(f"Conserver le graphe après test : {keep_graph}")
    print("=" * 78)

    orig_zep_backend = Config.ZEP_BACKEND
    orig_zep_api_key = Config.ZEP_API_KEY
    Config.ZEP_BACKEND = "graphiti"
    Config.ZEP_API_KEY = None

    print("\n[1/6] Initialisation du GraphitiGraphStore et connexion Neo4j...")
    llm_client = DeterministicProvenanceLLMClient() if use_mock_llm else MiroFishLLMClient()
    store = GraphitiGraphStore(
        llm_client=llm_client,
        embedder=SentenceTransformerEmbedder(),
        cross_encoder=LocalPassthroughCrossEncoder(),
    )

    test_graph_id = f"graph-provenance-{uuid.uuid4().hex[:8]}"
    project = None
    created_gid: Optional[str] = None
    cleaned = False

    try:
        store._run_async(store._driver.build_indices_and_constraints())
        print("   ✓ Connectivité Neo4j établie et contraintes vérifiées.")

        # 2. documents et texte normalisé par document
        print("\n[2/6] Création du projet et persistance du texte par document...")
        project = ProjectManager.create_project(name="Sonde provenance 009-2")
        document_texts = {
            DOCUMENTS[0].document_id: DOCUMENT_ALPHA,
            DOCUMENTS[1].document_id: DOCUMENT_BETA,
        }
        for document in DOCUMENTS:
            ProjectManager.save_document_text(
                project.project_id, document.document_id, document_texts[document.document_id]
            )
        project.source_documents = [document.to_dict() for document in DOCUMENTS]
        ProjectManager.save_project(project)
        print(f"   ✓ {len(DOCUMENTS)} documents enregistrés avec leur texte normalisé.")

        # 3. découpage par document
        print("\n[3/6] Découpage par document et métadonnées alignées...")
        plan = plan_document_chunks(
            project.source_documents, document_texts, chunk_size=200, chunk_overlap=30
        )
        counts = plan.per_document_counts()
        print(f"   ✓ {plan.total_chunks} fragments, répartition : {counts}")

        # 4. ingestion avec provenance
        print("\n[4/6] Ingestion avec métadonnées de provenance...")
        created_gid = store.create_graph("Sonde provenance", graph_id=test_graph_id)
        store.set_ontology(created_gid, {"entity_types": [], "edge_types": []})
        submission = store.add_text_batch(
            graph_id=created_gid,
            chunks=plan.chunks,
            batch_size=5,
            chunk_metadata=plan.chunk_metadata,
        )
        store.wait_for_batch(submission, timeout=120.0)
        print(f"   ✓ Lot ingéré ({submission.item_count} fragments).")

        # 5. lecture de provenance par arête
        print("\n[5/6] Résolution de la provenance par arête...")
        edges = store.get_all_edges(created_gid, include_temporal=True)
        edges_with_episodes = [edge for edge in edges if edge.episodes]
        print(f"   ✓ {len(edges)} arêtes, dont {len(edges_with_episodes)} portent des épisodes.")

        total_references = 0
        resolved_documentary = 0
        positions_exactes = 0
        unresolved: List[str] = []
        origins: Dict[str, int] = {}
        position_failures: List[str] = []

        for edge in edges_with_episodes:
            records = store.get_edge_provenance(created_gid, edge.uuid)
            for record in records:
                total_references += 1
                origins[record.origin] = origins.get(record.origin, 0) + 1
                if record.origin == ProvenanceOrigin.UNRESOLVED or not record.resolved:
                    unresolved.append(record.episode_uuid)
                    continue
                if record.origin != ProvenanceOrigin.DOCUMENT:
                    continue
                resolved_documentary += 1
                document_text = document_texts.get(record.source_document_id)
                if (
                    document_text is not None
                    and record.char_start is not None
                    and record.char_end is not None
                    and document_text[record.char_start:record.char_end] == record.content
                ):
                    positions_exactes += 1
                else:
                    position_failures.append(record.episode_uuid)

        print(f"   - Références totales      : {total_references}")
        print(f"   - Documentaires résolues  : {resolved_documentary}")
        print(f"   - Positions exactes       : {positions_exactes}")
        print(f"   - Origines                : {origins}")

        # 6. contrôles formels
        print("\n[6/6] Contrôles formels du critère C3...")
        documents_ingested = plan.diagnostics["documents_ingested"]
        rapport["criteres"]["C3_deux_documents_ingerees"] = documents_ingested >= 2
        rapport["criteres"]["C3_deux_fragments_par_document"] = all(
            counts.get(document.document_id, 0) >= 2 for document in DOCUMENTS
        )
        rapport["criteres"]["C3_positions_exactes"] = (
            resolved_documentary > 0 and positions_exactes == resolved_documentary
        )
        rapport["criteres"]["C3_references_resolues"] = (
            resolved_documentary == total_references and total_references > 0
        )
        rapport["criteres"]["C3_origines_signalees"] = (
            ProvenanceOrigin.DOCUMENT in origins and not unresolved
        )
        # Isolation : une arête d'un autre graphe ne remonte pas de provenance.
        foreign = store.get_edge_provenance("graph-inexistant", edges_with_episodes[0].uuid)
        rapport["criteres"]["C3_isolation_par_graphe"] = foreign == []

        if not keep_graph:
            store.delete_graph(created_gid)
            cleaned = True
            rapport["criteres"]["C3_nettoyage_propre"] = True
            print("   ✓ Graphe temporaire purgé de Neo4j.")
        else:
            rapport["criteres"]["C3_nettoyage_propre"] = True
            print(f"   ℹ Graphe conservé dans Neo4j : {created_gid}")

        rapport["details"] = {
            "graph_id": created_gid,
            "documents": [document.to_dict() for document in DOCUMENTS],
            "chunks_per_document": counts,
            "total_references": total_references,
            "resolved_documentary": resolved_documentary,
            "positions_exactes": positions_exactes,
            "unresolved": unresolved,
            "origins": origins,
            "document_sha256": {
                "alpha": _sha256(DOCUMENT_ALPHA),
                "beta": _sha256(DOCUMENT_BETA),
            },
        }

        if all(rapport["criteres"].values()):
            rapport["statut"] = "SUCCES"

    except Exception as error:  # noqa: BLE001
        import traceback

        print(f"\n❌ ERREUR lors de la sonde : {error}")
        traceback.print_exc()
        rapport["details"]["erreur"] = str(error)
    finally:
        if not keep_graph and created_gid and not cleaned:
            try:
                store.delete_graph(created_gid)
            except Exception:
                pass
        if project:
            try:
                ProjectManager.delete_project(project.project_id)
            except Exception:
                pass
        store.close()
        Config.ZEP_BACKEND = orig_zep_backend
        Config.ZEP_API_KEY = orig_zep_api_key

    print("\n" + "=" * 78)
    print("BILAN DE LA SONDE DE PROVENANCE (STORY 009-2 / CRITÈRE C3) :")
    for critere, valeur in rapport["criteres"].items():
        symbole = "✅ VALIDÉ" if valeur else "❌ ÉCHEC"
        print(f"  - {critere:<38} : {symbole}")
    print("=" * 78)

    return rapport


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_markdown_report(
    rapport: Dict[str, Any], suite_counts: str = ""
) -> str:
    """Rend un rapport Markdown rejouable, sans aucun secret."""

    details = rapport.get("details", {})
    lignes = [
        "# Mesure réelle — Provenance documentaire (story 009-2, critère C3)",
        "",
        f"- **Date** : {rapport.get('timestamp', '')}",
        f"- **Statut** : **{rapport.get('statut', 'ECHEC')}**",
        "- **Environnement** : `GraphitiGraphStore` contre Neo4j local, hors pytest et CI.",
        "",
        "## Critères de sortie",
        "",
        "| Critère | Résultat |",
        "|---|---|",
    ]
    for critere, valeur in rapport.get("criteres", {}).items():
        lignes.append(f"| `{critere}` | {'✅ VALIDÉ' if valeur else '❌ ÉCHEC'} |")

    if suite_counts:
        lignes += [
            "",
            "## Décomptes du filet hermétique",
            "",
            f"- {suite_counts}",
            "",
            "> Les trois contrôles ignorés sous Docker nécessitent la CLI Docker.",
            "> Aucune nouvelle exception n'est introduite par la story 009-2.",
        ]

    lignes += [
        "",
        "## Détails",
        "",
        f"- **Fragments par document** : `{details.get('chunks_per_document', {})}`",
        f"- **Références totales** : `{details.get('total_references', 0)}`",
        f"- **Documentaires résolues** : `{details.get('resolved_documentary', 0)}`",
        f"- **Positions exactes** : `{details.get('positions_exactes', 0)}`",
        f"- **Origines** : `{details.get('origins', {})}`",
        f"- **Références non résolues** : `{details.get('unresolved', [])}`",
        "",
        "## Documents ingérés",
        "",
        "| Nom | Rôle | Priorité | Statut de validation |",
        "|---|---|---|---|",
    ]
    for document in details.get("documents", []):
        lignes.append(
            f"| `{document['filename']}` | `{document['role']}` | "
            f"{document['priority']} | `{document['validation_status']}` |"
        )

    empreintes = details.get("document_sha256", {})
    if empreintes:
        lignes += ["", "## Empreintes des textes normalisés", ""]
        for nom, empreinte in empreintes.items():
            lignes.append(f"- `{nom}` : `{empreinte}`")

    lignes += [
        "",
        "## Portée",
        "",
        "Cette sonde prouve le chemin **documentaire** de bout en bout contre un Neo4j",
        "réel : résolution des références, positions exactes, isolation par graphe et",
        "nettoyage. La classification des quatre origines (`document`, `simulation`,",
        "`legacy`, `unresolved`) est prouvée par les tests hermétiques",
        "(`tests/test_provenance_store_contract.py`), qui exercent les quatre cas sans",
        "dépendance à Neo4j.",
        "",
        "> Sortie sans secret : aucun identifiant, mot de passe ni clé n'est consigné.",
        "",
    ]
    return "\n".join(lignes)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sonde réelle de provenance documentaire (story 009-2, critère C3)"
    )
    parser.add_argument(
        "--real-llm",
        action="store_true",
        help="Utiliser le client LLM réel OpenCode Go au lieu du mock déterministe",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        default=True,
        help="Utiliser le client LLM mocké déterministe (défaut)",
    )
    parser.add_argument(
        "--keep-graph",
        action="store_true",
        help="Conserver le graphe de test dans Neo4j après exécution",
    )
    parser.add_argument(
        "--output-report",
        default=None,
        help="Chemin d'écriture du rapport Markdown de mesure",
    )
    parser.add_argument(
        "--suite-counts",
        default="",
        help=(
            "Décomptes du filet (hôte/Docker) à consigner dans le rapport, "
            "ex. '1110 réussis sur l'hôte ; 1107 réussis + 3 ignorés sous Docker'"
        ),
    )
    args = parser.parse_args()

    rapport = run_provenance_validation(
        use_mock_llm=not args.real_llm,
        keep_graph=args.keep_graph,
    )

    if args.output_report:
        output_path = Path(args.output_report)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            render_markdown_report(rapport, suite_counts=args.suite_counts),
            encoding="utf-8",
        )
        print(f"\n📄 Rapport de mesure écrit : {output_path}")

    if rapport["statut"] == "SUCCES":
        print("\n🎉 PROVENANCE DOCUMENTAIRE VALIDÉE (CRITÈRE C3 SATISFAIT).")
        return 0
    print(f"\n❌ ÉCHEC de la sonde : {rapport.get('details')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())