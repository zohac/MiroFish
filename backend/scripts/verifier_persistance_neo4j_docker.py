#!/usr/bin/env python3
"""Sonde de vérification autonome de persistance des données Neo4j et cycle de vie des volumes.

Story 005-4 (Epic 005 : Environnement Docker de référence — Docker-first).
Démontre la conformité au critère de sortie C3 du PRD et à l'ADR 0006 :
  - C3 : Un graphe créé dans Neo4j est 100 % intact après un cycle `docker compose down && docker compose up -d` (sans flag -v).
  - Cycle de vie : Un cycle `docker compose down -v` détruit le volume nommé `neo4j_data` et réinitialise l'instance.
  - Persistance bind : Les montages bind `./backend/uploads` et `./backend/simulations` conservent leurs fichiers.

Usage :
    cd backend && uv run python scripts/verifier_persistance_neo4j_docker.py cycle-complet
    cd backend && uv run python scripts/verifier_persistance_neo4j_docker.py ecrire --tag mon_tag
    cd backend && uv run python scripts/verifier_persistance_neo4j_docker.py verifier --tag mon_tag
    cd backend && uv run python scripts/verifier_persistance_neo4j_docker.py purger --tag mon_tag
    cd backend && uv run python scripts/verifier_persistance_neo4j_docker.py cycle-complet --mock
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
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

try:
    from neo4j import Driver, GraphDatabase
except ImportError:
    Driver = Any
    GraphDatabase = None


LABEL_WITNESS = "PersistenceWitnessNode"
REL_WITNESS = "PERSISTENCE_WITNESS_REL"


@dataclass
class NodeWitness:
    name: str
    category: str
    score: float
    properties: Dict[str, Any]


@dataclass
class EdgeWitness:
    source_name: str
    target_name: str
    relation_type: str
    weight: float
    valid_at: str


@dataclass
class DonneesTemoin:
    tag: str
    created_at: str
    nodes: List[NodeWitness]
    edges: List[EdgeWitness]
    fichiers_bind: Dict[str, str] = field(default_factory=dict)  # rel_path -> sha256


@dataclass
class ResultatControle:
    nom: str
    statut: str  # OK, ECHEC, IGNORE
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RapportPersistance:
    timestamp_utc: str
    tag: str
    mode: str
    controles: List[ResultatControle]
    succes_global: bool
    duree_secondes: float


def generer_donnees_temoin(tag: Optional[str] = None) -> DonneesTemoin:
    """Génère un jeu de données témoin déterministe pour tester la persistance."""
    tag_effectif = tag or f"witness_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    nodes = [
        NodeWitness(
            name=f"Entity_Alpha_{tag_effectif}",
            category="Organization",
            score=0.95,
            properties={"tag": tag_effectif, "importance": "high", "active": True, "index": 1},
        ),
        NodeWitness(
            name=f"Entity_Beta_{tag_effectif}",
            category="Person",
            score=0.88,
            properties={"tag": tag_effectif, "role": "Lead Researcher", "active": True, "index": 2},
        ),
        NodeWitness(
            name=f"Entity_Gamma_{tag_effectif}",
            category="Concept",
            score=0.72,
            properties={"tag": tag_effectif, "field": "Simulation", "active": False, "index": 3},
        ),
        NodeWitness(
            name=f"Entity_Delta_{tag_effectif}",
            category="Location",
            score=0.64,
            properties={"tag": tag_effectif, "city": "Paris", "active": True, "index": 4},
        ),
        NodeWitness(
            name=f"Entity_Epsilon_{tag_effectif}",
            category="Document",
            score=0.55,
            properties={"tag": tag_effectif, "pages": 42, "active": True, "index": 5},
        ),
    ]

    edges = [
        EdgeWitness(
            source_name=nodes[0].name,
            target_name=nodes[1].name,
            relation_type="EMPLOYS",
            weight=1.0,
            valid_at=now_iso,
        ),
        EdgeWitness(
            source_name=nodes[1].name,
            target_name=nodes[2].name,
            relation_type="RESEARCHES",
            weight=0.85,
            valid_at=now_iso,
        ),
        EdgeWitness(
            source_name=nodes[0].name,
            target_name=nodes[3].name,
            relation_type="LOCATED_IN",
            weight=0.9,
            valid_at=now_iso,
        ),
        EdgeWitness(
            source_name=nodes[1].name,
            target_name=nodes[4].name,
            relation_type="AUTHORED",
            weight=0.75,
            valid_at=now_iso,
        ),
    ]

    return DonneesTemoin(
        tag=tag_effectif,
        created_at=now_iso,
        nodes=nodes,
        edges=edges,
    )


def creer_driver_neo4j(
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> Any:
    """Crée une instance de driver Neo4j connectée à la base."""
    if GraphDatabase is None:
        raise RuntimeError("Le paquet 'neo4j' n'est pas disponible dans l'environnement Python.")

    uri_eff = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user_eff = user or os.getenv("NEO4J_USER", "neo4j")
    pwd_eff = password or os.getenv("NEO4J_PASSWORD", "password")

    return GraphDatabase.driver(uri_eff, auth=(user_eff, pwd_eff))


def ecrire_graphe_temoin(driver: Any, donnees: DonneesTemoin) -> Dict[str, Any]:
    """Écrit les nœuds et arêtes témoins dans Neo4j."""
    query_node = (
        f"MERGE (n:{LABEL_WITNESS} {{name: $name, tag: $tag}}) "
        f"ON CREATE SET n.category = $category, n.score = $score, "
        f"n.created_at = $created_at, n += $properties "
        f"RETURN n.name AS name"
    )

    query_edge = (
        f"MATCH (a:{LABEL_WITNESS} {{name: $source, tag: $tag}}), "
        f"      (b:{LABEL_WITNESS} {{name: $target, tag: $tag}}) "
        f"MERGE (a)-[r:{REL_WITNESS} {{type: $rel_type, tag: $tag}}]->(b) "
        f"ON CREATE SET r.weight = $weight, r.valid_at = $valid_at "
        f"RETURN type(r) AS rel_type"
    )

    nodes_crees = 0
    edges_crees = 0

    with driver.session() as session:
        for node in donnees.nodes:
            params = {
                "name": node.name,
                "tag": donnees.tag,
                "category": node.category,
                "score": node.score,
                "created_at": donnees.created_at,
                "properties": node.properties,
            }
            res = session.run(query_node, params)
            if res.single():
                nodes_crees += 1

        for edge in donnees.edges:
            params = {
                "source": edge.source_name,
                "target": edge.target_name,
                "rel_type": edge.relation_type,
                "tag": donnees.tag,
                "weight": edge.weight,
                "valid_at": edge.valid_at,
            }
            res = session.run(query_edge, params)
            if res.single():
                edges_crees += 1

    return {
        "tag": donnees.tag,
        "nodes_crees": nodes_crees,
        "edges_crees": edges_crees,
    }


def relire_graphe_temoin(driver: Any, tag: str) -> Dict[str, Any]:
    """Relit l'intégralité du graphe témoin associé à un tag dans Neo4j."""
    query_nodes = (
        f"MATCH (n:{LABEL_WITNESS} {{tag: $tag}}) "
        f"RETURN n.name AS name, n.category AS category, n.score AS score, properties(n) AS props "
        f"ORDER BY n.name ASC"
    )

    query_edges = (
        f"MATCH (a:{LABEL_WITNESS} {{tag: $tag}})-[r:{REL_WITNESS} {{tag: $tag}}]->(b:{LABEL_WITNESS} {{tag: $tag}}) "
        f"RETURN a.name AS source, b.name AS target, r.type AS rel_type, r.weight AS weight, r.valid_at AS valid_at "
        f"ORDER BY a.name ASC, b.name ASC, r.type ASC"
    )

    nodes_lus = []
    edges_lus = []

    with driver.session() as session:
        res_n = session.run(query_nodes, {"tag": tag})
        for record in res_n:
            props = dict(record["props"])
            nodes_lus.append({
                "name": record["name"],
                "category": record["category"],
                "score": record["score"],
                "properties": props,
            })

        res_e = session.run(query_edges, {"tag": tag})
        for record in res_e:
            edges_lus.append({
                "source": record["source"],
                "target": record["target"],
                "relation_type": record["rel_type"],
                "weight": record["weight"],
                "valid_at": record["valid_at"],
            })

    # Calcul d'un hash canonique pour contrôle d'intégrité
    snapshot_data = json.dumps({"nodes": nodes_lus, "edges": edges_lus}, sort_keys=True)
    hash_sha256 = hashlib.sha256(snapshot_data.encode("utf-8")).hexdigest()

    return {
        "tag": tag,
        "count_nodes": len(nodes_lus),
        "count_edges": len(edges_lus),
        "nodes": nodes_lus,
        "edges": edges_lus,
        "hash_sha256": hash_sha256,
    }


def nettoyer_graphe_temoin(driver: Any, tag: str) -> int:
    """Supprime les nœuds et relations témoins associés à un tag."""
    query = (
        f"MATCH (n:{LABEL_WITNESS} {{tag: $tag}}) "
        f"DETACH DELETE n"
    )
    with driver.session() as session:
        summary = session.run(query, {"tag": tag}).consume()
        return summary.counters.nodes_deleted


def ecrire_fichiers_bind_temoins(backend_dir: Path, tag: str) -> Dict[str, str]:
    """Crée des fichiers témoins dans les montages bind backend/uploads et backend/simulations."""
    uploads_dir = backend_dir / "uploads"
    sims_dir = backend_dir / "simulations"

    uploads_dir.mkdir(parents=True, exist_ok=True)
    sims_dir.mkdir(parents=True, exist_ok=True)

    file_upload = uploads_dir / f"witness_upload_{tag}.txt"
    content_upload = f"MiroFish Witness Upload File - Tag {tag}\nTimestamp: {datetime.now(timezone.utc).isoformat()}\n"
    file_upload.write_text(content_upload, encoding="utf-8")
    sha_upload = hashlib.sha256(content_upload.encode("utf-8")).hexdigest()

    file_sim = sims_dir / f"witness_sim_{tag}.json"
    content_sim_dict = {
        "tag": tag,
        "type": "witness_simulation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETED",
        "rounds": 5,
    }
    content_sim_str = json.dumps(content_sim_dict, indent=2)
    file_sim.write_text(content_sim_str, encoding="utf-8")
    sha_sim = hashlib.sha256(content_sim_str.encode("utf-8")).hexdigest()

    return {
        str(file_upload.relative_to(backend_dir)): sha_upload,
        str(file_sim.relative_to(backend_dir)): sha_sim,
    }


def verifier_fichiers_bind_temoins(backend_dir: Path, fichiers_attendus: Dict[str, str]) -> Tuple[bool, List[str]]:
    """Vérifie l'existence et l'intégrité sha256 des fichiers bind témoins."""
    erreurs = []
    for rel_path, sha_attendu in fichiers_attendus.items():
        fichier_path = backend_dir / rel_path
        if not fichier_path.exists():
            erreurs.append(f"Fichier bind manquant : {rel_path}")
            continue

        contenu = fichier_path.read_bytes()
        sha_reel = hashlib.sha256(contenu).hexdigest()
        if sha_reel != sha_attendu:
            erreurs.append(
                f"Altération du fichier {rel_path} : hash attendu {sha_attendu[:8]}, obtenu {sha_reel[:8]}"
            )

    return len(erreurs) == 0, erreurs


def nettoyer_fichiers_bind_temoins(backend_dir: Path, fichiers: Dict[str, str]) -> None:
    """Nettoie les fichiers témoins créés dans les volumes bind."""
    for rel_path in fichiers.keys():
        fichier_path = backend_dir / rel_path
        if fichier_path.exists():
            fichier_path.unlink()


class MockNeo4jDriver:
    """Driver Neo4j simulé en mémoire pour les tests unitaires et vérifications hermétiques."""

    def __init__(self, data_store: Optional[Dict[str, Any]] = None):
        self._data_store = data_store if data_store is not None else {"nodes": {}, "edges": {}}
        self._is_closed = False

    def session(self):
        return MockNeo4jSession(self._data_store)

    def close(self):
        self._is_closed = True


class MockNeo4jSession:
    """Session Neo4j simulée en mémoire."""

    def __init__(self, data_store: Dict[str, Any]):
        self._store = data_store

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def run(self, query: str, parameters: Optional[Dict[str, Any]] = None):
        params = parameters or {}
        tag = params.get("tag", "")

        # 1. Écriture Node
        if f"MERGE (n:{LABEL_WITNESS}" in query:
            name = params["name"]
            self._store["nodes"].setdefault(tag, {})[name] = {
                "name": name,
                "category": params.get("category", ""),
                "score": params.get("score", 0.0),
                "props": {**params.get("properties", {}), "name": name, "category": params.get("category", ""), "score": params.get("score", 0.0), "tag": tag},
            }
            return MockResult([{"name": name}])

        # 2. Écriture Edge
        if f"MERGE (a)-[r:{REL_WITNESS}" in query:
            source = params["source"]
            target = params["target"]
            edge_key = f"{source}->{target}"
            self._store["edges"].setdefault(tag, {})[edge_key] = {
                "source": source,
                "target": target,
                "rel_type": params.get("rel_type", ""),
                "weight": params.get("weight", 1.0),
                "valid_at": params.get("valid_at", ""),
            }
            return MockResult([{"rel_type": params.get("rel_type", "")}])

        # 3. Lecture Nodes
        if f"MATCH (n:{LABEL_WITNESS} {{tag: $tag}})" in query and "RETURN n.name AS name" in query:
            nodes = self._store["nodes"].get(tag, {})
            records = [
                {"name": n["name"], "category": n["category"], "score": n["score"], "props": n["props"]}
                for n in sorted(nodes.values(), key=lambda x: x["name"])
            ]
            return MockResult(records)

        # 4. Lecture Edges
        if f"MATCH (a:{LABEL_WITNESS} {{tag: $tag}})-[r:{REL_WITNESS}" in query:
            edges = self._store["edges"].get(tag, {})
            records = [
                {"source": e["source"], "target": e["target"], "rel_type": e["rel_type"], "weight": e["weight"], "valid_at": e["valid_at"]}
                for e in sorted(edges.values(), key=lambda x: (x["source"], x["target"]))
            ]
            return MockResult(records)

        # 5. Suppression
        if "DETACH DELETE" in query:
            count = len(self._store["nodes"].pop(tag, {}))
            self._store["edges"].pop(tag, None)
            return MockResultSummary(count)

        return MockResult([])


class MockResult:
    def __init__(self, records: List[Dict[str, Any]]):
        self._records = records
        self._idx = 0

    def single(self):
        return self._records[0] if self._records else None

    def __iter__(self):
        return iter(self._records)


class MockResultSummary:
    def __init__(self, nodes_deleted: int):
        self.counters = type("Counters", (), {"nodes_deleted": nodes_deleted})()

    def consume(self):
        return self


def executer_commande_docker(cmd: List[str], cwd: Path) -> Tuple[int, str, str]:
    """Exécute une commande Docker CLI et retourne (code_retour, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout lors de l'exécution de la commande Docker."
    except Exception as exc:
        return -1, "", str(exc)


def executer_cycle_persistance_complet(
    compose_file: Path,
    backend_dir: Path,
    tag: Optional[str] = None,
    mock: bool = False,
    driver_override: Optional[Any] = None,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> RapportPersistance:
    """Exécute le cycle complet de validation de persistance et de cycle de vie."""
    t_start = time.time()
    tag_eff = tag or f"persist_{uuid.uuid4().hex[:8]}"
    controles: List[ResultatControle] = []
    repo_dir = compose_file.parent

    donnees_temoin = generer_donnees_temoin(tag_eff)
    fichiers_bind = ecrire_fichiers_bind_temoins(backend_dir, tag_eff)
    donnees_temoin.fichiers_bind = fichiers_bind

    driver: Optional[Any] = None
    driver_v: Optional[Any] = None

    if mock:
        # Initialisation d'une base simulée partagée
        mock_data = {"nodes": {}, "edges": {}}
        driver = driver_override or MockNeo4jDriver(mock_data)
    else:
        # Vérification préalable de Docker
        if shutil.which("docker") is None:
            return RapportPersistance(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                tag=tag_eff,
                mode="docker_reel",
                controles=[
                    ResultatControle(
                        nom="docker_disponible",
                        statut="ECHEC",
                        message="Docker CLI introuvable sur le système.",
                    )
                ],
                succes_global=False,
                duree_secondes=time.time() - t_start,
            )
        try:
            driver = driver_override or creer_driver_neo4j(uri=uri, user=user, password=password)
        except Exception as exc:
            return RapportPersistance(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                tag=tag_eff,
                mode="docker_reel",
                controles=[
                    ResultatControle(
                        nom="connexion_neo4j_initiale",
                        statut="ECHEC",
                        message=f"Impossible de se connecter à Neo4j : {exc}",
                    )
                ],
                succes_global=False,
                duree_secondes=time.time() - t_start,
            )

    try:
        # ----------------------------------------------------------------------
        # Contrôle 1 : Écriture du graphe témoin
        # ----------------------------------------------------------------------
        res_ecriture = ecrire_graphe_temoin(driver, donnees_temoin)
        if res_ecriture["nodes_crees"] == len(donnees_temoin.nodes) and res_ecriture["edges_crees"] == len(donnees_temoin.edges):
            controles.append(
                ResultatControle(
                    nom="1_ecriture_graphe_temoin",
                    statut="OK",
                    message=f"Écriture réussie de {res_ecriture['nodes_crees']} nœuds et {res_ecriture['edges_crees']} arêtes.",
                    details=res_ecriture,
                )
            )
        else:
            controles.append(
                ResultatControle(
                    nom="1_ecriture_graphe_temoin",
                    statut="ECHEC",
                    message=f"Échec écriture partielle : {res_ecriture}",
                    details=res_ecriture,
                )
            )

        # ----------------------------------------------------------------------
        # Contrôle 2 : Relecture immédiate avant arrêt (baseline)
        # ----------------------------------------------------------------------
        lecture_pre = relire_graphe_temoin(driver, tag_eff)
        hash_pre = lecture_pre["hash_sha256"]
        controles.append(
            ResultatControle(
                nom="2_relecture_baseline",
                statut="OK",
                message=f"Baseline enregistrée : {lecture_pre['count_nodes']} nœuds, {lecture_pre['count_edges']} arêtes (hash={hash_pre[:8]}).",
                details={"hash_sha256": hash_pre},
            )
        )

        # ----------------------------------------------------------------------
        # Contrôle 3 : Arrêt normal des conteneurs (docker compose down sans -v)
        # ----------------------------------------------------------------------
        if not mock:
            if driver is not None and hasattr(driver, "close"):
                try:
                    driver.close()
                except Exception:
                    pass
            code, out, err = executer_commande_docker(
                ["docker", "compose", "-f", str(compose_file), "down"],
                cwd=repo_dir,
            )
            if code == 0:
                controles.append(
                    ResultatControle(
                        nom="3_arret_conteneurs_sans_purge",
                        statut="OK",
                        message="Arrêt des conteneurs réussi (docker compose down sans -v).",
                    )
                )
            else:
                controles.append(
                    ResultatControle(
                        nom="3_arret_conteneurs_sans_purge",
                        statut="ECHEC",
                        message=f"Erreur lors de docker compose down : {err}",
                    )
                )
        else:
            controles.append(
                ResultatControle(
                    nom="3_arret_conteneurs_sans_purge",
                    statut="OK",
                    message="Arrêt simulé sans purge de volume.",
                )
            )

        # ----------------------------------------------------------------------
        # Contrôle 4 : Redémarrage des conteneurs (docker compose up -d --wait)
        # ----------------------------------------------------------------------
        if not mock:
            code, out, err = executer_commande_docker(
                ["docker", "compose", "-f", str(compose_file), "up", "-d", "--wait"],
                cwd=repo_dir,
            )
            if code == 0:
                controles.append(
                    ResultatControle(
                        nom="4_redemarrage_conteneurs",
                        statut="OK",
                        message="Redémarrage réussi de la stack (docker compose up -d --wait).",
                    )
                )
                # Re-créer le driver car la connexion précédente a été fermée
                try:
                    driver = creer_driver_neo4j(uri=uri, user=user, password=password)
                except Exception as exc:
                    controles.append(
                        ResultatControle(
                            nom="4_reconnexion_post_restart",
                            statut="ECHEC",
                            message=f"Reconnexion Neo4j impossible : {exc}",
                        )
                    )
            else:
                controles.append(
                    ResultatControle(
                        nom="4_redemarrage_conteneurs",
                        statut="ECHEC",
                        message=f"Erreur lors de docker compose up : {err}",
                    )
                )
        else:
            controles.append(
                ResultatControle(
                    nom="4_redemarrage_conteneurs",
                    statut="OK",
                    message="Redémarrage simulé réussi.",
                )
            )

        # ----------------------------------------------------------------------
        # Contrôle 5 : Vérification de la persistance Neo4j (Critère C3)
        # ----------------------------------------------------------------------
        lecture_post = relire_graphe_temoin(driver, tag_eff)
        hash_post = lecture_post["hash_sha256"]

        is_intact = (
            lecture_post["count_nodes"] == len(donnees_temoin.nodes)
            and lecture_post["count_edges"] == len(donnees_temoin.edges)
            and hash_post == hash_pre
        )

        if is_intact:
            controles.append(
                ResultatControle(
                    nom="5_persistance_neo4j_critere_c3",
                    statut="OK",
                    message=(
                        f"Persistance 100% validée (C3) : {lecture_post['count_nodes']} nœuds, "
                        f"{lecture_post['count_edges']} arêtes conservés à l'identique (hash={hash_post[:8]})."
                    ),
                    details={"nodes": lecture_post["count_nodes"], "edges": lecture_post["count_edges"], "hash": hash_post},
                )
            )
        else:
            controles.append(
                ResultatControle(
                    nom="5_persistance_neo4j_critere_c3",
                    statut="ECHEC",
                    message=(
                        f"Altération constatée après redémarrage : attendu {len(donnees_temoin.nodes)} nœuds / "
                        f"{len(donnees_temoin.edges)} arêtes, obtenu {lecture_post['count_nodes']} nœuds / {lecture_post['count_edges']} arêtes."
                    ),
                    details={"attendu_hash": hash_pre, "obtenu_hash": hash_post},
                )
            )

        # ----------------------------------------------------------------------
        # Contrôle 6 : Persistance des montages bind (uploads & simulations)
        # ----------------------------------------------------------------------
        bind_ok, bind_errs = verifier_fichiers_bind_temoins(backend_dir, fichiers_bind)
        if bind_ok:
            controles.append(
                ResultatControle(
                    nom="6_persistance_bind_mounts",
                    statut="OK",
                    message="Fichiers des volumes bind backend/uploads et backend/simulations 100% préservés.",
                    details={"fichiers": list(fichiers_bind.keys())},
                )
            )
        else:
            controles.append(
                ResultatControle(
                    nom="6_persistance_bind_mounts",
                    statut="ECHEC",
                    message=f"Échec persistance bind : {'; '.join(bind_errs)}",
                    details={"erreurs": bind_errs},
                )
            )

        # ----------------------------------------------------------------------
        # Contrôle 7 : Cycle de vie et Purge contrôlée (docker compose down -v)
        # ----------------------------------------------------------------------
        if not mock:
            if driver is not None and hasattr(driver, "close"):
                try:
                    driver.close()
                except Exception:
                    pass
            code_down_v, _, err_down_v = executer_commande_docker(
                ["docker", "compose", "-f", str(compose_file), "down", "-v"],
                cwd=repo_dir,
            )
            if code_down_v == 0:
                # Redémarrage pour vérifier que le volume a bien été vidé
                code_up_v, _, _ = executer_commande_docker(
                    ["docker", "compose", "-f", str(compose_file), "up", "-d", "--wait"],
                    cwd=repo_dir,
                )
                try:
                    driver_v = creer_driver_neo4j(uri=uri, user=user, password=password)
                    lecture_purge = relire_graphe_temoin(driver_v, tag_eff)
                    if lecture_purge["count_nodes"] == 0 and lecture_purge["count_edges"] == 0:
                        controles.append(
                            ResultatControle(
                                nom="7_purge_volume_down_v",
                                statut="OK",
                                message="Purge explicite validée : le volume neo4j_data a été réinitialisé à l'état vierge par down -v.",
                            )
                        )
                    else:
                        controles.append(
                            ResultatControle(
                                nom="7_purge_volume_down_v",
                                statut="ECHEC",
                                message=f"Résidus détectés après down -v : {lecture_purge['count_nodes']} nœuds persistants.",
                            )
                        )
                except Exception as exc:
                    controles.append(
                        ResultatControle(
                            nom="7_purge_volume_down_v",
                            statut="ECHEC",
                            message=f"Reconnexion après down -v échouée : {exc}",
                        )
                    )
            else:
                controles.append(
                    ResultatControle(
                        nom="7_purge_volume_down_v",
                        statut="ECHEC",
                        message=f"Échec docker compose down -v : {err_down_v}",
                    )
                )
        else:
            # En mode simulé, on vide la base en mémoire pour reproduire le down -v
            mock_data.clear()
            mock_data.update({"nodes": {}, "edges": {}})
            if hasattr(driver, "_data_store") and isinstance(driver._data_store, dict):
                driver._data_store.clear()
                driver._data_store.update({"nodes": {}, "edges": {}})
            lecture_purge = relire_graphe_temoin(driver, tag_eff)
            if lecture_purge["count_nodes"] == 0:
                controles.append(
                    ResultatControle(
                        nom="7_purge_volume_down_v",
                        statut="OK",
                        message="Purge simulée validée : réinitialisation complète du store.",
                    )
                )

    finally:
        # Fermeture explicite des drivers créés
        for d in (driver, driver_v):
            if d is not None and hasattr(d, "close"):
                try:
                    d.close()
                except Exception:
                    pass
        # Nettoyage des fichiers bind
        nettoyer_fichiers_bind_temoins(backend_dir, fichiers_bind)

    succes_global = all(c.statut == "OK" for c in controles)
    duree = time.time() - t_start

    return RapportPersistance(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        tag=tag_eff,
        mode="mock" if mock else "docker_reel",
        controles=controles,
        succes_global=succes_global,
        duree_secondes=duree,
    )


def afficher_rapport(rapport: RapportPersistance, format_json: bool = False) -> None:
    """Affiche le rapport de vérification sur stdout."""
    if format_json:
        print(json.dumps(asdict(rapport), indent=2, ensure_ascii=False))
        return

    symbole_global = "✅ VALIDÉ" if rapport.succes_global else "❌ ÉCHEC"
    print("\n" + "=" * 80)
    print(f"📊 RAPPORT DE VÉRIFICATION DE PERSISTANCE NEO4J & VOLUMES ({rapport.mode.upper()})")
    print("=" * 80)
    print(f"Date UTC    : {rapport.timestamp_utc}")
    print(f"Tag témoin  : {rapport.tag}")
    print(f"Durée       : {rapport.duree_secondes:.2f} s")
    print(f"Statut      : {symbole_global}")
    print("-" * 80)
    print("Détail des contrôles :")
    for ctrl in rapport.controles:
        icon = "  [✓] OK   " if ctrl.statut == "OK" else "  [✗] ÉCHEC"
        print(f"{icon} | {ctrl.nom:<32} | {ctrl.message}")
    print("=" * 80 + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vérification de la persistance Neo4j et du cycle de vie des volumes (Story 005-4)."
    )
    parser.add_argument(
        "commande",
        choices=["cycle-complet", "ecrire", "verifier", "purger"],
        default="cycle-complet",
        nargs="?",
        help="Action à exécuter (défaut : cycle-complet)",
    )
    parser.add_argument("--tag", type=str, default=None, help="Tag unique du jeu de données témoin.")
    parser.add_argument("--mock", action="store_true", help="Exécute la vérification en mode simulé (hermétique).")
    parser.add_argument("--json", action="store_true", help="Affiche la sortie au format JSON.")
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=_project_root / "docker-compose.yml",
        help="Chemin vers le fichier docker-compose.yml.",
    )
    parser.add_argument("--uri", type=str, default=None, help="URI Bolt Neo4j.")
    parser.add_argument("--user", type=str, default=None, help="Utilisateur Neo4j.")
    parser.add_argument("--password", type=str, default=None, help="Mot de passe Neo4j.")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.commande == "cycle-complet":
        rapport = executer_cycle_persistance_complet(
            compose_file=args.compose_file,
            backend_dir=_backend_dir,
            tag=args.tag,
            mock=args.mock,
            uri=args.uri,
            user=args.user,
            password=args.password,
        )
        afficher_rapport(rapport, format_json=args.json)
        return 0 if rapport.succes_global else 1

    # Commandes unitaires pas à pas
    tag = args.tag or "witness_default"
    if args.mock:
        driver = MockNeo4jDriver()
    else:
        try:
            driver = creer_driver_neo4j(uri=args.uri, user=args.user, password=args.password)
        except Exception as exc:
            print(f"Erreur de connexion Neo4j : {exc}", file=sys.stderr)
            return 1

    try:
        if args.commande == "ecrire":
            donnees = generer_donnees_temoin(tag)
            res = ecrire_graphe_temoin(driver, donnees)
            fichiers = ecrire_fichiers_bind_temoins(_backend_dir, tag)
            print(f"Graphe témoin écrit : {res}")
            print(f"Fichiers bind créés : {fichiers}")
            return 0

        elif args.commande == "verifier":
            lecture = relire_graphe_temoin(driver, tag)
            print(f"Graphe témoin relu : {lecture['count_nodes']} nœuds, {lecture['count_edges']} arêtes (hash={lecture['hash_sha256'][:8]})")
            return 0

        elif args.commande == "purger":
            del_nodes = nettoyer_graphe_temoin(driver, tag)
            fichiers_potentiels = {
                f"uploads/witness_upload_{tag}.txt": "",
                f"simulations/witness_sim_{tag}.json": "",
            }
            nettoyer_fichiers_bind_temoins(_backend_dir, fichiers_potentiels)
            print(f"Graphe témoin purgé : {del_nodes} nœuds supprimés.")
            return 0
    finally:
        if driver is not None and hasattr(driver, "close"):
            try:
                driver.close()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
