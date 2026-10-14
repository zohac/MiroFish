#!/usr/bin/env python3
"""Sonde de qualification C3 : régénération déterministe et budget de performance.

Cette sonde mesure :
1. La lecture des documents du corpus (10K et 50K) ;
2. La construction du contexte et l'appel LLM (`OntologyGenerator.generate`) à `temperature=0.0` ;
3. Le post-traitement et la validation de l'ontologie résultante ;
4. La pose durable réussie sur un graphe dédié via le contrat `GraphStore.set_ontology` ;
5. L'égalité stricte des projections canoniques (champs stables : types d'entité,
   types de relation, attributs rattachés à leur parent) entre deux générations
   indépendantes consécutives ;
6. Le respect des budgets de temps (< 30s hôte / < 45s Docker pour 50K).

Usage :
    uv run python scripts/verifier_ontology_regeneration.py
    uv run python scripts/verifier_ontology_regeneration.py --docker
    uv run python scripts/verifier_ontology_regeneration.py --output docs/plans/007-ontologie-dynamique/mesure-007-3-hote.json
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

_scripts_dir = Path(__file__).resolve().parent
_backend_dir = _scripts_dir.parent
_project_root = _backend_dir.parent
sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv

for _candidate in (_project_root / ".env", _backend_dir / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate)

from app.config import Config
from app.services.ontology_generator import OntologyGenerator
from app.utils.graph_store import GraphStore
from app.utils.graph_store.base import AppliedOntology
from app.utils.graph_store.graphiti_store import (
    GraphitiGraphStore,
    LocalPassthroughCrossEncoder,
)
from app.utils.graphiti_embedder import SentenceTransformerEmbedder
from app.utils.graphiti_llm_client import MiroFishLLMClient
from app.utils.ontology import canonical_ontology_projection

FIXTURES_REGEN_DIR = _backend_dir / "tests" / "fixtures" / "ontology" / "regeneration"

SEUIL_HOTE_50K_S = 30.0
SEUIL_DOCKER_50K_S = 45.0


def charger_corpus(corpus_id: str, racine: Optional[Path] = None) -> Dict[str, Any]:
    """Charge un corpus (10K ou 50K) depuis son dossier de fixture et manifeste."""
    base = racine or FIXTURES_REGEN_DIR
    corpus_dir = base / corpus_id
    manifest_path = corpus_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifeste introuvable : {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    docs_dir = corpus_dir / "documents"

    document_texts: List[str] = []
    documents_detail: List[Dict[str, Any]] = []

    for entry in manifest.get("documents", []):
        filename = entry["filename"]
        doc_path = docs_dir / filename
        text = doc_path.read_text(encoding="utf-8")
        raw_bytes = doc_path.read_bytes()
        sha = hashlib.sha256(raw_bytes).hexdigest()

        if sha != entry.get("sha256"):
            raise ValueError(
                f"Empreinte SHA-256 non conforme pour {filename} : "
                f"attendu {entry.get('sha256')}, calculé {sha}"
            )

        document_texts.append(text)
        documents_detail.append({
            "filename": filename,
            "char_count": len(text),
            "byte_count": len(raw_bytes),
            "sha256": sha,
        })

    brief_info = manifest.get("brief", {})
    brief_text = brief_info.get("text", "")
    if not brief_text:
        brief_file = corpus_dir / "brief.txt"
        if brief_file.exists():
            brief_text = brief_file.read_text(encoding="utf-8")

    return {
        "corpus_id": corpus_id,
        "target_chars": manifest.get("target_chars", sum(len(t) for t in document_texts)),
        "actual_chars": sum(len(t) for t in document_texts),
        "combined_chars": manifest.get("combined_chars", len("\n\n---\n\n".join(document_texts))),
        "documents": documents_detail,
        "document_paths": [str(docs_dir / entry["filename"]) for entry in manifest.get("documents", [])],
        "document_texts": document_texts,
        "brief": brief_text,
        "brief_sha256": hashlib.sha256(brief_text.encode("utf-8")).hexdigest(),
    }


class StructuralOntologyMockLLM:
    """Mock LLM déterministe pour tester le parcours de la sonde hors quota ou sans réseau."""

    def __init__(self):
        self._responses = {
            "corpus_10k": {
                "entity_types": [
                    {
                        "name": "Operator",
                        "description": "Opérateur de télécommunications",
                        "attributes": [{"name": "operator_name", "type": "text"}, {"name": "license_id", "type": "text"}],
                    },
                    {
                        "name": "Municipality",
                        "description": "Commune ou collectivité territoriale",
                        "attributes": [{"name": "inhabitants", "type": "text"}],
                    },
                    {
                        "name": "Subscriber",
                        "description": "Abonné ou usager du réseau",
                        "attributes": [{"name": "plan_type", "type": "text"}],
                    },
                    {
                        "name": "Regulator",
                        "description": "Autorité de régulation sectorielle",
                        "attributes": [{"name": "jurisdiction", "type": "text"}],
                    },
                    {
                        "name": "Person",
                        "description": "Individu par défaut",
                        "attributes": [{"name": "full_name", "type": "text"}],
                    },
                    {
                        "name": "Organization",
                        "description": "Organisation par défaut",
                        "attributes": [{"name": "org_name", "type": "text"}],
                    },
                ],
                "edge_types": [
                    {
                        "name": "OPERATES_IN",
                        "description": "Exploite des infrastructures dans la commune",
                        "source_targets": [{"source": "Operator", "target": "Municipality"}],
                        "attributes": [{"name": "since_year", "type": "text"}],
                    },
                    {
                        "name": "REGULATES",
                        "description": "Régule les activités de l'opérateur",
                        "source_targets": [{"source": "Regulator", "target": "Operator"}],
                        "attributes": [],
                    },
                ],
                "analysis_summary": "Ontologie télécom déterministe.",
            },
            "corpus_50k": {
                "entity_types": [
                    {
                        "name": "GridOperator",
                        "description": "Gestionnaire de réseau de transport ou distribution",
                        "attributes": [{"name": "grid_voltage", "type": "text"}, {"name": "region", "type": "text"}],
                    },
                    {
                        "name": "TelecomOperator",
                        "description": "Opérateur de réseau télécom",
                        "attributes": [{"name": "spectrum_band", "type": "text"}],
                    },
                    {
                        "name": "EnergyConsumer",
                        "description": "Consommateur industriel ou particulier d'énergie",
                        "attributes": [{"name": "tariff_category", "type": "text"}],
                    },
                    {
                        "name": "SectorRegulator",
                        "description": "Autorité publique de régulation",
                        "attributes": [{"name": "annual_budget", "type": "text"}],
                    },
                    {
                        "name": "Person",
                        "description": "Individu par défaut",
                        "attributes": [{"name": "full_name", "type": "text"}],
                    },
                    {
                        "name": "Organization",
                        "description": "Organisation par défaut",
                        "attributes": [{"name": "org_name", "type": "text"}],
                    },
                ],
                "edge_types": [
                    {
                        "name": "CONNECTS_TO",
                        "description": "Raccordement au réseau",
                        "source_targets": [{"source": "EnergyConsumer", "target": "GridOperator"}],
                        "attributes": [{"name": "capacity_mw", "type": "text"}],
                    },
                    {
                        "name": "GOVERNED_BY",
                        "description": "Soumis au cadre réglementaire",
                        "source_targets": [{"source": "GridOperator", "target": "SectorRegulator"}],
                        "attributes": [],
                    },
                ],
                "analysis_summary": "Ontologie multi-réseaux 50K déterministe.",
            },
        }

    def chat_json(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        # Identifier le corpus par inspection du contenu du message utilisateur
        user_content = ""
        for m in messages:
            if m.get("role") == "user":
                user_content = m.get("content", "")
                break
        if "GridOperator" in user_content or "50000" in user_content or "ANNEXE B" in user_content or "réseaux d'infrastructure" in user_content:
            res = self._responses["corpus_50k"]
        elif "fibre optique" in user_content or "Valmont" in user_content:
            res = self._responses["corpus_10k"]
        else:
            res = self._responses["corpus_10k"]
        return copy.deepcopy(res)


def instancier_store_graphiti(use_mock_llm: bool = False) -> GraphitiGraphStore:
    """Instancie le store concret Graphiti configuré pour la mesure."""
    from graphiti_core.llm_client.client import LLMClient as BaseGraphitiLLM
    from graphiti_core.llm_client.config import LLMConfig

    class _MinimalGraphitiLLM(BaseGraphitiLLM):
        def __init__(self):
            super().__init__(LLMConfig(api_key="mock", base_url="http://mock.local/v1", model="mock"))

        async def _generate_response(self, *args, **kwargs):
            return {}

    llm = _MinimalGraphitiLLM() if use_mock_llm else MiroFishLLMClient()
    return GraphitiGraphStore(
        llm_client=llm,
        embedder=SentenceTransformerEmbedder(),
        cross_encoder=LocalPassthroughCrossEncoder(),
    )


def mesurer_une_generation(
    generator: OntologyGenerator,
    store: GraphStore,
    corpus: Dict[str, Any],
    graph_id: str,
    strict_policy: bool = False,
    time_fn: Any = time.perf_counter,
    store_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    """Exécute et chronomètre une passe de régénération complète : lecture → pose."""
    t0 = time_fn()

    # 1. Lecture / préparation des documents depuis le disque (AC5)
    doc_paths = corpus.get("document_paths")
    if doc_paths:
        doc_texts = [Path(p).read_text(encoding="utf-8") for p in doc_paths]
        brief = str(corpus.get("brief", ""))
    else:
        doc_texts = list(corpus["document_texts"])
        brief = str(corpus["brief"])
    t_read = time_fn()

    # 2. Génération via OntologyGenerator
    ontology_result = generator.generate(
        document_texts=doc_texts,
        simulation_requirement=brief,
    )
    t_gen = time_fn()

    diagnostics = generator.last_context_diagnostics

    # 3. Projection canonique
    projection = canonical_ontology_projection(ontology_result)

    # 4. Pose de l'ontologie sur le store
    store.set_ontology(graph_id, ontology_result, strict=strict_policy)
    t_pose = time_fn()

    # 5. Vérification de l'application (instance neuve pour étanchéité AC4)
    reader_store = store_factory() if store_factory is not None else store
    try:
        applied: Optional[AppliedOntology] = reader_store.get_applied_ontology(graph_id)
        if applied is None:
            raise RuntimeError(f"Ontologie non retenue après set_ontology sur le graphe {graph_id}")
    finally:
        if reader_store is not store and hasattr(reader_store, "close"):
            reader_store.close()

    duree_totale = t_pose - t0
    duree_lecture = t_read - t0
    duree_generation = t_gen - t_read
    duree_pose = t_pose - t_gen

    return {
        "graph_id": graph_id,
        "corpus_id": corpus["corpus_id"],
        "duree_totale_s": round(duree_totale, 3),
        "duree_lecture_s": round(duree_lecture, 3),
        "duree_generation_s": round(duree_generation, 3),
        "duree_pose_s": round(duree_pose, 3),
        "diagnostics": diagnostics,
        "ontology_raw": ontology_result,
        "projection_canonique": projection,
        "applied_ontology_entity_types": list(applied.entity_type_names),
        "applied_ontology_edge_types": list(applied.edge_type_names),
        "applied_strict": applied.strict,
    }


def _comparer_items_projection(
    items1: List[Dict[str, Any]],
    items2: List[Dict[str, Any]],
    label: str,
) -> List[str]:
    """Compare deux listes d'items d'ontologie en préservant les doublons (AC3)."""
    diffs: List[str] = []
    from collections import Counter

    names1 = [str(item.get("name", "")) for item in items1]
    names2 = [str(item.get("name", "")) for item in items2]

    # Détection des types manquants ou surnuméraires
    set1, set2 = set(names1), set(names2)
    if set1 != set2:
        plural_label = "types d'entité" if "entité" in label else "types de relation"
        diffs.append(
            f"Noms de {plural_label} divergents : essai 1 = {sorted(set1)}, essai 2 = {sorted(set2)}"
        )

    # Détection des multiplicités divergentes (doublons masqués évités)
    count1 = Counter(names1)
    count2 = Counter(names2)
    for name in sorted(set1 & set2):
        c1, c2 = count1[name], count2[name]
        if c1 != c2:
            diffs.append(
                f"Multiplicité du {label} '{name}' divergente : "
                f"essai 1 = {c1} occurrence(s), essai 2 = {c2} occurrence(s)"
            )

    # Comparaison des listes d'attributs
    groups1: Dict[str, List[List[str]]] = {}
    for item in items1:
        groups1.setdefault(str(item.get("name", "")), []).append(item.get("attributes", []))
    groups2: Dict[str, List[List[str]]] = {}
    for item in items2:
        groups2.setdefault(str(item.get("name", "")), []).append(item.get("attributes", []))

    for name in sorted(set1 & set2):
        if count1[name] == count2[name]:
            attrs1 = sorted(groups1[name])
            attrs2 = sorted(groups2[name])
            if attrs1 != attrs2:
                diffs.append(
                    f"Attributs du {label} '{name}' divergents : "
                    f"essai 1 = {attrs1 if len(attrs1) > 1 else attrs1[0]}, "
                    f"essai 2 = {attrs2 if len(attrs2) > 1 else attrs2[0]}"
                )

    return diffs


def comparer_projections(proj1: Dict[str, Any], proj2: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Compare deux projections canoniques et signale les différences structurelles."""
    differences: List[str] = []

    # Comparaison des types d'entité (avec préservation des doublons, AC3)
    diff_entities = _comparer_items_projection(
        proj1.get("entity_types", []),
        proj2.get("entity_types", []),
        label="type d'entité",
    )
    differences.extend(diff_entities)

    # Comparaison des types de relations (avec préservation des doublons, AC3)
    diff_edges = _comparer_items_projection(
        proj1.get("edge_types", []),
        proj2.get("edge_types", []),
        label="type de relation",
    )
    differences.extend(diff_edges)

    conforme = len(differences) == 0
    return conforme, differences


def evaluer_corpus_c3(
    generator: OntologyGenerator,
    store: GraphStore,
    corpus: Dict[str, Any],
    run_id: str,
    seuil_max_s: float,
    keep_graphs: bool = False,
    time_fn: Any = time.perf_counter,
    store_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    """Exécute les deux passes indépendantes pour un corpus donné et évalue la conformité."""
    corpus_id = corpus["corpus_id"]
    graph_id_1 = f"c3_{corpus_id}_1_{run_id}"
    graph_id_2 = f"c3_{corpus_id}_2_{run_id}"

    essai_1 = None
    essai_2 = None
    graphes_crees = []

    try:
        # Essai 1
        print(f"   [{corpus_id}] Essai 1 : création du graphe {graph_id_1}...")
        store.create_graph(name=f"Epreuve C3 {corpus_id} Essai 1", graph_id=graph_id_1)
        graphes_crees.append(graph_id_1)
        print(f"   [{corpus_id}] Essai 1 : génération de l'ontologie (lecture -> LLM -> validation -> pose)...")
        essai_1 = mesurer_une_generation(
            generator=generator,
            store=store,
            corpus=corpus,
            graph_id=graph_id_1,
            time_fn=time_fn,
            store_factory=store_factory,
        )
        print(f"   [{corpus_id}] Essai 1 terminé en {essai_1['duree_totale_s']} s (lecture: {essai_1['duree_lecture_s']} s, LLM: {essai_1['duree_generation_s']} s, pose: {essai_1['duree_pose_s']} s).")

        # Essai 2 (indépendant, sur graphe neuf)
        print(f"   [{corpus_id}] Essai 2 : création du graphe {graph_id_2}...")
        store.create_graph(name=f"Epreuve C3 {corpus_id} Essai 2", graph_id=graph_id_2)
        graphes_crees.append(graph_id_2)
        print(f"   [{corpus_id}] Essai 2 : génération indépendante...")
        essai_2 = mesurer_une_generation(
            generator=generator,
            store=store,
            corpus=corpus,
            graph_id=graph_id_2,
            time_fn=time_fn,
            store_factory=store_factory,
        )
        print(f"   [{corpus_id}] Essai 2 terminé en {essai_2['duree_totale_s']} s (lecture: {essai_2['duree_lecture_s']} s, LLM: {essai_2['duree_generation_s']} s, pose: {essai_2['duree_pose_s']} s).")

        deterministe, diffs = comparer_projections(
            essai_1["projection_canonique"],
            essai_2["projection_canonique"],
        )

        durees = [essai_1["duree_totale_s"], essai_2["duree_totale_s"]]
        max_duree = max(durees)
        budget_respecte = max_duree < seuil_max_s

        conforme_global = deterministe and budget_respecte

        return {
            "corpus_id": corpus_id,
            "target_chars": corpus["target_chars"],
            "actual_chars": corpus["actual_chars"],
            "combined_chars": corpus["combined_chars"],
            "essai_1": essai_1,
            "essai_2": essai_2,
            "deterministe": deterministe,
            "differences": diffs,
            "duree_essai_1_s": essai_1["duree_totale_s"],
            "duree_essai_2_s": essai_2["duree_totale_s"],
            "max_duree_s": max_duree,
            "seuil_s": seuil_max_s,
            "budget_respecte": budget_respecte,
            "conforme": conforme_global,
        }

    finally:
        if not keep_graphs:
            for g_id in graphes_crees:
                try:
                    store.delete_graph(g_id)
                except Exception as clean_err:
                    print(f"⚠ Nettoyage du graphe {g_id} : {clean_err}", file=sys.stderr)


def executer_verification_c3(
    is_docker: bool = False,
    output_path: Optional[Path] = None,
    keep_graphs: bool = False,
    use_mock_llm: bool = False,
    generator: Optional[OntologyGenerator] = None,
    store: Optional[GraphStore] = None,
    time_fn: Any = time.perf_counter,
    store_factory: Optional[Any] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Orchestre la vérification complète de C3 sur 10K et 50K."""
    seuil_50k = SEUIL_DOCKER_50K_S if is_docker else SEUIL_HOTE_50K_S
    # Le seuil pour 10K est indicatif ou aligné sur 50K
    seuil_10k = seuil_50k

    run_id = uuid.uuid4().hex[:8]
    if generator is not None:
        gen = generator
    elif use_mock_llm:
        gen = OntologyGenerator(llm_client=StructuralOntologyMockLLM())
    else:
        gen = OntologyGenerator()

    resolved_factory = store_factory
    if resolved_factory is None and store is None:
        resolved_factory = lambda: instancier_store_graphiti(use_mock_llm=use_mock_llm)

    if store is not None:
        st = store
    else:
        st = resolved_factory()

    try:
        # Initialisation à froid mesurée séparément
        t_init_start = time_fn()
        if hasattr(st, "_driver") and hasattr(st._driver, "build_indices_and_constraints"):
            st._run_async(st._driver.build_indices_and_constraints())
        t_init_duree = time_fn() - t_init_start

        resultats_corpora = []
        conforme_total = True

        for c_id, seuil in [("corpus_10k", seuil_10k), ("corpus_50k", seuil_50k)]:
            print(f"\n-> Évaluation du {c_id} (seuil {seuil}s)...")
            corpus = charger_corpus(c_id)
            res = evaluer_corpus_c3(
                generator=gen,
                store=st,
                corpus=corpus,
                run_id=run_id,
                seuil_max_s=seuil,
                keep_graphs=keep_graphs,
                time_fn=time_fn,
                store_factory=resolved_factory,
            )
            resultats_corpora.append(res)
            if not res["conforme"]:
                conforme_total = False

        payload = {
            "run_id": run_id,
            "date_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "environnement": "docker" if is_docker else "hote",
            "mode_mock_llm": use_mock_llm,
            "duree_initialisation_froide_s": round(t_init_duree, 3),
            "configuration_llm": {
                "temperature": 0.0,
                "max_tokens": None,
                "max_attempts": 2,
                "model_name": "mock-structural" if use_mock_llm else os.environ.get("LLM_MODEL_NAME", Config.LLM_MODEL_NAME),
                "base_url": "mock://local" if use_mock_llm else os.environ.get("LLM_BASE_URL", Config.LLM_BASE_URL),
            },
            "seuils": {
                "seuil_50k_s": seuil_50k,
                "seuil_10k_s": seuil_10k,
            },
            "corpora": {r["corpus_id"]: r for r in resultats_corpora},
            "verdict_global_go": conforme_total,
        }

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return conforme_total, payload
    finally:
        if store is None and hasattr(st, "close"):
            try:
                st.close()
            except Exception as close_err:
                print(f"⚠ Erreur lors de la fermeture du store : {close_err}", file=sys.stderr)



def main() -> int:
    parser = argparse.ArgumentParser(description="Sonde C3 : régénération déterministe et budget")
    parser.add_argument("--docker", action="store_true", help="Applique le seuil Docker (< 45s)")
    parser.add_argument("--mock-llm", action="store_true", help="Utilise un LLM simulé déterministe (test hors-quota/structurel)")
    parser.add_argument("--output", type=Path, default=None, help="Chemin du fichier JSON de sortie")
    parser.add_argument("--keep-graphs", action="store_true", help="Conserve les graphes Neo4j créés")
    args = parser.parse_args()

    print("=" * 78)
    print("SONDE C3 — RÉGÉNÉRATION DÉTERMINISTE ET BUDGET DE PERFORMANCE")
    print(f"Environnement : {'Docker (seuil < 45s)' if args.docker else 'Hôte (seuil < 30s)'}")
    print(f"Mode LLM : {'MOCK STRUCTUREL' if args.mock_llm else 'RÉEL'}")
    print("=" * 78)

    try:
        succes, payload = executer_verification_c3(
            is_docker=args.docker,
            output_path=args.output,
            keep_graphs=args.keep_graphs,
            use_mock_llm=args.mock_llm,
        )
        print(f"\nInitialisation store : {payload['duree_initialisation_froide_s']} s")
        for c_id, data in payload["corpora"].items():
            print(f"\n[{c_id}] ({data['actual_chars']} chars)")
            print(f"  Essai 1 : {data['duree_essai_1_s']} s")
            print(f"  Essai 2 : {data['duree_essai_2_s']} s")
            print(f"  Déterministe : {'OUI' if data['deterministe'] else 'NON'}")
            if data["differences"]:
                for diff in data["differences"]:
                    print(f"    - {diff}")
            print(f"  Budget respecté (< {data['seuil_s']}s) : {'OUI' if data['budget_respecte'] else 'NON'}")
            print(f"  Verdict corpus : {'CONFORME' if data['conforme'] else 'NON CONFORME'}")

        print("\n" + "=" * 78)
        print(f"VERDICT GLOBAL : {'GO' if succes else 'NO-GO'}")
        print("=" * 78)

        if args.output:
            print(f"Sortie enregistrée dans : {args.output}")

        return 0 if succes else 1

    except Exception as exc:
        print(f"\n❌ ERREUR LORS DE L'EXÉCUTION DE LA SONDE C3 : {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
