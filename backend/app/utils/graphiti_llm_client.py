"""Client LLM Graphiti avec injection des en-têtes de session OpenCode Go.

Ce module fournit un client LLM dérivé de ``OpenAIGenericClient`` de ``graphiti-core``,
adapté aux spécificités de l'environnement MiroFish et de la passerelle OpenCode Go :

1. Injection automatique des en-têtes de requête nécessaires (``x-opencode-session``,
   ``User-Agent``) via ``llm_request_headers(base_url)`` (ADR 0004).
2. Mode de sortie structurée par défaut sur ``"json_object"`` pour compatibilité avec
   les modèles qui ne supportent pas les contraintes strictes de ``json_schema``.
3. Transmission de l'effort de raisonnement (``LLM_REASONING_EFFORT``) via ``extra_body``
   lors des appels de complétion.
4. Neutralité stricte pour les autres fournisseurs LLM (OpenAI, Ollama, etc.).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from graphiti_core.llm_client.config import DEFAULT_MAX_TOKENS, LLMConfig, ModelSize
from graphiti_core.llm_client.errors import EmptyResponseError, RateLimitError
from graphiti_core.llm_client.openai_generic_client import (
    DEFAULT_MODEL,
    OpenAIGenericClient,
    StructuredOutputMode,
)
from graphiti_core.prompts.models import Message

from ..config import Config
from .llm_compat import llm_completion_kwargs, llm_request_headers

logger = logging.getLogger(__name__)


class MiroFishLLMClient(OpenAIGenericClient):
    """Client LLM pour Graphiti compatible avec OpenCode Go et les fournisseurs OpenAI-compatibles."""

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        cache: bool = False,
        client: Optional[Any] = None,
        max_tokens: int = 16384,
        structured_output_mode: StructuredOutputMode = "json_object",
    ):
        """Initialise le client LLM Graphiti avec injection d'en-têtes de session.

        Args:
            config: Configuration LLM (URL, clé API, modèle, température, etc.). Si non
                fournie, dérive les paramètres depuis ``backend/app/config.py`` (Config).
            cache: Active la mise en cache (non supportée par OpenAI/Graphiti, défaut False).
            client: Instance personnalisée d'AsyncOpenAI. Si None, une instance est
                créée avec les ``default_headers`` adaptés à l'hôte cible.
            max_tokens: Nombre maximal de tokens de complétion (défaut 16384).
            structured_output_mode: Mode de sortie structurée (``"json_object"`` par
                défaut, ou ``"json_schema"`` pour les fournisseurs stricts).
        """
        if config is None:
            config = LLMConfig(
                api_key=os.environ.get("LLM_API_KEY") or Config.LLM_API_KEY,
                base_url=os.environ.get("LLM_BASE_URL") or Config.LLM_BASE_URL,
                model=os.environ.get("LLM_MODEL_NAME") or Config.LLM_MODEL_NAME,
            )
            target_base_url = config.base_url
        else:
            target_base_url = config.base_url

        if client is None:
            # Si config a été fourni explicitement avec base_url=None, l'appelant vise
            # l'endpoint OpenAI par défaut (api.openai.com). Ne dériver l'en-tête de session
            # que si target_base_url est explicitement renseigné ou issu du fallback Config/env.
            headers = (
                llm_request_headers(target_base_url)
                if target_base_url
                else {"User-Agent": "mirofish/0.1.0"}
            )
            client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                default_headers=headers,
            )

        super().__init__(
            config=config,
            cache=cache,
            client=client,
            max_tokens=max_tokens,
            structured_output_mode=structured_output_mode,
        )

    @staticmethod
    def _clean_response_text(content: str) -> str:
        """Nettoie le texte de réponse du modèle.

        Supprime les blocs de raisonnement (<think>...</think>), les BOM UTF-8
        et les balises Markdown ```json ... ``` pour éviter les échecs de désérialisation JSON.
        """
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
        cleaned = cleaned.lstrip("\ufeff")
        return OpenAIGenericClient._strip_code_fences(cleaned)

    async def _generate_response(
        self,
        messages: List[Message],
        response_model: Optional[type[BaseModel]] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
    ) -> Dict[str, Any]:
        """Génère une réponse via l'API OpenAI compatible en relayant les options d'inférence.

        Surcharge la méthode interne de ``OpenAIGenericClient`` pour intégrer l'effort
        de raisonnement (``reasoning_effort``) via ``extra_body`` si configuré dans
        l'environnement (``LLM_REASONING_EFFORT``).
        """
        openai_messages: List[ChatCompletionMessageParam] = []
        for m in messages:
            m.content = self._clean_input(m.content)
            if m.role == "user":
                openai_messages.append({"role": "user", "content": m.content})
            elif m.role == "system":
                openai_messages.append({"role": "system", "content": m.content})
            elif m.role == "assistant":
                openai_messages.append({"role": "assistant", "content": m.content})

        try:
            kwargs: Dict[str, Any] = {
                "model": self.model or DEFAULT_MODEL,
                "messages": openai_messages,
                "temperature": self.temperature,
                "max_tokens": max_tokens,
                "response_format": self._build_response_format(response_model),
            }

            completion_kwargs = llm_completion_kwargs()
            if completion_kwargs:
                kwargs["extra_body"] = completion_kwargs

            response = await self.client.chat.completions.create(**kwargs)
            choices = getattr(response, "choices", None) or []
            if not choices:
                raise EmptyResponseError("LLM returned an empty choices list")

            result = choices[0].message.content or ""
            if not result:
                raise EmptyResponseError("LLM returned an empty response")
            return json.loads(self._clean_response_text(result))
        except openai.RateLimitError as e:
            raise RateLimitError from e
        except Exception as e:
            logger.error(f"Error in generating LLM response: {e}")
            raise
