"""Gestionnaire et vérificateur de respect du temps simulé et des métriques quantitatives (Story 011-4).

Ce module implémente :
  - `TimeHorizonGuard` : analyseur et contrôleur du temps simulé (`SimulationBrief.time_horizon`),
    conversion déterministe round <-> heure simulée, et interdiction d'extrapolations hors horizon (Critère C8).
  - Détection et neutralisation des métriques quantitatives fantômes non adossées aux traces réelles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..models.evidence_pack import EvidencePack


@dataclass(frozen=True)
class TimeHorizonValidationResult:
    """Résultat de vérification d'une assertion temporelle."""

    valid: bool
    mentioned_hours: Optional[float]
    horizon_hours: float
    is_out_of_bounds: bool
    reason: Optional[str] = None


@dataclass(frozen=True)
class QuantitativeMetricDetectionResult:
    """Résultat de l'analyse d'une assertion quantitative."""

    has_unsupported_metrics: bool
    detected_metrics: List[str] = field(default_factory=list)
    reason: Optional[str] = None


class TimeHorizonGuard:
    """Garde-fou temporel garantissant le respect strict de l'horizon de simulation (Story 011-4, FR-08, C8)."""

    # Motifs regex pour parser l'horizon temporel exprimé en texte naturel
    _HOURS_REGEX = re.compile(r"(\d+(?:[.,]\d+)?)\s*[- ]?\s*(?:h(?:eures?)?|hours?)\b", re.IGNORECASE)
    _DAYS_REGEX = re.compile(r"(\d+(?:[.,]\d+)?)\s*[- ]?\s*(?:j(?:ours?)?|days?)\b", re.IGNORECASE)
    _WEEKS_REGEX = re.compile(r"(\d+(?:[.,]\d+)?)\s*[- ]?\s*(?:semaines?|weeks?)\b", re.IGNORECASE)
    _MONTHS_REGEX = re.compile(r"(\d+(?:[.,]\d+)?)\s*[- ]?\s*(?:mois|months?)\b", re.IGNORECASE)

    # Motifs regex pour détecter les mentions temporelles absolues ou relatives dans un texte
    _TIME_MENTION_HOURS = re.compile(r"\b(?:à|at|après|after|pendant|during)?\s*(\d+(?:[.,]\d+)?)\s*[- ]?\s*(?:h|heures?|hours?)\b", re.IGNORECASE)
    _TIME_MENTION_DAYS = re.compile(r"\b(?:j\+|day\s*|jour\s*)(\d+(?:[.,]\d+)?)\b", re.IGNORECASE)
    _TIME_MENTION_LONG = re.compile(r"\b(\d+)\s*[- ]?\s*(?:jours?|days?|semaines?|weeks?|mois|months?|ans?|années?|years?)\b", re.IGNORECASE)

    # Motifs pour métriques quantitatives péremptoires (taux de conversion/churn/saturation sans base de calcul)
    _GHOST_METRIC_PATTERNS = [
        re.compile(r"\b(?:churn\s*(?:à|a|de|at|after|of)?\s*\d+\s*(?:jours?|mois|semaines?|days?|months?|weeks?)|\d+\s*[- ]?(?:jours?|mois|semaines?|days?|months?|weeks?)\s*churn)\b", re.IGNORECASE),
        re.compile(r"\b(?:taux\s*de\s*(?:churn|résiliation|saturation|conversion)|(?:churn|attrition|retention|saturation|conversion)\s*rate)\s*(?:de|of)?\s*\d+(?:[.,]\d+)?\s*%", re.IGNORECASE),
        re.compile(r"\bsaturation\s*(?:de|rate\s*of)?\s*\d+(?:[.,]\d+)?\s*%", re.IGNORECASE),
        re.compile(r"\b(?:coût\s*(?:d'acquisition|onboarding)?\s*mathématiquement\s*insoutenable|mathematically\s*unsustainable\s*(?:acquisition|onboarding)?\s*costs?)\b", re.IGNORECASE),
        re.compile(r"\b(?:conversion|adhésion|adoption)\s*(?:totale|unanime|de\s*100\s*%)\b", re.IGNORECASE),
        re.compile(r"\b(?:total|100%|unanimous)\s*(?:conversion|adoption)\b", re.IGNORECASE),
    ]

    @classmethod
    def parse_horizon_hours(cls, time_horizon_str: Optional[str], default_hours: float = 72.0) -> float:
        """Parse une chaîne d'horizon temporel et retourne la durée en heures réelles."""
        if not time_horizon_str or not isinstance(time_horizon_str, str):
            return default_hours

        text = time_horizon_str.strip().lower()
        if not text:
            return default_hours

        # 1. Heures directes
        m_h = cls._HOURS_REGEX.search(text)
        if m_h:
            val = float(m_h.group(1).replace(",", "."))
            return max(val, 1.0)

        # 2. Jours
        m_d = cls._DAYS_REGEX.search(text)
        if m_d:
            val = float(m_d.group(1).replace(",", "."))
            return max(val * 24.0, 1.0)

        # 3. Semaines
        m_w = cls._WEEKS_REGEX.search(text)
        if m_w:
            val = float(m_w.group(1).replace(",", "."))
            return max(val * 168.0, 1.0)

        # 4. Mois (base 30 jours)
        m_m = cls._MONTHS_REGEX.search(text)
        if m_m:
            val = float(m_m.group(1).replace(",", "."))
            return max(val * 720.0, 1.0)

        # 5. Entier brut supposé en heures
        digits = re.findall(r"\d+", text)
        if digits:
            return max(float(digits[0]), 1.0)

        return default_hours

    @classmethod
    def round_to_simulated_hour(
        cls,
        round_num: int,
        total_rounds: int,
        horizon_hours: float,
    ) -> float:
        """Calcule l'heure simulée correspondante à un numéro de round."""
        if total_rounds <= 0:
            return 0.0
        clamped_round = max(0, round_num)
        ratio = clamped_round / total_rounds
        return round(ratio * horizon_hours, 2)

    @classmethod
    def extract_time_mentions_in_hours(cls, text: str) -> List[float]:
        """Extrait toutes les mentions d'heures ou jours converties en heures absolues."""
        if not text or not isinstance(text, str):
            return []

        hours_found: List[float] = []

        # Heures : 48h, 72 heures, etc.
        for m in cls._TIME_MENTION_HOURS.finditer(text):
            try:
                val = float(m.group(1).replace(",", "."))
                hours_found.append(val)
            except ValueError:
                pass

        # Jours : J+2, jour 3
        for m in cls._TIME_MENTION_DAYS.finditer(text):
            try:
                val = float(m.group(1).replace(",", "."))
                hours_found.append(val * 24.0)
            except ValueError:
                pass

        # Long terme : 90 jours, 3 mois, etc.
        for m in cls._TIME_MENTION_LONG.finditer(text):
            try:
                num = float(m.group(1).replace(",", "."))
                matched_str = m.group(0).lower()
                if "jour" in matched_str or "day" in matched_str:
                    hours_found.append(num * 24.0)
                elif "semaine" in matched_str or "week" in matched_str:
                    hours_found.append(num * 168.0)
                elif "mois" in matched_str or "month" in matched_str:
                    hours_found.append(num * 720.0)
                elif "an" in matched_str or "year" in matched_str:
                    hours_found.append(num * 8760.0)
            except ValueError:
                pass

        return hours_found

    @classmethod
    def validate_claim_time_horizon(
        cls,
        claim_text: str,
        horizon_hours: float,
        round_num: Optional[int] = None,
        total_rounds: int = 40,
    ) -> TimeHorizonValidationResult:
        """Vérifie si une affirmation respecte l'horizon temporel de la simulation."""
        if horizon_hours <= 0:
            horizon_hours = 72.0

        mentions = cls.extract_time_mentions_in_hours(claim_text)
        max_mention = max(mentions) if mentions else None

        if max_mention is not None and max_mention > horizon_hours:
            return TimeHorizonValidationResult(
                valid=False,
                mentioned_hours=max_mention,
                horizon_hours=horizon_hours,
                is_out_of_bounds=True,
                reason=(
                    f"Affirmation hors horizon temporel : mention de {max_mention:.1f}h "
                    f"alors que le temps simulé maximal est fixé à {horizon_hours:.1f}h."
                ),
            )

        # Vérification optionnelle sur le round
        if round_num is not None and total_rounds > 0:
            simulated_h = cls.round_to_simulated_hour(round_num, total_rounds, horizon_hours)
            if simulated_h > horizon_hours:
                return TimeHorizonValidationResult(
                    valid=False,
                    mentioned_hours=simulated_h,
                    horizon_hours=horizon_hours,
                    is_out_of_bounds=True,
                    reason=f"Round {round_num} dépasse l'horizon temporel simulé de {horizon_hours:.1f}h.",
                )

        return TimeHorizonValidationResult(
            valid=True,
            mentioned_hours=max_mention,
            horizon_hours=horizon_hours,
            is_out_of_bounds=False,
            reason=None,
        )

    @classmethod
    def detect_unsupported_quantitative_metrics(
        cls,
        text: str,
        evidence_pack: Optional[EvidencePack] = None,
    ) -> QuantitativeMetricDetectionResult:
        """Détecte les métriques quantitatives péremptoires non calculables dans le run (Critère C8)."""
        if not text or not isinstance(text, str):
            return QuantitativeMetricDetectionResult(has_unsupported_metrics=False)

        detected: List[str] = []
        for pattern in cls._GHOST_METRIC_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                for match in matches:
                    if isinstance(match, str):
                        detected.append(match)
                    elif isinstance(match, tuple):
                        detected.append(" ".join(match))

        if detected:
            return QuantitativeMetricDetectionResult(
                has_unsupported_metrics=True,
                detected_metrics=detected,
                reason=(
                    f"Présence de métriques quantitatives ou jugements péremptoires non prouvés : "
                    f"{', '.join(detected)}. Requalification requise en ANALYST_INFERENCE ou SPECULATIVE_PROJECTION."
                ),
            )

        return QuantitativeMetricDetectionResult(has_unsupported_metrics=False)
