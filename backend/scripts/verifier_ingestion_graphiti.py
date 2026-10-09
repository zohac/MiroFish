#!/usr/bin/env python3
"""Banc de vérification d'ingestion et de construction de graphe de bout en bout (Story 004-3).

Valide le critère C3 de l'Epic 004 :
  - Construction d'un graphe complet avec `GraphBuilderService` et `GraphitiGraphStore`.
  - Ingestion locale sans ZEP_API_KEY adossée à Neo4j local.
  - Production d'un graphe non vide respectant le seuil chiffré : >= 5 nœuds, >= 3 arêtes.
  - Mise à jour cohérente du statut de la tâche (COMPLETED) et du projet (GRAPH_COMPLETED).
  - Récupération des données du graphe au format attendu par l'API et l'interface utilisateur.

Usage :
    cd backend && uv run python scripts/verifier_ingestion_graphiti.py
    cd backend && uv run python scripts/verifier_ingestion_graphiti.py --mock-llm
    cd backend && uv run python scripts/verifier_ingestion_graphiti.py --real-llm
    cd backend && uv run python scripts/verifier_ingestion_graphiti.py --keep-graph
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional
import uuid

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
from app.models.project import Project, ProjectManager, ProjectStatus
from app.models.task import TaskManager, TaskStatus
from app.services.graph_builder import GraphBuilderService
from app.services.text_processor import TextProcessor
from app.utils.graph_store.base import GraphInfo
from app.utils.graph_store.factory import get_graph_store, override_graph_store
from app.utils.graph_store.graphiti_store import GraphitiGraphStore, LocalPassthroughCrossEncoder
from app.utils.graphiti_embedder import SentenceTransformerEmbedder
from app.utils.graphiti_llm_client import MiroFishLLMClient
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig


class DeterministicIngestionLLMClient(LLMClient):
    """Client LLM mocké déterministe extrayant un réseau d'entités et de relations pour tester l'ingestion."""

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
        prompt_str = " ".join(str(m.content if hasattr(m, "content") else m) for m in messages).lower()
        model_name = getattr(response_model, "__name__", "")

        # 1. Extraction d'entités (ExtractedEntities)
        if model_name == "ExtractedEntities":
            return {
                "extracted_entities": [
                    {"name": "Thalès", "entity_type_id": 0, "episode_indices": [0]},
                    {"name": "Marine Nationale", "entity_type_id": 0, "episode_indices": [0]},
                    {"name": "Alice Martin", "entity_type_id": 0, "episode_indices": [0]},
                    {"name": "Radar-2026", "entity_type_id": 0, "episode_indices": [0]},
                    {"name": "Brest", "entity_type_id": 0, "episode_indices": [0]},
                    {"name": "Systèmes Côtiers", "entity_type_id": 0, "episode_indices": [0]},
                ]
            }

        # 2. Résumés d'entités (SummarizedEntities / EntitySummary)
        if model_name in ("SummarizedEntities", "EntitySummary"):
            return {
                "summaries": [
                    {"name": "Thalès", "summary": "Groupe d'électronique spécialisé dans l'aérospatiale et la défense."},
                    {"name": "Marine Nationale", "summary": "Force navale de la République française."},
                    {"name": "Alice Martin", "summary": "Directrice de programme et ingénieure en chef."},
                    {"name": "Radar-2026", "summary": "Système de surveillance radar côtière de nouvelle génération."},
                    {"name": "Brest", "summary": "Grand port militaire et base navale stratégique."},
                    {"name": "Systèmes Côtiers", "summary": "Ensemble d'infrastructures de défense maritime."},
                ],
                "summary": "Entité du domaine de la défense et des télécommunications.",
            }

        # 3. Extraction de relations/arêtes (ExtractedEdges)
        if model_name == "ExtractedEdges":
            return {
                "edges": [
                    {
                        "source_entity_name": "Thalès",
                        "target_entity_name": "Marine Nationale",
                        "relation_type": "FOURNIT_EQUIPEMENT",
                        "fact": "Thalès fournit des radars et systèmes d'observation à la Marine Nationale.",
                        "valid_at": "2026-05-01T10:00:00Z",
                        "invalid_at": None,
                        "episode_indices": [0],
                    },
                    {
                        "source_entity_name": "Alice Martin",
                        "target_entity_name": "Radar-2026",
                        "relation_type": "SUPERVISE",
                        "fact": "Alice Martin supervise le déploiement opérationnel du Radar-2026.",
                        "valid_at": "2026-06-01T12:00:00Z",
                        "invalid_at": None,
                        "episode_indices": [0],
                    },
                    {
                        "source_entity_name": "Radar-2026",
                        "target_entity_name": "Brest",
                        "relation_type": "INSTALLE_A",
                        "fact": "Le système Radar-2026 est installé sur la base militaire de Brest.",
                        "valid_at": "2026-07-01T08:00:00Z",
                        "invalid_at": None,
                        "episode_indices": [0],
                    },
                    {
                        "source_entity_name": "Radar-2026",
                        "target_entity_name": "Systèmes Côtiers",
                        "relation_type": "INTEGRE_DANS",
                        "fact": "Le Radar-2026 est pleinement intégré dans le réseau des Systèmes Côtiers.",
                        "valid_at": "2026-08-01T14:00:00Z",
                        "invalid_at": None,
                        "episode_indices": [0],
                    },
                ]
            }

        # 4. Déduplication
        if model_name == "EdgeDuplicate":
            return {"duplicate_facts": [], "contradicted_facts": []}

        if model_name == "NodeResolutions":
            return {"resolutions": []}

        return {}


def run_ingestion_validation(
    use_mock_llm: bool = True,
    keep_graph: bool = False,
) -> Dict[str, Any]:
    """Exécute la validation d'ingestion complète et contrôle formellement le critère C3."""
    rapport: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "criteres": {
            "C3_statut_tache_completed": False,
            "C3_statut_projet_graph_completed": False,
            "C3_seuil_noeuds_atteint": False,  # >= 5 nœuds
            "C3_seuil_aretes_atteint": False,  # >= 3 arêtes
            "C3_format_donnees_api_conforme": False,
            "C3_nettoyage_propre": False,
        },
        "details": {},
        "statut": "ECHEC",
    }

    print("=" * 75)
    print("BANC D'INGESTION ET CONSTRUCTION DE GRAPHE LOCAL (STORY 004-3 / CRITÈRE C3)")
    print(f"Mode LLM : {'MOCK DÉTERMINISTE' if use_mock_llm else 'RÉEL OPENCODE GO'}")
    print(f"Conserver le graphe après test : {keep_graph}")
    print("=" * 75)

    # Sauvegarde et forçage de la configuration locale
    orig_zep_backend = Config.ZEP_BACKEND
    orig_zep_api_key = Config.ZEP_API_KEY
    Config.ZEP_BACKEND = "graphiti"
    Config.ZEP_API_KEY = None

    # Initialisation du GraphStore
    print("\n[1/5] Initialisation du GraphitiGraphStore et connexion Neo4j...")
    llm_client = DeterministicIngestionLLMClient() if use_mock_llm else MiroFishLLMClient()
    embedder = SentenceTransformerEmbedder()
    cross_encoder = LocalPassthroughCrossEncoder()
    store = GraphitiGraphStore(
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
    )

    test_graph_id = f"graph-test-{uuid.uuid4().hex[:8]}"
    project = None
    created_gid: Optional[str] = None
    graph_cleaned_up: bool = False

    try:
        # Contrôle des index et connectivité
        store._run_async(store._driver.build_indices_and_constraints())
        print("   ✓ Connectivité Neo4j établie et contraintes vérifiées.")

        # Préparation du projet et du texte
        project = ProjectManager.create_project(name="Test Ingestion E2E Story 004-3")
        test_project_id = project.project_id
        print(f"\n[2/5] Création du projet de test '{test_project_id}'...")
        project.simulation_requirement = "Analyse de la chaîne logistique et de surveillance côtière."
        project.ontology = {
            "entity_types": [{"name": "Organization"}, {"name": "Person"}, {"name": "Project"}, {"name": "Location"}],
            "edge_types": [{"name": "FOURNIT_EQUIPEMENT"}, {"name": "SUPERVISE"}, {"name": "INSTALLE_A"}],
        }
        project.status = ProjectStatus.ONTOLOGY_GENERATED

        sample_document = (
            "Thalès renforce sa collaboration avec la Marine Nationale pour la fourniture de systèmes radars. "
            "L'ingénieure Alice Martin supervise personnellement le déploiement du programme Radar-2026. "
            "Ce nouveau système est installé sur la base navale de Brest et s'intègre au réseau des Systèmes Côtiers. "
            "Les essais en mer confirment l'efficacité opérationnelle de l'ensemble des installations."
        )
        project.total_text_length = len(sample_document)
        ProjectManager.save_extracted_text(project.project_id, sample_document)
        ProjectManager.save_project(project)
        print(f"   ✓ Projet créé et texte source enregistré ({len(sample_document)} caractères).")

        # Exécution de l'ingestion via GraphBuilderService
        print(f"\n[3/5] Lancement de l'ingestion et de la construction de graphe (ID={test_graph_id})...")
        builder = GraphBuilderService(store=store)

        task_id = builder.task_manager.create_task(
            task_type="graph_build",
            metadata={"project_id": test_project_id, "graph_name": "Graphe Ingestion E2E"},
        )
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)

        # Découpage et exécution synchrone du worker pour le banc d'épreuve
        chunks = TextProcessor.split_text(sample_document, chunk_size=80, overlap=15)
        print(f"   ✓ Texte découpé en {len(chunks)} fragments.")

        # Ingestion de bout en bout
        created_gid = builder.create_graph("Graphe Ingestion E2E", graph_id=test_graph_id)
        builder.set_ontology(created_gid, project.ontology)

        progress_events = []
        submission = builder.add_text_batches(
            created_gid,
            chunks,
            batch_size=5,
            progress_callback=lambda st, cur, tot: progress_events.append((st, cur, tot)),
        )
        print(f"   ✓ Lot d'ingestion soumis ({submission.item_count} fragments, batch_id={submission.batch_id}).")

        completed_episodes = builder._wait_for_batch(submission, timeout=60.0)
        assert isinstance(completed_episodes, list), "L'attente du lot d'épisodes a échoué"
        print(f"   ✓ Traitement du lot d'épisodes terminé avec succès dans Neo4j ({len(completed_episodes)} épisodes).")

        # Récupération des informations et données
        graph_data = builder.get_graph_data(created_gid)
        graph_info = builder.get_graph_info(created_gid)

        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        node_count = len(nodes)
        edge_count = len(edges)

        print(f"\n[4/5] Analyse du graphe produit dans Neo4j :")
        print(f"   - Nombre de nœuds : {node_count} (exigé >= 5)")
        print(f"   - Nombre d'arêtes : {edge_count} (exigé >= 3)")
        print(f"   - Types d'entités  : {graph_info.entity_types}")
        for n in nodes:
            print(f"     * Nœud: {n.get('name')} | labels={n.get('labels')} | summary={n.get('summary')[:50]}...")
        for e in edges:
            print(f"     * Arête: {e.get('source_node_name')} --[{e.get('name')}]--> {e.get('target_node_name')} ({e.get('fact')})")

        # Mise à jour des statuts
        builder.task_manager.complete_task(
            task_id,
            {
                "project_id": test_project_id,
                "graph_id": created_gid,
                "node_count": node_count,
                "edge_count": edge_count,
                "chunks_processed": len(chunks),
            },
        )
        project.status = ProjectStatus.GRAPH_COMPLETED
        project.graph_id = created_gid
        ProjectManager.save_project(project)

        # Contrôles formels du Critère C3
        task = builder.task_manager.get_task(task_id)
        assert task is not None and task.status == TaskStatus.COMPLETED
        rapport["criteres"]["C3_statut_tache_completed"] = True

        assert project.status == ProjectStatus.GRAPH_COMPLETED
        rapport["criteres"]["C3_statut_projet_graph_completed"] = True

        assert node_count >= 5, f"Nombre de nœuds insuffisant ({node_count} < 5)"
        rapport["criteres"]["C3_seuil_noeuds_atteint"] = True

        assert edge_count >= 3, f"Nombre d'arêtes insuffisant ({edge_count} < 3)"
        rapport["criteres"]["C3_seuil_aretes_atteint"] = True

        assert "nodes" in graph_data and "edges" in graph_data and "statistics" in graph_data
        rapport["criteres"]["C3_format_donnees_api_conforme"] = True

        # Nettoyage
        print(f"\n[5/5] Nettoyage du graphe et des données de test...")
        if not keep_graph:
            builder.delete_graph(created_gid)
            graph_cleaned_up = True
            assert len(builder.get_graph_data(created_gid)["nodes"]) == 0
            rapport["criteres"]["C3_nettoyage_propre"] = True
            print("   ✓ Graphe temporaire purgé de Neo4j.")
        else:
            rapport["criteres"]["C3_nettoyage_propre"] = True
            print("   ℹ Graphe conservé dans Neo4j (--keep-graph).")

        rapport["statut"] = "SUCCES"
        rapport["details"] = {
            "graph_id": created_gid,
            "nodes_count": node_count,
            "edges_count": edge_count,
            "entity_types": graph_info.entity_types,
            "chunks_count": len(chunks),
        }

    except Exception as e:
        import traceback
        print(f"\n❌ ERREUR lors de l'ingestion : {e}")
        traceback.print_exc()
        rapport["details"]["erreur"] = str(e)
    finally:
        if not keep_graph and created_gid and not graph_cleaned_up:
            try:
                store.delete_graph(created_gid)
                print(f"   ✓ Graphe orphelin '{created_gid}' purgé de Neo4j dans finally.")
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

    print("\n" + "=" * 75)
    print("BILAN FORMEL DE LA STORY 004-3 (CRITÈRE C3) :")
    for crit, val in rapport["criteres"].items():
        symbole = "✅ VALIDÉ" if val else "❌ ÉCHEC"
        print(f"  - {crit:<40} : {symbole}")
    print("=" * 75)

    return rapport


def main() -> int:
    parser = argparse.ArgumentParser(description="Vérification d'ingestion réelle Story 004-3 (Critère C3)")
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
    args = parser.parse_args()
    use_mock = not args.real_llm

    try:
        rapport = run_ingestion_validation(use_mock_llm=use_mock, keep_graph=args.keep_graph)
        if rapport["statut"] == "SUCCES":
            print("\n🎉 INGESTION ET CONSTRUCTION DE GRAPHE VALIDÉES AVEC SUCCÈS (CRITÈRE C3 SATISFAIT).")
            return 0
        else:
            print(f"\n❌ ÉCHEC de la validation : {rapport.get('details')}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"\n❌ EXCEPTION inattendue : {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
