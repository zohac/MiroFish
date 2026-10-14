"""Modèles de version d'ontologie et magasin persistant (story 007-4, AC1).

Ce module implémente :
- Les dataclasses immutables `OntologyEntityType` et `OntologyEdgeType`
- Le modèle immuable `OntologyVersion` identifié par `ont_<uuid12>`
- Le magasin `OntologyVersionStore` qui assure la persistance atomique de JSON
  sous `Config.UPLOAD_FOLDER/ontologies/<version_id>.json` avec un index projet.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..utils.ontology import MAX_ONTOLOGY_TYPES
from .source_document import InformationOrigin


def _utc_now_iso() -> str:
    """Horodatage ISO 8601 UTC normalisé."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class OntologyEntityType:
    """Représentation immuable d'un type d'entité d'ontologie."""

    name: str
    description: str = ""
    attributes: Tuple[str, ...] = ()
    source: InformationOrigin = InformationOrigin.DOCUMENTARY

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Le nom du type d'entité ne peut pas être vide")
        if not re.fullmatch(r"[A-Za-z0-9_]+", self.name):
            raise ValueError(f"Nom de type d'entité invalide : {self.name!r}")
        if not isinstance(self.attributes, tuple):
            object.__setattr__(self, "attributes", tuple(self.attributes))
        if not isinstance(self.source, InformationOrigin):
            object.__setattr__(self, "source", InformationOrigin.from_str(str(self.source)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "attributes": list(self.attributes),
            "source": self.source.value if isinstance(self.source, InformationOrigin) else str(self.source),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OntologyEntityType":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            attributes=tuple(data.get("attributes", ())),
            source=InformationOrigin.from_str(data.get("source")),
        )


@dataclass(frozen=True)
class OntologyEdgeType:
    """Représentation immuable d'un type de relation d'ontologie."""

    name: str
    source_types: Tuple[str, ...] = ()
    target_types: Tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Le nom du type de relation ne peut pas être vide")
        if not re.fullmatch(r"[A-Za-z0-9_]+", self.name):
            raise ValueError(f"Nom de type de relation invalide : {self.name!r}")
        if not isinstance(self.source_types, tuple):
            object.__setattr__(self, "source_types", tuple(self.source_types))
        if not isinstance(self.target_types, tuple):
            object.__setattr__(self, "target_types", tuple(self.target_types))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source_types": list(self.source_types),
            "target_types": list(self.target_types),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OntologyEdgeType":
        return cls(
            name=data["name"],
            source_types=tuple(data.get("source_types", ())),
            target_types=tuple(data.get("target_types", ())),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class OntologyVersion:
    """Version immuable d'ontologie projet (AC1, architecture §2.1)."""

    version_id: str
    project_id: str
    entity_types: Tuple[OntologyEntityType, ...]
    edge_types: Tuple[OntologyEdgeType, ...]
    created_at: str
    source_summary: str = ""
    parent_version_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.version_id or not self.version_id.startswith("ont_"):
            raise ValueError(f"L'identifiant de version doit commencer par 'ont_' : {self.version_id!r}")
        if not self.project_id:
            raise ValueError("project_id est obligatoire pour une version d'ontologie")
        if not isinstance(self.entity_types, tuple):
            object.__setattr__(self, "entity_types", tuple(self.entity_types))
        if not isinstance(self.edge_types, tuple):
            object.__setattr__(self, "edge_types", tuple(self.edge_types))
        if len(self.entity_types) > MAX_ONTOLOGY_TYPES:
            raise ValueError(
                f"Nombre de types d'entité ({len(self.entity_types)}) supérieur au plafond autorisé ({MAX_ONTOLOGY_TYPES})"
            )

    @classmethod
    def generate_version_id(cls) -> str:
        """Génère un identifiant ont_<uuid12> sécurisé."""
        return f"ont_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        """Sérialisation réversible en dictionnaire JSON-compatible."""
        return {
            "version_id": self.version_id,
            "project_id": self.project_id,
            "entity_types": [et.to_dict() for et in self.entity_types],
            "edge_types": [et.to_dict() for et in self.edge_types],
            "created_at": self.created_at,
            "source_summary": self.source_summary,
            "parent_version_id": self.parent_version_id,
        }

    def to_ontology_dict(self) -> Dict[str, Any]:
        """Convertit vers le format dict standard attendu par GraphStore.set_ontology."""
        return {
            "entity_types": [et.to_dict() for et in self.entity_types],
            "edge_types": [et.to_dict() for et in self.edge_types],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OntologyVersion":
        entity_types = tuple(
            OntologyEntityType.from_dict(item) if isinstance(item, dict) else item
            for item in data.get("entity_types", ())
        )
        edge_types = tuple(
            OntologyEdgeType.from_dict(item) if isinstance(item, dict) else item
            for item in data.get("edge_types", ())
        )
        return cls(
            version_id=data["version_id"],
            project_id=data["project_id"],
            entity_types=entity_types,
            edge_types=edge_types,
            created_at=data.get("created_at") or _utc_now_iso(),
            source_summary=data.get("source_summary", ""),
            parent_version_id=data.get("parent_version_id"),
        )


class OntologyVersionStore:
    """Magasin de versions d'ontologie avec écriture atomique et index projet.
    
    Persistance :
      - Versions : `Config.UPLOAD_FOLDER/ontologies/<version_id>.json`
      - Index : `Config.UPLOAD_FOLDER/ontologies/index.json` (project_id -> [version_id, ...])
    """

    @classmethod
    def get_storage_dir(cls) -> str:
        """Chemin vers le dossier de stockage des ontologies."""
        path = os.path.join(Config.UPLOAD_FOLDER, "ontologies")
        os.makedirs(path, exist_ok=True)
        return path

    @classmethod
    def get_version_path(cls, version_id: str) -> str:
        """Chemin d'un fichier de version d'ontologie."""
        if not re.fullmatch(r"[A-Za-z0-9_]+", version_id):
            raise ValueError(f"version_id invalide : {version_id!r}")
        return os.path.join(cls.get_storage_dir(), f"{version_id}.json")

    @classmethod
    def get_index_path(cls) -> str:
        """Chemin du fichier d'index projet."""
        return os.path.join(cls.get_storage_dir(), "index.json")

    @classmethod
    def _read_index(cls) -> Dict[str, List[str]]:
        index_path = cls.get_index_path()
        if not os.path.exists(index_path):
            return {}
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            return {}
        return {}

    @classmethod
    def _update_index(cls, project_id: str, version_id: str) -> None:
        index_path = cls.get_index_path()
        storage_dir = cls.get_storage_dir()
        index = cls._read_index()
        versions = index.setdefault(project_id, [])
        if version_id not in versions:
            versions.append(version_id)
        
        tmp_path = os.path.join(storage_dir, f"index_{uuid.uuid4().hex[:8]}.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, index_path)

    @classmethod
    def create(
        cls,
        project_id: str,
        ontology_dict: Dict[str, Any],
        parent_version_id: Optional[str] = None,
        source_summary: str = "",
        version_id: Optional[str] = None,
    ) -> OntologyVersion:
        """Crée, persiste atomiquement et indexe une nouvelle OntologyVersion."""
        if not project_id:
            raise ValueError("project_id est requis")
        
        vid = version_id or OntologyVersion.generate_version_id()

        raw_entities = ontology_dict.get("entity_types", [])
        entity_types: List[OntologyEntityType] = []
        for item in raw_entities:
            if isinstance(item, OntologyEntityType):
                entity_types.append(item)
            elif isinstance(item, dict):
                entity_types.append(OntologyEntityType.from_dict(item))
            elif isinstance(item, str):
                entity_types.append(OntologyEntityType(name=item))

        raw_edges = ontology_dict.get("edge_types", [])
        edge_types: List[OntologyEdgeType] = []
        for item in raw_edges:
            if isinstance(item, OntologyEdgeType):
                edge_types.append(item)
            elif isinstance(item, dict):
                edge_types.append(OntologyEdgeType.from_dict(item))
            elif isinstance(item, str):
                edge_types.append(OntologyEdgeType(name=item))

        version = OntologyVersion(
            version_id=vid,
            project_id=project_id,
            entity_types=tuple(entity_types),
            edge_types=tuple(edge_types),
            created_at=_utc_now_iso(),
            source_summary=source_summary,
            parent_version_id=parent_version_id,
        )

        # Écriture atomique
        cls.save(version)
        cls._update_index(project_id, version.version_id)
        return version

    @classmethod
    def save(cls, version: OntologyVersion) -> None:
        """Sauvegarde atomique d'une OntologyVersion."""
        storage_dir = cls.get_storage_dir()
        target_path = cls.get_version_path(version.version_id)
        tmp_path = os.path.join(storage_dir, f"{version.version_id}_{uuid.uuid4().hex[:8]}.tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(version.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, target_path)

    @classmethod
    def get(cls, version_id: str) -> Optional[OntologyVersion]:
        """Lit une version d'ontologie par son ID."""
        try:
            target_path = cls.get_version_path(version_id)
        except ValueError:
            return None
        if not os.path.exists(target_path):
            return None
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return OntologyVersion.from_dict(data)
        except Exception:
            return None

    @classmethod
    def list_for_project(cls, project_id: str) -> List[OntologyVersion]:
        """Liste toutes les versions d'ontologie enregistrées pour un projet."""
        index = cls._read_index()
        version_ids = index.get(project_id, [])
        results: List[OntologyVersion] = []
        for vid in version_ids:
            v = cls.get(vid)
            if v:
                results.append(v)
        return results
