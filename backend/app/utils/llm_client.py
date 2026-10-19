"""Client LLM MiroFish.

Appels unifiés au format OpenAI compatible.
"""

import json
import logging
import os
import re
import time
from typing import Optional, Dict, Any, List, Callable
from openai import OpenAI

from ..config import Config
from .llm_compat import llm_request_headers
from .openai_chat_compat import create_chat_completion, extract_chat_completion_text


logger = logging.getLogger(__name__)


class LLMResponseError(ValueError):
    """A safe, structured error for unusable model responses."""

    def __init__(self, message: str, *, finish_reason: Optional[str] = None):
        super().__init__(message)
        self.finish_reason = finish_reason


def _is_response_format_unsupported(error: Exception) -> bool:
    """Detect an explicit provider rejection of JSON response_format."""

    if getattr(error, "status_code", None) not in {400, 422}:
        return False

    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return False

    details = body.get("error", body)
    if not isinstance(details, dict):
        return False

    param = str(details.get("param") or "").strip().lower()
    if param == "response_format" or param.startswith("response_format."):
        return True

    message = str(details.get("message") or "").lower()
    if "response_format" not in message:
        return False

    code = str(details.get("code") or "").lower()
    unsupported_codes = {
        "unsupported_parameter",
        "unsupported_value",
        "unknown_parameter",
        "invalid_parameter",
    }
    unsupported_phrases = (
        "not support",
        "unsupported",
        "unknown parameter",
        "unrecognized parameter",
    )
    return code in unsupported_codes or any(
        phrase in message for phrase in unsupported_phrases
    )


def _clean_chat_text(content: str) -> str:
    """Remove common reasoning wrappers and an outer Markdown JSON fence."""
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
    cleaned = cleaned.lstrip("\ufeff")
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    return cleaned.strip()


def _contains_additional_json_container(content: str) -> bool:
    """Return True when trailing text embeds another JSON object or array."""

    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", content):
        try:
            value, _ = decoder.raw_decode(content[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, (dict, list)):
            return True
    return False


class LLMClient:
    """LLM客户端"""
    profile: Optional[Any] = None
    reasoning_effort: Optional[str] = None
    last_response: Any = None
    last_usage: Any = None
    usage_callback: Optional[Callable[..., Any]] = None
    pre_request_callback: Optional[Callable[..., Any]] = None
    request_timeout: Optional[float] = None
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        profile: Optional[Any] = None,
        usage_callback: Optional[Callable[..., Any]] = None,
        pre_request_callback: Optional[Callable[..., Any]] = None,
        request_timeout: Optional[float] = None,
    ):
        self.profile = profile
        if profile is not None:
            self.api_key = api_key or getattr(profile, "api_key", None) or os.environ.get("LLM_API_KEY") or Config.LLM_API_KEY
            self.base_url = base_url or getattr(profile, "base_url", None) or os.environ.get("LLM_BASE_URL") or Config.LLM_BASE_URL
            self.model = model or getattr(profile, "model", None) or os.environ.get("LLM_MODEL_NAME") or Config.LLM_MODEL_NAME
            self.reasoning_effort = (
                reasoning_effort
                if reasoning_effort is not None
                else getattr(profile, "reasoning_effort", None)
            )
        else:
            self.api_key = api_key or os.environ.get("LLM_API_KEY") or Config.LLM_API_KEY
            self.base_url = base_url or os.environ.get("LLM_BASE_URL") or Config.LLM_BASE_URL
            self.model = model or os.environ.get("LLM_MODEL_NAME") or Config.LLM_MODEL_NAME
            self.reasoning_effort = reasoning_effort
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers=llm_request_headers(self.base_url)
        )
        self.last_response: Any = None
        self.last_usage: Any = None
        self.usage_callback = usage_callback
        self.pre_request_callback = pre_request_callback
        self.request_timeout = request_timeout
        if request_timeout is not None:
            try:
                self.client.timeout = float(request_timeout)
            except Exception:
                pass

    def _create_completion(
        self,
        *,
        messages: List[Dict[str, str]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        response_format: Optional[Dict[str, Any]],
        reasoning_effort: Optional[str] = None,
    ) -> Any:
        """Send one raw Chat Completions request through the compatibility layer."""
        effort = reasoning_effort if reasoning_effort is not None else getattr(self, "reasoning_effort", None)
        # Garde-fou pré-requête (plafonds budget/temps). Cette exception doit
        # remonter : elle empêche la requête de partir (Story 013-4, AC4).
        pre_request = getattr(self, "pre_request_callback", None)
        if pre_request is not None:
            pre_request(model=self.model, reasoning_effort=effort)
        started = time.monotonic()
        resp = create_chat_completion(
            self.client,
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            reasoning_effort=effort,
            timeout=getattr(self, "request_timeout", None),
        )
        duration_seconds = max(0.0, time.monotonic() - started)
        self.last_response = resp
        self.last_usage = getattr(resp, "usage", None)

        # Télémétrie d'usage (Story 013-4). Le callback ne doit jamais casser la
        # requête LLM : une défaillance de mesure est journalisée et ignorée.
        callback = getattr(self, "usage_callback", None)
        if callback is not None:
            try:
                callback(
                    usage=self.last_usage,
                    model=self.model,
                    duration_seconds=duration_seconds,
                    reasoning_effort=effort,
                )
            except Exception as telemetry_error:  # pragma: no cover - défensif
                logger.warning(
                    "Échec non bloquant du callback de télémétrie LLM : %s",
                    telemetry_error,
                )
        return resp
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = 4096,
        response_format: Optional[Dict] = None,
        reasoning_effort: Optional[str] = None,
    ) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）
            reasoning_effort: niveau d'effort explicite optionnel (low, medium, high)
            
        Returns:
            模型响应文本
        """
        profile = getattr(self, "profile", None)
        if profile is not None:
            if getattr(profile, "temperature", None) is not None and temperature == 0.7:
                temperature = profile.temperature
            if getattr(profile, "max_tokens", None) is not None and max_tokens == 4096:
                max_tokens = profile.max_tokens

        response = self._create_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            reasoning_effort=reasoning_effort,
        )
        content = extract_chat_completion_text(response)
        return _clean_chat_text(content)
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = 4096,
        max_attempts: int = 1,
        reasoning_effort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            max_attempts: 内容生成尝试次数（不含一次明确的JSON模式能力降级）
            
        Returns:
            解析后的JSON对象
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

        profile = getattr(self, "profile", None)
        if profile is not None:
            if getattr(profile, "temperature", None) is not None and temperature == 0.3:
                temperature = profile.temperature
            if getattr(profile, "max_tokens", None) is not None and max_tokens == 4096:
                max_tokens = profile.max_tokens

        response_format: Optional[Dict[str, str]] = {"type": "json_object"}
        request_max_tokens = max_tokens
        last_error: Optional[LLMResponseError] = None

        for attempt in range(1, max_attempts + 1):
            # JSON-mode capability negotiation is separate from content
            # regeneration. An explicit response_format rejection may add one
            # request, but it must not consume a content attempt.
            while True:
                try:
                    response = self._create_completion(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=request_max_tokens,
                        response_format=response_format,
                        reasoning_effort=reasoning_effort,
                    )
                except Exception as error:
                    if (
                        response_format is not None
                        and _is_response_format_unsupported(error)
                    ):
                        logger.warning(
                            "LLM provider explicitly rejected response_format; "
                            "retrying once with prompt-only JSON guidance"
                        )
                        response_format = None
                        continue
                    raise
                break

            try:
                return self._parse_json_response(response)
            except LLMResponseError as error:
                last_error = error
                if attempt >= max_attempts:
                    raise

                # A caller-supplied cap is the common cause of a partial JSON
                # object. Omit it for the one bounded retry so the provider can
                # use its model-specific output limit.
                had_token_cap = request_max_tokens is not None
                request_max_tokens = None
                logger.warning(
                    "LLM returned unusable JSON (finish_reason=%s); "
                    "retrying content generation%s",
                    error.finish_reason or "unknown",
                    " without an output token cap" if had_token_cap else "",
                )

        if last_error is not None:  # pragma: no cover - defensive loop guard
            raise last_error
        raise LLMResponseError("LLM did not produce a JSON response")

    @staticmethod
    def _parse_json_response(response: Any) -> Dict[str, Any]:
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise LLMResponseError("LLM returned no choices")

        choice = choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason == "length":
            raise LLMResponseError(
                "LLM JSON output was truncated at the token limit",
                finish_reason=finish_reason,
            )
        if finish_reason not in {None, "stop"}:
            raise LLMResponseError(
                f"LLM JSON generation stopped unexpectedly ({finish_reason})",
                finish_reason=finish_reason,
            )

        content = _clean_chat_text(extract_chat_completion_text(response))
        if not content:
            raise LLMResponseError(
                "LLM returned empty JSON content",
                finish_reason=finish_reason,
            )

        try:
            value = json.loads(content)
        except json.JSONDecodeError as strict_error:
            # Some compatible providers append a short explanation after an
            # otherwise complete JSON object. Accept only an object decoded
            # from the beginning; never repair or invent truncated JSON.
            try:
                value, end = json.JSONDecoder().raw_decode(content)
            except json.JSONDecodeError:
                raise LLMResponseError(
                    "LLM returned invalid JSON "
                    f"(line {strict_error.lineno}, column {strict_error.colno})",
                    finish_reason=finish_reason,
                ) from strict_error

            trailing = content[end:].strip()
            if trailing:
                if _contains_additional_json_container(trailing):
                    raise LLMResponseError(
                        "LLM returned multiple JSON values",
                        finish_reason=finish_reason,
                    )
                logger.warning("Ignoring text after a complete LLM JSON object")

        if not isinstance(value, dict):
            raise LLMResponseError(
                "LLM JSON response must be a top-level JSON object",
                finish_reason=finish_reason,
            )

        return value
