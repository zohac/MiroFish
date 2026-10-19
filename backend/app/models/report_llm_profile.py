"""Modèle de configuration LLM par job de rapport (ReportLLMProfile).

Permet d'isoler les paramètres de modèle, de fournisseur et d'effort de raisonnement
sans altérer les variables d'environnement globales du processus.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

VALID_REASONING_EFFORTS = {"minimal", "low", "medium", "high"}
VALID_BILLING_MODES = {"auto", "free", "metered"}


@dataclass(frozen=True)
class ReportLLMProfile:
    """Profil LLM immuable injecté dans ReportAgent."""

    profile_id: str
    model: str
    provider_id: str = "custom"
    reasoning_effort: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    max_total_cost_usd: float = 2.0
    max_wall_seconds: int = 900
    billing_mode: str = "auto"

    def __post_init__(self) -> None:
        if not self.profile_id or not str(self.profile_id).strip():
            raise ValueError("profile_id ne peut pas être vide")
        if not self.model or not str(self.model).strip():
            raise ValueError("model ne peut pas être vide")
        if self.reasoning_effort is not None:
            normalized = str(self.reasoning_effort).strip().lower()
            if normalized and normalized not in VALID_REASONING_EFFORTS:
                raise ValueError(
                    f"reasoning_effort invalide '{self.reasoning_effort}'. "
                    f"Valeurs acceptées : {sorted(VALID_REASONING_EFFORTS)}"
                )
            object.__setattr__(self, "reasoning_effort", normalized or None)
        normalized_billing = str(self.billing_mode or "auto").strip().lower()
        if normalized_billing not in VALID_BILLING_MODES:
            raise ValueError(
                f"billing_mode invalide '{self.billing_mode}'. "
                f"Valeurs acceptées : {sorted(VALID_BILLING_MODES)}"
            )
        object.__setattr__(self, "billing_mode", normalized_billing)

    def to_dict(self, expose_secrets: bool = False) -> Dict[str, Any]:
        """Sérialise le profil en dictionnaire. Masque les clés API par défaut."""
        data = asdict(self)
        if not expose_secrets:
            data.pop("api_key", None)
            # Masquer les tokens éventuels dans l'URL
            if data.get("base_url"):
                data["base_url_configured"] = True
                data.pop("base_url", None)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ReportLLMProfile:
        """Désérialise un dictionnaire en ReportLLMProfile."""
        data_copy = dict(data)
        # Éliminer les champs informatifs non constructeurs
        data_copy.pop("base_url_configured", None)
        return cls(
            profile_id=str(data_copy.get("profile_id", "default")),
            model=str(data_copy.get("model", "")),
            provider_id=str(data_copy.get("provider_id", "custom")),
            reasoning_effort=data_copy.get("reasoning_effort"),
            temperature=float(data_copy["temperature"]) if data_copy.get("temperature") is not None else None,
            max_tokens=int(data_copy["max_tokens"]) if data_copy.get("max_tokens") is not None else None,
            base_url=data_copy.get("base_url"),
            api_key=data_copy.get("api_key"),
            max_total_cost_usd=float(data_copy.get("max_total_cost_usd", 2.0)),
            max_wall_seconds=int(data_copy.get("max_wall_seconds", 900)),
            billing_mode=str(data_copy.get("billing_mode", "auto")),
        )

    @classmethod
    def default_from_env(cls, profile_id: str = "env-default") -> ReportLLMProfile:
        """Construit un profil par défaut basé sur la configuration globale actuelle."""
        from ..config import Config

        effort = (Config.LLM_REASONING_EFFORT or "").strip().lower() or None
        model_name = Config.LLM_MODEL_NAME or "gemini-3.8-flash"
        is_free_model = "free" in str(model_name).lower()
        return cls(
            profile_id=profile_id,
            model=model_name,
            provider_id="env",
            reasoning_effort=effort,
            base_url=Config.LLM_BASE_URL,
            api_key=Config.LLM_API_KEY,
            billing_mode="free" if is_free_model else "auto",
        )

    @classmethod
    def get_standard_profile(cls, profile_id: str) -> Optional[ReportLLMProfile]:
        """Retourne un profil standard par son identifiant."""
        from ..config import Config

        base_url = Config.LLM_BASE_URL
        api_key = Config.LLM_API_KEY

        catalog = {
            "flash-medium": cls(
                profile_id="flash-medium",
                model="gemini-3.8-flash",
                provider_id="antigravity-local" if "18081" in (base_url or "") else "custom",
                reasoning_effort="medium",
                base_url=base_url,
                api_key=api_key,
                billing_mode="auto",
            ),
            "flash-high": cls(
                profile_id="flash-high",
                model="gemini-3.8-flash",
                provider_id="antigravity-local" if "18081" in (base_url or "") else "custom",
                reasoning_effort="high",
                base_url=base_url,
                api_key=api_key,
                billing_mode="auto",
            ),
            "deepseek-v4-pro": cls(
                profile_id="deepseek-v4-pro",
                model="deepseek-v4-pro",
                provider_id="opencode-go",
                reasoning_effort=None,
                base_url=base_url,
                api_key=api_key,
                billing_mode="metered",
            ),
            "qwen3.8-max": cls(
                profile_id="qwen3.8-max",
                model="qwen3.8-max",
                provider_id="opencode-go",
                reasoning_effort=None,
                base_url=base_url,
                api_key=api_key,
                billing_mode="metered",
            ),
            "gpt-6.1-sol": cls(
                profile_id="gpt-6.1-sol",
                model="gpt-6.1-sol",
                provider_id="opencode-go",
                reasoning_effort=None,
                base_url=base_url,
                api_key=api_key,
                billing_mode="metered",
            ),
        }
        return catalog.get(profile_id)
