#!/usr/bin/env python3
"""Sonde réelle du critère C1 — persistance effective des labels d'ontologie.

Cette sonde mesure ce que l'ADR 0014 prétend avoir gagné : après une ingestion
**sous ontologie**, les nœuds du graphe portent-ils les labels déclarés, ou
restent-ils tous sur le label générique `:Entity` ?

Elle s'exécute contre l'instance Neo4j locale de l'environnement de référence
(ADR 0006, Epic 005) avec le moteur d'extraction réel de Graphiti, donc avec un
appel LLM réel par défaut. Le mode `--mock-llm` ne remplace que le LLM, jamais
le store, jamais Cypher : il vérifie le mécanisme, pas la qualité d'extraction.

Deux fixtures de domaines distincts sont ingérées, cinq documents chacune dont
un long de plus de 20 000 caractères. Le document long alimente l'échantillonnage
de l'ontologie ; l'ingestion en consomme un nombre borné de fragments par
document, comme le ferait une ingestion réelle bornée par `--max-fragments`.

Usage :
    cd backend && uv run python scripts/verifier_ontology_persistence.py
    cd backend && uv run python scripts/verifier_ontology_persistence.py --mock-llm
    cd backend && uv run python scripts/verifier_ontology_persistence.py --keep-graph
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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

from graphiti_core.llm_client.client import LLMClient
from graphiti_core.llm_client.config import LLMConfig

from app.services.graph_builder import plan_document_chunks
from app.utils.graph_store.graphiti_store import (
    GraphitiGraphStore,
    LocalPassthroughCrossEncoder,
)
from app.utils.graphiti_embedder import SentenceTransformerEmbedder
from app.utils.graphiti_llm_client import MiroFishLLMClient

#: Racine des fixtures d'épreuve C1 : deux domaines, cinq documents chacun.
FIXTURES_DIR = _backend_dir / "tests" / "fixtures" / "ontology"

#: Domaines measurés. Deux, parce qu'un seul ne prouverait pas que le mécanisme
#: est agnostique du contenu : c'est le critère même de l'epic 009 (C2).
DOMAINES = ("telecom", "energie")

#: Seuil du PRD : proportion minimale de nœuds portant un label d'ontologie.
SEUIL_POURCENTAGE = 80.0

#: Découpage aligné sur la production (`TextProcessor`, Epic 001).
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


class StructuralMockLLMClient(LLMClient):
    """LLM déterministe : vérifie le chemin des labels, pas la qualité d'extraction.

    Mesuré sur `graphiti-core` 0.30.2 : `_build_entity_types_context` **préfixe**
    un type générique `Entity` d'identifiant 0, et les types déclarés commencent à
    l'identifiant **1** (`node_operations.py:156-181`). Un LLM qui renvoie donc
    `entity_type_id = 0` produit un nœud `:Entity` — ce n'est pas un défaut de la
    pose des labels, c'est le choix « cette entité n'entre dans aucun type
    déclaré ». Pour vérifier le mécanisme, ce mock renvoie l'identifiant du
    premier type **déclaré** : si la pose échoue, le nœud portera quand même
    `Entity` seul, et la mesure le montrera.
    """

    #: Identifiant du premier type déclaré, l'index 0 étant le type générique
    #: injecté par Graphiti lui-même.
    PREMIER_TYPE_DECLARE = 1

    def __init__(self, entite: str = "Entite de preuve") -> None:
        super().__init__(
            LLMConfig(
                api_key="mock-key",
                base_url="https://mock.opencode.local/v1",
                model="mock-model",
            )
        )
        self.entite = entite

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
                    {
                        "name": self.entite,
                        "entity_type_id": self.PREMIER_TYPE_DECLARE,
                        "episode_indices": [0],
                    }
                ]
            }
        if model_name in ("SummarizedEntities", "EntitySummary"):
            return {
                "summaries": [
                    {"name": self.entite, "summary": "Entite de preuve structurelle."}
                ],
                "summary": "Entite de preuve structurelle.",
            }
        if model_name == "ExtractedEdges":
            return {"edges": []}
        if model_name == "EdgeDuplicate":
            return {"duplicate_facts": [], "contradicted_facts": []}
        if model_name == "NodeResolutions":
            return {"resolutions": []}
        return {}


def charger_fixture(domaine: str) -> Dict[str, Any]:
    """Charge le manifeste, l'ontologie et les documents d'un domaine.

    Les empreintes SHA-256 sont calculées ici, sur le texte réellement ingéré :
    c'est ce texte-là qui est mesuré, donc c'est lui qui est empreint.
    """
    racine = FIXTURES_DIR / domaine
    manifeste = json.loads((racine / "manifest.json").read_text(encoding="utf-8"))
    ontologie = json.loads(
        (racine / manifeste["ontology"]).read_text(encoding="utf-8")
    )

    documents: List[Dict[str, Any]] = []
    empreinte_documents = hashlib.sha256()
    for entree in manifeste["documents"]:
        chemin = racine / "documents" / entree["filename"]
        texte = chemin.read_text(encoding="utf-8")
        empreinte = hashlib.sha256(texte.encode("utf-8")).hexdigest()
        empreinte_documents.update(entree["filename"].encode("utf-8"))
        empreinte_documents.update(texte.encode("utf-8"))
        documents.append(
            {
                "document_id": entree["document_id"],
                "filename": entree["filename"],
                "role": entree["role"],
                "kind": entree["kind"],
                "text": texte,
                "sha256": empreinte,
                "longueur": len(texte),
            }
        )

    return {
        "domaine": domaine,
        "ontologie": ontologie,
        "documents": documents,
        "empreinte_documents": empreinte_documents.hexdigest(),
    }


def borner_fragments(
    plan_chunks: List[str],
    chunk_metadata: List[Dict[str, Any]],
    max_fragments: int,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Garde les `max_fragments` premiers fragments de chaque document.

    Le bornage est fait **après** le découpage et **par document**, pour qu'aucun
    document ne disparaisse : AC4 demande au moins deux fragments par document,
    pas une découpe uniforme qui viderait le document long.
    """
    par_document: Dict[str, int] = {}
    chunks: List[str] = []
    metadata: List[Dict[str, Any]] = []
    for texte, entree in zip(plan_chunks, chunk_metadata):
        document_id = entree["source_document_id"]
        deja_vus = par_document.get(document_id, 0)
        if deja_vus >= max_fragments:
            continue
        par_document[document_id] = deja_vus + 1
        chunks.append(texte)
        metadata.append(entree)
    return chunks, metadata


def compter_labels(store: GraphitiGraphStore, graph_id: str) -> Dict[str, Any]:
    """Comptage Cypher des nœuds typés et non typés du graphe `graph_id`.

    Le seuil porte sur `:Entity` : les nœuds `:Episodic` sont des épisodes, pas
    des entités, et les compter gonflerait artificiellement le dénominateur.
    """
    resultat = store._run_async(
        store._execute_cypher(
            """
            MATCH (n:Entity {group_id: $group_id})
            WITH n,
                 [label IN labels(n) WHERE label <> 'Entity' AND label <> 'Node'] AS specifiques
            RETURN count(n) AS total,
                   sum(CASE WHEN size(specifiques) > 0 THEN 1 ELSE 0 END) AS labelled,
                   max(size(specifiques)) AS max_labels_specifiques
            """,
            params={"group_id": graph_id},
        )
    )
    enregistrements = store._extract_records(resultat)
    if not enregistrements:
        raise RuntimeError(f"le comptage Cypher n'a rien renvoyé pour {graph_id}")
    return enregistrements[0]


def detail_par_label(
    store: GraphitiGraphStore, graph_id: str
) -> List[Tuple[str, int]]:
    """Répartition des nœuds par label d'ontologie, pour lire la mesure."""
    resultat = store._run_async(
        store._execute_cypher(
            """
            MATCH (n:Entity {group_id: $group_id})
            UNWIND labels(n) AS label
            WITH label, count(*) AS occurrences
            WHERE label <> 'Entity' AND label <> 'Node'
            RETURN label, occurrences
            ORDER BY occurrences DESC
            """,
            params={"group_id": graph_id},
        )
    )
    return [(str(r["label"]), int(r["occurrences"])) for r in store._extract_records(resultat)]


def compter_aretes(store: GraphitiGraphStore, graph_id: str) -> int:
    """Nombre d'arêtes du graphe — contexte, pas critère."""
    resultat = store._run_async(
        store._execute_cypher(
            "MATCH ()-[r]->() WHERE r.group_id = $group_id RETURN count(r) AS total",
            params={"group_id": graph_id},
        )
    )
    enregistrements = store._extract_records(resultat)
    return int(enregistrements[0]["total"]) if enregistrements else 0


def calculer_ratio(total_noeuds: int, noeuds_types: int) -> float:
    """Proportion de nœuds portant un label d'ontologie, en pourcentage.

    Fonction pure, pour que le calcul soit testable sans Neo4j : un graphe vide
    vaut **0**, jamais 100. Une division par zéro qui rendrait « tout va bien »
    ferait passer une ingestion qui n'a rien produit.
    """
    if total_noeuds <= 0:
        return 0.0
    return round(100.0 * noeuds_types / total_noeuds, 1)


def mesurer_domaine(
    store: GraphitiGraphStore,
    fixture: Dict[str, Any],
    graph_id: str,
    max_fragments: int,
) -> Dict[str, Any]:
    """Pose l'ontologie, ingère les fragments bornés, puis mesure."""
    domaine = fixture["domaine"]
    ontologie = fixture["ontologie"]
    types_declares = [t["name"] for t in ontologie["entity_types"]]

    documents = [
        {
            "document_id": doc["document_id"],
            "filename": doc["filename"],
            "role": doc["role"],
        }
        for doc in fixture["documents"]
    ]
    textes = {
        doc["document_id"]: doc["text"] for doc in fixture["documents"]
    }

    store.create_graph(name=f"Epreuve C1 {domaine}", graph_id=graph_id)

    # L'ontologie est posée AVANT toute ingestion : c'est l'ordre que
    # `GraphBuilderService` garantit, et celui que l'ADR 0014 déclare porteur.
    store.set_ontology(graph_id, ontologie)
    appliquee = store.get_applied_ontology(graph_id)
    if not appliquee or not (appliquee.entity_type_names or appliquee.edge_type_names):
        raise RuntimeError(f"l'ontologie n'a pas ete retenue pour {graph_id}")

    plan = plan_document_chunks(
        documents, textes, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    chunks, chunk_metadata = borner_fragments(
        plan.chunks, plan.chunk_metadata, max_fragments
    )
    if not chunks:
        raise RuntimeError(f"aucun fragment a ete produit pour le domaine {domaine}")

    debut = time.perf_counter()
    lot = store.add_text_batch(
        graph_id=graph_id,
        chunks=chunks,
        batch_size=350,
        chunk_metadata=chunk_metadata,
    )
    store.wait_for_batch(lot, timeout=900.0)
    duree = time.perf_counter() - debut

    comptage = compter_labels(store, graph_id)
    total = int(comptage["total"])
    types = int(comptage["labelled"])
    pourcentage = calculer_ratio(total, types)

    return {
        "domaine": domaine,
        "graph_id": graph_id,
        "types_declares": types_declares,
        "documents_total": len(documents),
        "documents_ingestes": len(plan.per_document_counts()),
        "fragments_ingestes": len(chunks),
        "total_noeuds": total,
        "noeuds_types": types,
        "pourcentage": pourcentage,
        "max_labels_specifiques": int(comptage["max_labels_specifiques"] or 0),
        "aretes": compter_aretes(store, graph_id),
        "detail_labels": detail_par_label(store, graph_id),
        "empreinte_documents": fixture["empreinte_documents"],
        "empreinte_ontologie": hashlib.sha256(
            json.dumps(ontologie, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "duree_ingestion_s": round(duree, 1),
        "documents_detail": [
            {
                "document_id": doc["document_id"],
                "filename": doc["filename"],
                "kind": doc["kind"],
                "longueur": doc["longueur"],
                "sha256": doc["sha256"],
            }
            for doc in fixture["documents"]
        ],
    }


def rendre_rapport(
    mesures: List[Dict[str, Any]],
    seuil: float,
    run_id: str,
    mock_llm: bool,
    max_fragments: int,
) -> str:
    """Rend la mesure en texte, dans la forme de la convention Epic 001-2."""
    toutes_conformes = all(m["pourcentage"] >= seuil for m in mesures)
    lignes = []
    lignes.append("=" * 78)
    lignes.append("MESURE 007-1 — PERSISTANCE EFFECTIVE DES LABELS D'ONTOLOGIE")
    lignes.append(f"Mesure sur : {datetime.now(timezone.utc).isoformat()}")
    lignes.append(f"Run : {run_id}")
    lignes.append(f"Mode LLM : {'MOCK STRUCTUREL' if mock_llm else 'REEL (OpenCode Go)'}")
    lignes.append(f"Fragments ingeres par document : {max_fragments}")
    lignes.append(f"Seuil C1 : {seuil:.1f} % de noeuds avec un label custom non `Entity`")
    lignes.append("=" * 78)
    lignes.append("")
    lignes.append(
        "Domaine | Documents | Fragments | Noeuds :Entity | Avec label custom | % | Max labels/nœud"
    )
    lignes.append("-" * 110)
    for mesure in mesures:
        lignes.append(
            f"{mesure['domaine']} | {mesure['documents_ingestes']}/{mesure['documents_total']}"
            f" | {mesure['fragments_ingestes']}"
            f" | {mesure['total_noeuds']}"
            f" | {mesure['noeuds_types']}"
            f" | {mesure['pourcentage']:.1f} %"
            f" | {mesure['max_labels_specifiques']}"
        )
    lignes.append("")
    lignes.append("Empreintes SHA-256 des fixtures")
    lignes.append("-" * 110)
    for mesure in mesures:
        lignes.append(
            f"  {mesure['domaine']} : documents={mesure['empreinte_documents']}"
        )
        lignes.append(f"  {mesure['domaine']} : ontologie={mesure['empreinte_ontologie']}")
        for document in mesure["documents_detail"]:
            lignes.append(
                f"    {document['document_id']} ({document['kind']}, "
                f"{document['longueur']} car.) : {document['sha256']}"
            )
    lignes.append("")
    lignes.append("Detail par label d'ontologie")
    lignes.append("-" * 110)
    for mesure in mesures:
        lignes.append(f"  {mesure['domaine']} ({mesure['graph_id']}) :")
        lignes.append(f"    types declares : {', '.join(mesure['types_declares'])}")
        if mesure["detail_labels"]:
            for label, occurrences in mesure["detail_labels"]:
                lignes.append(f"    {label} : {occurrences}")
        else:
            lignes.append("    (aucun label d'ontologie pose)")
        lignes.append(
            f"    aretes : {mesure['aretes']} | duree d'ingestion : "
            f"{mesure['duree_ingestion_s']} s"
        )
    lignes.append("")
    lignes.append("Controle de l'invariant architecture §9.2")
    lignes.append("-" * 110)
    lignes.append(
        "Un nœud doit porter au plus un label non `Entity`."
    )
    for mesure in mesures:
        verdict = "TENU" if mesure["max_labels_specifiques"] <= 1 else "ROMPU"
        lignes.append(
            f"  {mesure['domaine']} : max {mesure['max_labels_specifiques']} "
            f"label(s) specifique(s) -> {verdict}"
        )
    lignes.append("")
    lignes.append("=" * 78)
    for mesure in mesures:
        verdict = "CONFORME" if mesure["pourcentage"] >= seuil else "NON CONFORME"
        lignes.append(
            f"C1 / {mesure['domaine']} : {mesure['pourcentage']:.1f} % "
            f"(seuil {seuil:.1f} %) -> {verdict}"
        )
    lignes.append("")
    lignes.append(
        "VERDICT GLOBAL : "
        + ("GO — les labels d'ontologie sont persistes" if toutes_conformes else "NO-GO")
    )
    lignes.append("=" * 78)
    return "\n".join(lignes)


def verifier_critere_c1(
    use_mock_llm: bool = False,
    keep_graph: bool = False,
    max_fragments: int = 3,
    seuil: float = SEUIL_POURCENTAGE,
    output_path: Optional[Path] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Exécute la mesure C1 sur les deux domaines et rend le verdict."""
    print("=" * 78)
    print("SONDE C1 — PERSISTANCE EFFECTIVE DES LABELS D'ONTOLOGIE (EPIC 007-1)")
    print(f"Mode LLM : {'MOCK STRUCTUREL' if use_mock_llm else 'REEL (OpenCode Go)'}")
    print(f"Fragments ingeres par document : {max_fragments}")
    print(f"Seuil : {seuil:.1f} %")
    print("=" * 78)

    llm_client = (
        StructuralMockLLMClient(entite="Entite de preuve structurelle")
        if use_mock_llm
        else MiroFishLLMClient()
    )
    store = GraphitiGraphStore(
        llm_client=llm_client,
        embedder=SentenceTransformerEmbedder(),
        cross_encoder=LocalPassthroughCrossEncoder(),
    )

    run_id = uuid.uuid4().hex[:8]
    mesures: List[Dict[str, Any]] = []
    # Le nettoyage doit avoir lieu **avant** `close()` : le runner asynchrone est
    # arrêté à la fermeture, et un Cypher Afterwards lèverait au lieu de
    # supprimer.
    try:
        neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
        print(f"\n[1/3] Connexion a l'instance Neo4j ({neo4j_uri}, user={neo4j_user})...")
        store._run_async(store._driver.build_indices_and_constraints())
        print("   ✓ Connectivite Bolt etablie, index Graphiti initialises.")

        print(f"\n[2/3] Mesure sur {len(DOMAINES)} domaines de fixtures...")
        for domaine in DOMAINES:
            fixture = charger_fixture(domaine)
            graph_id = f"c1_{domaine}_{run_id}"
            mesure = mesurer_domaine(store, fixture, graph_id, max_fragments)
            mesures.append(mesure)
            print(
                f"   {domaine} : {mesure['total_noeuds']} noeuds, "
                f"{mesure['noeuds_types']} avec label custom "
                f"({mesure['pourcentage']:.1f} %), {mesure['aretes']} aretes, "
                f"{mesure['duree_ingestion_s']} s"
            )

        rapport = rendre_rapport(mesures, seuil, run_id, use_mock_llm, max_fragments)
        print("\n" + rapport)

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rapport + "\n", encoding="utf-8")
            print(f"\nMesure consignee : {output_path}")
            print(
                "SHA-256 du rapport : "
                f"{hashlib.sha256(rapport.encode('utf-8')).hexdigest()}"
            )

        if not keep_graph:
            for mesure in mesures:
                store._run_async(
                    store._execute_cypher(
                        "MATCH (n {group_id: $group_id}) DETACH DELETE n",
                        params={"group_id": mesure["graph_id"]},
                    )
                )
            print("\nGraphes d'epreuve supprimes (group_id isole).")
        else:
            print(
                "\nGraphes conserves : " + ", ".join(m["graph_id"] for m in mesures)
            )
    finally:
        store.close()

    conforme = all(m["pourcentage"] >= seuil for m in mesures)
    return conforme, {"mesures": mesures, "rapport": rapport, "run_id": run_id}


def main() -> int:
    analyseur = argparse.ArgumentParser(
        description="Mesure le critere C1 de l'epic 007-1 (labels d'ontologie persistes)."
    )
    analyseur.add_argument(
        "--mock-llm",
        action="store_true",
        help="Remplace le LLM par un client deterministe (verifie le mecanisme, pas la qualite).",
    )
    analyseur.add_argument(
        "--keep-graph",
        action="store_true",
        help="Conserve les graphes d'epreuve dans Neo4j au lieu de les supprimer.",
    )
    analyseur.add_argument(
        "--max-fragments",
        type=int,
        default=3,
        help="Fragments ingeres par document (AC4 demande au moins 2).",
    )
    analyseur.add_argument(
        "--seuil",
        type=float,
        default=SEUIL_POURCENTAGE,
        help="Pourcentage minimal de noeuds avec un label d'ontologie.",
    )
    analyseur.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Fichier de sortie de la mesure (aucun fichier ecrit si absent).",
    )
    arguments = analyseur.parse_args()

    if arguments.max_fragments < 2:
        print("ERREUR : --max-fragments doit valoir au moins 2 (AC4).", file=sys.stderr)
        return 2

    conforme, _ = verifier_critere_c1(
        use_mock_llm=arguments.mock_llm,
        keep_graph=arguments.keep_graph,
        max_fragments=arguments.max_fragments,
        seuil=arguments.seuil,
        output_path=arguments.output,
    )
    return 0 if conforme else 1


if __name__ == "__main__":
    raise SystemExit(main())