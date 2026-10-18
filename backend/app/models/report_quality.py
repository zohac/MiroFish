"""Modèle structuré de contrôle qualité des rapports (Epic 011, FR-09, C9).

Définit :
  - QualityCategory : catégories d'inspection (intégrité structurelle, anti-troncature,
    conformité linguistique, section d'objections et limites, vérification des claims).
  - QualityStatus : verdict individuel (PASSED, WARNING, FAILED).
  - QualityCheckItem : item individuel d'évaluation avec titre, message et détails.
  - QualityGateResult : résultat global de la barrière ReportQualityGate, déterminant
    si le rapport est publiable (`is_publishable`) et persistant `quality_checks.json`.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class PublicationStatus(str, Enum):
    """Statut formel de certification pour publication d'un rapport (Epic 012, FR-05, C5).
    
    Distinction stricte de 4 états :
      - DRAFT : rapport en cours de génération ou non encore soumis à l'évaluation.
      - NEEDS_REVIEW : rapport consultable avec réserves explicites (synthèse théorique
        sans simulation d'actions, ou assertions d'actions partiellement prouvées entre 50% et 80%).
      - VERIFIED_PUBLISHABLE : rapport certifié publiable (>= 80% des assertions d'actions
        vérifiées dans l'EvidencePack, 0 contradiction critique, intégrité structurelle OK).
      - FAILED_VALIDATION : publication refusée (0 action vérifiée alors que des actions sont alléguées,
        ou contradiction d'action critique avérée, ou affabulation commerciale d'adoption non sourcée).
    """
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    VERIFIED_PUBLISHABLE = "verified_publishable"
    FAILED_VALIDATION = "failed_validation"


class QualityCategory(str, Enum):
    """Catégories d'inspection du ReportQualityGate."""
    STRUCTURAL_INTEGRITY = "structural_integrity"
    COMPLETION_GUARD = "completion_guard"
    LANGUAGE_COMPLIANCE = "language_compliance"
    LIMITATIONS_SECTION = "limitations_section"
    CLAIM_VERIFICATION = "claim_verification"


class QualityStatus(str, Enum):
    """Statut d'une vérification qualité individuelle ou globale."""
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


@dataclass
class QualityCheckItem:
    """Élément individuel d'inspection qualité."""
    category: QualityCategory
    title: str
    status: QualityStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "title": self.title,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> QualityCheckItem:
        if not isinstance(data, dict):
            raise ValueError("Données dictionnaire requises pour QualityCheckItem.from_dict")
        return cls(
            category=QualityCategory(data.get("category", QualityCategory.STRUCTURAL_INTEGRITY.value)),
            title=str(data.get("title", "")),
            status=QualityStatus(data.get("status", QualityStatus.PASSED.value)),
            message=str(data.get("message", "")),
            details=dict(data.get("details") or {}),
        )


@dataclass
class QualityGateResult:
    """Résultat consolidé de la barrière ReportQualityGate."""
    simulation_id: str
    report_id: str
    is_publishable: bool
    final_status: QualityStatus
    summary: str
    checks: List[QualityCheckItem] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    metadata: Dict[str, Any] = field(default_factory=dict)
    publication_status: PublicationStatus = PublicationStatus.DRAFT

    @property
    def total_checks(self) -> int:
        return len(self.checks)

    @property
    def passed_checks(self) -> int:
        return sum(1 for c in self.checks if c.status == QualityStatus.PASSED)

    @property
    def warning_checks(self) -> int:
        return sum(1 for c in self.checks if c.status == QualityStatus.WARNING)

    @property
    def failed_checks(self) -> int:
        return sum(1 for c in self.checks if c.status == QualityStatus.FAILED)

    def add_check(self, item: QualityCheckItem) -> None:
        self.checks.append(item)
        self._recompute_status()

    def _recompute_status(self) -> None:
        """Recalcule final_status, publication_status et is_publishable d'après les checks en mode Fail-Closed (Story 012-4)."""
        if not self.checks:
            self.final_status = QualityStatus.WARNING
            self.publication_status = PublicationStatus.DRAFT
            self.is_publishable = False
            return
        if any(c.status == QualityStatus.FAILED for c in self.checks):
            self.final_status = QualityStatus.FAILED
            self.publication_status = PublicationStatus.FAILED_VALIDATION
            self.is_publishable = False
        elif any(c.status == QualityStatus.WARNING for c in self.checks):
            self.final_status = QualityStatus.WARNING
            self.publication_status = PublicationStatus.NEEDS_REVIEW
            self.is_publishable = False
        else:
            self.final_status = QualityStatus.PASSED
            self.publication_status = PublicationStatus.VERIFIED_PUBLISHABLE
            self.is_publishable = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "report_id": self.report_id,
            "evaluated_at": self.evaluated_at,
            "is_publishable": self.is_publishable,
            "final_status": self.final_status.value,
            "publication_status": self.publication_status.value,
            "summary": self.summary,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "warning_checks": self.warning_checks,
            "failed_checks": self.failed_checks,
            "checks": [c.to_dict() for c in self.checks],
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save_to_file(self, target_path: str) -> None:
        """Sauvegarde atomique du résultat au format JSON."""
        target_dir = os.path.dirname(os.path.abspath(target_path))
        os.makedirs(target_dir, exist_ok=True)
        tmp_path = f"{target_path}.tmp.{os.getpid()}_{uuid.uuid4().hex[:8]}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        os.replace(tmp_path, target_path)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> QualityGateResult:
        if not isinstance(data, dict):
            raise ValueError("Données dictionnaire requises pour QualityGateResult.from_dict")
        checks_data = data.get("checks") or []
        checks = [QualityCheckItem.from_dict(c) for c in checks_data if isinstance(c, dict)]
        
        # Résolution rétrocompatible de publication_status
        raw_pub = data.get("publication_status")
        pub_status: Optional[PublicationStatus] = None
        if raw_pub:
            try:
                pub_status = PublicationStatus(str(raw_pub).strip())
            except (ValueError, KeyError):
                pub_status = None

        if pub_status is None:
            # Rétrocompatibilité sur anciens exports
            final_st = str(data.get("final_status", "")).lower()
            is_pub_raw = bool(data.get("is_publishable", False))
            if final_st == "failed":
                pub_status = PublicationStatus.FAILED_VALIDATION
            elif final_st == "warning":
                pub_status = PublicationStatus.NEEDS_REVIEW
            elif is_pub_raw and final_st == "passed":
                pub_status = PublicationStatus.VERIFIED_PUBLISHABLE
            else:
                pub_status = PublicationStatus.DRAFT

        # Garantie Fail-Closed : is_publishable ne peut valoir True QUE si verified_publishable
        enforced_is_publishable = bool(data.get("is_publishable", False)) and (
            pub_status == PublicationStatus.VERIFIED_PUBLISHABLE
        )

        return cls(
            simulation_id=str(data.get("simulation_id", "")),
            report_id=str(data.get("report_id", "")),
            is_publishable=enforced_is_publishable,
            final_status=QualityStatus(data.get("final_status", QualityStatus.FAILED.value)),
            summary=str(data.get("summary", "")),
            checks=checks,
            evaluated_at=str(data.get("evaluated_at", datetime.utcnow().isoformat() + "Z")),
            metadata=dict(data.get("metadata") or {}),
            publication_status=pub_status,
        )

    @classmethod
    def load_from_file(cls, file_path: str) -> QualityGateResult:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
