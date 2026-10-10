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
from typing import Any, Dict, List, Optional, get_origin

import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from graphiti_core.llm_client.config import DEFAULT_MAX_TOKENS, LLMConfig, ModelSize
from graphiti_core.llm_client.errors import EmptyResponseError, RateLimitError
from graphiti_core.llm_client.openai_generic_client import (
    DEFAULT_MODEL,
    OpenAIGenericClient,
    StructuredOutputMode,
)
from graphiti_core.llm_client.client import get_extraction_language_instruction
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
            resolved_api_key = (
                os.environ.get("LLM_API_KEY")
                or Config.LLM_API_KEY
                or os.environ.get("OPENAI_API_KEY")
                or "mock-key"
            )
            config = LLMConfig(
                api_key=resolved_api_key,
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
            api_key_for_client = (
                config.api_key
                or os.environ.get("OPENAI_API_KEY")
                or "mock-key"
            )
            client = AsyncOpenAI(
                api_key=api_key_for_client,
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

    @classmethod
    def _extract_json_payload(cls, text: str) -> Any:
        """Désérialise le JSON avec repli sur extraction de bloc si du texte entoure le JSON."""
        cleaned = cls._clean_response_text(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
            if match:
                return json.loads(match.group(1))
            raise

    @classmethod
    def _build_default_instance_dict(cls, model_cls: type[BaseModel]) -> Dict[str, Any]:
        """Construit un dictionnaire par défaut sûr pour un modèle Pydantic."""
        data: Dict[str, Any] = {}
        for field_name, field_info in model_cls.model_fields.items():
            if field_info.default is not PydanticUndefined and field_info.default is not None:
                data[field_name] = field_info.default
            elif field_info.default_factory is not None:
                data[field_name] = field_info.default_factory()
            else:
                origin = get_origin(field_info.annotation)
                if origin in (list, List) or origin is list:
                    data[field_name] = []
                elif origin in (dict, Dict) or origin is dict:
                    data[field_name] = {}
                else:
                    data[field_name] = None
        return data

    @classmethod
    def _is_json_schema_definition(cls, parsed: Dict[str, Any]) -> bool:
        """Détecte si un dictionnaire représente une définition brute de JSON Schema."""
        if "$defs" in parsed or "$schema" in parsed:
            return True
        if parsed.get("type") == "object" and "properties" in parsed and isinstance(parsed["properties"], dict):
            for prop in parsed["properties"].values():
                if isinstance(prop, dict) and ("type" in prop or "$ref" in prop or "title" in prop):
                    return True
        return False

    @classmethod
    def _normalize_response(
        cls,
        parsed: Any,
        response_model: Optional[type[BaseModel]],
    ) -> Dict[str, Any]:
        """Normalise et assainit le payload retourné par le LLM pour correspondre à response_model."""
        if response_model is None:
            return parsed if isinstance(parsed, dict) else {"data": parsed}

        # 1. Vérification directe : si déjà conforme, retour immédiat
        if isinstance(parsed, dict):
            try:
                response_model.model_validate(parsed)
                return parsed
            except Exception:
                pass

        # 2. Cas où le LLM renvoie directement une liste pour un modèle contenant un seul champ liste
        if isinstance(parsed, list):
            list_fields = [
                name
                for name, info in response_model.model_fields.items()
                if get_origin(info.annotation) in (list, List) or info.annotation is list
            ]
            if len(list_fields) == 1:
                candidate = {list_fields[0]: parsed}
                try:
                    response_model.model_validate(candidate)
                    logger.debug(
                        "Payload liste encapsulé sous le champ '%s' pour %s",
                        list_fields[0],
                        response_model.__name__,
                    )
                    return candidate
                except Exception:
                    pass

        # 3. Données encapsulées dans un sous-dictionnaire (properties, data, ou nom de classe)
        if isinstance(parsed, dict):
            for candidate_key in ("properties", "data", getattr(response_model, "__name__", "")):
                sub_val = parsed.get(candidate_key)
                if isinstance(sub_val, dict):
                    try:
                        response_model.model_validate(sub_val)
                        logger.debug(
                            "Payload extrait de la clé '%s' pour %s",
                            candidate_key,
                            response_model.__name__,
                        )
                        return sub_val
                    except Exception:
                        pass

        # 4. Alias courants pour l'extraction d'entités (entities -> extracted_entities)
        if isinstance(parsed, dict) and "entities" in parsed and "extracted_entities" not in parsed:
            candidate = dict(parsed)
            candidate["extracted_entities"] = candidate.pop("entities")
            try:
                response_model.model_validate(candidate)
                logger.debug("Clé 'entities' renommée en 'extracted_entities'")
                return candidate
            except Exception:
                pass

        # 5. Détection de schéma JSON brut renvoyé en écho par le LLM
        if isinstance(parsed, dict) and cls._is_json_schema_definition(parsed):
            logger.warning(
                "Le LLM a retourné une définition de JSON Schema au lieu d'une instance pour %s. "
                "Repli sécurisé sur les valeurs par défaut.",
                response_model.__name__,
            )
            fallback = cls._build_default_instance_dict(response_model)
            try:
                response_model.model_validate(fallback)
                return fallback
            except Exception as exc:
                logger.error(
                    "Échec de validation du repli par défaut pour %s: %s",
                    response_model.__name__,
                    exc,
                )

        # 6. Fallback général si parsed n'est pas un dictionnaire
        if not isinstance(parsed, dict):
            fallback = cls._build_default_instance_dict(response_model)
            try:
                response_model.model_validate(fallback)
                return fallback
            except Exception:
                return {"data": parsed}

        return parsed

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
            parsed = self._extract_json_payload(result)
            return self._normalize_response(parsed, response_model)
        except openai.RateLimitError as e:
            raise RateLimitError from e
        except Exception as e:
            logger.error(f"Error in generating LLM response: {e}")
            raise

    async def generate_response(
        self,
        messages: List[Message],
        response_model: Optional[type[BaseModel]] = None,
        max_tokens: Optional[int] = None,
        model_size: ModelSize = ModelSize.medium,
        group_id: Optional[str] = None,
        prompt_name: Optional[str] = None,
        *,
        attribute_extraction: bool = False,
    ) -> Dict[str, Any]:
        """Génère une réponse avec cadrage impératif contre l'écho de schémas JSON."""
        self._apply_attribute_extraction_preamble(messages, attribute_extraction)
        if max_tokens is None:
            max_tokens = self.max_tokens

        # En mode json_object, injecter le schéma en guidant le modèle pour ne jamais renvoyer le schéma brut
        if response_model is not None and self.structured_output_mode == "json_object":
            serialized_model = json.dumps(response_model.model_json_schema())
            instruction = (
                f"\n\nRespond with a JSON object in the following format:\n\n{serialized_model}\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "- Return ONLY a valid JSON data instance conforming to the format above, NEVER the schema itself.\n"
                "- Do NOT output schema metadata keywords like '$defs', 'properties', 'title', 'type', or '$ref'.\n"
                "- If no items or entities match the text, return empty collections or default values "
                '(e.g. {"extracted_entities": []}).'
            )
            if "Respond with a JSON object in the following format:" not in messages[-1].content:
                messages[-1].content += instruction

        lang_instruction = get_extraction_language_instruction(group_id)
        if lang_instruction and lang_instruction not in messages[0].content:
            messages[0].content += lang_instruction

        with self.tracer.start_span("llm.generate") as span:
            attributes = {
                "llm.provider": "openai",
                "model.size": model_size.value,
                "max_tokens": max_tokens,
            }
            if prompt_name:
                attributes["prompt.name"] = prompt_name
            span.add_attributes(attributes)

            try:
                return await self._generate_response_with_retry(
                    messages, response_model, max_tokens=max_tokens, model_size=model_size
                )
            except Exception as e:
                span.set_status("error", str(e))
                span.record_exception(e)
                raise
