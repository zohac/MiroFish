"""Traqueur de télémétrie d'usage et garde-fous budgétaires/temporels (Story 013-4).

Ce service capture, pour chaque appel LLM du ``ReportAgent``, les tokens
consommés (prompt, complétion, réflexion), la durée d'inférence et le coût
estimé. Il agrège ensuite les mesures par phase (``planning``, ``sections``,
``claims_reconciliation``, ``interviews``) et par job de rapport.

Deux garanties structurent ce module :
  - **Honnêteté (AT-12)** : un appel sans objet ``usage`` fournisseur est marqué
    ``usage_available = False`` ; aucun coût n'est inventé.
  - **Fail-Safe (AT-11)** : les plafonds ``max_total_cost_usd`` et
    ``max_wall_seconds`` interrompent la génération avant toute requête
    additionnelle. Aucune escalade automatique vers un autre modèle n'est
    possible ici : le garde-fou lève une exception, il ne change jamais de
    configuration.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..models.report_usage import (
    CallUsageRecord,
    PricingTable,
    ReportUsageMetrics,
)
from ..utils.logger import get_logger

logger = get_logger("mirofish.report_usage")

KNOWN_PHASES = ("planning", "sections", "claims_reconciliation", "interviews")


class ReportBudgetExceededError(RuntimeError):
    """Plafond budgétaire atteint : aucune requête LLM supplémentaire n'est permise."""

    def __init__(
        self,
        message: str,
        *,
        estimated_cost_usd: Optional[float] = None,
        max_total_cost_usd: Optional[float] = None,
        phase: Optional[str] = None,
    ):
        super().__init__(message)
        self.estimated_cost_usd = estimated_cost_usd
        self.max_total_cost_usd = max_total_cost_usd
        self.phase = phase


class ReportTimeoutError(RuntimeError):
    """Durée maximale de génération dépassée : arrêt contrôlé du job."""

    def __init__(
        self,
        message: str,
        *,
        elapsed_seconds: Optional[float] = None,
        max_wall_seconds: Optional[float] = None,
        phase: Optional[str] = None,
    ):
        super().__init__(message)
        self.elapsed_seconds = elapsed_seconds
        self.max_wall_seconds = max_wall_seconds
        self.phase = phase


def _usage_field(usage: Any, name: str) -> Any:
    """Lit un champ d'usage sur un objet SDK ou un dictionnaire, sans lever."""
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage.get(name)
    return getattr(usage, name, None)


def _safe_str(value: Any) -> Optional[str]:
    """Retourne une chaîne réelle, sinon ``None`` (protège des mocks/exotiques)."""
    if isinstance(value, str):
        return value
    return None


def _safe_float(value: Any) -> Optional[float]:
    """Retourne un nombre réel fini, sinon ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if result != result or result in (float("inf"), float("-inf")):
        return None
    return result


def infer_provider_id(
    profile: Optional[Any],
    explicit_provider_id: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Optional[str]:
    """Résout le fournisseur, en reconnaissant les passerelles locales.

    Ne conserve jamais l'URL elle-même : seul un identifiant de passerelle
    (``antigravity-local``, ``codex-local``) est dérivé des ports connus.
    """
    candidate = str(
        _safe_str(explicit_provider_id)
        or _safe_str(getattr(profile, "provider_id", None))
        or ""
    ).strip()
    if candidate and candidate.lower() not in {"custom", "env", "unknown"}:
        return candidate
    resolved_url = (
        _safe_str(base_url)
        or _safe_str(getattr(profile, "base_url", None))
        or ""
    )
    if "18081" in resolved_url:
        return "antigravity-local"
    if "18080" in resolved_url:
        return "codex-local"
    return candidate or None


def extract_usage_counts(usage: Any) -> Dict[str, Any]:
    """Extrait défensivement tokens et disponibilité d'un objet ``usage``.

    Retourne un dictionnaire avec ``usage_available``, ``prompt_tokens``,
    ``completion_tokens``, ``thinking_tokens`` et ``total_tokens``. Aucune
    exception n'est levée pour un objet partiel ou absent (AT-12).
    """
    if usage is None:
        return {
            "usage_available": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "thinking_tokens": 0,
            "total_tokens": 0,
        }

    def _to_int(value: Any) -> int:
        try:
            if value is None or isinstance(value, bool):
                return 0
            return max(0, int(value))
        except (TypeError, ValueError, OverflowError):
            return 0

    raw_prompt = _usage_field(usage, "prompt_tokens")
    raw_completion = _usage_field(usage, "completion_tokens")
    raw_total = _usage_field(usage, "total_tokens")
    usage_available = any(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in (raw_prompt, raw_completion, raw_total)
    )
    if not usage_available:
        return {
            "usage_available": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "thinking_tokens": 0,
            "total_tokens": 0,
        }

    prompt = _to_int(raw_prompt)
    completion = _to_int(raw_completion)
    total = _to_int(raw_total)

    thinking = 0
    details = _usage_field(usage, "completion_tokens_details")
    if details is not None:
        thinking = _to_int(_usage_field(details, "reasoning_tokens"))
    if thinking == 0:
        thinking = _to_int(_usage_field(usage, "reasoning_tokens"))
    if thinking == 0:
        details = _usage_field(usage, "output_tokens_details")
        if details is not None:
            thinking = _to_int(_usage_field(details, "reasoning_tokens"))

    if total == 0:
        total = prompt + completion

    return {
        "usage_available": True,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "thinking_tokens": thinking,
        "total_tokens": total,
    }


class ReportUsageTracker:
    """Capture et agrège l'usage LLM d'une génération de rapport."""

    def __init__(
        self,
        report_id: str = "",
        *,
        simulation_id: Optional[str] = None,
        profile: Optional[Any] = None,
        model: Optional[str] = None,
        provider_id: Optional[str] = None,
        base_url: Optional[str] = None,
        pricing_table: Optional[PricingTable] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.report_id = str(report_id or "")
        self.simulation_id = simulation_id
        self.profile = profile
        self.model = _safe_str(model) or _safe_str(getattr(profile, "model", None)) or ""
        self.provider_id = infer_provider_id(profile, provider_id, base_url)
        self._billing_mode = (
            _safe_str(getattr(profile, "billing_mode", None)) or "auto"
        )
        self.pricing_table = pricing_table or PricingTable()
        self._clock = clock
        self._start_monotonic = float(clock())
        self._started_at: Optional[str] = datetime.utcnow().isoformat() + "Z"
        self._completed_at: Optional[str] = None
        self._current_phase = "other"
        self._calls: List[CallUsageRecord] = []
        self._phase_totals: Dict[str, Dict[str, int]] = {}
        self._reasoning_effort_effective: Optional[str] = "unknown"
        self._budget_exceeded = False
        self._timeout_exceeded = False
        self._stop_reason: Optional[str] = None
        self._unpriced_model_calls = 0
        self._previous_callback: Optional[Callable[..., Any]] = None
        # Référence stable : un *bound method* est recréé à chaque accès, donc
        # toute comparaison par identité doit porter sur cette valeur.
        self._bound_callback = self.handle_llm_usage

    # ──────────────────────────────────────────────────────────────────
    # Cycle de vie
    # ──────────────────────────────────────────────────────────────────

    def begin(self, report_id: str, simulation_id: Optional[str] = None) -> None:
        """Démarre une nouvelle mesure pour un job de rapport."""
        self.report_id = str(report_id or "")
        if simulation_id is not None:
            self.simulation_id = simulation_id
        self._start_monotonic = float(self._clock())
        self._started_at = datetime.utcnow().isoformat() + "Z"
        self._completed_at = None
        self._current_phase = "planning"
        self._calls = []
        self._phase_totals = {}
        self._budget_exceeded = False
        self._timeout_exceeded = False
        self._stop_reason = None
        self._unpriced_model_calls = 0
        self._reasoning_effort_effective = "unknown"

    def set_phase(self, phase: str) -> None:
        """Fixe la phase courante utilisée pour attribuer les appels suivants."""
        normalized = str(phase or "").strip().lower()
        self._current_phase = normalized if normalized in KNOWN_PHASES else "other"

    @property
    def current_phase(self) -> str:
        return self._current_phase

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, float(self._clock()) - self._start_monotonic)

    def mark_reasoning_effort_effective(self, effort: Optional[str]) -> None:
        """Enregistre un effort réellement confirmé par le fournisseur.

        À défaut, la valeur reste ``"unknown"`` : le benchmark ne prétend jamais
        qu'un effort a été appliqué quand le fournisseur ne le confirme pas
        (AT-03).
        """
        value = str(effort or "").strip().lower()
        self._reasoning_effort_effective = value if value else "unknown"

    def mark_stop(
        self,
        reason: str,
        *,
        budget_exceeded: bool = False,
        timeout_exceeded: bool = False,
    ) -> None:
        """Consigne le motif d'arrêt contrôlé du job."""
        self._stop_reason = str(reason or "stopped")
        self._budget_exceeded = self._budget_exceeded or budget_exceeded
        self._timeout_exceeded = self._timeout_exceeded or timeout_exceeded

    # ──────────────────────────────────────────────────────────────────
    # Capture
    # ──────────────────────────────────────────────────────────────────

    def record_call(
        self,
        *,
        usage: Any = None,
        model: Optional[str] = None,
        provider_id: Optional[str] = None,
        duration_seconds: float = 0.0,
        phase: Optional[str] = None,
        reasoning_effort_requested: Optional[str] = None,
        reasoning_effort_effective: Optional[str] = None,
    ) -> CallUsageRecord:
        """Enregistre un appel LLM et met à jour les cumuls du job."""
        counts = extract_usage_counts(usage)
        resolved_model = str(model or self.model or "")
        resolved_provider = provider_id or self.provider_id
        requested_effort = (
            _safe_str(reasoning_effort_requested)
            if reasoning_effort_requested is not None
            else _safe_str(getattr(self.profile, "reasoning_effort", None))
        )
        if reasoning_effort_effective is not None:
            effective = str(reasoning_effort_effective).strip().lower() or "unknown"
        elif requested_effort and counts["usage_available"] and resolved_provider == "antigravity-local":
            # L'effort n'est déclaré effectif qu'avec une preuve par réponse :
            # la passerelle locale traduit l'effort en thinkingConfig (013-1),
            # mais AC3 interdit de l'affirmer sans objet `usage`.
            effective = str(requested_effort).strip().lower()
            self._reasoning_effort_effective = effective
        else:
            effective = "unknown"

        pricing = self.pricing_table.get_pricing(resolved_model)
        provider_free = self.pricing_table.is_free_provider(resolved_provider)
        model_free = self.pricing_table.is_free_model(resolved_model)
        known_billable = pricing is not None and not provider_free and not model_free
        # « free » déclaratif n'est honoré que si la grille ne prouve pas le
        # contraire : un client ne peut pas annuler le coût d'un modèle tarifé.
        free_granted = self._billing_mode == "free" and not known_billable

        if self._billing_mode == "metered" and not provider_free:
            cost = self.pricing_table.theoretical_cost(
                resolved_model,
                prompt_tokens=counts["prompt_tokens"],
                completion_tokens=counts["completion_tokens"],
                thinking_tokens=counts["thinking_tokens"],
            )
        else:
            cost = self.pricing_table.calculate_cost(
                resolved_model,
                prompt_tokens=counts["prompt_tokens"],
                completion_tokens=counts["completion_tokens"],
                thinking_tokens=counts["thinking_tokens"],
                provider_id=resolved_provider,
            )
        if free_granted:
            cost = 0.0
        if not counts["usage_available"]:
            cost = None

        if pricing is None and not provider_free and not model_free and not free_granted:
            self._unpriced_model_calls += 1

        record = CallUsageRecord(
            call_index=len(self._calls) + 1,
            phase=phase or self._current_phase,
            model=resolved_model,
            provider_id=resolved_provider,
            reasoning_effort_requested=requested_effort,
            reasoning_effort_effective=effective,
            prompt_tokens=counts["prompt_tokens"],
            completion_tokens=counts["completion_tokens"],
            thinking_tokens=counts["thinking_tokens"],
            total_tokens=counts["total_tokens"],
            duration_seconds=max(0.0, float(duration_seconds or 0.0)),
            estimated_cost_usd=cost,
            usage_available=bool(counts["usage_available"]),
        )
        self._calls.append(record)

        phase_key = record.phase or "other"
        totals = self._phase_totals.setdefault(
            phase_key,
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "thinking_tokens": 0,
                "total_tokens": 0,
                "calls_count": 0,
            },
        )
        totals["prompt_tokens"] += record.prompt_tokens
        totals["completion_tokens"] += record.completion_tokens
        totals["thinking_tokens"] += record.thinking_tokens
        totals["total_tokens"] += record.total_tokens
        totals["calls_count"] += 1

        if pricing is None and not provider_free and not model_free and not free_granted:
            logger.warning(
                "Modèle sans grille tarifaire connue (%s) : coût laissé inconnu",
                resolved_model,
            )
        return record

    def handle_llm_usage(
        self,
        *,
        usage: Any = None,
        model: Optional[str] = None,
        duration_seconds: float = 0.0,
        reasoning_effort: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[CallUsageRecord]:
        """Callback branché sur ``LLMClient.usage_callback``.

        Ne lève jamais : une défaillance de télémétrie ne doit pas casser la
        génération du rapport. Les erreurs sont journalisées. Un callback
        précédent éventuel est réémis après enregistrement.
        """
        record: Optional[CallUsageRecord] = None
        try:
            record = self.record_call(
                usage=usage,
                model=model,
                duration_seconds=duration_seconds,
                reasoning_effort_requested=reasoning_effort,
            )
        except Exception as error:  # pragma: no cover - barrière défensive
            logger.warning("Échec non bloquant de la télémétrie d'usage : %s", error)
        if self._previous_callback is not None:
            try:
                self._previous_callback(
                    usage=usage,
                    model=model,
                    duration_seconds=duration_seconds,
                    reasoning_effort=reasoning_effort,
                    **kwargs,
                )
            except Exception as error:  # pragma: no cover - callback tiers
                logger.warning("Échec du callback de télémétrie précédent : %s", error)
        return record

    def attach_to(self, llm_client: Any) -> None:
        """Branche le traqueur sur un client LLM en chaînant un callback existant."""
        if llm_client is None:
            return
        try:
            previous = getattr(llm_client, "usage_callback", None)
            if callable(previous) and previous is not self._bound_callback:
                self._previous_callback = previous
            llm_client.usage_callback = self._bound_callback
        except Exception as error:  # pragma: no cover - client exotique
            logger.warning("Impossible de brancher la télémétrie sur le client LLM : %s", error)

    def detach(self, llm_client: Any) -> None:
        """Restaure le callback précédent à la fin du job (client partagé)."""
        if llm_client is None:
            return
        try:
            if getattr(llm_client, "usage_callback", None) is self._bound_callback:
                llm_client.usage_callback = self._previous_callback
        except Exception:  # pragma: no cover - client exotique
            pass

    # ──────────────────────────────────────────────────────────────────
    # Agrégats
    # ──────────────────────────────────────────────────────────────────

    @property
    def calls(self) -> List[CallUsageRecord]:
        return list(self._calls)

    @property
    def calls_count(self) -> int:
        return len(self._calls)

    @property
    def total_tokens(self) -> int:
        return sum(call.total_tokens for call in self._calls)

    @property
    def prompt_tokens(self) -> int:
        return sum(call.prompt_tokens for call in self._calls)

    @property
    def completion_tokens(self) -> int:
        return sum(call.completion_tokens for call in self._calls)

    @property
    def thinking_tokens(self) -> int:
        return sum(call.thinking_tokens for call in self._calls)

    @property
    def known_cost_usd(self) -> float:
        """Somme des coûts connus (les appels non tarifés ne comptent pas zéro)."""
        return round(
            sum(
                float(call.estimated_cost_usd)
                for call in self._calls
                if call.estimated_cost_usd is not None
            ),
            8,
        )

    @property
    def last_cost_usd(self) -> float:
        """Coût du dernier appel tarifé, utilisé pour projeter le suivant."""
        for call in reversed(self._calls):
            if call.estimated_cost_usd is not None:
                return float(call.estimated_cost_usd)
        return 0.0

    @property
    def unpriced_model_calls(self) -> int:
        """Nombre d'appels dont le modèle n'a aucune grille tarifaire connue."""
        return self._unpriced_model_calls

    @property
    def all_calls_priced(self) -> bool:
        return all(call.estimated_cost_usd is not None for call in self._calls)

    @property
    def all_usage_available(self) -> bool:
        return all(call.usage_available for call in self._calls)

    @property
    def average_cost_per_call(self) -> float:
        priced = [
            float(call.estimated_cost_usd)
            for call in self._calls
            if call.estimated_cost_usd is not None
        ]
        if not priced:
            return 0.0
        return round(sum(priced) / len(priced), 8)

    def build_metrics(self) -> ReportUsageMetrics:
        """Construit l'agrégat persistable du job de rapport."""
        self._completed_at = datetime.utcnow().isoformat() + "Z"
        all_priced = self.all_calls_priced and bool(self._calls)
        all_usage = self.all_usage_available and bool(self._calls)
        known_cost = self.known_cost_usd
        theoretical_cost = None
        if all_priced:
            theoretical_cost = round(known_cost, 8)
            needs_theoretical = (
                self.pricing_table.is_free_provider(self.provider_id)
                or self._billing_mode in {"free", "metered"}
            )
            if needs_theoretical:
                per_call = [
                    self.pricing_table.theoretical_cost(
                        call.model,
                        prompt_tokens=call.prompt_tokens,
                        completion_tokens=call.completion_tokens,
                        thinking_tokens=call.thinking_tokens,
                    )
                    for call in self._calls
                ]
                # Aucun coût théorique n'est inventé : un modèle hors grille
                # laisse la valeur inconnue plutôt que de publier 0.0 (AT-12).
                theoretical_cost = (
                    round(sum(per_call), 8)
                    if all(value is not None for value in per_call)
                    else None
                )

        return ReportUsageMetrics(
            report_id=self.report_id,
            simulation_id=self.simulation_id,
            profile_id=(
                _safe_str(getattr(self.profile, "profile_id", None)) or None
            ),
            model=self.model,
            provider_id=self.provider_id,
            reasoning_effort_requested=(
                _safe_str(getattr(self.profile, "reasoning_effort", None))
                if self.profile is not None
                else None
            ),
            reasoning_effort_effective=(
                str(self._reasoning_effort_effective or "unknown")
            ),
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            thinking_tokens=self.thinking_tokens,
            total_tokens=self.total_tokens,
            duration_seconds=round(
                sum(max(0.0, call.duration_seconds) for call in self._calls), 4
            ),
            wall_seconds=self.elapsed_seconds,
            calls_count=len(self._calls),
            estimated_cost_usd=(round(known_cost, 8) if all_priced else None),
            theoretical_cost_usd=theoretical_cost,
            currency="USD",
            pricing_table_version=self.pricing_table.version,
            pricing_available=all_priced,
            usage_available=all_usage,
            max_total_cost_usd=_safe_float(
                getattr(self.profile, "max_total_cost_usd", None)
            )
            if self.profile is not None
            else None,
            max_wall_seconds=_safe_float(
                getattr(self.profile, "max_wall_seconds", None)
            )
            if self.profile is not None
            else None,
            budget_exceeded=self._budget_exceeded,
            timeout_exceeded=self._timeout_exceeded,
            stop_reason=self._stop_reason,
            phase_totals={phase: dict(totals) for phase, totals in self._phase_totals.items()},
            calls=list(self._calls),
            started_at=self._started_at,
            completed_at=self._completed_at,
        )


class BudgetGuard:
    """Garde-fou Fail-Safe des plafonds de coût et de durée (AT-11).

    Le garde-fou ne modifie **jamais** le modèle ou le fournisseur. Il lève une
    exception explicite, que le ``ReportAgent`` convertit en arrêt contrôlé
    avec sauvegarde partielle et métriques persistées.
    """

    def __init__(
        self,
        tracker: ReportUsageTracker,
        *,
        max_total_cost_usd: Optional[float] = None,
        max_wall_seconds: Optional[float] = None,
        project_next_call: bool = True,
        fail_closed_unpriced: bool = False,
    ):
        self.tracker = tracker
        self.max_total_cost_usd = (
            float(max_total_cost_usd) if max_total_cost_usd is not None else None
        )
        self.max_wall_seconds = (
            float(max_wall_seconds) if max_wall_seconds is not None else None
        )
        self.project_next_call = project_next_call
        # Le Fail-Closed tarifaire n'est armé que sur un profil explicitement
        # payant : un run gratuit ou non tarifé ne doit pas être interrompu.
        self.fail_closed_unpriced = fail_closed_unpriced

    @classmethod
    def from_profile(
        cls, tracker: ReportUsageTracker, profile: Optional[Any]
    ) -> "BudgetGuard":
        billing_mode = _safe_str(getattr(profile, "billing_mode", None)) or "auto"
        return cls(
            tracker,
            max_total_cost_usd=_safe_float(
                getattr(profile, "max_total_cost_usd", None)
            ),
            max_wall_seconds=_safe_float(
                getattr(profile, "max_wall_seconds", None)
            ),
            fail_closed_unpriced=(billing_mode == "metered"),
        )

    @property
    def remaining_wall_seconds(self) -> Optional[float]:
        """Temps restant avant le plafond temporel, ou ``None`` si non borné."""
        if self.max_wall_seconds is None:
            return None
        return max(0.0, self.max_wall_seconds - self.tracker.elapsed_seconds)

    def check(
        self,
        *,
        phase: Optional[str] = None,
        projected_next_cost_usd: Optional[float] = None,
    ) -> None:
        """Vérifie les plafonds avant toute requête LLM additionnelle."""
        elapsed = self.tracker.elapsed_seconds
        if self.max_wall_seconds is not None and elapsed >= self.max_wall_seconds:
            self.tracker.mark_stop("timeout", timeout_exceeded=True)
            raise ReportTimeoutError(
                (
                    f"Durée maximale de génération dépassée ({elapsed:.1f} s "
                    f">= {self.max_wall_seconds:.1f} s) ; arrêt contrôlé sans "
                    "requête LLM supplémentaire."
                ),
                elapsed_seconds=elapsed,
                max_wall_seconds=self.max_wall_seconds,
                phase=phase,
            )

        if self.max_total_cost_usd is None:
            return

        # Fail-Closed tarifaire : un modèle facturable sans grille connue ne
        # peut pas être borné. On refuse de continuer plutôt que de considérer
        # « inconnu » comme gratuit.
        if self.fail_closed_unpriced and self.tracker.unpriced_model_calls > 0:
            self.tracker.mark_stop("pricing_unavailable", budget_exceeded=True)
            raise ReportBudgetExceededError(
                (
                    "Plafond budgétaire non vérifiable : au moins un modèle "
                    "facturable est absent de la grille tarifaire. Arrêt "
                    "contrôlé sans requête LLM supplémentaire."
                ),
                estimated_cost_usd=self.tracker.known_cost_usd,
                max_total_cost_usd=self.max_total_cost_usd,
                phase=phase,
            )

        current_cost = self.tracker.known_cost_usd
        projected = current_cost
        if projected_next_cost_usd is not None:
            projected += max(0.0, float(projected_next_cost_usd))
        elif self.project_next_call:
            # Projeter avec le dernier appel tarifé est plus juste qu'une
            # moyenne globale : les prompts d'outline et de section diffèrent.
            projected += self.tracker.last_cost_usd
        projected = round(projected, 8)

        if projected >= self.max_total_cost_usd:
            self.tracker.mark_stop("budget_exceeded", budget_exceeded=True)
            raise ReportBudgetExceededError(
                (
                    f"Plafond budgétaire atteint (coût estimé projeté "
                    f"{projected:.6f} USD >= plafond "
                    f"{self.max_total_cost_usd:.6f} USD) ; arrêt contrôlé avant "
                    "toute requête LLM supplémentaire, sans escalade de modèle."
                ),
                estimated_cost_usd=current_cost,
                max_total_cost_usd=self.max_total_cost_usd,
                phase=phase,
            )
