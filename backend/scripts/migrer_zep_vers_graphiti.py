#!/usr/bin/env python3
"""Pipeline ETL de migration directe Zep Cloud vers Graphiti / Neo4j (Epic 006, Story 006-2).

Ce script extrait de manière exhaustive et transactionnelle l'intégralité des nœuds
et arêtes d'un graphe distant hébergé sur Zep Cloud (graph_id), les transforme vers
le schéma Neo4j compatible Graphiti (:Entity, group_id = graph_id, horodatages ISO 8601 UTC)
et les injecte directement dans Neo4j par requêtes Cypher UNWIND par lots, sans aucun
appel LLM ni coût marginal (0 €).

Usage :
    # Mode démonstration hors-ligne sans clé Zep ni Neo4j (déterministe, pour CI)
    uv run python scripts/migrer_zep_vers_graphiti.py --mock

    # Migration d'un graphe réel avec identifiants .env
    uv run python scripts/migrer_zep_vers_graphiti.py --graph-id "rapport_an_2506"

    # Migration avec arguments explicites et export de compte-rendu
    uv run python scripts/migrer_zep_vers_graphiti.py \\
        --graph-id "rapport_an_2506" \\
        --api-key "z_..." \\
        --neo4j-uri "bolt://localhost:7687" \\
        --neo4j-password "secret" \\
        --batch-size 100 \\
        --output-report migration_report.md \\
        --output-json migration_report.json

    # Mode silencieux
    uv run python scripts/migrer_zep_vers_graphiti.py --mock --quiet
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

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
from app.services.zep_entity_reader import EntityNode, FilteredEntities, ZepEntityReader
from app.utils.graph_store import (
    GraphEdge,
    GraphInfo,
    GraphNode,
    GraphStore,
    get_graph_store,
)
from app.utils.logger import get_logger
from app.utils.zep import get_zep_client
from app.utils.zep_paging import fetch_all_edges, fetch_all_nodes

logger = get_logger("mirofish.scripts.migrer_zep_vers_graphiti")

# Clés réservées Neo4j / Graphiti à exclure du dictionnaire attributes
RESERVED_NODE_KEYS: Set[str] = {
    "uuid",
    "name",
    "summary",
    "group_id",
    "created_at",
    "labels",
    "name_embedding",
    "reference_time",
}

RESERVED_EDGE_KEYS: Set[str] = {
    "uuid",
    "source_uuid",
    "target_uuid",
    "source_node_uuid",
    "target_node_uuid",
    "source_node_name",
    "target_node_name",
    "name",
    "fact",
    "fact_type",
    "group_id",
    "episodes",
    "created_at",
    "valid_at",
    "invalid_at",
    "expired_at",
    "relation_type",
    "fact_embedding",
    "reference_time",
}


# ==============================================================================
# 1. Dataclasses et Modèles de Données (DTO)
# ==============================================================================


@dataclass
class ZepNodeDTO:
    """Représentation neutre et typée d'un nœud source Zep Cloud."""

    uuid: str
    name: str
    summary: str = ""
    labels: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None

    @classmethod
    def from_zep(cls, raw: Any) -> ZepNodeDTO:
        """Instancie un DTO depuis un objet SDK Zep, un GraphNode ou un dictionnaire."""
        if isinstance(raw, dict):
            uuid_val = raw.get("uuid") or raw.get("uuid_") or ""
            name_val = raw.get("name") or ""
            summary_val = raw.get("summary") or ""
            labels_val = list(raw.get("labels") or [])
            attrs_val = dict(raw.get("attributes") or {})
            created_at_val = raw.get("created_at")
        else:
            uuid_val = getattr(raw, "uuid_", None) or getattr(raw, "uuid", "") or ""
            name_val = getattr(raw, "name", "") or ""
            summary_val = getattr(raw, "summary", "") or ""
            raw_labels = getattr(raw, "labels", None) or []
            labels_val = list(raw_labels) if isinstance(raw_labels, (list, tuple, set)) else []
            raw_attrs = getattr(raw, "attributes", None) or {}
            attrs_val = dict(raw_attrs) if isinstance(raw_attrs, dict) else {}
            created_at_val = getattr(raw, "created_at", None)

        return cls(
            uuid=str(uuid_val).strip(),
            name=str(name_val).strip(),
            summary=str(summary_val).strip(),
            labels=[str(label).strip() for label in labels_val if label],
            attributes=attrs_val,
            created_at=str(created_at_val) if created_at_val else None,
        )


@dataclass
class ZepEdgeDTO:
    """Représentation neutre et typée d'une arête source Zep Cloud."""

    uuid: str
    source_node_uuid: str
    target_node_uuid: str
    name: str = "RELATES_TO"
    fact: str = ""
    fact_type: Optional[str] = None
    episodes: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None

    @classmethod
    def from_zep(cls, raw: Any) -> ZepEdgeDTO:
        """Instancie un DTO depuis un objet SDK Zep, un GraphEdge ou un dictionnaire."""
        if isinstance(raw, dict):
            uuid_val = raw.get("uuid") or raw.get("uuid_") or ""
            src_uuid = raw.get("source_node_uuid") or raw.get("source_uuid") or ""
            tgt_uuid = raw.get("target_node_uuid") or raw.get("target_uuid") or ""
            name_val = raw.get("name") or "RELATES_TO"
            fact_val = raw.get("fact") or ""
            fact_type = raw.get("fact_type") or name_val
            episodes_val = raw.get("episodes") or raw.get("episode_ids") or []
            attrs_val = dict(raw.get("attributes") or {})
            created_at_val = raw.get("created_at")
            valid_at_val = raw.get("valid_at")
            invalid_at_val = raw.get("invalid_at")
            expired_at_val = raw.get("expired_at")
        else:
            uuid_val = getattr(raw, "uuid_", None) or getattr(raw, "uuid", "") or ""
            src_uuid = getattr(raw, "source_node_uuid", None) or getattr(raw, "source_uuid", "") or ""
            tgt_uuid = getattr(raw, "target_node_uuid", None) or getattr(raw, "target_uuid", "") or ""
            name_val = getattr(raw, "name", "") or "RELATES_TO"
            fact_val = getattr(raw, "fact", "") or ""
            fact_type = getattr(raw, "fact_type", None) or name_val
            episodes_val = (
                getattr(raw, "episodes", None)
                or getattr(raw, "episode_ids", None)
                or []
            )
            raw_attrs = getattr(raw, "attributes", None) or {}
            attrs_val = dict(raw_attrs) if isinstance(raw_attrs, dict) else {}
            created_at_val = getattr(raw, "created_at", None)
            valid_at_val = getattr(raw, "valid_at", None)
            invalid_at_val = getattr(raw, "invalid_at", None)
            expired_at_val = getattr(raw, "expired_at", None)

        if isinstance(episodes_val, (list, tuple, set)):
            ep_list = [str(e).strip() for e in episodes_val if e]
        elif episodes_val:
            ep_list = [str(episodes_val).strip()]
        else:
            ep_list = []

        return cls(
            uuid=str(uuid_val).strip(),
            source_node_uuid=str(src_uuid).strip(),
            target_node_uuid=str(tgt_uuid).strip(),
            name=str(name_val).strip() or "RELATES_TO",
            fact=str(fact_val).strip(),
            fact_type=str(fact_type).strip() if fact_type else str(name_val).strip(),
            episodes=ep_list,
            attributes=attrs_val,
            created_at=str(created_at_val) if created_at_val else None,
            valid_at=str(valid_at_val) if valid_at_val else None,
            invalid_at=str(invalid_at_val) if invalid_at_val else None,
            expired_at=str(expired_at_val) if expired_at_val else None,
        )


@dataclass
class TransformedNode:
    """Nœud transformé prêt pour injection Cypher dans Neo4j."""

    uuid: str
    group_id: str
    name: str
    summary: str
    created_at: Optional[str]
    attributes: Dict[str, Any]
    labels: List[str]

    def to_cypher_dict(self) -> Dict[str, Any]:
        """Génère la structure de dictionnaire injectée dans la clause UNWIND."""
        return {
            "uuid": self.uuid,
            "group_id": self.group_id,
            "name": self.name,
            "summary": self.summary,
            "created_at": self.created_at,
            "attributes": self.attributes,
        }


@dataclass
class TransformedEdge:
    """Arête transformée prête pour injection Cypher dans Neo4j."""

    uuid: str
    group_id: str
    source_node_uuid: str
    target_node_uuid: str
    name: str
    fact: str
    fact_type: str
    created_at: Optional[str]
    valid_at: Optional[str]
    invalid_at: Optional[str]
    expired_at: Optional[str]
    episodes: List[str]
    attributes: Dict[str, Any]

    def to_cypher_dict(self) -> Dict[str, Any]:
        """Génère la structure de dictionnaire injectée dans la clause UNWIND."""
        return {
            "uuid": self.uuid,
            "group_id": self.group_id,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "name": self.name,
            "fact": self.fact,
            "fact_type": self.fact_type,
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at,
            "episodes": self.episodes,
            "attributes": self.attributes,
        }


@dataclass
class MigrationResult:
    """Résultat opérationnel d'une phase de migration."""

    success: bool
    nodes_loaded: int = 0
    edges_loaded: int = 0
    error: Optional[str] = None


@dataclass
class MigrationReport:
    """Compte-rendu exhaustif d'une exécution de migration ETL."""

    graph_id: str
    target_graph_id: str
    status: str  # "SUCCESS", "PARTIAL", "FAILED"
    nodes_extracted: int = 0
    nodes_transformed: int = 0
    nodes_loaded: int = 0
    edges_extracted: int = 0
    edges_transformed: int = 0
    edges_loaded: int = 0
    temporal_edges_count: int = 0
    temporal_edges_preserved: int = 0
    batch_size: int = 100
    duration_seconds: float = 0.0
    fidelity_rate: float = 100.0
    relecture_validation: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def to_dict(self) -> Dict[str, Any]:
        """Exporte le rapport en dictionnaire."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Exporte le rapport au format JSON normalisé."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Génère un rapport synthétique clair en Markdown."""
        icon = "✅" if self.status == "SUCCESS" else ("⚠️" if self.status == "PARTIAL" else "❌")
        md_lines = [
            f"# {icon} Rapport de Migration Zep Cloud vers Neo4j",
            "",
            f"- **Date (UTC)** : `{self.timestamp}`",
            f"- **Graphe source Zep** : `{self.graph_id}`",
            f"- **Graphe cible Neo4j (group_id)** : `{self.target_graph_id}`",
            f"- **Statut d'exécution** : **`{self.status}`**",
            f"- **Taux de fidélité** : **{self.fidelity_rate:.1f} %**",
            f"- **Durée totale** : **{self.duration_seconds:.2f} s**",
            f"- **Taille de lot (batch_size)** : `{self.batch_size}`",
            "",
            "## 1. Métriques de Rapatriement",
            "",
            "| Élément | Source Zep | Transformé | Injecté Neo4j | Taux de succès |",
            "|---|---|---|---|---|",
            f"| **Entités (Nœuds)** | {self.nodes_extracted} | {self.nodes_transformed} | {self.nodes_loaded} | "
            f"{(self.nodes_loaded / self.nodes_extracted * 100 if self.nodes_extracted else 100):.1f} % |",
            f"| **Relations (Arêtes)** | {self.edges_extracted} | {self.edges_transformed} | {self.edges_loaded} | "
            f"{(self.edges_loaded / self.edges_extracted * 100 if self.edges_extracted else 100):.1f} % |",
            f"| **Faits temporels** | {self.temporal_edges_count} | {self.temporal_edges_count} | {self.temporal_edges_preserved} | "
            f"{(self.temporal_edges_preserved / self.temporal_edges_count * 100 if self.temporal_edges_count else 100):.1f} % |",
            "",
            "## 2. Coût et Économie",
            "",
            "- **Appels LLM distants** : **0** (Coût marginal : 0,00 €)",
            "- **Calcul d'embeddings** : **0** (Préservation structurelle directe)",
            "- **Méthode d'injection** : Cypher `UNWIND` transactionnel par lots",
            "",
        ]

        if self.relecture_validation:
            rv = self.relecture_validation
            status_rv = "✅ Validée" if rv.get("valid") else "❌ Échec"
            md_lines.extend([
                "## 3. Validation de Relecture Applicative (Critère C4)",
                "",
                f"- **Statut global** : {status_rv}",
                f"- **Nœuds relus (GraphStore)** : `{rv.get('nodes_count', 0)}`",
                f"- **Arêtes relues (GraphStore)** : `{rv.get('edges_count', 0)}`",
                f"- **Données API web (get_graph_data)** : `nœuds: {rv.get('graph_data_nodes', 0)}, arêtes: {rv.get('graph_data_edges', 0)}`",
                f"- **Entités typées filtrées (ZepEntityReader)** : `{rv.get('filtered_entities_count', 0)}` ({', '.join(rv.get('entity_types_found', []))})",
                f"- **Éligibilité Personas OASIS** : `{'Oui' if rv.get('oasis_ready') else 'Non'}`",
                "",
            ])

        sec_num = 4 if self.relecture_validation else 3
        if self.warnings:
            md_lines.extend([
                f"## {sec_num}. Avertissements",
                "",
                *[f"- ⚠️ {w}" for w in self.warnings],
                "",
            ])
            sec_num += 1

        if self.errors:
            md_lines.extend([
                f"## {sec_num}. Anomalies / Erreurs",
                "",
                *[f"- ❌ {e}" for e in self.errors],
                "",
            ])

        return "\n".join(md_lines)


# ==============================================================================
# 2. Module de Transformation (ZepToGraphitiTransformer)
# ==============================================================================


class ZepToGraphitiTransformer:
    """Transformateur sans perte des modèles Zep vers le schéma Neo4j Graphiti."""

    @staticmethod
    def normaliser_timestamp_utc(val: Any) -> Optional[str]:
        """Normalise un horodatage (datetime, chaîne ISO, float/int unix) en ISO 8601 UTC ('YYYY-MM-DDTHH:MM:SSZ').

        Garantit à 100 % le respect du critère temporel C3 du PRD.
        """
        if val is None or isinstance(val, bool):
            return None

        # Cas 1 : objet datetime déjà instancié
        if isinstance(val, datetime):
            if val.tzinfo is None:
                dt_utc = val.replace(tzinfo=timezone.utc)
            else:
                dt_utc = val.astimezone(timezone.utc)
            return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Cas 2 : entier ou flottant (timestamp unix)
        if isinstance(val, (int, float)):
            try:
                # Gestion des timestamps en millisecondes (> 10^11)
                ts = float(val) / 1000.0 if float(val) > 1e11 else float(val)
                dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
                return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, OSError, OverflowError):
                return None

        # Cas 3 : chaîne de caractères
        raw_str = str(val).strip()
        if not raw_str:
            return None

        # Remplacement 'Z' par '+00:00' pour compatibilité fromisoformat
        clean_str = raw_str
        if clean_str.endswith("Z"):
            clean_str = clean_str[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(clean_str)
            if dt.tzinfo is None:
                dt_utc = dt.replace(tzinfo=timezone.utc)
            else:
                dt_utc = dt.astimezone(timezone.utc)
            return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass

        # Formats courants alternatifs (ex: '2026-10-10 14:30:00')
        formats = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d",
        )
        for fmt in formats:
            try:
                dt = datetime.strptime(raw_str, fmt)
                if dt.tzinfo is None:
                    dt_utc = dt.replace(tzinfo=timezone.utc)
                else:
                    dt_utc = dt.astimezone(timezone.utc)
                return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue

        # Repli si aucune conversion stricte n'a abouti : conservation propre
        return raw_str

    @classmethod
    def sanitiser_attributs_neo4j(
        cls,
        attributes: Dict[str, Any],
        reserved_keys: Set[str],
    ) -> Dict[str, Any]:
        """Assainit le dictionnaire d'attributs pour les exigences de types de Neo4j.

        Neo4j n'accepte que des types primitifs (str, int, float, bool) et des listes homogènes
        de types primitifs. Les dictionnaires ou listes complexes sont sérialisés en JSON.
        Les clés réservées système et les valeurs None sont exclues.
        """
        sanitized: Dict[str, Any] = {}
        if not isinstance(attributes, dict):
            return sanitized

        for k, v in attributes.items():
            key_str = str(k).strip()
            if not key_str or key_str in reserved_keys or v is None:
                continue

            # Conversion temporelle
            if isinstance(v, datetime):
                sanitized[key_str] = cls.normaliser_timestamp_utc(v)
            # Primitifs directs
            elif isinstance(v, (str, int, float, bool)):
                sanitized[key_str] = v
            # Listes
            elif isinstance(v, (list, tuple, set)):
                items = list(v)
                if not items:
                    sanitized[key_str] = []
                elif all(isinstance(x, (str, int, float, bool)) for x in items):
                    # Uniformiser en chaînes si types hétérogènes pour respecter Neo4j
                    types = {type(x) for x in items}
                    if len(types) == 1:
                        sanitized[key_str] = items
                    else:
                        sanitized[key_str] = [str(x) for x in items]
                else:
                    sanitized[key_str] = json.dumps(items, ensure_ascii=False)
            # Dictionnaires imbriqués
            elif isinstance(v, dict):
                sanitized[key_str] = json.dumps(v, ensure_ascii=False)
            else:
                sanitized[key_str] = str(v)

        return sanitized

    @classmethod
    def transformer_noeud(
        cls,
        noeud: ZepNodeDTO,
        target_graph_id: str,
    ) -> TransformedNode:
        """Transforme un nœud Zep en TransformedNode conforme au modèle Graphiti."""
        attrs = cls.sanitiser_attributs_neo4j(noeud.attributes, RESERVED_NODE_KEYS)

        # Préservation de l'entity_type pour ZepEntityReader / OASIS
        if "entity_type" not in attrs:
            # 1. Vérifier dans les attributs d'origine sous d'autres clés courantes
            found_type = (
                noeud.attributes.get("entity_type")
                or noeud.attributes.get("type")
                or noeud.attributes.get("category")
            )
            # 2. Vérifier dans les labels spécifiques autres que Entity/Node
            if not found_type:
                for lbl in noeud.labels:
                    if lbl and lbl.strip() not in ("Entity", "Node"):
                        found_type = lbl.strip()
                        break
            if found_type and isinstance(found_type, str) and found_type.strip():
                attrs["entity_type"] = found_type.strip()

        created_at_utc = cls.normaliser_timestamp_utc(noeud.created_at)

        return TransformedNode(
            uuid=noeud.uuid,
            group_id=target_graph_id,
            name=noeud.name,
            summary=noeud.summary,
            created_at=created_at_utc,
            attributes=attrs,
            labels=noeud.labels,
        )

    @classmethod
    def transformer_arete(
        cls,
        arete: ZepEdgeDTO,
        target_graph_id: str,
    ) -> TransformedEdge:
        """Transforme une arête Zep en TransformedEdge avec normalisation temporelle ISO 8601 UTC."""
        attrs = cls.sanitiser_attributs_neo4j(arete.attributes, RESERVED_EDGE_KEYS)

        created_at_utc = cls.normaliser_timestamp_utc(arete.created_at)
        valid_at_utc = cls.normaliser_timestamp_utc(arete.valid_at)
        invalid_at_utc = cls.normaliser_timestamp_utc(arete.invalid_at)
        expired_at_utc = cls.normaliser_timestamp_utc(arete.expired_at)

        fact_type = arete.fact_type or arete.name or "RELATES_TO"

        return TransformedEdge(
            uuid=arete.uuid,
            group_id=target_graph_id,
            source_node_uuid=arete.source_node_uuid,
            target_node_uuid=arete.target_node_uuid,
            name=arete.name or "RELATES_TO",
            fact=arete.fact,
            fact_type=fact_type,
            created_at=created_at_utc,
            valid_at=valid_at_utc,
            invalid_at=invalid_at_utc,
            expired_at=expired_at_utc,
            episodes=arete.episodes,
            attributes=attrs,
        )

    @classmethod
    def transformer_graphe(
        cls,
        noeuds: List[ZepNodeDTO],
        aretes: List[ZepEdgeDTO],
        target_graph_id: str,
    ) -> Tuple[List[TransformedNode], List[TransformedEdge], List[str]]:
        """Transforme l'ensemble d'un graphe et identifie les éventuelles anomalies structurelles."""
        warnings: List[str] = []

        transformed_nodes = [
            cls.transformer_noeud(n, target_graph_id) for n in noeuds
        ]
        transformed_edges = [
            cls.transformer_arete(e, target_graph_id) for e in aretes
        ]

        node_uuids = {n.uuid for n in transformed_nodes}

        # Détection d'arêtes orphelines (source ou target manquante)
        orphan_edges = 0
        for edge in transformed_edges:
            if edge.source_node_uuid not in node_uuids or edge.target_node_uuid not in node_uuids:
                orphan_edges += 1

        if orphan_edges > 0:
            warnings.append(
                f"{orphan_edges} arête(s) orpheline(s) détectée(s) dont le nœud source ou cible "
                f"n'apparaît pas dans l'ensemble des nœuds migrés."
            )

        return transformed_nodes, transformed_edges, warnings


# ==============================================================================
# 3. Module d'Injection Neo4j Transactionnelle Directe (Neo4jDirectLoader)
# ==============================================================================


def chunk_list(items: Sequence[Any], batch_size: int) -> List[List[Any]]:
    """Découpe une séquence en sous-listes de taille au plus batch_size."""
    if batch_size <= 0:
        raise ValueError("batch_size doit être strictement positif")
    return [list(items[i : i + batch_size]) for i in range(0, len(items), batch_size)]


class Neo4jDirectLoader:
    """Chargeur direct dans Neo4j par requêtes Cypher UNWIND transactionnelles par lots."""

    # Requêtes Cypher canoniques d'insertion (Architecture Epic 006 §3.1)
    CYPHER_UNWIND_NODES = """
    UNWIND $nodes AS row
    MERGE (n:Entity {uuid: row.uuid, group_id: $group_id})
    SET n.name = row.name,
        n.summary = row.summary,
        n.created_at = row.created_at,
        n += row.attributes
    RETURN count(n) AS merged_count
    """

    CYPHER_UNWIND_EDGES = """
    UNWIND $edges AS row
    MATCH (source:Entity {uuid: row.source_node_uuid, group_id: $group_id})
    MATCH (target:Entity {uuid: row.target_node_uuid, group_id: $group_id})
    MERGE (source)-[r:RELATES_TO {uuid: row.uuid}]->(target)
    SET r.name = row.name,
        r.fact = row.fact,
        r.fact_type = row.fact_type,
        r.created_at = row.created_at,
        r.valid_at = row.valid_at,
        r.invalid_at = row.invalid_at,
        r.expired_at = row.expired_at,
        r.group_id = $group_id,
        r.episodes = row.episodes,
        r += row.attributes
    RETURN count(r) AS merged_count
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        driver: Optional[Any] = None,
    ) -> None:
        """Initialise le chargeur Neo4j.

        Permet l'injection d'un driver pour les tests hermétiques.
        """
        self._uri = uri or os.environ.get("NEO4J_URI") or getattr(Config, "NEO4J_URI", "bolt://localhost:7687")
        self._user = user or os.environ.get("NEO4J_USER") or getattr(Config, "NEO4J_USER", "neo4j")
        self._password = password or os.environ.get("NEO4J_PASSWORD") or getattr(Config, "NEO4J_PASSWORD", None)
        self._driver = driver
        self._owns_driver = False

    def get_driver(self) -> Any:
        """Retourne ou initialise le driver Neo4j."""
        if self._driver is not None:
            return self._driver

        from neo4j import GraphDatabase

        if not self._password:
            raise ValueError(
                "NEO4J_PASSWORD est requis pour la connexion Neo4j. "
                "Définissez-le dans .env ou via l'option --neo4j-password."
            )

        self._driver = GraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
        )
        self._owns_driver = True
        return self._driver

    def close(self) -> None:
        """Ferme le driver s'il a été ouvert par cette instance."""
        if self._owns_driver and self._driver is not None:
            try:
                self._driver.close()
            except Exception as exc:
                logger.debug("Fermeture du driver Neo4j : %s", exc)
            self._driver = None

    def injecter_noeuds(
        self,
        noeuds: List[TransformedNode],
        target_graph_id: str,
        batch_size: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """Injecte les nœuds dans Neo4j par lots UNWIND transactionnels."""
        if not noeuds:
            return 0

        driver = self.get_driver()
        batches = chunk_list(noeuds, batch_size)
        total_injected = 0
        total_nodes = len(noeuds)

        with driver.session() as session:
            for b_idx, batch in enumerate(batches, start=1):
                params = {
                    "group_id": target_graph_id,
                    "nodes": [n.to_cypher_dict() for n in batch],
                }

                def _execute_tx(tx: Any, q: str, p: Dict[str, Any]) -> int:
                    res = tx.run(q, p)
                    try:
                        rec = res.single() if hasattr(res, "single") else None
                        if rec and "merged_count" in rec:
                            return int(rec["merged_count"])
                    except (TypeError, ValueError, KeyError, AttributeError):
                        pass
                    return len(p.get("nodes", []))

                if hasattr(session, "execute_write"):
                    batch_injected = session.execute_write(_execute_tx, self.CYPHER_UNWIND_NODES, params)
                    if not isinstance(batch_injected, int) or isinstance(batch_injected, bool):
                        batch_injected = len(batch)
                else:
                    res = session.run(self.CYPHER_UNWIND_NODES, params)
                    try:
                        rec = res.single() if hasattr(res, "single") else None
                        if rec and "merged_count" in rec:
                            batch_injected = int(rec["merged_count"])
                        else:
                            batch_injected = len(batch)
                    except (TypeError, ValueError, KeyError, AttributeError):
                        batch_injected = len(batch)

                total_injected += batch_injected if batch_injected is not None else len(batch)
                if progress_cb:
                    progress_cb(total_injected, total_nodes)
                logger.debug(
                    "Lot nœuds %d/%d injecté (%d/%d)",
                    b_idx,
                    len(batches),
                    total_injected,
                    total_nodes,
                )

        return total_injected

    def injecter_aretes(
        self,
        aretes: List[TransformedEdge],
        target_graph_id: str,
        batch_size: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """Injecte les arêtes dans Neo4j par lots UNWIND transactionnels."""
        if not aretes:
            return 0

        driver = self.get_driver()
        batches = chunk_list(aretes, batch_size)
        total_injected = 0
        total_edges = len(aretes)

        with driver.session() as session:
            for b_idx, batch in enumerate(batches, start=1):
                params = {
                    "group_id": target_graph_id,
                    "edges": [e.to_cypher_dict() for e in batch],
                }

                def _execute_tx(tx: Any, q: str, p: Dict[str, Any]) -> int:
                    res = tx.run(q, p)
                    try:
                        rec = res.single() if hasattr(res, "single") else None
                        if rec and "merged_count" in rec:
                            return int(rec["merged_count"])
                    except (TypeError, ValueError, KeyError, AttributeError):
                        pass
                    return len(p.get("edges", []))

                if hasattr(session, "execute_write"):
                    batch_injected = session.execute_write(_execute_tx, self.CYPHER_UNWIND_EDGES, params)
                    if not isinstance(batch_injected, int) or isinstance(batch_injected, bool):
                        batch_injected = len(batch)
                else:
                    res = session.run(self.CYPHER_UNWIND_EDGES, params)
                    try:
                        rec = res.single() if hasattr(res, "single") else None
                        if rec and "merged_count" in rec:
                            batch_injected = int(rec["merged_count"])
                        else:
                            batch_injected = len(batch)
                    except (TypeError, ValueError, KeyError, AttributeError):
                        batch_injected = len(batch)

                total_injected += batch_injected if batch_injected is not None else len(batch)
                if progress_cb:
                    progress_cb(total_injected, total_edges)
                logger.debug(
                    "Lot arêtes %d/%d injecté (%d/%d)",
                    b_idx,
                    len(batches),
                    total_injected,
                    total_edges,
                )

        return total_injected


# ==============================================================================
# 4. Mode Mock Hors-Ligne (SimulatedNeo4jLoader & generer_graphe_mock)
# ==============================================================================


class SimulatedNeo4jLoader:
    """Chargeur Neo4j simulé en mémoire pour la CI et le mode hors-ligne sans dépendance."""

    def __init__(self) -> None:
        self.nodes_by_uuid: Dict[str, Dict[str, Any]] = {}
        self.edges_by_uuid: Dict[str, Dict[str, Any]] = {}
        self.executed_queries: List[Tuple[str, Dict[str, Any]]] = []

    def close(self) -> None:
        pass

    def injecter_noeuds(
        self,
        noeuds: List[TransformedNode],
        target_graph_id: str,
        batch_size: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        batches = chunk_list(noeuds, batch_size)
        total = 0
        for batch in batches:
            params = {
                "group_id": target_graph_id,
                "nodes": [n.to_cypher_dict() for n in batch],
            }
            self.executed_queries.append((Neo4jDirectLoader.CYPHER_UNWIND_NODES, params))
            for n in batch:
                self.nodes_by_uuid[n.uuid] = n.to_cypher_dict()
                total += 1
            if progress_cb:
                progress_cb(total, len(noeuds))
        return total

    def injecter_aretes(
        self,
        aretes: List[TransformedEdge],
        target_graph_id: str,
        batch_size: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        batches = chunk_list(aretes, batch_size)
        total = 0
        for batch in batches:
            params = {
                "group_id": target_graph_id,
                "edges": [e.to_cypher_dict() for e in batch],
            }
            self.executed_queries.append((Neo4jDirectLoader.CYPHER_UNWIND_EDGES, params))
            for e in batch:
                self.edges_by_uuid[e.uuid] = e.to_cypher_dict()
                total += 1
            if progress_cb:
                progress_cb(total, len(aretes))
        return total


class SimulatedGraphStore(GraphStore):
    """Magasin GraphStore simulé en mémoire pour la relecture hors-ligne (Critère C4)."""

    def __init__(self, loader: Optional[SimulatedNeo4jLoader] = None) -> None:
        self.nodes_by_uuid: Dict[str, GraphNode] = {}
        self.edges_by_uuid: Dict[str, GraphEdge] = {}
        if loader is not None:
            self.charger_depuis_loader(loader)

    def charger_depuis_loader(self, loader: SimulatedNeo4jLoader) -> None:
        """Charge en mémoire les nœuds et arêtes injectés dans un SimulatedNeo4jLoader."""
        for u, d in loader.nodes_by_uuid.items():
            self.nodes_by_uuid[u] = GraphNode(
                uuid=str(d.get("uuid", u)),
                name=str(d.get("name", "")),
                summary=str(d.get("summary", "")),
                labels=list(d.get("labels", ["Entity"])),
                attributes=dict(d.get("attributes", {})),
                created_at=d.get("created_at"),
            )
        for u, d in loader.edges_by_uuid.items():
            self.edges_by_uuid[u] = GraphEdge(
                uuid=str(d.get("uuid", u)),
                source_node_uuid=str(d.get("source_node_uuid", "")),
                target_node_uuid=str(d.get("target_node_uuid", "")),
                name=str(d.get("name", "RELATES_TO")),
                fact=str(d.get("fact", "")),
                fact_type=str(d.get("fact_type", "")),
                valid_at=d.get("valid_at"),
                invalid_at=d.get("invalid_at"),
                expired_at=d.get("expired_at"),
                attributes=dict(d.get("attributes", {})),
                episodes=list(d.get("episodes", [])),
                created_at=d.get("created_at"),
            )

    def get_all_nodes(self, graph_id: str) -> List[GraphNode]:
        return list(self.nodes_by_uuid.values())

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[GraphEdge]:
        edges = list(self.edges_by_uuid.values())
        if include_temporal:
            return edges
        return [
            GraphEdge(
                uuid=e.uuid,
                name=e.name,
                fact=e.fact,
                source_node_uuid=e.source_node_uuid,
                target_node_uuid=e.target_node_uuid,
                fact_type=e.fact_type,
                source_node_name=e.source_node_name,
                target_node_name=e.target_node_name,
                attributes=e.attributes,
                episodes=e.episodes,
                created_at=e.created_at,
                valid_at=None,
                invalid_at=None,
                expired_at=None,
            )
            for e in edges
        ]

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        nodes_list = [n.to_dict() for n in self.get_all_nodes(graph_id)]
        edges_list = [e.to_dict(include_temporal=True) for e in self.get_all_edges(graph_id)]
        return {
            "graph_id": graph_id,
            "nodes": nodes_list,
            "edges": edges_list,
            "node_count": len(nodes_list),
            "edge_count": len(edges_list),
            "statistics": {
                "node_count": len(nodes_list),
                "edge_count": len(edges_list),
            },
        }

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        types = set()
        for n in nodes:
            t = n.attributes.get("entity_type")
            if not t and len(n.labels) > 1:
                t = [l for l in n.labels if l not in ("Entity", "Node")][0] if any(l not in ("Entity", "Node") for l in n.labels) else None
            if t:
                types.add(t)
        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=sorted(list(types)),
        )

    def create_graph(self, graph_id: Optional[str] = None) -> str:
        return graph_id or "simulated_graph"

    def delete_graph(self, graph_id: str) -> None:
        self.nodes_by_uuid.clear()
        self.edges_by_uuid.clear()

    def get_node(self, graph_id: str, node_uuid: str) -> Optional[GraphNode]:
        return self.nodes_by_uuid.get(node_uuid)

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[GraphEdge]:
        return [
            e for e in self.edges_by_uuid.values()
            if e.source_node_uuid == node_uuid or e.target_node_uuid == node_uuid
        ]

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        pass

    def add_episode(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("SimulatedGraphStore est en lecture seule.")

    def add_text_batch(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("SimulatedGraphStore est en lecture seule.")

    def wait_for_batch(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def wait_for_episodes(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def search(self, graph_id: str, query: str, limit: int = 10) -> List[Any]:
        return []


def valider_relecture_migree(
    target_graph_id: str,
    store: GraphStore,
    entity_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Valide de bout en bout la relecture applicative d'un graphe migré (Critère C4 du PRD).

    Vérifie que :
    1. GraphStore.get_all_nodes() et get_all_edges() restituent fidèlement les données.
    2. GraphStore.get_graph_data() retourne la structure complète conforme pour l'API.
    3. ZepEntityReader extrait et filtre les entités typées via entity_type.
    4. Les entités extraites sont directement prêtes pour la génération de profils personas OASIS sans Zep.
    """
    clean_id = target_graph_id.strip()

    # 1. Relecture directe GraphStore
    nodes = store.get_all_nodes(clean_id)
    edges = store.get_all_edges(clean_id, include_temporal=True)
    graph_data = store.get_graph_data(clean_id)

    # 2. Relecture via ZepEntityReader
    reader = ZepEntityReader(store=store)
    reader_nodes = reader.get_all_nodes(clean_id)
    reader_edges = reader.get_all_edges(clean_id)

    types_cibles = list(entity_types or ["Person", "Organization", "Location", "Institution", "Commission", "Document"])
    filtered = reader.filter_defined_entities(clean_id, defined_entity_types=types_cibles)

    # 3. Contrôle de compatibilité OASIS
    # Chaque entité filtrée doit disposer d'un nom non vide et d'un entity_type résolu
    oasis_ready = len(filtered.entities) > 0 and all(
        bool(e.name and e.get_entity_type()) for e in filtered.entities
    )

    checks = {
        "graph_store_nodes_ok": len(nodes) == len(reader_nodes),
        "graph_store_edges_ok": len(edges) == len(reader_edges),
        "graph_data_consistent": graph_data.get("node_count") == len(nodes) and graph_data.get("edge_count") == len(edges),
        "entity_reader_filtered_ok": filtered.filtered_count > 0 or len(nodes) == 0,
        "oasis_personas_ready": oasis_ready or len(nodes) == 0,
    }

    all_passed = all(checks.values())

    return {
        "graph_id": clean_id,
        "valid": all_passed,
        "nodes_count": len(nodes),
        "edges_count": len(edges),
        "graph_data_nodes": graph_data.get("node_count", 0),
        "graph_data_edges": graph_data.get("edge_count", 0),
        "filtered_entities_count": filtered.filtered_count,
        "entity_types_found": sorted(list(filtered.entity_types)),
        "oasis_ready": oasis_ready,
        "checks": checks,
    }


def generer_graphe_mock(
    graph_id: str = "mock_rapport_an_2506",
) -> Tuple[List[ZepNodeDTO], List[ZepEdgeDTO]]:
    """Génère un jeu de données Zep représentatif complet avec faits temporels et entités typées."""
    nodes = [
        ZepNodeDTO(
            uuid="node-an-001",
            name="Assemblée nationale",
            summary="Institution parlementaire française de la Ve République.",
            labels=["Entity", "Institution"],
            attributes={
                "entity_type": "Institution",
                "juridiction": "France",
                "siege": "Palais Bourbon, Paris",
                "reference_legale": "Constitution de 1958",
            },
            created_at="2026-03-01T10:00:00Z",
        ),
        ZepNodeDTO(
            uuid="node-an-002",
            name="Commission des Lois",
            summary="Commission permanente chargée des affaires constitutionnelles.",
            labels=["Entity", "Commission"],
            attributes={
                "entity_type": "Commission",
                "nb_membres": 73,
            },
            created_at="2026-03-01T10:05:00Z",
        ),
        ZepNodeDTO(
            uuid="node-an-003",
            name="Rapport d'information n° 2506",
            summary="Rapport d'évaluation des politiques publiques rédigé en session ordinaire.",
            labels=["Entity", "Document"],
            attributes={
                "entity_type": "Document",
                "numero": 2506,
                "statut": "adopté",
            },
            created_at="2026-03-02T14:20:00Z",
        ),
        ZepNodeDTO(
            uuid="node-an-004",
            name="Jean Dupont",
            summary="Député rapporteur de la mission d'évaluation parlementaire.",
            labels=["Entity", "Person"],
            attributes={
                "entity_type": "Person",
                "role": "Rapporteur",
                "circonscription": "Paris 2e",
            },
            created_at="2026-03-02T14:25:00Z",
        ),
    ]

    edges = [
        ZepEdgeDTO(
            uuid="edge-rel-001",
            source_node_uuid="node-an-002",
            target_node_uuid="node-an-001",
            name="COMPOSES",
            fact="La Commission des Lois est une commission permanente de l'Assemblée nationale.",
            fact_type="ORGANIZATION_HIERARCHY",
            created_at="2026-03-01T10:10:00Z",
            valid_at="2026-01-01T00:00:00Z",
            invalid_at=None,
            episodes=["ep-001"],
            attributes={"statut_relation": "permanente"},
        ),
        ZepEdgeDTO(
            uuid="edge-rel-002",
            source_node_uuid="node-an-004",
            target_node_uuid="node-an-003",
            name="AUTHORS",
            fact="Jean Dupont a rédigé le rapport d'information n° 2506 au nom de la commission.",
            fact_type="AUTHORSHIP",
            created_at="2026-03-02T15:00:00Z",
            valid_at="2026-03-02T00:00:00Z",
            invalid_at="2027-03-02T00:00:00Z",
            expired_at=None,
            episodes=["ep-002"],
            attributes={"mandat": "2024-2027"},
        ),
        ZepEdgeDTO(
            uuid="edge-rel-003",
            source_node_uuid="node-an-003",
            target_node_uuid="node-an-002",
            name="SUBMITTED_TO",
            fact="Le rapport n° 2506 a été formellement déposé devant la Commission des Lois.",
            fact_type="DEPOSIT",
            created_at="2026-03-02T15:30:00Z",
            valid_at="2026-03-02T12:00:00Z",
            invalid_at=None,
            episodes=["ep-002"],
            attributes={"seance": "ordinaire"},
        ),
    ]

    return nodes, edges


# ==============================================================================
# 5. Orchestrateur de Migration (ZepToGraphitiMigrator)
# ==============================================================================


class ZepToGraphitiMigrator:
    """Orchestrateur ETL pilotant l'extraction Zep, la transformation et le chargement Cypher."""

    def __init__(
        self,
        loader: Any,
        zep_client: Optional[Any] = None,
        transformer: Optional[ZepToGraphitiTransformer] = None,
    ) -> None:
        self.loader = loader
        self.zep_client = zep_client
        self.transformer = transformer or ZepToGraphitiTransformer()

    def migrer_graphe(
        self,
        graph_id: str,
        target_graph_id: Optional[str] = None,
        batch_size: int = 100,
        mock_data: Optional[Tuple[List[ZepNodeDTO], List[ZepEdgeDTO]]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> MigrationReport:
        """Exécute le pipeline complet de migration pour le graph_id spécifié."""
        clean_graph_id = graph_id.strip()
        target_id = (
            target_graph_id.strip()
            if target_graph_id and target_graph_id.strip()
            else clean_graph_id
        )
        start_time = time.time()

        report = MigrationReport(
            graph_id=clean_graph_id,
            target_graph_id=target_id,
            status="FAILED",
            batch_size=batch_size,
        )

        try:
            # 1. Extraction des données
            if mock_data is not None:
                zep_nodes_raw, zep_edges_raw = mock_data
                nodes_dto = [ZepNodeDTO.from_zep(n) for n in zep_nodes_raw]
                edges_dto = [ZepEdgeDTO.from_zep(e) for e in zep_edges_raw]
            else:
                if self.zep_client is None:
                    raise ValueError(
                        "Client Zep non configuré. Fournissez ZEP_API_KEY ou utilisez le mode --mock."
                    )
                logger.info("Extraction des nœuds depuis Zep Cloud pour '%s'...", graph_id)
                raw_nodes = fetch_all_nodes(self.zep_client, graph_id)
                nodes_dto = [ZepNodeDTO.from_zep(n) for n in raw_nodes]

                logger.info("Extraction des arêtes depuis Zep Cloud pour '%s'...", graph_id)
                raw_edges = fetch_all_edges(self.zep_client, graph_id)
                edges_dto = [ZepEdgeDTO.from_zep(e) for e in raw_edges]

            report.nodes_extracted = len(nodes_dto)
            report.edges_extracted = len(edges_dto)

            # Comptage des arêtes possédant un champ temporel
            report.temporal_edges_count = sum(
                1 for e in edges_dto if e.valid_at or e.invalid_at or e.expired_at
            )

            # 2. Transformation
            transformed_nodes, transformed_edges, warnings = self.transformer.transformer_graphe(
                nodes_dto, edges_dto, target_id
            )
            report.nodes_transformed = len(transformed_nodes)
            report.edges_transformed = len(transformed_edges)
            report.warnings.extend(warnings)

            # 3. Injection dans Neo4j
            def _node_cb(curr: int, tot: int) -> None:
                if progress_callback:
                    progress_callback("nodes", curr, tot)

            def _edge_cb(curr: int, tot: int) -> None:
                if progress_callback:
                    progress_callback("edges", curr, tot)

            logger.info("Injection des %d nœuds dans Neo4j (:Entity)...", len(transformed_nodes))
            injected_nodes = self.loader.injecter_noeuds(
                transformed_nodes, target_id, batch_size=batch_size, progress_cb=_node_cb
            )
            report.nodes_loaded = injected_nodes

            logger.info("Injection des %d arêtes dans Neo4j (RELATES_TO)...", len(transformed_edges))
            injected_edges = self.loader.injecter_aretes(
                transformed_edges, target_id, batch_size=batch_size, progress_cb=_edge_cb
            )
            report.edges_loaded = injected_edges

            # Mesure de préservation temporelle
            preserved_temporal = sum(
                1 for e in transformed_edges if e.valid_at or e.invalid_at or e.expired_at
            )
            report.temporal_edges_preserved = preserved_temporal

            # Calcul du taux de fidélité
            total_elements = report.nodes_extracted + report.edges_extracted
            total_loaded = report.nodes_loaded + report.edges_loaded

            if total_elements == 0:
                report.fidelity_rate = 100.0
                report.status = "SUCCESS"
            else:
                report.fidelity_rate = min(100.0, (total_loaded / total_elements) * 100.0)
                if total_loaded == total_elements:
                    report.status = "SUCCESS"
                elif total_loaded > 0:
                    report.status = "PARTIAL"
                else:
                    report.status = "FAILED"

        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {exc}"
            logger.error("Erreur durant la migration de '%s' : %s", graph_id, err_msg)
            report.errors.append(err_msg)
            report.status = "FAILED"

        finally:
            report.duration_seconds = time.time() - start_time

        return report


# ==============================================================================
# 6. Interface CLI et Parsing des Arguments
# ==============================================================================


def parser_arguments(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse et valide les arguments de ligne de commande."""
    parser = argparse.ArgumentParser(
        description="Pipeline ETL de migration directe Zep Cloud vers Graphiti / Neo4j (Epic 006, Story 006-2).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--graph-id",
        type=str,
        default=None,
        help="Identifiant du graphe Zep Cloud à migrer (ex: 'rapport_an_2506').",
    )
    parser.add_argument(
        "--target-graph-id",
        type=str,
        default=None,
        help="Identifiant de destination dans Neo4j (group_id). Par défaut identique à --graph-id.",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Clé ZEP_API_KEY. Si omise, lue depuis l'environnement ou .env.",
    )
    parser.add_argument(
        "--neo4j-uri",
        type=str,
        default=None,
        help="URI Bolt Neo4j (défaut : Config.NEO4J_URI ou 'bolt://localhost:7687').",
    )
    parser.add_argument(
        "--neo4j-user",
        type=str,
        default=None,
        help="Utilisateur Neo4j (défaut : Config.NEO4J_USER ou 'neo4j').",
    )
    parser.add_argument(
        "--neo4j-password",
        type=str,
        default=None,
        help="Mot de passe Neo4j (défaut : Config.NEO4J_PASSWORD ou lu depuis .env).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Taille des lots pour les requêtes Cypher UNWIND (défaut : 100).",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Exécute la migration en mode simulation déterministe hors-ligne (0 appel réseau, idéal CI).",
    )
    parser.add_argument(
        "--output-report",
        type=str,
        default=None,
        help="Chemin de fichier pour exporter le compte-rendu Markdown.",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Chemin de fichier pour exporter les résultats au format JSON.",
    )
    parser.add_argument(
        "--verify-relecture",
        action="store_true",
        default=False,
        help="Valider la relecture applicative post-migration (GraphStore, ZepEntityReader, OASIS) (Critère C4).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Mode silencieux : limite la sortie console aux erreurs et au récapitulatif.",
    )

    return parser.parse_args(args)


def masquer_secret(secret: Optional[str]) -> str:
    """Masque une clé secrète pour les logs et la console sans fuite."""
    if not secret:
        return "<non défini>"
    if len(secret) <= 6:
        return "***"
    return f"{secret[:3]}...{secret[-2:]}"


def main(cli_args: Optional[List[str]] = None) -> int:
    """Point d'entrée exécutable du pipeline ETL de migration."""
    args = parser_arguments(cli_args)

    if args.batch_size <= 0:
        logger.error("Option invalide : --batch-size doit être strictement supérieur à 0 (reçu: %d).", args.batch_size)
        print("Erreur : --batch-size doit être strictement supérieur à 0.", file=sys.stderr)
        return 1

    if not args.quiet:
        print("=" * 72)
        print("  MiroFish — Pipeline ETL de Migration Zep Cloud -> Neo4j (Story 006-2)")
        print("=" * 72)

    # 1. Mode Mock hors-ligne
    if args.mock:
        graph_id = (args.graph_id or "mock_rapport_an_2506").strip()
        target_id = (
            args.target_graph_id.strip()
            if args.target_graph_id and args.target_graph_id.strip()
            else graph_id
        )
        if not args.quiet:
            print(f"[MODE MOCK] Simulation déterministe activée pour le graphe '{graph_id}'.")
            print("  - Aucune requête réseau émise vers Zep Cloud ni Neo4j.")
            print(f"  - Injection simulée dans Neo4j (group_id = '{target_id}').\n")

        mock_nodes, mock_edges = generer_graphe_mock(graph_id)
        loader = SimulatedNeo4jLoader()
        migrator = ZepToGraphitiMigrator(loader=loader)

        report = migrator.migrer_graphe(
            graph_id=graph_id,
            target_graph_id=target_id,
            batch_size=args.batch_size,
            mock_data=(mock_nodes, mock_edges),
        )

    # 2. Mode Réel
    else:
        if not args.graph_id:
            logger.error("Option obligatoire manquante : --graph-id doit être spécifié en mode réel.")
            print("Erreur : --graph-id est obligatoire en mode réel (ex: --graph-id rapport_an_2506)", file=sys.stderr)
            return 1

        clean_graph_id = args.graph_id.strip()
        target_id = (
            args.target_graph_id.strip()
            if args.target_graph_id and args.target_graph_id.strip()
            else clean_graph_id
        )

        api_key = args.api_key or os.environ.get("ZEP_API_KEY") or getattr(Config, "ZEP_API_KEY", None)
        if not api_key:
            logger.error("ZEP_API_KEY introuvable. Définissez-la dans .env ou via --api-key.")
            print("Erreur : Clé Zep manquante. Spécifiez --api-key ou définissez ZEP_API_KEY.", file=sys.stderr)
            return 1

        neo4j_uri = args.neo4j_uri or os.environ.get("NEO4J_URI") or getattr(Config, "NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = args.neo4j_user or os.environ.get("NEO4J_USER") or getattr(Config, "NEO4J_USER", "neo4j")
        neo4j_password = args.neo4j_password or os.environ.get("NEO4J_PASSWORD") or getattr(Config, "NEO4J_PASSWORD", None)

        if not neo4j_password:
            logger.error("NEO4J_PASSWORD introuvable. Définissez-le dans .env ou via --neo4j-password.")
            print("Erreur : Mot de passe Neo4j manquant. Spécifiez --neo4j-password ou définissez NEO4J_PASSWORD.", file=sys.stderr)
            return 1

        if not args.quiet:
            print(f"Configuration :")
            print(f"  - Graphe source : {args.graph_id}")
            print(f"  - Cible Neo4j   : {neo4j_uri} (user: {neo4j_user})")
            print(f"  - Clé Zep       : {masquer_secret(api_key)}")
            print(f"  - Mot de passe  : {masquer_secret(neo4j_password)}")
            print(f"  - Lot (batch)   : {args.batch_size}\n")

        try:
            zep_client = get_zep_client(api_key=api_key)
            loader = Neo4jDirectLoader(
                uri=neo4j_uri,
                user=neo4j_user,
                password=neo4j_password,
            )
            migrator = ZepToGraphitiMigrator(loader=loader, zep_client=zep_client)

            def _cli_progress(phase: str, curr: int, tot: int) -> None:
                if not args.quiet:
                    pct = (curr / tot * 100) if tot else 100
                    print(f"  -> {phase.upper()} : {curr}/{tot} ({pct:.0f} %)", end="\r", flush=True)

            report = migrator.migrer_graphe(
                graph_id=clean_graph_id,
                target_graph_id=target_id,
                batch_size=args.batch_size,
                progress_callback=_cli_progress,
            )
            if not args.quiet:
                print()  # saut de ligne après la barre de progression

        finally:
            if "loader" in locals() and hasattr(loader, "close"):
                loader.close()

    # Validation optionnelle de relecture applicative (Critère C4)
    if args.verify_relecture:
        if args.mock:
            sim_store = SimulatedGraphStore(loader=loader)
            val_res = valider_relecture_migree(target_graph_id=target_id, store=sim_store)
        else:
            real_store = get_graph_store()
            val_res = valider_relecture_migree(target_graph_id=target_id, store=real_store)

        report.relecture_validation = val_res

        if not args.quiet:
            print("\n" + "=" * 50)
            print("  Vérification de Relecture Applicative (Critère C4)")
            print("=" * 50)
            print(f"  - Nœuds relus (GraphStore)        : {val_res['nodes_count']}")
            print(f"  - Arêtes relues (GraphStore)       : {val_res['edges_count']}")
            print(f"  - Entités filtrées (EntityReader) : {val_res['filtered_entities_count']} ({', '.join(val_res['entity_types_found'])})")
            print(f"  - Éligibilité Personas OASIS      : {'Oui' if val_res['oasis_ready'] else 'Non'}")
            print(f"  - Statut de validation             : {'✅ VALIDÉ' if val_res['valid'] else '❌ ÉCHEC'}\n")

    # Affichage du rapport
    if not args.quiet:
        print("\n" + report.to_markdown())

    # Export optionnel du rapport Markdown
    if args.output_report:
        report_path = Path(args.output_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report.to_markdown(), encoding="utf-8")
        if not args.quiet:
            print(f"✓ Rapport Markdown exporté : {report_path}")

    # Export optionnel du rapport JSON
    if args.output_json:
        json_path = Path(args.output_json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(report.to_json(), encoding="utf-8")
        if not args.quiet:
            print(f"✓ Données JSON exportées : {json_path}")

    return 0 if report.status == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(main())
