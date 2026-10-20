"""Modèle de configuration LLM par job de rapport (ReportLLMProfile).

Permet d'isoler les paramètres de modèle, de fournisseur et d'effort de raisonnement
sans altérer les variables d'environnement globales du processus.
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

from .report_usage import PricingTable

VALID_REASONING_EFFORTS = {"minimal", "low", "medium", "high"}
VALID_BILLING_MODES = {"auto", "free", "metered"}

# Catalogue fermé et explicite des profils LLM de rapport (Story 013-5, FR-08).
# La liste est figée dans le code : aucune découverte dynamique, afin que le
# navigateur ne puisse jamais élargir la surface d'exécution par lui-même.
# L'exhaustivité de ce catalogue est gardée par un test (test_report_profiles_api.py).
STANDARD_PROFILE_IDS: Tuple[str, ...] = (
    "flash-medium",
    "flash-high",
    "deepseek-v4-pro",
    "qwen3.8-max",
    "gpt-6.1-sol",
)


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

        # Un plafond négatif ou non fini produirait un arrêt immédiat (ou un
        # plafond silencieusement désactivé en aval) : on refuse à l'entrée.
        cost_cap = self.max_total_cost_usd
        if (
            isinstance(cost_cap, bool)
            or not isinstance(cost_cap, (int, float))
            or not math.isfinite(float(cost_cap))
            or float(cost_cap) < 0
        ):
            raise ValueError(
                "max_total_cost_usd doit être un nombre fini positif ou nul"
            )
        wall_cap = self.max_wall_seconds
        if (
            isinstance(wall_cap, bool)
            or not isinstance(wall_cap, (int, float))
            or not math.isfinite(float(wall_cap))
            or float(wall_cap) < 0
        ):
            raise ValueError(
                "max_wall_seconds doit être un nombre fini positif ou nul"
            )
        object.__setattr__(self, "max_total_cost_usd", float(cost_cap))
        object.__setattr__(self, "max_wall_seconds", int(wall_cap))

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
    def from_dict(
        cls,
        data: Dict[str, Any],
        *,
        allow_endpoint: bool = False,
    ) -> ReportLLMProfile:
        """Désérialise un dictionnaire en ReportLLMProfile.

        ``allow_endpoint=False`` (défaut) est le régime d'un profil **reçu
        d'un client** : la destination et la clé en sont refusées. Un client
        qui désignerait une passerelle OpenAI-compatible arbitraire y ferait
        transiter le paquet de preuves entier (documents, personas, événements
        observés) : le catalogue est fermé, donc le chemin inline l'est aussi
        (Story 013-5, décision du 20 octobre 2026).

        ``allow_endpoint=True`` est réservé à un usage serveur interne qui
        doit effectivement fixer la destination (aucun appelant actuel).
        """
        data_copy = dict(data)
        # Éliminer les champs informatifs non constructeurs
        data_copy.pop("base_url_configured", None)
        if not allow_endpoint:
            for forbidden in ("base_url", "api_key"):
                if data_copy.get(forbidden):
                    raise ValueError(
                        f"'{forbidden}' ne peut pas être fourni par un client : "
                        "la destination et la clé restent côté serveur "
                        "(catalogue fermé des profils LLM de rapport)."
                    )
        return cls(
            profile_id=str(data_copy.get("profile_id", "default")),
            model=str(data_copy.get("model", "")),
            provider_id=str(data_copy.get("provider_id", "custom")),
            reasoning_effort=data_copy.get("reasoning_effort"),
            temperature=float(data_copy["temperature"]) if data_copy.get("temperature") is not None else None,
            max_tokens=int(data_copy["max_tokens"]) if data_copy.get("max_tokens") is not None else None,
            base_url=data_copy.get("base_url") if allow_endpoint else None,
            api_key=data_copy.get("api_key") if allow_endpoint else None,
            max_total_cost_usd=float(data_copy.get("max_total_cost_usd", 2.0)),
            max_wall_seconds=int(data_copy.get("max_wall_seconds", 900)),
            billing_mode=(
                str(data_copy.get("billing_mode"))
                if data_copy.get("billing_mode") is not None
                else "auto"
            ),
        )

    @staticmethod
    def gateway_alias(base_url: Optional[str]) -> str:
        """Retourne l'alias de la passerelle configurée.

        ``provider_id`` désigne la **passerelle qui a servi**, pas l'éditeur
        du modèle : les cinq profils standard partagent le même ``base_url``,
        donc un éditeur codé en dur annoncerait « opencode-go » pour un
        rapport que la passerelle Antigravity a produit (Story 013-5,
        décision du 20 octobre 2026).

        L'alias reprend la convention déjà employée par le manifeste de run
        de la story 013-4.
        """
        url = str(base_url or "").strip().lower()
        if not url:
            return "custom"
        if "18081" in url or "antigravity" in url:
            return "antigravity-local"
        if "18080" in url or "codex" in url:
            return "codex-local"
        if "opencode" in url:
            return "opencode-go"
        return "custom"

    @classmethod
    def from_client(cls, data: Dict[str, Any]) -> ReportLLMProfile:
        """Construit un profil depuis un corps client, aligné sur le catalogue.

        Le navigateur peut choisir le **modèle** et l'**effort** — c'est la
        raison d'être des « appels avancés » — mais jamais la destination ni
        la clé, ni un mode de facturation ou des plafonds plus permissifs que
        ceux du catalogue (Story 013-5, décision du 20 octobre 2026).

        L'``profile_id`` est **dérivé** du couple (modèle, effort) : un client
        ne peut pas étiqueter un job « flash-high » alors que l'effort retenu
        est « medium », sans quoi l'historique porterait un mensonge.
        """
        data_copy = dict(data or {})
        data_copy.pop("base_url_configured", None)

        model = str(data_copy.get("model") or "").strip()
        if not model:
            raise ValueError("model est obligatoire pour un profil client")

        catalog = cls._build_standard_catalog()
        matches = [profile for profile in catalog.values() if profile.model == model]
        if not matches:
            raise ValueError(
                f"model '{model}' absent du catalogue des profils LLM de rapport "
                f"(modèles : {', '.join(sorted({p.model for p in catalog.values()}))})"
            )
        reference = matches[0]

        # Le mode de facturation ne peut pas être plus permissif que celui du
        # catalogue : `free` désarmerait le Fail-Closed tarifaire de la 013-4.
        requested_billing = str(
            data_copy.get("billing_mode") or reference.billing_mode
        ).strip().lower()
        if requested_billing != reference.billing_mode:
            raise ValueError(
                f"billing_mode '{requested_billing}' refusé : le catalogue impose "
                f"'{reference.billing_mode}' pour le modèle '{model}'"
            )

        # Les plafonds ne peuvent pas être plus permissifs que ceux du catalogue.
        requested_cost = float(
            data_copy.get("max_total_cost_usd", reference.max_total_cost_usd)
        )
        if requested_cost > reference.max_total_cost_usd:
            raise ValueError(
                f"max_total_cost_usd {requested_cost} supérieur au plafond du "
                f"catalogue ({reference.max_total_cost_usd}) pour le modèle '{model}'"
            )
        requested_wall = int(
            data_copy.get("max_wall_seconds", reference.max_wall_seconds)
        )
        if requested_wall > reference.max_wall_seconds:
            raise ValueError(
                f"max_wall_seconds {requested_wall} supérieur au plafond du "
                f"catalogue ({reference.max_wall_seconds}) pour le modèle '{model}'"
            )

        effort = str(data_copy.get("reasoning_effort") or "").strip().lower() or None
        exact = [p for p in matches if (p.reasoning_effort or None) == effort]

        data_copy["profile_id"] = (
            exact[0].profile_id if len(exact) == 1 else f"custom-{model}"
        )
        data_copy["billing_mode"] = reference.billing_mode
        data_copy["max_total_cost_usd"] = requested_cost
        data_copy["max_wall_seconds"] = requested_wall
        data_copy.setdefault("provider_id", reference.provider_id)
        # ``from_dict`` refuse ``base_url`` et ``api_key`` : c'est le garde
        # qui empêche un client de désigner une passerelle arbitraire.
        return cls.from_dict(data_copy)

    @classmethod
    def default_from_env(cls, profile_id: str = "env-default") -> ReportLLMProfile:
        """Construit un profil par défaut basé sur la configuration globale actuelle."""
        from ..config import Config

        effort = (Config.LLM_REASONING_EFFORT or "").strip().lower() or None
        model_name = Config.LLM_MODEL_NAME or "gemini-3.8-flash"
        is_free_model = PricingTable.is_free_model(model_name)
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
    def standard_profile_ids(cls) -> Tuple[str, ...]:
        """Retourne les identifiants du catalogue standard, dans un ordre stable.

        Source de vérité unique pour l'endpoint ``GET /api/report/profiles`` et
        pour le rejet d'un ``profile_id`` inconnu (Story 013-5, AC2).
        """
        return STANDARD_PROFILE_IDS

    @classmethod
    def _build_standard_catalog(cls) -> Dict[str, "ReportLLMProfile"]:
        """Construit le catalogue standard à la demande.

        La configuration est lue au moment de l'appel (et non figée à
        l'import) : un test ou un environnement peut ajuster ``LLM_BASE_URL``
        ou ``LLM_API_KEY`` avant de résoudre un profil.
        """
        from ..config import Config

        base_url = Config.LLM_BASE_URL
        api_key = Config.LLM_API_KEY
        # ``provider_id`` = la passerelle réellement configurée, pas l'éditeur
        # du modèle : les cinq profils partagent le même ``base_url``.
        provider_id = cls.gateway_alias(base_url)

        catalog = {
            "flash-medium": cls(
                profile_id="flash-medium",
                model="gemini-3.8-flash",
                provider_id=provider_id,
                reasoning_effort="medium",
                base_url=base_url,
                api_key=api_key,
                # Profil de benchmark : le plafond doit être réellement
                # opposable, donc le Fail-Closed tarifaire est armé. Une
                # passerelle locale reste facturée 0 $ par la grille.
                billing_mode="metered",
            ),
            "flash-high": cls(
                profile_id="flash-high",
                model="gemini-3.8-flash",
                provider_id=provider_id,
                reasoning_effort="high",
                base_url=base_url,
                api_key=api_key,
                billing_mode="metered",
            ),
            "deepseek-v4-pro": cls(
                profile_id="deepseek-v4-pro",
                model="deepseek-v4-pro",
                provider_id=provider_id,
                reasoning_effort=None,
                base_url=base_url,
                api_key=api_key,
                billing_mode="metered",
            ),
            "qwen3.8-max": cls(
                profile_id="qwen3.8-max",
                model="qwen3.8-max",
                provider_id=provider_id,
                reasoning_effort=None,
                base_url=base_url,
                api_key=api_key,
                billing_mode="metered",
            ),
            "gpt-6.1-sol": cls(
                profile_id="gpt-6.1-sol",
                model="gpt-6.1-sol",
                provider_id=provider_id,
                reasoning_effort=None,
                base_url=base_url,
                api_key=api_key,
                billing_mode="metered",
            ),
        }
        return catalog

    @classmethod
    def get_standard_profile(cls, profile_id: str) -> Optional[ReportLLMProfile]:
        """Retourne un profil standard par son identifiant."""
        return cls._build_standard_catalog().get(profile_id)
