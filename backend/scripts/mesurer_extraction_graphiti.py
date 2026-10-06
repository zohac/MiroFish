#!/usr/bin/env python3
"""Banc de mesure autonome et reproductible de l'extraction Graphiti local (Story 001-5).

Ce script exécute l'épreuve de l'Epic 001 :
- Valide l'intégrité SHA256 du document d'entrée (Rapport AN n° 2506)
- Découpe le document en chunks de 500 caractères (recouvrement 50)
- Exécute séquentiellement l'extraction Graphiti sur les 30 premiers chunks
- Calcule précisément les critères C1 à C5 de prd.md
- Vérifie la persistance des entités et relations dans Neo4j
- Génère le rapport Markdown versionné docs/plans/001-epreuve-graphiti-local/rapport.md

Usage :
    # Mode réel (nécessite Neo4j et clé OpenCode Go) :
    cd backend && uv run python scripts/mesurer_extraction_graphiti.py

    # Mode simulation déterministe hors-ligne (sans réseau ni conteneur) :
    cd backend && uv run python scripts/mesurer_extraction_graphiti.py --mock
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# S'assurer que le package backend est dans le sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Config  # noqa: E402
from app.utils.file_parser import FileParser, split_text_into_chunks  # noqa: E402
from app.utils.graphiti_embedder import SentenceTransformerEmbedder  # noqa: E402
from app.utils.graphiti_llm_client import MiroFishLLMClient  # noqa: E402
from graphiti_core import Graphiti  # noqa: E402
from graphiti_core.cross_encoder.client import CrossEncoderClient  # noqa: E402
from graphiti_core.driver.neo4j_driver import Neo4jDriver  # noqa: E402
from graphiti_core.nodes import EpisodeType  # noqa: E402

# Constantes par défaut
DEFAULT_PDF_RELATIVE_PATH = "uploads/documents/rapport-an-2506-territorialisation-transition-energetique.pdf"
DEFAULT_EXPECTED_SHA256 = "4281a931545537f56625c3f4d0907fc66f54be82fef5d7b10e655dcdaf72ce88"
DEFAULT_REPORT_RELATIVE_PATH = "../docs/plans/001-epreuve-graphiti-local/rapport.md"
DEFAULT_CHUNKS_LIMIT = 30
DEFAULT_CHUNKS_START = 0
DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 50


class LocalPassthroughCrossEncoder(CrossEncoderClient):
    """Cross-encoder local pass-through évitant tout appel externe ou clé OpenAI (NFR-1)."""

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        """Conserve l'ordre avec un score unitaire décroissant."""
        return [(p, 1.0 - (i * 0.001)) for i, p in enumerate(passages)]


@dataclass
class ChunkResultat:
    """Résultat de l'extraction d'un chunk."""

    index: int
    taille_caracteres: int
    nb_mots: int
    apercu_texte: str
    succes: bool
    duree_sec: float
    nb_noeuds: int = 0
    nb_aretes: int = 0
    nb_valid_at: int = 0
    missing_session_id: bool = False
    type_erreur: Optional[str] = None
    message_erreur: Optional[str] = None
    noms_entites: List[str] = field(default_factory=list)
    faits_relations: List[str] = field(default_factory=list)


@dataclass
class DonneesMesure:
    """Structure globale des mesures collectées lors de l'épreuve."""

    date_mesure: str
    mode_mock: bool
    pdf_path: str
    pdf_sha256: str
    sha256_valide: bool
    nb_total_chunks_document: int
    chunks_testes: int
    chunk_size: int
    overlap: int
    model_llm: str
    endpoint_llm: str
    model_embedder: str
    dims_embedder: int
    duree_totale_sec: float
    resultats_chunks: List[ChunkResultat]
    c1_succes_count: int
    c1_total_count: int
    c1_taux_succes: float
    c1_valide: bool
    c2_missing_session_count: int
    c2_valide: bool
    c3_nb_noeuds_neo4j: int
    c3_nb_relations_neo4j: int
    c3_valide: bool
    c4_nb_aretes_valid_at: int
    c4_valide: bool
    c5_rapport_genere: bool
    verdict_global_go: bool
    details_erreurs: List[Dict[str, Any]] = field(default_factory=list)


def verifier_sha256(file_path: Path, expected_hash: str) -> Tuple[bool, str]:
    """Vérifie l'empreinte SHA256 d'un fichier."""
    if not file_path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {file_path}")

    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    calcule = hasher.hexdigest()
    return (calcule.lower() == expected_hash.lower(), calcule)


def charger_et_decouper_document(
    file_path: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> Tuple[str, List[str]]:
    """Extrait le texte du PDF via FileParser et le découpe en chunks."""
    texte = FileParser.extract_text(str(file_path))
    chunks = split_text_into_chunks(texte, chunk_size=chunk_size, overlap=overlap)
    return texte, chunks


async def reinitialiser_graphe_neo4j(driver: Any) -> None:
    """Réinitialise les données Neo4j sans appeler la procédure obsolète CALL db.indexes()."""
    # Nettoyage sécurisé des données
    await driver.execute_query("MATCH (n) DETACH DELETE n")
    # Application des contraintes et index sans supprimer les index via CALL db.indexes()
    await driver.build_indices_and_constraints(delete_existing=False)


def assainir_message_erreur(msg: Optional[str]) -> Optional[str]:
    """Caviarde les clés API, tokens et mots de passe dans les messages d'erreurs (NFR-2)."""
    if not msg:
        return msg
    import re
    # Masque tokens d'autorisation (Bearer xxx)
    nettoye = re.sub(r"(bearer\s+)[a-zA-Z0-9_\-\.]{8,}", r"\1[MASQUÉ]", msg, flags=re.IGNORECASE)
    # Masque clés API ou tokens explicites (sk-..., api_key=..., session_id=...)
    nettoye = re.sub(r"(api[_-]?key[\"'\s:=]+)[a-zA-Z0-9_\-\.]{8,}", r"\1[MASQUÉ]", nettoye, flags=re.IGNORECASE)
    nettoye = re.sub(r"(password[\"'\s:=]+)[^\s,\"']+", r"\1[MASQUÉ]", nettoye, flags=re.IGNORECASE)
    nettoye = re.sub(r"(session[_-]?id[\"'\s:=]+)[a-zA-Z0-9_\-\.]{8,}", r"\1[MASQUÉ]", nettoye, flags=re.IGNORECASE)
    return nettoye


def _extraire_valeur_compteur(res: Any) -> int:
    """Extrait une valeur entière de compteur depuis un résultat Cypher (EagerResult, Record ou dict)."""
    if res is None:
        return 0
    records = getattr(res, "records", None)
    if records is None:
        if isinstance(res, (list, tuple)) and len(res) > 0 and isinstance(res[0], (list, tuple)):
            records = res[0]
        else:
            records = res

    if not records or len(records) == 0:
        return 0

    first = records[0]
    if isinstance(first, (int, float)):
        return int(first)
    if hasattr(first, "get"):
        val = first.get("cnt")
        return int(val) if val is not None else 0
    if hasattr(first, "__getitem__"):
        try:
            val = first["cnt"]
            return int(val) if val is not None else 0
        except (TypeError, KeyError, IndexError):
            try:
                val = first[0]
                return int(val) if val is not None else 0
            except (TypeError, KeyError, IndexError):
                return 0
    return 0


async def compter_elements_neo4j(driver: Any) -> Tuple[int, int, int]:
    """Compte le nombre de nœuds, de relations totales et d'arêtes avec valid_at."""
    res_nodes = await driver.execute_query("MATCH (n) RETURN count(n) AS cnt")
    res_edges = await driver.execute_query("MATCH ()-[r]->() RETURN count(r) AS cnt")
    res_valid = await driver.execute_query(
        "MATCH ()-[r]->() WHERE r.valid_at IS NOT NULL RETURN count(r) AS cnt"
    )

    nb_nodes = _extraire_valeur_compteur(res_nodes)
    nb_edges = _extraire_valeur_compteur(res_edges)
    nb_valid = _extraire_valeur_compteur(res_valid)

    return nb_nodes, nb_edges, nb_valid


class MockGraphDriver:
    """Double factice de GraphDriver pour les tests et le mode simulation hors-ligne."""

    def __init__(self) -> None:
        self.nodes: Dict[str, Any] = {}
        self.edges: List[Dict[str, Any]] = []

    async def build_indices_and_constraints(self, delete_existing: bool = False) -> None:
        pass

    async def delete_all_indexes(self) -> None:
        pass

    async def execute_query(self, query: str, **kwargs: Any) -> List[Dict[str, Any]]:
        q = query.strip()
        if "DETACH DELETE" in q:
            self.nodes.clear()
            self.edges.clear()
            return []
        if "count(n)" in q:
            return [{"cnt": len(self.nodes)}]
        if "r.valid_at IS NOT NULL" in q:
            valid_cnt = sum(1 for e in self.edges if e.get("valid_at") is not None)
            return [{"cnt": valid_cnt}]
        if "count(r)" in q:
            return [{"cnt": len(self.edges)}]
        return []

    async def session(self) -> Any:
        return self

    async def close(self) -> None:
        pass

    def clone(self) -> MockGraphDriver:
        return self


def creer_mock_graphiti() -> Tuple[Any, MockGraphDriver]:
    """Instancie un Graphiti mocké pour exécution déterministe hors-ligne."""
    from unittest.mock import AsyncMock, MagicMock
    from graphiti_core.nodes import EntityNode, EpisodicNode
    from graphiti_core.edges import EntityEdge
    from graphiti_core.graphiti import AddEpisodeResults

    driver = MockGraphDriver()
    mock_graphiti = MagicMock(spec=Graphiti)

    async def mock_add_episode(
        name: str,
        episode_body: str,
        source: EpisodeType = EpisodeType.text,
        source_description: str = "",
        reference_time: Optional[datetime] = None,
        **kwargs: Any,
    ) -> AddEpisodeResults:
        # Simulation déterministe : création de 2 entités et 1 relation par chunk
        now = reference_time or datetime.now(timezone.utc)
        idx = len(driver.nodes) // 2 + 1
        n1 = EntityNode(name=f"Entite_A_{idx}", summary=f"Description A {idx}", group_id="epreuve-group", created_at=now)
        n2 = EntityNode(name=f"Entite_B_{idx}", summary=f"Description B {idx}", group_id="epreuve-group", created_at=now)
        driver.nodes[n1.uuid] = n1
        driver.nodes[n2.uuid] = n2

        edge = EntityEdge(
            source_node_uuid=n1.uuid,
            target_node_uuid=n2.uuid,
            group_id="epreuve-group",
            created_at=now,
            name="LIE_A",
            fact=f"Liaison constatée dans chunk {idx}",
            valid_at=now if idx % 2 == 0 else None,
        )
        driver.edges.append({
            "uuid": edge.uuid,
            "source": n1.uuid,
            "target": n2.uuid,
            "name": edge.name,
            "fact": edge.fact,
            "valid_at": edge.valid_at,
        })

        ep = EpisodicNode(
            name=name,
            group_id="epreuve-group",
            created_at=now,
            valid_at=now,
            source=source,
            source_description=source_description,
            content=episode_body,
        )

        return AddEpisodeResults(
            episode=ep,
            nodes=[n1, n2],
            edges=[edge],
            episodic_edges=[],
            communities=[],
            community_edges=[],
        )

    mock_graphiti.add_episode = AsyncMock(side_effect=mock_add_episode)
    return mock_graphiti, driver


def calculer_criteres(
    resultats: List[ChunkResultat],
    nb_nodes_neo4j: int,
    nb_edges_neo4j: int,
    nb_edges_valid_at_neo4j: int,
) -> Dict[str, Any]:
    """Évalue précisément les critères C1 à C5 de prd.md."""
    total_chunks = len(resultats)
    succes_chunks = sum(1 for r in resultats if r.succes)
    missing_session_count = sum(1 for r in resultats if r.missing_session_id)
    taux_succes = (succes_chunks / total_chunks) if total_chunks > 0 else 0.0

    # C1 : ≥ 90 % d'extractions sans erreur (soit ≥ 27/30 en nominal)
    c1_valide = (taux_succes >= 0.90) if total_chunks > 0 else False
    # C2 : 0 échec MissingSessionID
    c2_valide = missing_session_count == 0
    # C3 : ≥ 1 entité et ≥ 1 relation dans Neo4j
    c3_valide = nb_nodes_neo4j >= 1 and nb_edges_neo4j >= 1
    # C4 : ≥ 1 arête avec valid_at renseigné (priorité au décompte persistant Neo4j, sinon somme en mémoire)
    total_valid_at = nb_edges_valid_at_neo4j if nb_edges_valid_at_neo4j > 0 else sum(r.nb_valid_at for r in resultats)
    c4_valide = total_valid_at >= 1
    # C5 : Rapport produit
    c5_valide = True

    # Règle de décision : C1 et C2 sont bloquants, C3 est bloquant
    verdict_go = c1_valide and c2_valide and c3_valide

    return {
        "c1_succes_count": succes_chunks,
        "c1_total_count": total_chunks,
        "c1_taux_succes": taux_succes,
        "c1_valide": c1_valide,
        "c2_missing_session_count": missing_session_count,
        "c2_valide": c2_valide,
        "c3_nb_noeuds_neo4j": nb_nodes_neo4j,
        "c3_nb_relations_neo4j": nb_edges_neo4j,
        "c3_valide": c3_valide,
        "c4_nb_aretes_valid_at": total_valid_at,
        "c4_valide": c4_valide,
        "c5_valide": c5_valide,
        "verdict_global_go": verdict_go,
    }


def generer_rapport_markdown(donnees: DonneesMesure) -> str:
    """Génère le rapport Markdown complet et versionné pour docs/plans/001-epreuve-graphiti-local/rapport.md."""
    lignes = []

    # En-tête et UX Requirements : Verdict en tête (NFR-4)
    statut_badge = "✅ **GO — EXTRACTION VALIDÉE**" if donnees.verdict_global_go else "❌ **NO-GO — ÉCHEC EXTRACTION**"
    lignes.append("# Rapport de mesure — Épreuve Graphiti local sur 30 chunks (Epic 001)")
    lignes.append("")
    lignes.append(f"> **Verdict global** : {statut_badge}  ")
    lignes.append(f"> **Date de mesure** : {donnees.date_mesure}  ")
    lignes.append(f"> **Mode d'exécution** : {'Simulation déterministe (--mock)' if donnees.mode_mock else 'Exécution réelle (OpenCode Go + Neo4j local)'}")
    lignes.append("")
    lignes.append("---")
    lignes.append("")

    # 1. Synthèse des critères de sortie chiffrés
    lignes.append("## 1. Synthèse des critères de sortie (PRD Epic 001)")
    lignes.append("")
    lignes.append("| # | Critère | Seuil | Valeur mesurée | Statut |")
    lignes.append("|---|---|---|---|---|")

    # C1
    c1_statut = "✅ Conforme" if donnees.c1_valide else "❌ Non conforme"
    lignes.append(
        f"| C1 | Épisodes extraits sans erreur | ≥ 90 % (≥ 27/30) | **{donnees.c1_succes_count}/{donnees.c1_total_count}** ({donnees.c1_taux_succes * 100:.1f} %) | {c1_statut} |"
    )

    # C2
    c2_statut = "✅ Conforme" if donnees.c2_valide else "❌ Non conforme"
    lignes.append(
        f"| C2 | Échecs d'authentification (`MissingSessionID`) | **0** | **{donnees.c2_missing_session_count}** | {c2_statut} |"
    )

    # C3
    c3_statut = "✅ Conforme" if donnees.c3_valide else "❌ Non conforme"
    lignes.append(
        f"| C3 | Graphe non vide et persistant dans Neo4j | ≥ 1 nœud, ≥ 1 rel. | **{donnees.c3_nb_noeuds_neo4j}** nœuds, **{donnees.c3_nb_relations_neo4j}** rel. | {c3_statut} |"
    )

    # C4
    c4_statut = "✅ Conforme" if donnees.c4_valide else "⚠️ Signal d'alerte"
    lignes.append(
        f"| C4 | Temporalité : arêtes avec `valid_at` | ≥ 1 arête | **{donnees.c4_nb_aretes_valid_at}** arête(s) | {c4_statut} |"
    )

    # C5
    lignes.append(
        f"| C5 | Rapport de mesure versionné | 1 fichier | **1** (`rapport.md`) | ✅ Conforme |"
    )

    lignes.append("")
    lignes.append("---")
    lignes.append("")

    # 2. Environnement et configuration du banc d'essai
    lignes.append("## 2. Configuration du banc d'essai")
    lignes.append("")
    lignes.append(f"- **Document source** : `{donnees.pdf_path}`")
    lignes.append(f"- **Empreinte SHA256** : `{donnees.pdf_sha256}` ({'Valide ✓' if donnees.sha256_valide else 'INVALIDE ✗'})")
    lignes.append(f"- **Volume total du document** : {donnees.nb_total_chunks_document} chunks découverts")
    lignes.append(f"- **Échantillon mesuré** : {donnees.chunks_testes} chunks séquentiels")
    lignes.append(f"- **Découpage** : {donnees.chunk_size} caractères par chunk, {donnees.overlap} caractères de recouvrement")
    lignes.append(f"- **Endpoint LLM** : `{donnees.endpoint_llm}`")
    lignes.append(f"- **Modèle LLM** : `{donnees.model_llm}` (structured output mode: `json_object`)")
    lignes.append(f"- **Embedder** : `{donnees.model_embedder}` ({donnees.dims_embedder} dimensions, 100 % local)")
    lignes.append(f"- **Cross-Encoder** : `LocalPassthroughCrossEncoder` (0 € marginal, sans clé externe)")
    lignes.append(f"- **Durée totale de l'épreuve** : {donnees.duree_totale_sec:.2f} s")
    if donnees.chunks_testes > 0:
        latence_moy = donnees.duree_totale_sec / donnees.chunks_testes
        lignes.append(f"- **Latence moyenne par chunk** : {latence_moy:.2f} s/chunk")
    lignes.append("")
    lignes.append("---")
    lignes.append("")

    # 3. Tableau détaillé des 30 chunks
    lignes.append("## 3. Résultats détaillés par chunk")
    lignes.append("")
    lignes.append("| Chunk | Taille (car.) | Durée (s) | Nœuds | Arêtes | `valid_at` | Statut | Erreur / Remarque |")
    lignes.append("|---|---|---|---|---|---|---|---|")

    for r in donnees.resultats_chunks:
        statut_str = "✅ Succès" if r.succes else "❌ Échec"
        erreur_str = r.type_erreur if r.type_erreur else "-"
        if r.missing_session_id:
            erreur_str = "🚨 MissingSessionID"
        lignes.append(
            f"| #{r.index:02d} | {r.taille_caracteres} | {r.duree_sec:.2f}s | {r.nb_noeuds} | {r.nb_aretes} | {r.nb_valid_at} | {statut_str} | {erreur_str} |"
        )

    lignes.append("")

    # 4. Échantillon d'entités et relations extraites
    lignes.append("## 4. Échantillon d'entités et de faits extraits")
    lignes.append("")
    entites_collectees: List[str] = []
    faits_collectes: List[str] = []
    for r in donnees.resultats_chunks:
        entites_collectees.extend(r.noms_entites)
        faits_collectes.extend(r.faits_relations)

    if entites_collectees:
        echantillon_entites = sorted(list(set(entites_collectees)))[:15]
        lignes.append("### Exemples d'entités extraites :")
        for ent in echantillon_entites:
            lignes.append(f"- **{ent}**")
        lignes.append("")

    if faits_collectes:
        echantillon_faits = faits_collectes[:10]
        lignes.append("### Exemples de faits et relations extraits :")
        for fait in echantillon_faits:
            lignes.append(f"- {fait}")
        lignes.append("")

    # 5. Journal des anomalies
    if donnees.details_erreurs:
        lignes.append("## 5. Journal détaillé des anomalies")
        lignes.append("")
        for err in donnees.details_erreurs:
            lignes.append(f"- **Chunk #{err.get('chunk') :02d}** : `{err.get('type')}`")
            lignes.append(f"  - Message : {err.get('message')}")
        lignes.append("")

    return "\n".join(lignes)


async def executer_mesure_extraction(
    mock: bool = False,
    limit: int = DEFAULT_CHUNKS_LIMIT,
    chunks_start: int = DEFAULT_CHUNKS_START,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    pdf_path_str: str = DEFAULT_PDF_RELATIVE_PATH,
    expected_sha256: str = DEFAULT_EXPECTED_SHA256,
    output_report_str: str = DEFAULT_REPORT_RELATIVE_PATH,
    skip_reset: bool = False,
    delay_between_chunks: float = 0.0,
) -> Tuple[DonneesMesure, str]:
    """Point d'entrée principal de l'exécution du banc de mesure."""
    t_start = time.perf_counter()
    date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if chunk_size <= overlap:
        raise ValueError(
            f"Paramètres invalides : chunk_size ({chunk_size}) doit être strictement supérieur à overlap ({overlap})."
        )
    if limit <= 0:
        raise ValueError(f"Paramètre invalide : limit ({limit}) doit être un entier strictement positif.")

    # Résolution des chemins
    pdf_path = BACKEND_DIR / pdf_path_str if not Path(pdf_path_str).is_absolute() else Path(pdf_path_str)
    output_path = BACKEND_DIR / output_report_str if not Path(output_report_str).is_absolute() else Path(output_report_str)

    print("=" * 70)
    print("BANC DE MESURE GRAPHITI LOCAL SUR 30 CHUNKS (STORY 001-5)")
    print(f"Date d'exécution : {date_iso}")
    print(f"Mode : {'SIMULATION DÉTERMINISTE (--mock)' if mock else 'RÉEL (OpenCode Go + Neo4j)'}")
    print("=" * 70)

    # 1. Validation de l'intégrité du document
    print("\n--- 1. Validation du document d'entrée ---")
    print(f"Chemin du PDF : {pdf_path}")
    if not pdf_path.exists():
        raise FileNotFoundError(f"Le document d'épreuve est introuvable à l'emplacement : {pdf_path}")

    sha_valide, sha_calcule = verifier_sha256(pdf_path, expected_sha256)
    print(f"SHA256 calculé  : {sha_calcule}")
    print(f"SHA256 attendu  : {expected_sha256}")
    if not sha_valide:
        print("❌ ERREUR : Empreinte SHA256 non conforme !")
        raise ValueError(
            f"Empreinte SHA256 du document d'épreuve non conforme : calculé={sha_calcule}, attendu={expected_sha256}"
        )
    print("✓ Empreinte SHA256 validée avec succès.")

    # 2. Découpage du document
    print("\n--- 2. Extraction du texte et découpage ---")
    texte_complet, chunks = charger_et_decouper_document(pdf_path, chunk_size=chunk_size, overlap=overlap)
    nb_total_chunks = len(chunks)
    print(f"Longueur totale du texte : {len(texte_complet)} caractères")
    print(f"Nombre total de chunks   : {nb_total_chunks} (chunk_size={chunk_size}, overlap={overlap})")

    # Sélection de la tranche d'échantillon
    chunks_selection = chunks[chunks_start : chunks_start + limit]
    nb_testes = len(chunks_selection)
    print(f"Échantillon retenu       : {nb_testes} chunks (de l'indice {chunks_start} à {chunks_start + nb_testes - 1})")

    # 3. Initialisation de Graphiti et Neo4j
    print("\n--- 3. Initialisation de Graphiti et du graphe ---")
    base_url = os.environ.get("LLM_BASE_URL") or Config.LLM_BASE_URL or "https://opencode.ai/zen/go/v1"
    model_name = os.environ.get("LLM_MODEL_NAME") or Config.LLM_MODEL_NAME or "space-bunny-free"
    embedder_name = "all-MiniLM-L6-v2"
    embedder_dim = 384

    driver: Any = None
    graphiti: Any = None

    try:
        if mock:
            print("✓ Initialisation du double factice Graphiti en mode simulation")
            graphiti, driver = creer_mock_graphiti()
        else:
            neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
            neo4j_pwd = os.environ.get("NEO4J_PASSWORD") or getattr(Config, "NEO4J_PASSWORD", None)
            if not neo4j_pwd:
                raise ValueError(
                    "La variable d'environnement NEO4J_PASSWORD est requise pour l'exécution réelle. "
                    "Définissez-la dans votre fichier .env conformément à AGENTS.md §2.9."
                )
    
            print(f"Connexion Neo4j : {neo4j_uri} (utilisateur: {neo4j_user})")
            driver = Neo4jDriver(uri=neo4j_uri, user=neo4j_user, password=neo4j_pwd)
    
            if not skip_reset:
                print("Remise à zéro sécurisée du graphe Neo4j...")
                await reinitialiser_graphe_neo4j(driver)
                print("✓ Graphe réinitialisé et contraintes appliquées (sans CALL db.indexes())")
    
            llm_client = MiroFishLLMClient()
            embedder_client = SentenceTransformerEmbedder()
            cross_encoder = LocalPassthroughCrossEncoder()
    
            graphiti = Graphiti(
                graph_driver=driver,
                llm_client=llm_client,
                embedder=embedder_client,
                cross_encoder=cross_encoder,
            )
            print("✓ Graphiti instancié avec MiroFishLLMClient, SentenceTransformerEmbedder et LocalPassthroughCrossEncoder")
    
        # 4. Exécution séquentielle de l'extraction sur les 30 chunks
        print("\n--- 4. Exécution séquentielle de l'extraction ---")
        resultats: List[ChunkResultat] = []
        details_erreurs: List[Dict[str, Any]] = []
    
        for i, chunk_text in enumerate(chunks_selection, start=1):
            t_chunk_0 = time.perf_counter()
            nb_mots = len(chunk_text.split())
            apercu = chunk_text[:80].replace("\n", " ") + "..."
    
            print(f"[{i:02d}/{nb_testes:02d}] Traitement chunk ({len(chunk_text)} car., {nb_mots} mots)... ", end="", flush=True)
    
            succes = False
            nb_nodes = 0
            nb_edges = 0
            nb_valid_at = 0
            missing_session = False
            type_err = None
            msg_err = None
            noms_ent = []
            faits_rel = []
    
            try:
                res = await graphiti.add_episode(
                    name=f"Chunk {i:02d}",
                    episode_body=chunk_text,
                    source=EpisodeType.text,
                    source_description="Rapport AN n° 2506",
                    reference_time=datetime.now(timezone.utc),
                )
                duree_chunk = time.perf_counter() - t_chunk_0
                succes = True
    
                # Extraction des métriques de résultat
                if hasattr(res, "nodes") and res.nodes:
                    nb_nodes = len(res.nodes)
                    noms_ent = [getattr(n, "name", str(n)) for n in res.nodes]
                if hasattr(res, "edges") and res.edges:
                    nb_edges = len(res.edges)
                    faits_rel = [getattr(e, "fact", getattr(e, "name", str(e))) for e in res.edges]
                    nb_valid_at = sum(1 for e in res.edges if getattr(e, "valid_at", None) is not None)
    
                print(f"✓ OK ({duree_chunk:.2f}s) — {nb_nodes} nœuds, {nb_edges} relations, {nb_valid_at} valid_at")
    
            except Exception as exc:
                duree_chunk = time.perf_counter() - t_chunk_0
                succes = False
                type_err = exc.__class__.__name__
                msg_err = assainir_message_erreur(str(exc)) or str(exc)
    
                if "MissingSessionID" in msg_err or ("400" in msg_err and "session" in msg_err.lower()):
                    missing_session = True
    
                print(f"✗ ÉCHEC ({duree_chunk:.2f}s) — {type_err}: {msg_err[:60]}")
                details_erreurs.append({
                    "chunk": i,
                    "type": type_err,
                    "message": msg_err,
                })
    
            resultats.append(
                ChunkResultat(
                    index=i,
                    taille_caracteres=len(chunk_text),
                    nb_mots=nb_mots,
                    apercu_texte=apercu,
                    succes=succes,
                    duree_sec=duree_chunk,
                    nb_noeuds=nb_nodes,
                    nb_aretes=nb_edges,
                    nb_valid_at=nb_valid_at,
                    missing_session_id=missing_session,
                    type_erreur=type_err,
                    message_erreur=msg_err,
                    noms_entites=noms_ent,
                    faits_relations=faits_rel,
                )
            )
    
            if delay_between_chunks > 0 and i < nb_testes:
                await asyncio.sleep(delay_between_chunks)
    
        t_total = time.perf_counter() - t_start
    
        # 5. Relecture et vérification de la persistance Neo4j
        print("\n--- 5. Contrôle de persistance Neo4j ---")
        nb_nodes_neo4j, nb_edges_neo4j, nb_valid_at_neo4j = await compter_elements_neo4j(driver)
        print(f"Nœuds persistés dans Neo4j     : {nb_nodes_neo4j}")
        print(f"Relations persistées dans Neo4j : {nb_edges_neo4j}")
        print(f"Relations avec valid_at         : {nb_valid_at_neo4j}")
    
        # 6. Évaluation des critères C1 à C5
        print("\n--- 6. Évaluation des critères de sortie ---")
        criteres = calculer_criteres(resultats, nb_nodes_neo4j, nb_edges_neo4j, nb_valid_at_neo4j)
    
        donnees_mesure = DonneesMesure(
            date_mesure=date_iso,
            mode_mock=mock,
            pdf_path=str(pdf_path_str),
            pdf_sha256=sha_calcule,
            sha256_valide=sha_valide,
            nb_total_chunks_document=nb_total_chunks,
            chunks_testes=nb_testes,
            chunk_size=chunk_size,
            overlap=overlap,
            model_llm=model_name,
            endpoint_llm=base_url,
            model_embedder=embedder_name,
            dims_embedder=embedder_dim,
            duree_totale_sec=t_total,
            resultats_chunks=resultats,
            c1_succes_count=criteres["c1_succes_count"],
            c1_total_count=criteres["c1_total_count"],
            c1_taux_succes=criteres["c1_taux_succes"],
            c1_valide=criteres["c1_valide"],
            c2_missing_session_count=criteres["c2_missing_session_count"],
            c2_valide=criteres["c2_valide"],
            c3_nb_noeuds_neo4j=criteres["c3_nb_noeuds_neo4j"],
            c3_nb_relations_neo4j=criteres["c3_nb_relations_neo4j"],
            c3_valide=criteres["c3_valide"],
            c4_nb_aretes_valid_at=criteres["c4_nb_aretes_valid_at"],
            c4_valide=criteres["c4_valide"],
            c5_rapport_genere=True,
            verdict_global_go=criteres["verdict_global_go"],
            details_erreurs=details_erreurs,
        )
    
        print(f"C1 — Épisodes extraits sans erreur : {donnees_mesure.c1_succes_count}/{donnees_mesure.c1_total_count} ({donnees_mesure.c1_taux_succes*100:.1f}%) -> {'CONFORME ✓' if donnees_mesure.c1_valide else 'ÉCHEC ✗'}")
        print(f"C2 — Échecs MissingSessionID      : {donnees_mesure.c2_missing_session_count} -> {'CONFORME ✓' if donnees_mesure.c2_valide else 'ÉCHEC ✗'}")
        print(f"C3 — Graphe non vide et persistant : {donnees_mesure.c3_nb_noeuds_neo4j} nœuds, {donnees_mesure.c3_nb_relations_neo4j} relations -> {'CONFORME ✓' if donnees_mesure.c3_valide else 'ÉCHEC ✗'}")
        print(f"C4 — Temporalité (valid_at)        : {donnees_mesure.c4_nb_aretes_valid_at} arête(s) -> {'CONFORME ✓' if donnees_mesure.c4_valide else 'SIGNAL ALERTE ⚠️'}")
        print(f"C5 — Rapport versionné             : rapport.md -> CONFORME ✓")
        print(f"VERDICT GLOBAL                     : {'GO ✅' if donnees_mesure.verdict_global_go else 'NO-GO ❌'}")
    
        # 7. Génération et écriture du rapport
        print("\n--- 7. Génération du rapport de mesure ---")
        rapport_markdown = generer_rapport_markdown(donnees_mesure)
    
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(rapport_markdown)
        print(f"✓ Rapport consigné dans : {output_path}")
    
    
        return donnees_mesure, rapport_markdown
    finally:
        # Fermeture propre du driver dans tous les cas
        if driver and hasattr(driver, "close"):
            await driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Banc de mesure de l'extraction Graphiti local sur 30 chunks (Story 001-5)"
    )
    parser.add_argument("--mock", action="store_true", help="Exécution en simulation déterministe hors-ligne")
    parser.add_argument("--limit", type=int, default=DEFAULT_CHUNKS_LIMIT, help="Nombre de chunks à tester (défaut: 30)")
    parser.add_argument("--chunks-start", type=int, default=DEFAULT_CHUNKS_START, help="Index de début des chunks (défaut: 0)")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Taille des chunks en caractères (défaut: 500)")
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP, help="Recouvrement en caractères (défaut: 50)")
    parser.add_argument("--pdf-path", type=str, default=DEFAULT_PDF_RELATIVE_PATH, help="Chemin vers le PDF source")
    parser.add_argument("--output-report", type=str, default=DEFAULT_REPORT_RELATIVE_PATH, help="Chemin du rapport Markdown de sortie")
    parser.add_argument("--skip-reset", action="store_true", help="Ne pas vider le graphe Neo4j avant l'épreuve")
    parser.add_argument("--delay", type=float, default=0.0, help="Délai en secondes entre chaque chunk (rate limiting)")

    args = parser.parse_args()

    try:
        donnees, _ = asyncio.run(
            executer_mesure_extraction(
                mock=args.mock,
                limit=args.limit,
                chunks_start=args.chunks_start,
                chunk_size=args.chunk_size,
                overlap=args.overlap,
                pdf_path_str=args.pdf_path,
                output_report_str=args.output_report,
                skip_reset=args.skip_reset,
                delay_between_chunks=args.delay,
            )
        )
        sys.exit(0 if donnees.verdict_global_go else 1)
    except Exception as exc:
        print(f"\n❌ ERREUR CRITIQUE lors de l'exécution du banc de mesure : {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
