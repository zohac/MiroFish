"""Modèle de télémétrie d'usage LLM par génération de rapport (Story 013-4, FR-08, C5).

Définit :
  - ``ModelPricing`` / ``PricingTable`` : grille tarifaire explicite, datée et
    extensible, distinguant les fournisseurs locaux gratuits des modèles
    facturables.
  - ``CallUsageRecord`` : usage mesuré pour un appel LLM individuel (tokens,
    durée, coût estimé, drapeaux de disponibilité).
  - ``ReportUsageMetrics`` : agrégat par job de rapport (cumuls par phase,
    durée totale, coût estimé, motif d'arrêt éventuel) persisté atomiquement
    sous ``reports/<report_id>/usage.json``.

Règle d'honnêteté (AT-12) : aucune donnée de facturation n'est inventée. Si le
fournisseur ne renvoie pas d'objet ``usage``, ``usage_available`` vaut ``False``
et ``estimated_cost_usd`` reste ``None``. Aucun prompt, message ou clé d'API
n'est conservé dans ces structures.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# Version datée de la grille tarifaire. Toute mise à jour doit créer une
# nouvelle version plutôt que réécrire silencieusement l'historique.
PRICING_TABLE_VERSION = "2026-10-19"

# Grille indicative en USD pour 1 million de tokens, reprise de la table de
# référence du PRD source (§6, captures du 19 octobre 2026). Les tarifs
# fournisseurs évoluent : ``estimated_cost_usd`` est une estimation, jamais une
# facture. Toute mise à jour doit être datée plutôt que réécrite en silence.
DEFAULT_PRICING: Dict[str, Dict[str, Any]] = {
    "gemini-3.8-flash": {
        "input_cost_per_million": 1.50,
        "output_cost_per_million": 7.50,
        "currency": "USD",
    },
    "deepseek-v4-pro": {
        "input_cost_per_million": 1.74,
        "output_cost_per_million": 3.84,
        "currency": "USD",
    },
    "qwen3.8-max": {
        "input_cost_per_million": 2.00,
        "output_cost_per_million": 6.00,
        "currency": "USD",
    },
    "gpt-6.1-sol": {
        "input_cost_per_million": 2.00,
        "output_cost_per_million": 10.00,
        "currency": "USD",
    },
}

# Fournisseurs dont le coût facturable réel est nul (passerelles locales ou
# quotas d'IDE). Le coût théorique reste calculable à titre informatif.
FREE_PROVIDER_IDS = frozenset({"antigravity-local", "codex-local", "local", "ollama"})

# Modèles explicitement gratuits (suffixe `-free`, `:free`), y compris sur un
# fournisseur par ailleurs facturable.
FREE_MODEL_MARKERS = ("-free", ":free", "free-")

# Champs interdits dans toute sérialisation de télémétrie (NFR-4).
SENSITIVE_FIELD_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "base_url",
        "baseurl",
        "bearer",
        "content",
        "cookie",
        "endpoint",
        "llm_api_key",
        "messages",
        "password",
        "prompt",
        "prompt_messages",
        "refresh_token",
        "secret",
        "token",
        "access_token",
        "url",
    }
)


def _normalize_field_name(name: Any) -> str:
    """Normalise une clé (casse, tirets, underscores, espaces) pour la filtrer."""
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


_SENSITIVE_NORMALIZED = frozenset(
    _normalize_field_name(name) for name in SENSITIVE_FIELD_NAMES
)


def is_sensitive_field_name(name: Any) -> bool:
    """Indique si un nom de champ ressemble à un secret ou à du contenu brut."""
    normalized = _normalize_field_name(name)
    return normalized in _SENSITIVE_NORMALIZED or normalized.endswith("apikey")


def _as_non_negative_int(value: Any) -> int:
    """Convertit défensivement une valeur en entier positif ou nul."""
    try:
        if value is None or isinstance(value, bool):
            return 0
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _as_float_or_none(value: Any) -> Optional[float]:
    """Convertit défensivement une valeur en float, sinon ``None``."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def sanitize_usage_payload(payload: Any) -> Any:
    """Retire récursivement les champs sensibles d'une charge de télémétrie.

    La télémétrie ne doit jamais transporter de clé d'API, d'URL privée, de
    prompt ou de message brut (NFR-4). Cette fonction est une barrière
    défensive supplémentaire, même si les structures produites en amont ne
    contiennent déjà aucune de ces données.
    """
    if isinstance(payload, dict):
        cleaned: Dict[str, Any] = {}
        for key, value in payload.items():
            if is_sensitive_field_name(key):
                continue
            cleaned[key] = sanitize_usage_payload(value)
        return cleaned
    if isinstance(payload, list):
        return [sanitize_usage_payload(item) for item in payload]
    return payload


@dataclass(frozen=True)
class ModelPricing:
    """Tarifs d'un modèle pour un million de tokens, dans une devise donnée."""

    model: str
    input_cost_per_million: float
    output_cost_per_million: float
    currency: str = "USD"
    # Tarif spécifique des tokens de réflexion uniquement quand le fournisseur
    # les facture séparément du total de complétion.
    thinking_cost_per_million: Optional[float] = None
    thinking_billed_separately: bool = False
    as_of: str = PRICING_TABLE_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "input_cost_per_million": self.input_cost_per_million,
            "output_cost_per_million": self.output_cost_per_million,
            "currency": self.currency,
            "thinking_cost_per_million": self.thinking_cost_per_million,
            "thinking_billed_separately": self.thinking_billed_separately,
            "as_of": self.as_of,
        }


class PricingTable:
    """Table de tarification explicite, datée et extensible."""

    def __init__(
        self,
        entries: Optional[Dict[str, Dict[str, Any]]] = None,
        *,
        version: str = PRICING_TABLE_VERSION,
    ):
        raw_entries = entries if entries is not None else DEFAULT_PRICING
        self.version = version
        self._pricing: Dict[str, ModelPricing] = {}
        for model, values in raw_entries.items():
            if not isinstance(values, dict):
                continue
            self._pricing[str(model)] = ModelPricing(
                model=str(model),
                input_cost_per_million=_as_float_or_none(
                    values.get("input_cost_per_million")
                )
                or 0.0,
                output_cost_per_million=_as_float_or_none(
                    values.get("output_cost_per_million")
                )
                or 0.0,
                currency=str(values.get("currency") or "USD"),
                thinking_cost_per_million=_as_float_or_none(
                    values.get("thinking_cost_per_million")
                ),
                thinking_billed_separately=bool(
                    values.get("thinking_billed_separately", False)
                ),
                as_of=str(values.get("as_of") or version),
            )
        # Index insensible à la casse, du plus long au plus court, pour résoudre
        # les alias de type ``gemini-3.8-flash-tiered`` sans ambiguïté.
        self._lookup_keys = sorted(self._pricing.keys(), key=len, reverse=True)

    @property
    def models(self) -> List[str]:
        return sorted(self._pricing.keys())

    @staticmethod
    def is_free_provider(provider_id: Optional[str]) -> bool:
        """Indique si un fournisseur local est à coût facturable nul."""
        return str(provider_id or "").strip().lower() in FREE_PROVIDER_IDS

    @staticmethod
    def is_free_model(model: Optional[str]) -> bool:
        """Indique si un modèle est explicitement gratuit (suffixe ``-free``)."""
        lowered = str(model or "").strip().lower()
        return bool(lowered) and any(marker in lowered for marker in FREE_MODEL_MARKERS)

    def is_free(self, model: Optional[str], provider_id: Optional[str]) -> bool:
        """Combine gratuité du fournisseur et gratuité explicite du modèle."""
        return self.is_free_provider(provider_id) or self.is_free_model(model)

    def get_pricing(self, model: Optional[str]) -> Optional[ModelPricing]:
        """Résout la grille d'un modèle, sans jamais inventer un tarif inconnu.

        Seuls un nom exact et les alias préfixés (``gemini-3.8-flash-tiered``)
        sont résolus : un modèle distinct qui contient un nom connu
        (``gemini-3.8-flash-pro``) ne doit pas hériter du tarif du modèle de
        base, sous peine de sous-estimer le coût et de contourner le plafond.
        """
        model_str = str(model or "").strip()
        if not model_str:
            return None
        if model_str in self._pricing:
            return self._pricing[model_str]
        lowered = model_str.lower()
        for key in self._lookup_keys:
            if lowered == key.lower():
                return self._pricing[key]
        for key in self._lookup_keys:
            if lowered.startswith(key.lower()):
                return self._pricing[key]
        return None

    def theoretical_cost(
        self,
        model: Optional[str],
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        thinking_tokens: int = 0,
    ) -> Optional[float]:
        """Coût théorique en USD, indépendamment de la gratuité du fournisseur.

        Les tokens de réflexion sont, dans l'API OpenAI-compatible, un
        sous-ensemble de ``completion_tokens`` : ils ne sont donc pas ajoutés
        une seconde fois. Un tarif séparé n'est appliqué que si la grille le
        déclare explicitement.
        """
        pricing = self.get_pricing(model)
        if pricing is None:
            return None
        prompt = _as_non_negative_int(prompt_tokens)
        completion = _as_non_negative_int(completion_tokens)
        thinking = _as_non_negative_int(thinking_tokens)
        cost = (
            prompt / 1_000_000.0 * pricing.input_cost_per_million
            + completion / 1_000_000.0 * pricing.output_cost_per_million
        )
        if pricing.thinking_billed_separately and pricing.thinking_cost_per_million is not None:
            cost += thinking / 1_000_000.0 * pricing.thinking_cost_per_million
        return round(cost, 8)

    def calculate_cost(
        self,
        model: Optional[str],
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        thinking_tokens: int = 0,
        *,
        provider_id: Optional[str] = None,
    ) -> Optional[float]:
        """Coût estimé facturable en USD, ou ``None`` si le modèle est inconnu.

        Un fournisseur local (``antigravity-local``, ``codex-local``, etc.)
        produit un coût facturable de ``0.0`` : le benchmark ne doit jamais
        présenter une dépense inexistante.
        """
        # Une passerelle locale ou un modèle explicitement gratuit reste à 0 $,
        # même si le modèle n'est pas dans la grille tarifaire. On ne fabrique
        # jamais un coût inconnu pour un run gratuit.
        if self.is_free(model, provider_id):
            return 0.0
        theoretical = self.theoretical_cost(
            model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            thinking_tokens=thinking_tokens,
        )
        if theoretical is None:
            return None
        return theoretical


@dataclass
class CallUsageRecord:
    """Usage mesuré d'un appel LLM individuel."""

    call_index: int
    phase: str
    model: str
    provider_id: Optional[str] = None
    reasoning_effort_requested: Optional[str] = None
    reasoning_effort_effective: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    thinking_tokens: int = 0
    total_tokens: int = 0
    duration_seconds: float = 0.0
    estimated_cost_usd: Optional[float] = None
    usage_available: bool = True
    recorded_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_index": self.call_index,
            "phase": self.phase,
            "model": self.model,
            "provider_id": self.provider_id,
            "reasoning_effort_requested": self.reasoning_effort_requested,
            "reasoning_effort_effective": self.reasoning_effort_effective,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "thinking_tokens": self.thinking_tokens,
            "total_tokens": self.total_tokens,
            "duration_seconds": round(float(self.duration_seconds or 0.0), 4),
            "estimated_cost_usd": self.estimated_cost_usd,
            "usage_available": bool(self.usage_available),
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CallUsageRecord":
        if not isinstance(data, dict):
            raise ValueError("Dictionnaire requis pour CallUsageRecord.from_dict")
        return cls(
            call_index=_as_non_negative_int(data.get("call_index")),
            phase=str(data.get("phase") or "other"),
            model=str(data.get("model") or ""),
            provider_id=data.get("provider_id"),
            reasoning_effort_requested=data.get("reasoning_effort_requested"),
            reasoning_effort_effective=str(
                data.get("reasoning_effort_effective") or "unknown"
            ),
            prompt_tokens=_as_non_negative_int(data.get("prompt_tokens")),
            completion_tokens=_as_non_negative_int(data.get("completion_tokens")),
            thinking_tokens=_as_non_negative_int(data.get("thinking_tokens")),
            total_tokens=_as_non_negative_int(data.get("total_tokens")),
            duration_seconds=_as_float_or_none(data.get("duration_seconds")) or 0.0,
            estimated_cost_usd=_as_float_or_none(data.get("estimated_cost_usd")),
            usage_available=bool(data.get("usage_available", True)),
            recorded_at=str(
                data.get("recorded_at") or datetime.utcnow().isoformat() + "Z"
            ),
        )


@dataclass
class ReportUsageMetrics:
    """Agrégat de télémétrie d'usage pour une génération de rapport."""

    report_id: str
    simulation_id: Optional[str] = None
    profile_id: Optional[str] = None
    model: str = ""
    provider_id: Optional[str] = None
    reasoning_effort_requested: Optional[str] = None
    reasoning_effort_effective: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    thinking_tokens: int = 0
    total_tokens: int = 0
    duration_seconds: float = 0.0
    wall_seconds: float = 0.0
    calls_count: int = 0
    estimated_cost_usd: Optional[float] = None
    theoretical_cost_usd: Optional[float] = None
    currency: str = "USD"
    pricing_table_version: str = PRICING_TABLE_VERSION
    pricing_available: bool = True
    usage_available: bool = True
    max_total_cost_usd: Optional[float] = None
    max_wall_seconds: Optional[float] = None
    budget_exceeded: bool = False
    timeout_exceeded: bool = False
    stop_reason: Optional[str] = None
    # Message d'arrêt contrôlé, porté par le job : le code seul ne dit pas
    # *pourquoi* le générateur s'est arrêté (Story 013-5, AC4).
    stop_message: Optional[str] = None
    phase_totals: Dict[str, Dict[str, int]] = field(default_factory=dict)
    calls: List[CallUsageRecord] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "profile_id": self.profile_id,
            "model": self.model,
            "provider_id": self.provider_id,
            "reasoning_effort_requested": self.reasoning_effort_requested,
            "reasoning_effort_effective": self.reasoning_effort_effective,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "thinking_tokens": self.thinking_tokens,
            "total_tokens": self.total_tokens,
            "duration_seconds": round(float(self.duration_seconds or 0.0), 4),
            "wall_seconds": round(float(self.wall_seconds or 0.0), 4),
            "calls_count": self.calls_count,
            "estimated_cost_usd": self.estimated_cost_usd,
            "theoretical_cost_usd": self.theoretical_cost_usd,
            "currency": self.currency,
            "pricing_table_version": self.pricing_table_version,
            "pricing_available": bool(self.pricing_available),
            "usage_available": bool(self.usage_available),
            "max_total_cost_usd": self.max_total_cost_usd,
            "max_wall_seconds": self.max_wall_seconds,
            "budget_exceeded": bool(self.budget_exceeded),
            "timeout_exceeded": bool(self.timeout_exceeded),
            "stop_reason": self.stop_reason,
            "stop_message": self.stop_message,
            "phase_totals": self.phase_totals,
            "calls": [call.to_dict() for call in self.calls],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
        return payload

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportUsageMetrics":
        if not isinstance(data, dict):
            raise ValueError("Dictionnaire requis pour ReportUsageMetrics.from_dict")
        raw_calls = data.get("calls") or []
        calls = [
            CallUsageRecord.from_dict(entry)
            for entry in raw_calls
            if isinstance(entry, dict)
        ]
        raw_phase_totals = data.get("phase_totals") or {}
        phase_totals: Dict[str, Dict[str, int]] = {}
        if isinstance(raw_phase_totals, dict):
            for phase, totals in raw_phase_totals.items():
                if not isinstance(totals, dict):
                    continue
                phase_totals[str(phase)] = {
                    "prompt_tokens": _as_non_negative_int(totals.get("prompt_tokens")),
                    "completion_tokens": _as_non_negative_int(
                        totals.get("completion_tokens")
                    ),
                    "thinking_tokens": _as_non_negative_int(
                        totals.get("thinking_tokens")
                    ),
                    "total_tokens": _as_non_negative_int(totals.get("total_tokens")),
                    "calls_count": _as_non_negative_int(totals.get("calls_count")),
                }
        return cls(
            report_id=str(data.get("report_id") or ""),
            simulation_id=data.get("simulation_id"),
            profile_id=data.get("profile_id"),
            model=str(data.get("model") or ""),
            provider_id=data.get("provider_id"),
            reasoning_effort_requested=data.get("reasoning_effort_requested"),
            reasoning_effort_effective=str(
                data.get("reasoning_effort_effective") or "unknown"
            ),
            prompt_tokens=_as_non_negative_int(data.get("prompt_tokens")),
            completion_tokens=_as_non_negative_int(data.get("completion_tokens")),
            thinking_tokens=_as_non_negative_int(data.get("thinking_tokens")),
            total_tokens=_as_non_negative_int(data.get("total_tokens")),
            duration_seconds=_as_float_or_none(data.get("duration_seconds")) or 0.0,
            wall_seconds=_as_float_or_none(data.get("wall_seconds")) or 0.0,
            calls_count=_as_non_negative_int(data.get("calls_count")),
            estimated_cost_usd=_as_float_or_none(data.get("estimated_cost_usd")),
            theoretical_cost_usd=_as_float_or_none(data.get("theoretical_cost_usd")),
            currency=str(data.get("currency") or "USD"),
            pricing_table_version=str(
                data.get("pricing_table_version") or PRICING_TABLE_VERSION
            ),
            pricing_available=bool(data.get("pricing_available", True)),
            usage_available=bool(data.get("usage_available", True)),
            max_total_cost_usd=_as_float_or_none(data.get("max_total_cost_usd")),
            max_wall_seconds=_as_float_or_none(data.get("max_wall_seconds")),
            budget_exceeded=bool(data.get("budget_exceeded", False)),
            timeout_exceeded=bool(data.get("timeout_exceeded", False)),
            stop_reason=data.get("stop_reason"),
            stop_message=data.get("stop_message"),
            phase_totals=phase_totals,
            calls=calls,
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
        )

    def summary(self) -> Dict[str, Any]:
        """Résumé compact destiné à ``report_history.json`` et ``run_manifest.json``."""
        return {
            "calls_count": self.calls_count,
            "model": self.model,
            "provider_id": self.provider_id,
            "reasoning_effort_requested": self.reasoning_effort_requested,
            "reasoning_effort_effective": self.reasoning_effort_effective,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "thinking_tokens": self.thinking_tokens,
            "total_tokens": self.total_tokens,
            "duration_seconds": round(float(self.duration_seconds or 0.0), 4),
            "wall_seconds": round(float(self.wall_seconds or 0.0), 4),
            "estimated_cost_usd": self.estimated_cost_usd,
            "theoretical_cost_usd": self.theoretical_cost_usd,
            "currency": self.currency,
            "pricing_table_version": self.pricing_table_version,
            "usage_available": bool(self.usage_available),
            "pricing_available": bool(self.pricing_available),
            "budget_exceeded": bool(self.budget_exceeded),
            "timeout_exceeded": bool(self.timeout_exceeded),
            "stop_reason": self.stop_reason,
            "stop_message": self.stop_message,
        }

    def save_to_file(self, target_path: str) -> str:
        """Sérialise les métriques de façon atomique (écriture + fsync + replace)."""
        directory = os.path.dirname(os.path.abspath(target_path))
        os.makedirs(directory, exist_ok=True)
        tmp_path = f"{target_path}.tmp.{os.getpid()}_{uuid.uuid4().hex[:8]}"
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(
                    sanitize_usage_payload(self.to_dict()),
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, target_path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        return target_path

    @classmethod
    def load_from_file(cls, target_path: str) -> Optional["ReportUsageMetrics"]:
        """Charge des métriques depuis le disque, ou ``None`` si absentes/illisibles."""
        if not target_path or not os.path.exists(target_path):
            return None
        try:
            with open(target_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return None
            return cls.from_dict(data)
        except (OSError, ValueError, TypeError, OverflowError, json.JSONDecodeError):
            return None
