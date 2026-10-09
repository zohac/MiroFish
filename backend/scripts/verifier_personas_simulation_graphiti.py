#!/usr/bin/env python3
"""Banc de vérification de l'extraction d'entités, de la génération de personas et de la configuration de simulation (Story 004-4).

Valide le critère C4 de l'Epic 004 :
  - Extraction d'entités typées depuis un graphe local `GraphitiGraphStore` adossé à Neo4j.
  - Génération avec succès d'au moins 3 personas typés (Reddit JSON et Twitter CSV) sans clé Zep.
  - Production d'une configuration de simulation multi-agents valide (`simulation_config.json`).
  - Orchestration de bout en bout via `SimulationManager.prepare_simulation`.
  - Contrôle de la conformité des formats OASIS (user_id, username, bio, persona, user_char, etc.).
  - Nettoyage propre des données de test.

Usage :
    cd backend && uv run python scripts/verifier_personas_simulation_graphiti.py
    cd backend && uv run python scripts/verifier_personas_simulation_graphiti.py --mock-llm
    cd backend && uv run python scripts/verifier_personas_simulation_graphiti.py --real-llm
    cd backend && uv run python scripts/verifier_personas_simulation_graphiti.py --keep-graph
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
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
from app.services.oasis_profile_generator import OasisAgentProfile, OasisProfileGenerator
from app.services.simulation_config_generator import (
    SimulationConfigGenerator,
    SimulationParameters,
)
from app.services.simulation_manager import (
    SimulationManager,
    SimulationState,
    SimulationStatus,
)
from app.services.zep_entity_reader import EntityNode, FilteredEntities, ZepEntityReader
from app.utils.graph_store.factory import get_graph_store, override_graph_store
from app.utils.graph_store.graphiti_store import GraphitiGraphStore, LocalPassthroughCrossEncoder
from app.utils.graphiti_embedder import SentenceTransformerEmbedder
from app.utils.graphiti_llm_client import MiroFishLLMClient
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig


class DeterministicPersonasLLMClient(LLMClient):
    """Client LLM mocké déterministe pour alimenter le graphe Graphiti et la génération."""

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

        # 1. Extraction d'entités (ExtractedEntities)
        if model_name == "ExtractedEntities":
            return {
                "extracted_entities": [
                    {"name": "Alice Martin", "entity_type_id": 0, "episode_indices": [0]},
                    {"name": "Thalès Défense", "entity_type_id": 0, "episode_indices": [0]},
                    {"name": "Brest Maritime", "entity_type_id": 0, "episode_indices": [0]},
                    {"name": "Professeur Durand", "entity_type_id": 0, "episode_indices": [0]},
                ]
            }

        # 2. Résumés d'entités (SummarizedEntities / EntitySummary)
        if model_name in ("SummarizedEntities", "EntitySummary"):
            return {
                "summaries": [
                    {"name": "Alice Martin", "summary": "Ingénieure en chef et directrice de projet de surveillance côtière."},
                    {"name": "Thalès Défense", "summary": "Entreprise industrielle leader des technologies de défense maritime."},
                    {"name": "Brest Maritime", "summary": "Pôle portuaire et base stratégique navale."},
                    {"name": "Professeur Durand", "summary": "Expert académique en acoustique sous-marine et télécommunications."},
                ],
                "summary": "Acteur clé du secteur maritime et de la sécurité des côtes.",
            }

        # 3. Extraction de relations/arêtes (ExtractedEdges)
        if model_name == "ExtractedEdges":
            return {
                "edges": [
                    {
                        "source_entity_name": "Alice Martin",
                        "target_entity_name": "Thalès Défense",
                        "relation_type": "EMPLOYEE_DE",
                        "fact": "Alice Martin dirige l'équipe d'ingénierie au sein de Thalès Défense.",
                        "valid_at": "2026-01-01T00:00:00Z",
                        "invalid_at": None,
                        "episode_indices": [0],
                    },
                    {
                        "source_entity_name": "Thalès Défense",
                        "target_entity_name": "Brest Maritime",
                        "relation_type": "IMPLANTE_A",
                        "fact": "Thalès Défense maintient un centre technique majeur à Brest Maritime.",
                        "valid_at": "2026-02-01T00:00:00Z",
                        "invalid_at": None,
                        "episode_indices": [0],
                    },
                    {
                        "source_entity_name": "Professeur Durand",
                        "target_entity_name": "Thalès Défense",
                        "relation_type": "CONSEILLE",
                        "fact": "Le Professeur Durand conseille scientifiquement Thalès Défense sur l'acoustique.",
                        "valid_at": "2026-03-01T00:00:00Z",
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


def run_personas_simulation_validation(
    use_mock_llm: bool = True,
    keep_graph: bool = False,
    keep_artifacts: bool = False,
) -> Dict[str, Any]:
    """Exécute la validation complète personas + config de simulation et contrôle formellement le critère C4."""
    rapport: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "criteres": {
            "C4_extraction_entites_reussie": False,
            "C4_seuil_personas_atteint": False,  # >= 3 personas typés
            "C4_format_reddit_json_valide": False,
            "C4_format_twitter_csv_valide": False,
            "C4_config_simulation_valide": False,
            "C4_zero_cle_zep_exigee": False,
            "C4_nettoyage_propre": False,
        },
        "details": {},
        "statut": "ECHEC",
    }

    print("=" * 75)
    print("BANC DE GÉNÉRATION DE PERSONAS ET SIMULATION LOCAL (STORY 004-4 / CRITÈRE C4)")
    print(f"Mode LLM : {'MOCK DÉTERMINISTE' if use_mock_llm else 'RÉEL OPENCODE GO'}")
    print(f"Conserver le graphe Neo4j : {keep_graph}")
    print(f"Conserver les artefacts : {keep_artifacts}")
    print("=" * 75)

    # Sauvegarde et forçage de la configuration locale sans clé Zep
    orig_zep_backend = Config.ZEP_BACKEND
    orig_zep_api_key = Config.ZEP_API_KEY
    Config.ZEP_BACKEND = "graphiti"
    Config.ZEP_API_KEY = None

    rapport["criteres"]["C4_zero_cle_zep_exigee"] = (Config.requires_zep_api_key() is False)

    # Initialisation du GraphStore
    print("\n[1/6] Initialisation du GraphitiGraphStore et connexion Neo4j...")
    llm_client = DeterministicPersonasLLMClient() if use_mock_llm else MiroFishLLMClient()
    embedder = SentenceTransformerEmbedder()
    cross_encoder = LocalPassthroughCrossEncoder()
    store = GraphitiGraphStore(
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
    )

    test_graph_id = f"graph-personas-{uuid.uuid4().hex[:8]}"
    project: Optional[Project] = None
    created_gid: Optional[str] = None
    simulation_id: Optional[str] = None
    graph_cleaned_up: bool = False

    try:
        # Contrôle défensif des index Neo4j
        try:
            store._run_async(store._driver.build_indices_and_constraints())
            print("   ✓ Connectivité Neo4j établie et contraintes vérifiées.")
        except Exception as idx_err:
            print(f"   ℹ Notice contraintes Neo4j : {idx_err}")

        # Ingestion des données d'épisode via le contrat public GraphStore
        print(f"\n[2/6] Peuplement du graphe de test (ID={test_graph_id})...")
        created_gid = store.create_graph("Graphe Personas E2E", graph_id=test_graph_id)

        sample_episodes = [
            "Alice Martin dirige l'équipe d'ingénierie chez Thalès Défense à Brest Maritime. "
            "Le Professeur Durand collabore avec Alice Martin sur les systèmes sonar de pointe.",
            "Thalès Défense étend ses infrastructures à Brest Maritime pour tester de nouveaux capteurs maritimes.",
        ]

        for ep in sample_episodes:
            store.add_episode(
                graph_id=created_gid,
                text=ep,
                source_description="Rapport maritime local",
            )
        print(f"   ✓ Épisodes ingérés dans Neo4j via store.add_episode (group_id={created_gid}).")

        # Création du projet MiroFish
        project = ProjectManager.create_project(name="Test Simulation E2E Story 004-4")
        project.graph_id = created_gid
        project.simulation_requirement = "Simuler les interactions et réactions autour des technologies de défense navale."
        project.status = ProjectStatus.GRAPH_COMPLETED
        sample_doc = "Rapport complet sur les programmes de défense navale à Brest."
        ProjectManager.save_extracted_text(project.project_id, sample_doc)
        ProjectManager.save_project(project)
        print(f"   ✓ Projet '{project.project_id}' configuré et lié au graphe local.")

        # Étape 3 : Extraction des entités via ZepEntityReader
        print("\n[3/6] Extraction et filtrage des entités via ZepEntityReader...")
        reader = ZepEntityReader(store=store)
        filtered = reader.filter_defined_entities(graph_id=created_gid, enrich_with_edges=True)
        print(f"   ✓ Entités extraites : {filtered.filtered_count} entités trouvées.")
        for e in filtered.entities:
            print(f"     * Entité: {e.name} | type={e.get_entity_type()} | summary={e.summary[:60]}... | {len(e.related_edges)} arêtes")

        assert filtered.filtered_count >= 3, f"Nombre d'entités insuffisant ({filtered.filtered_count} < 3)"
        rapport["criteres"]["C4_extraction_entites_reussie"] = True

        # Étape 4 : Orchestration complète via SimulationManager.prepare_simulation
        print("\n[4/6] Exécution de SimulationManager.create_simulation et prepare_simulation...")
        sim_manager = SimulationManager()
        sim_state = sim_manager.create_simulation(
            project_id=project.project_id,
            graph_id=created_gid,
            enable_twitter=True,
            enable_reddit=True,
        )
        simulation_id = sim_state.simulation_id
        print(f"   ✓ Simulation créée : {simulation_id}")

        # On utilise store mocké/injecté et use_llm=False pour un banc rapide et déterministe
        # (ou use_llm=True si --real-llm est spécifié)
        use_llm_profiles = not use_mock_llm
        # Injection de store via le gestionnaire officiel override_graph_store
        with override_graph_store(store):
            prepared_state = sim_manager.prepare_simulation(
                simulation_id=simulation_id,
                simulation_requirement=project.simulation_requirement,
                document_text=sample_doc,
                use_llm_for_profiles=use_llm_profiles,
                parallel_profile_count=2,
            )

        print(f"   ✓ Préparation terminée avec statut={prepared_state.status.value}")
        print(f"     - Profils générés : {prepared_state.profiles_count} (exigé >= 3)")
        print(f"     - Config générée : {prepared_state.config_generated}")

        assert prepared_state.status == SimulationStatus.READY
        assert prepared_state.profiles_count >= 3
        rapport["criteres"]["C4_seuil_personas_atteint"] = True

        # Étape 5 : Contrôle formel des fichiers générés
        print("\n[5/6] Contrôle de conformité des fichiers d'artefacts générés...")
        sim_dir = sim_manager._get_simulation_dir(simulation_id)
        
        reddit_json_path = os.path.join(sim_dir, "reddit_profiles.json")
        twitter_csv_path = os.path.join(sim_dir, "twitter_profiles.csv")
        sim_config_path = os.path.join(sim_dir, "simulation_config.json")

        assert os.path.exists(reddit_json_path), "reddit_profiles.json manquant"
        assert os.path.exists(twitter_csv_path), "twitter_profiles.csv manquant"
        assert os.path.exists(sim_config_path), "simulation_config.json manquant"

        # Validation Reddit JSON
        with open(reddit_json_path, "r", encoding="utf-8") as f:
            reddit_data = json.load(f)
        assert isinstance(reddit_data, list) and len(reddit_data) >= 3
        for item in reddit_data:
            assert "user_id" in item and isinstance(item["user_id"], int)
            assert "username" in item and len(item["username"]) > 0
            assert "name" in item and len(item["name"]) > 0
            assert "bio" in item
            assert "persona" in item
            assert "gender" in item and item["gender"] in ("male", "female", "other")
            assert "mbti" in item
            assert "country" in item
        print(f"   ✓ reddit_profiles.json valide ({len(reddit_data)} profils complets).")
        rapport["criteres"]["C4_format_reddit_json_valide"] = True

        # Validation Twitter CSV
        with open(twitter_csv_path, "r", encoding="utf-8", newline="") as f:
            reader_csv = csv.DictReader(f)
            twitter_rows = list(reader_csv)
        assert len(twitter_rows) >= 3
        expected_headers = {"user_id", "name", "username", "user_char", "description"}
        assert expected_headers.issubset(set(twitter_rows[0].keys()))
        for row in twitter_rows:
            assert row["user_id"].isdigit()
            assert len(row["name"]) > 0
            assert len(row["username"]) > 0
            assert len(row["user_char"]) > 0
            assert len(row["description"]) > 0
        print(f"   ✓ twitter_profiles.csv valide ({len(twitter_rows)} profils CSV OASIS conformes).")
        rapport["criteres"]["C4_format_twitter_csv_valide"] = True

        # Validation Simulation Config JSON
        with open(sim_config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        assert "simulation_id" in config_data and config_data["simulation_id"] == simulation_id
        assert "time_config" in config_data
        assert "agent_configs" in config_data and len(config_data["agent_configs"]) >= 3
        assert "event_config" in config_data
        assert "twitter_config" in config_data and config_data["twitter_config"] is not None
        assert "reddit_config" in config_data and config_data["reddit_config"] is not None
        print(f"   ✓ simulation_config.json valide (TimeConfig, EventConfig, {len(config_data['agent_configs'])} AgentConfigs).")
        rapport["criteres"]["C4_config_simulation_valide"] = True

        # Étape 6 : Nettoyage
        print("\n[6/6] Nettoyage des données et du graphe de test...")
        if not keep_graph:
            store.delete_graph(created_gid)
            graph_cleaned_up = True
            print("   ✓ Graphe temporaire purgé de Neo4j.")
        if not keep_artifacts and os.path.exists(sim_dir):
            shutil.rmtree(sim_dir, ignore_errors=True)
            print("   ✓ Répertoire de simulation temporaire purgé.")
        
        rapport["criteres"]["C4_nettoyage_propre"] = True
        rapport["statut"] = "SUCCES"
        rapport["details"] = {
            "simulation_id": simulation_id,
            "graph_id": created_gid,
            "profiles_count": len(reddit_data),
            "agent_configs_count": len(config_data["agent_configs"]),
        }

    except Exception as e:
        import traceback
        print(f"\n❌ ERREUR lors de la génération de personas/simulation : {e}")
        traceback.print_exc()
        rapport["details"]["erreur"] = str(e)
    finally:
        if not keep_graph and created_gid and not graph_cleaned_up:
            try:
                store.delete_graph(created_gid)
                print(f"   ✓ Graphe orphelin '{created_gid}' purgé de Neo4j dans finally.")
            except Exception:
                pass
        if project and not keep_graph:
            try:
                ProjectManager.delete_project(project.project_id)
            except Exception:
                pass
        if not keep_artifacts and simulation_id:
            try:
                sim_d = sim_manager._get_simulation_dir(simulation_id)
                if os.path.exists(sim_d):
                    shutil.rmtree(sim_d, ignore_errors=True)
            except Exception:
                pass
        try:
            store.close()
        except Exception:
            pass
        finally:
            Config.ZEP_BACKEND = orig_zep_backend
            Config.ZEP_API_KEY = orig_zep_api_key

    print("\n" + "=" * 75)
    print("BILAN FORMEL DE LA STORY 004-4 (CRITÈRE C4) :")
    for crit, val in rapport["criteres"].items():
        symbole = "✅ VALIDÉ" if val else "❌ ÉCHEC"
        print(f"  - {crit:<40} : {symbole}")
    print("=" * 75)

    return rapport


def main() -> int:
    parser = argparse.ArgumentParser(description="Vérification personas et simulation Story 004-4 (Critère C4)")
    llm_group = parser.add_mutually_exclusive_group()
    llm_group.add_argument(
        "--real-llm",
        action="store_true",
        help="Utiliser le client LLM réel OpenCode Go au lieu du mock déterministe",
    )
    llm_group.add_argument(
        "--mock-llm",
        action="store_true",
        help="Utiliser le client LLM mocké déterministe (défaut)",
    )
    parser.add_argument(
        "--keep-graph",
        action="store_true",
        help="Conserver le graphe de test dans Neo4j après exécution",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Conserver les artefacts générés (reddit_profiles.json, twitter_profiles.csv, simulation_config.json)",
    )
    args = parser.parse_args()
    use_mock = not args.real_llm

    try:
        rapport = run_personas_simulation_validation(
            use_mock_llm=use_mock,
            keep_graph=args.keep_graph,
            keep_artifacts=args.keep_artifacts,
        )
        if rapport["statut"] == "SUCCES":
            print("\n🎉 GÉNÉRATION DE PERSONAS ET CONFIGURATION DE SIMULATION VALIDÉES (CRITÈRE C4 SATISFAIT).")
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
