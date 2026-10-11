"""Modèle d'éligibilité des acteurs (story 009-1, FR-1/FR-2).

Ce module isole le contrat de qualification d'une entité de graphe : une entité
de connaissance ne devient un agent OASIS que si elle est explicitement
qualifiée comme acteur (`person` ou `organization`) avec le statut `eligible`.

Aucune règle métier spécifique à un domaine n'y figure : le rôle décrit une
catégorie sémantique universelle, le statut une décision de la barrière.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, field_validator


# Version de la politique de qualification du lot (story 009-1).
# Toute évolution de la politique doit incrémenter cette valeur : elle est
# inscrite dans la preuve de préparation et invalide les préparations passées.
ACTOR_ELIGIBILITY_POLICY_VERSION = "009-1-v1"

# Seuil de confiance minimal, borne incluse, commun aux domaines.
DEFAULT_CONFIDENCE_THRESHOLD = 0.7


class ActorRole(str, Enum):
    """Rôle sémantique générique d'une entité."""

    PERSON = "person"              # Individu réel ou persona humaine décrite
    ORGANIZATION = "organization"  # Société, organisme officiel, institution
    COLLECTIVE = "collective"      # Communauté, groupe informel
    PRODUCT = "product"            # Produit, logiciel, offre, formule
    SERVICE = "service"            # Service rendu
    DOMAIN = "domain"              # Nom de domaine, site web, URL
    PLACE = "place"                # Lieu géographique, ville, pays
    EVENT = "event"                # Événement daté, réunion, incident
    CONCEPT = "concept"            # Idée abstraite, sujet, thématique
    UNKNOWN = "unknown"            # Non déterminé


class EligibilityStatus(str, Enum):
    """Statut d'éligibilité à devenir un agent de simulation."""

    ELIGIBLE = "eligible"      # Autorisé à devenir un compte OASIS actif
    INELIGIBLE = "ineligible"  # Conservé en base de connaissances, exclu des agents
    REVIEW = "review"          # Nécessite une confirmation (ambigu)


# Seuls les rôles capables d'action sociale peuvent porter `eligible`.
ACTIVE_ROLES = frozenset({ActorRole.PERSON, ActorRole.ORGANIZATION})


class ActorEligibilityError(ValueError):
    """Erreur de construction d'une qualification incohérente."""


@dataclass
class ActorEligibility:
    """Qualification d'une entité du graphe.

    L'identité (UUID, nom, type d'origine, attributs) est toujours construite
    depuis l'entrée du graphe, jamais depuis une identité inventée par le LLM.
    """

    entity_uuid: str
    entity_name: str
    role: ActorRole
    status: EligibilityStatus
    rationale: str
    confidence: float
    original_type: str = "Entity"
    attributes: Dict[str, Any] = field(default_factory=dict)
    diagnostic: Optional[str] = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Refuse toute qualification incohérente ou non bornée."""

        if not isinstance(self.entity_uuid, str) or not self.entity_uuid.strip():
            raise ActorEligibilityError("entity_uuid doit être une chaîne non vide")
        if not isinstance(self.entity_name, str):
            raise ActorEligibilityError("entity_name doit être une chaîne")
        if not isinstance(self.role, ActorRole):
            raise ActorEligibilityError("role doit être un ActorRole")
        if not isinstance(self.status, EligibilityStatus):
            raise ActorEligibilityError("status doit être un EligibilityStatus")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ActorEligibilityError("rationale doit être une chaîne non vide")
        if isinstance(self.confidence, bool) or not isinstance(
            self.confidence, (int, float)
        ):
            raise ActorEligibilityError("confidence doit être un nombre")
        if not math.isfinite(float(self.confidence)):
            raise ActorEligibilityError("confidence doit être finie")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ActorEligibilityError("confidence doit être dans [0, 1]")
        if self.status == EligibilityStatus.ELIGIBLE and self.role not in ACTIVE_ROLES:
            raise ActorEligibilityError(
                "un rôle passif ne peut jamais porter le statut eligible"
            )

    @property
    def is_eligible(self) -> bool:
        return self.status == EligibilityStatus.ELIGIBLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_uuid": self.entity_uuid,
            "entity_name": self.entity_name,
            "role": self.role.value,
            "status": self.status.value,
            "rationale": self.rationale,
            "confidence": float(self.confidence),
            "original_type": self.original_type,
            "attributes": self.attributes,
            "diagnostic": self.diagnostic,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActorEligibility":
        return cls(
            entity_uuid=data["entity_uuid"],
            entity_name=data.get("entity_name", ""),
            role=ActorRole(data["role"]),
            status=EligibilityStatus(data["status"]),
            rationale=data["rationale"],
            confidence=data["confidence"],
            original_type=data.get("original_type", "Entity"),
            attributes=dict(data.get("attributes") or {}),
            diagnostic=data.get("diagnostic"),
        )


class ActorEligibilityResponse(BaseModel):
    """Réponse LLM structurée et validée de la passe 2.

    La validation couvre strictement `role`, `status`, `rationale` et
    `confidence`. Les champs supplémentaires sont ignorés et ne sont jamais
    utilisés comme consignes. Une chaîne ou un booléen est refusé comme
    confiance : la coercition silencieuse produirait une décision fausse.
    """

    model_config = ConfigDict(extra="ignore")

    role: ActorRole
    status: EligibilityStatus
    rationale: str
    confidence: float

    @field_validator("role", "status", mode="before")
    @classmethod
    def _strict_enum(cls, value: Any, info) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("rationale", mode="before")
    @classmethod
    def _rationale_required(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("rationale doit être une chaîne non vide")
        return value.strip()

    @field_validator("confidence", mode="before")
    @classmethod
    def _confidence_strict(cls, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("confidence doit être un nombre JSON")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("confidence doit être finie")
        if not 0.0 <= numeric <= 1.0:
            raise ValueError("confidence doit être dans [0, 1]")
        return numeric


def qualify_from_response(
    entity_uuid: str,
    entity_name: str,
    *,
    original_type: str,
    attributes: Dict[str, Any],
    response: ActorEligibilityResponse,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> ActorEligibility:
    """Construit une qualification sûre à partir d'une réponse validée.

    Une incohérence (rôle passif `eligible`, confiance insuffisante) dégrade en
    `review` avec un motif : on ne corrige jamais une sortie incohérente en
    `eligible`.
    """

    role = response.role
    status = response.status
    rationale = response.rationale
    diagnostic: Optional[str] = None

    if status == EligibilityStatus.ELIGIBLE and role not in ACTIVE_ROLES:
        status = EligibilityStatus.REVIEW
        diagnostic = "rôle passif déclaré eligible par le modèle : ramené en review"
    elif status != EligibilityStatus.REVIEW and response.confidence < confidence_threshold:
        status = EligibilityStatus.REVIEW
        diagnostic = (
            f"confiance {response.confidence:.3f} inférieure au seuil "
            f"{confidence_threshold:.2f} : ramené en review"
        )

    return ActorEligibility(
        entity_uuid=entity_uuid,
        entity_name=entity_name,
        role=role,
        status=status,
        rationale=rationale,
        confidence=response.confidence,
        original_type=original_type,
        attributes=dict(attributes),
        diagnostic=diagnostic,
    )
