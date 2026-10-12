"""Modèle de sélection d'acteurs et persistance versionnée `actors.json` (story 009-3, AC1/AC3).

Ce module implémente le contrat d'échange entre la classification automatique,
les arbitrages motivés humains et les moteurs de simulation OASIS.
Il garantit :
  - la structure canonique de `actors.json` avec version de schéma et révision,
  - la validation stricte des qualifications et l'interdiction absolue de déclarer
    éligible un rôle passif (produit, concept, tarif, URL, lieu, événement),
  - le contrôle de concurrence optimiste par `expected_revision`,
  - la traçabilité intégrale de l'historique des modifications avec justifications,
  - la persistance atomique sur disque (fichier temporaire + fsync + os.replace).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .actor_eligibility import (
    ACTOR_ELIGIBILITY_POLICY_VERSION,
    ACTIVE_ROLES,
    ActorRole,
    EligibilityStatus,
)


ACTOR_SELECTION_SCHEMA_VERSION = 1
ACTOR_SELECTION_FILENAME = "actors.json"


class ActorSelectionError(ValueError):
    """Erreur de base liée à la sélection d'acteurs."""


class OptimisticLockError(ActorSelectionError):
    """Erreur de concurrence optimiste : révision désynchronisée (HTTP 409)."""


class SelectionValidationError(ActorSelectionError):
    """Erreur de validation de rôle ou de statut d'éligibilité (HTTP 400)."""


def _utc_now_iso() -> str:
    """Horodatage ISO 8601 UTC déterministe."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ActorItem:
    """Représentation d'une entité qualifiée au sein de la sélection."""

    entity_uuid: str
    entity_name: str
    original_type: str = "Entity"
    qualified_role: ActorRole = ActorRole.UNKNOWN
    eligibility_status: EligibilityStatus = EligibilityStatus.REVIEW
    confidence: float = 0.0
    reasoning: str = ""
    is_human_modified: bool = False
    last_modified_at: Optional[str] = None
    justification: Optional[str] = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not isinstance(self.entity_uuid, str) or not self.entity_uuid.strip():
            raise SelectionValidationError("entity_uuid doit être une chaîne non vide")
        if not isinstance(self.entity_name, str):
            raise SelectionValidationError("entity_name doit être une chaîne")
        if isinstance(self.qualified_role, str):
            try:
                self.qualified_role = ActorRole(self.qualified_role)
            except ValueError as error:
                raise SelectionValidationError(
                    f"Rôle inconnu : {self.qualified_role}"
                ) from error
        if isinstance(self.eligibility_status, str):
            try:
                self.eligibility_status = EligibilityStatus(self.eligibility_status)
            except ValueError as error:
                raise SelectionValidationError(
                    f"Statut inconnu : {self.eligibility_status}"
                ) from error

        if (
            self.eligibility_status == EligibilityStatus.ELIGIBLE
            and self.qualified_role not in ACTIVE_ROLES
        ):
            raise SelectionValidationError(
                f"Le rôle '{self.qualified_role.value}' ne peut pas porter le statut 'eligible'. "
                f"Seuls {[r.value for r in ACTIVE_ROLES]} sont admissibles."
            )

    @property
    def is_eligible(self) -> bool:
        return self.eligibility_status == EligibilityStatus.ELIGIBLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_uuid": self.entity_uuid,
            "entity_name": self.entity_name,
            "original_type": self.original_type,
            "qualified_role": self.qualified_role.value,
            "eligibility_status": self.eligibility_status.value,
            "confidence": float(self.confidence),
            "reasoning": self.reasoning,
            "is_human_modified": self.is_human_modified,
            "last_modified_at": self.last_modified_at,
            "justification": self.justification,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActorItem":
        if not isinstance(data, dict):
            raise SelectionValidationError("Les données d'acteur doivent être un dictionnaire")
        raw_role = data.get("qualified_role") or ActorRole.UNKNOWN.value
        raw_status = data.get("eligibility_status") or EligibilityStatus.REVIEW.value
        raw_conf = data.get("confidence")
        confidence = float(raw_conf) if raw_conf is not None else 0.0
        return cls(
            entity_uuid=data.get("entity_uuid", ""),
            entity_name=data.get("entity_name", ""),
            original_type=data.get("original_type") or "Entity",
            qualified_role=ActorRole(raw_role),
            eligibility_status=EligibilityStatus(raw_status),
            confidence=confidence,
            reasoning=data.get("reasoning", "") or data.get("rationale", "") or "",
            is_human_modified=bool(data.get("is_human_modified", False)),
            last_modified_at=data.get("last_modified_at"),
            justification=data.get("justification"),
        )



@dataclass
class ModificationRecord:
    """Consigne un lot d'arbitrages humains appliqués à une révision."""

    revision: int
    timestamp: str
    modifications: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "revision": self.revision,
            "timestamp": self.timestamp,
            "modifications": [dict(m) for m in self.modifications],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModificationRecord":
        return cls(
            revision=int(data.get("revision", 1)),
            timestamp=data.get("timestamp", _utc_now_iso()),
            modifications=list(data.get("modifications") or []),
        )


@dataclass
class ActorSelection:
    """Sélection d'acteurs versionnée rattachée à une simulation (`actors.json`)."""

    simulation_id: str
    project_id: str
    graph_id: str
    input_fingerprint: str
    schema_version: int = ACTOR_SELECTION_SCHEMA_VERSION
    policy_version: str = ACTOR_ELIGIBILITY_POLICY_VERSION
    revision: int = 1
    counts: Dict[str, int] = field(default_factory=dict)
    actors: List[ActorItem] = field(default_factory=list)
    modifications_history: List[ModificationRecord] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        if not self.counts or len(self.counts) != 4:
            self.recalculate_counts()

    def recalculate_counts(self) -> Dict[str, int]:
        total = len(self.actors)
        eligible = sum(1 for a in self.actors if a.eligibility_status == EligibilityStatus.ELIGIBLE)
        review = sum(1 for a in self.actors if a.eligibility_status == EligibilityStatus.REVIEW)
        ineligible = sum(
            1 for a in self.actors if a.eligibility_status == EligibilityStatus.INELIGIBLE
        )
        self.counts = {
            "total": total,
            "eligible": eligible,
            "review": review,
            "ineligible": ineligible,
        }
        return self.counts

    def by_uuid(self) -> Dict[str, ActorItem]:
        return {actor.entity_uuid: actor for actor in self.actors}

    @property
    def eligible_actors(self) -> List[ActorItem]:
        return [a for a in self.actors if a.eligibility_status == EligibilityStatus.ELIGIBLE]

    @property
    def review_actors(self) -> List[ActorItem]:
        return [a for a in self.actors if a.eligibility_status == EligibilityStatus.REVIEW]

    @property
    def ineligible_actors(self) -> List[ActorItem]:
        return [a for a in self.actors if a.eligibility_status == EligibilityStatus.INELIGIBLE]

    def apply_review(
        self,
        expected_revision: int,
        modifications: List[Dict[str, Any]],
    ) -> "ActorSelection":
        """Applique un lot de modifications motivées avec contrôle de concurrence.

        Contrôles stricts :
          - `expected_revision == self.revision` (lève `OptimisticLockError`),
          - `modifications` non vide,
          - chaque `entity_uuid` existe,
          - chaque modification porte une `justification` non vide,
          - rôles cibles : seuls `person` et `organization` peuvent être `eligible`.
        """
        if not isinstance(expected_revision, int) or expected_revision < 1:
            raise SelectionValidationError(
                f"expected_revision doit être un entier positif, reçu {expected_revision}"
            )
        if expected_revision != self.revision:
            raise OptimisticLockError(
                f"Conflit de révision : attendu {expected_revision}, "
                f"révision actuelle {self.revision}"
            )
        if not modifications or not isinstance(modifications, list):
            raise SelectionValidationError("La liste des modifications ne peut pas être vide")

        actors_map = self.by_uuid()
        validated_modifications: List[Dict[str, Any]] = []

        for mod in modifications:
            if not isinstance(mod, dict):
                raise SelectionValidationError("Chaque modification doit être un dictionnaire")
            entity_uuid = mod.get("entity_uuid")
            if not entity_uuid or entity_uuid not in actors_map:
                raise SelectionValidationError(
                    f"Entité inconnue dans la sélection : {entity_uuid}"
                )

            justification = (mod.get("justification") or "").strip()
            if not justification:
                raise SelectionValidationError(
                    f"Justification obligatoire pour modifier l'entité {entity_uuid}"
                )

            raw_role = mod.get("role") or mod.get("target_role")
            raw_status = mod.get("status") or mod.get("target_status")
            if not raw_role or not raw_status:
                raise SelectionValidationError(
                    f"Rôle et statut cibles obligatoires pour {entity_uuid}"
                )

            try:
                target_role = ActorRole(raw_role)
            except ValueError as error:
                raise SelectionValidationError(
                    f"Rôle cible invalide '{raw_role}' pour {entity_uuid}"
                ) from error

            try:
                target_status = EligibilityStatus(raw_status)
            except ValueError as error:
                raise SelectionValidationError(
                    f"Statut cible invalide '{raw_status}' pour {entity_uuid}"
                ) from error

            # Interdiction absolue de la combinaison rôle passif + statut eligible
            if target_status == EligibilityStatus.ELIGIBLE and target_role not in ACTIVE_ROLES:
                raise SelectionValidationError(
                    f"Interdiction stricte : l'entité '{entity_uuid}' requalifiée en "
                    f"'{target_role.value}' ne peut pas porter le statut 'eligible'. "
                    f"Seuls {[r.value for r in ACTIVE_ROLES]} peuvent être éligibles."
                )

            validated_modifications.append({
                "entity_uuid": entity_uuid,
                "target_role": target_role.value,
                "target_status": target_status.value,
                "justification": justification,
            })

        # Application atomique des modifications
        now_iso = _utc_now_iso()
        for vmod in validated_modifications:
            actor = actors_map[vmod["entity_uuid"]]
            actor.qualified_role = ActorRole(vmod["target_role"])
            actor.eligibility_status = EligibilityStatus(vmod["target_status"])
            actor.is_human_modified = True
            actor.last_modified_at = now_iso
            actor.justification = vmod["justification"]

        self.recalculate_counts()
        self.revision += 1
        self.updated_at = now_iso
        self.modifications_history.append(
            ModificationRecord(
                revision=self.revision,
                timestamp=now_iso,
                modifications=validated_modifications,
            )
        )
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "revision": self.revision,
            "input_fingerprint": self.input_fingerprint,
            "counts": dict(self.counts),
            "actors": [a.to_dict() for a in self.actors],
            "modifications_history": [m.to_dict() for m in self.modifications_history],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActorSelection":
        if not isinstance(data, dict):
            raise SelectionValidationError(
                "Les données de sélection doivent être un dictionnaire"
            )
        actors = [ActorItem.from_dict(item) for item in (data.get("actors") or [])]
        history = [
            ModificationRecord.from_dict(rec)
            for rec in (data.get("modifications_history") or [])
        ]
        return cls(
            simulation_id=data.get("simulation_id", ""),
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            input_fingerprint=data.get("input_fingerprint", ""),
            schema_version=int(data.get("schema_version", ACTOR_SELECTION_SCHEMA_VERSION)),
            policy_version=data.get("policy_version", ACTOR_ELIGIBILITY_POLICY_VERSION),
            revision=int(data.get("revision", 1)),
            counts=dict(data.get("counts") or {}),
            actors=actors,
            modifications_history=history,
            created_at=data.get("created_at", _utc_now_iso()),
            updated_at=data.get("updated_at", _utc_now_iso()),
        )

    def save_atomic(self, file_path: str) -> str:
        """Écriture atomique sécurisée sur disque via fichier temporaire et remplacement."""
        dir_path = os.path.dirname(os.path.abspath(file_path))
        os.makedirs(dir_path, exist_ok=True)
        temp_path = f"{file_path}.{os.getpid()}_{id(self)}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, file_path)
            return file_path
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


    @classmethod
    def load(cls, file_path: str) -> Optional["ActorSelection"]:
        """Lit la sélection depuis un fichier. Retourne None si absent."""
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
