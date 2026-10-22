"""Modèle de données pour les affirmations du rapport (ReportClaim) et registre d'audit (Story 011-3).

Ce module implémente :
  - `ClaimKind` : typologie sémantique stricte d'une affirmation de rapport (FR-03).
  - `VerificationStatus` : statut de vérification déterministe serveur (VERIFIED, UNSUPPORTED, CONTRADICTED).
  - `ReportClaim` : assertion immuable dotée d'un identifiant stable, d'un typage épistémique et de preuves.
  - `ReportClaimRegistry` : registre conteneur calculant les statistiques d'audit et assurant la sérialisation `report_claims.json`.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .provenance_regime import ProvenanceRegime
from .source_document import InformationOrigin


class ClaimKind(str, Enum):
    """Typologie stricte d'une affirmation de rapport (Story 011-3, FR-03).
    
    Catégories :
      - SOURCE_FACT : fait issu directement des documents sources historiques ou canoniques.
      - SCENARIO_HYPOTHESIS : paramètre, contrainte ou consigne de scénario issue du brief.
      - OBSERVED_SOCIAL_ACTION : action concrète et exécutée constatée dans les traces de la simulation.
      - REPORTED_INTENTION : déclaration verbale d'intention sans preuve d'exécution d'action.
      - ANALYST_INFERENCE : déduction logique ou interprétation analytique de l'agent de rapport.
      - SPECULATIVE_PROJECTION : projection prospective au-delà des faits observés.
    """

    SOURCE_FACT = "SOURCE_FACT"
    SCENARIO_HYPOTHESIS = "SCENARIO_HYPOTHESIS"
    OBSERVED_SOCIAL_ACTION = "OBSERVED_SOCIAL_ACTION"
    REPORTED_INTENTION = "REPORTED_INTENTION"
    ANALYST_INFERENCE = "ANALYST_INFERENCE"
    SPECULATIVE_PROJECTION = "SPECULATIVE_PROJECTION"

    @classmethod
    def from_str(cls, value: Optional[str]) -> "ClaimKind":
        """Convertit une chaîne en ClaimKind de manière robuste."""
        if not value or not isinstance(value, str):
            return cls.ANALYST_INFERENCE
        val = value.strip().upper()
        for member in cls:
            if member.value == val or member.name == val:
                return member
        # Synonymes et replis
        if "OBSERVED" in val or "ACTION" in val:
            return cls.OBSERVED_SOCIAL_ACTION
        if "INTENT" in val:
            return cls.REPORTED_INTENTION
        if "SOURCE" in val or "FACT" in val or "DOC" in val:
            return cls.SOURCE_FACT
        if "HYPOTHESIS" in val or "SCENARIO" in val:
            return cls.SCENARIO_HYPOTHESIS
        if "PROJECTION" in val or "SPECULAT" in val:
            return cls.SPECULATIVE_PROJECTION
        return cls.ANALYST_INFERENCE


class VerificationStatus(str, Enum):
    """Statut de vérification serveur d'une affirmation."""

    VERIFIED = "VERIFIED"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTED = "CONTRADICTED"

    @classmethod
    def from_str(cls, value: Optional[str]) -> "VerificationStatus":
        if not value or not isinstance(value, str):
            return cls.UNSUPPORTED
        val = value.strip().upper()
        for member in cls:
            if member.value == val or member.name == val:
                return member
        return cls.UNSUPPORTED


def compute_claim_id(
    text: str,
    claim_kind: Any,
    agent_name: Optional[str] = None,
    round_num: Optional[int] = None,
) -> str:
    """Calcule un identifiant stable et déterministe pour une affirmation : clm_<sha256_8>."""
    kind_str = claim_kind.value if isinstance(claim_kind, ClaimKind) else str(claim_kind)
    seed = f"{text.strip().lower()}|{kind_str}|{str(agent_name or '').lower()}|{round_num}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    return f"clm_{digest}"


@dataclass(frozen=True)
class ReportClaim:
    """Assertion individuelle formulée dans le rapport analytique (AC1).
    
    Immuable, typée et reliée à des références probatoires.
    """

    claim_id: str
    text: str
    claim_kind: ClaimKind
    origin: InformationOrigin
    evidence_refs: List[str] = field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.UNSUPPORTED
    agent_name: Optional[str] = None
    round_num: Optional[int] = None
    confidence: float = 1.0
    limitations: List[str] = field(default_factory=list)
    provenance_regime: Optional[ProvenanceRegime] = None

    def __post_init__(self) -> None:
        if not self.text or not str(self.text).strip():
            raise ValueError("Le texte de l'affirmation ne peut être vide")

        if not isinstance(self.claim_kind, ClaimKind):
            object.__setattr__(self, "claim_kind", ClaimKind.from_str(str(self.claim_kind)))

        if not isinstance(self.origin, InformationOrigin):
            object.__setattr__(self, "origin", InformationOrigin.from_str(str(self.origin)))

        if not isinstance(self.verification_status, VerificationStatus):
            object.__setattr__(
                self,
                "verification_status",
                VerificationStatus.from_str(str(self.verification_status)),
            )

        if not self.claim_id:
            object.__setattr__(
                self,
                "claim_id",
                compute_claim_id(self.text, self.claim_kind, self.agent_name, self.round_num),
            )

        if not isinstance(self.evidence_refs, list):
            object.__setattr__(self, "evidence_refs", list(self.evidence_refs or []))

        if not isinstance(self.limitations, list):
            object.__setattr__(self, "limitations", list(self.limitations or []))

        # Régime de provenance (Story 014-1) : champ optionnel, rétrocompatible.
        if self.provenance_regime is not None and not isinstance(self.provenance_regime, ProvenanceRegime):
            object.__setattr__(
                self, "provenance_regime", ProvenanceRegime.from_str(self.provenance_regime)
            )
        confidence_val = float(self.confidence) if self.confidence is not None else 1.0
        confidence_val = max(0.0, min(1.0, confidence_val))
        object.__setattr__(self, "confidence", confidence_val)

    def to_dict(self) -> Dict[str, Any]:
        """Sérialisation structurée en dictionnaire."""
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "claim_kind": self.claim_kind.value,
            "origin": self.origin.value,
            "evidence_refs": list(self.evidence_refs),
            "verification_status": self.verification_status.value,
            "agent_name": self.agent_name,
            "round_num": self.round_num,
            "confidence": self.confidence,
            "limitations": list(self.limitations),
            "provenance_regime": (
                self.provenance_regime.value if self.provenance_regime is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportClaim":
        """Désérialisation depuis un dictionnaire."""
        if not isinstance(data, dict):
            raise ValueError("Données dictionnaire requises pour ReportClaim.from_dict")

        return cls(
            claim_id=str(data.get("claim_id") or ""),
            text=str(data.get("text", "")),
            claim_kind=ClaimKind.from_str(data.get("claim_kind")),
            origin=InformationOrigin.from_str(data.get("origin")),
            evidence_refs=list(data.get("evidence_refs") or []),
            verification_status=VerificationStatus.from_str(data.get("verification_status")),
            agent_name=data.get("agent_name"),
            round_num=data.get("round_num"),
            confidence=float(data.get("confidence", 1.0)),
            limitations=list(data.get("limitations") or []),
            provenance_regime=data.get("provenance_regime"),
        )


@dataclass
class ReportClaimRegistry:
    """Registre des affirmations du rapport avec statistiques d'intégrité (AC1, AC6)."""

    simulation_id: str
    claims: List[ReportClaim] = field(default_factory=list)

    @property
    def total_claims(self) -> int:
        return len(self.claims)

    @property
    def verified_claims(self) -> int:
        return sum(1 for c in self.claims if c.verification_status == VerificationStatus.VERIFIED)

    @property
    def unsupported_claims(self) -> int:
        return sum(1 for c in self.claims if c.verification_status == VerificationStatus.UNSUPPORTED)

    @property
    def contradicted_claims(self) -> int:
        return sum(1 for c in self.claims if c.verification_status == VerificationStatus.CONTRADICTED)

    @property
    def verification_ratio(self) -> float:
        if not self.claims:
            return 1.0
        return round(self.verified_claims / len(self.claims), 4)

    def add_claim(self, claim: ReportClaim) -> None:
        """Ajoute une affirmation au registre en évitant les doublons stricts par claim_id."""
        for idx, existing in enumerate(self.claims):
            if existing.claim_id == claim.claim_id:
                self.claims[idx] = claim
                return
        self.claims.append(claim)

    def get_claim(self, claim_id: str) -> Optional[ReportClaim]:
        for c in self.claims:
            if c.claim_id == claim_id:
                return c
        return None

    def filter_by_kind(self, claim_kind: ClaimKind) -> List[ReportClaim]:
        return [c for c in self.claims if c.claim_kind == claim_kind]

    def filter_by_status(self, status: VerificationStatus) -> List[ReportClaim]:
        return [c for c in self.claims if c.verification_status == status]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "total_claims": self.total_claims,
            "verified_claims": self.verified_claims,
            "unsupported_claims": self.unsupported_claims,
            "contradicted_claims": self.contradicted_claims,
            "verification_ratio": self.verification_ratio,
            "claims": [c.to_dict() for c in self.claims],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save_to_file(self, target_path: str) -> None:
        """Sauvegarde atomique du registre au format JSON."""
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        tmp_path = f"{target_path}.tmp.{os.getpid()}_{uuid.uuid4().hex[:8]}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        os.replace(tmp_path, target_path)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportClaimRegistry":
        if not isinstance(data, dict):
            raise ValueError("Données dictionnaire requises pour ReportClaimRegistry.from_dict")
        sim_id = str(data.get("simulation_id", ""))
        claims_data = data.get("claims") or []
        claims = [ReportClaim.from_dict(c) for c in claims_data if isinstance(c, dict)]
        return cls(simulation_id=sim_id, claims=claims)

    @classmethod
    def load_from_file(cls, file_path: str) -> "ReportClaimRegistry":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
