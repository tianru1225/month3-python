import json
import math
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.config import settings
from app.providers.contracts import (
    Capability,
    ModelProvider,
    ModelRequest,
    ModelResult,
    ModelUsage,
)
from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderExecutionError,
    ProviderGenerationTimeoutError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.schemas.chat import ChatMessage
from app.schemas.llm_stream import (
    DoneEvent,
    StreamEvent,
    TextDeltaEvent,
    UsageEvent,
)


class QwenAdapter:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        configured_key = settings.dashscope_api_key if api_key is None else api_key
        if not configured_key.strip():
            raise ValueError("DASHSCOPE_API_KEY must not be empty")

        self._client = client
        self._api_key = configured_key
        self._base_url = settings.qwen_base_url if base_url is None else base_url
        self._timeout = timeout or httpx.Timeout(
            connect=settings.qwen_connect_timeout_seconds,
            read=settings.qwen_read_timeout_seconds,
            write=settings.qwen_write_timeout_seconds,
            pool=settings.qwen_pool_timeout_seconds,
        )
        self._provider = ModelProvider(
            name="qwen",
            capabilities=frozenset(
                {
                    Capability.CHAT,
                    Capability.STREAMING,
                    Capability.STRUCTURED_OUTPUT,
                    Capability.USAGE,
                }
            ),
            complete=self._complete,
            stream=self._stream,
        )

    @property
    def provider(self) -> ModelProvider:
        return self._provider

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        request: ModelRequest,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [message.model_dump() for message in request.messages],
            "stream": stream,
        }

        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "schema": request.response_schema,
                    "strict": True,
                },
            }
        if stream:
            payload["stream_options"] = {"include_usage": True}

        return payload

    async def _complete(self, request: ModelRequest) -> ModelResult:
        try:
            response = await self._client.post(
                f"{self._base_url.rstrip('/')}/chat/completions",
                headers=self._headers(),
                json=self._build_payload(request, stream=False),
                timeout=self._timeout,
            )
        except httpx.ReadTimeout as exc:
            raise ProviderGenerationTimeoutError(provider="qwen") from exc
        except (httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
            raise ProviderTimeoutError(provider="qwen") from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(provider="qwen") from exc

        self._raise_for_status(response)

        try:
            body = response.json()
            choice = body["choices"][0]
            message = choice["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError(
                "Qwen response does not match the chat completion shape"
            ) from exc

        if not isinstance(content, str):
            raise ValueError("Qwen message content must be a string")

        structured_output: dict[str, Any] | None = None
        if request.response_schema is not None:
            structured_output = self._parse_structured_output(content)

        return ModelResult(
            provider="qwen",
            model=body.get("model", request.model),
            message=ChatMessage(
                role=message["role"],
                content=content,
            ),
            finish_reason=choice.get("finish_reason"),
            usage=self._build_usage(body.get("usage")),
            structured_output=structured_output,
        )

    async def _stream(self, request: ModelRequest) -> AsyncGenerator[StreamEvent, None]:
        finish_reason: str | None = None
        usage: ModelUsage | None = None

        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url.rstrip('/')}/chat/completions",
                headers=self._headers(),
                json=self._build_payload(request, stream=True),
                timeout=self._timeout,
            ) as response:
                self._raise_for_status(response)

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue

                    data = line[5:].strip()
                    if data == "[DONE]":
                        break

                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise ValueError("Qwen stream event is not valid JSON") from exc

                    if not isinstance(payload, dict):
                        raise ValueError("Qwen stream event must be an object")
                    if "error" in payload:
                        raise ValueError("Qwen stream returned an error event")
                    if payload.get("usage") is not None:
                        usage = self._build_usage(payload["usage"])

                    choices = payload.get("choices", [])
                    if not isinstance(choices, list):
                        raise ValueError("Qwen stream choices must be a list")
                    if not choices:
                        continue

                    choice = choices[0]
                    if not isinstance(choice, dict):
                        raise ValueError("Qwen stream choice must be an object")

                    delta = choice.get("delta", {})
                    if not isinstance(delta, dict):
                        raise ValueError("Qwen stream delta must be an object")

                    content = delta.get("content")
                    if content is not None:
                        if not isinstance(content, str):
                            raise ValueError("Qwen stream content must be a string")
                        if content:
                            yield TextDeltaEvent(text=content)

                    chunk_finish_reason = choice.get("finish_reason")
                    if chunk_finish_reason is not None:
                        if not isinstance(chunk_finish_reason, str):
                            raise ValueError("Qwen finish_reason must be a string")
                        finish_reason = chunk_finish_reason
        except httpx.ReadTimeout as exc:
            raise ProviderGenerationTimeoutError(provider="qwen") from exc
        except (httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
            raise ProviderTimeoutError(provider="qwen") from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(provider="qwen") from exc

        if finish_reason is None:
            raise ValueError("Qwen stream ended without a finish reason")

        if usage is not None:
            yield UsageEvent(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_input_tokens=usage.cached_input_tokens,
            )
        yield DoneEvent(finish_reason=finish_reason)

    @classmethod
    def _raise_for_status(cls, response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = response.status_code
            if status_code in {401, 403}:
                raise ProviderAuthenticationError(provider="qwen") from exc
            if status_code == 429:
                raise ProviderRateLimitError(
                    provider="qwen",
                    retry_after_seconds=cls._parse_retry_after(
                        response.headers.get("Retry-After")
                    ),
                ) from exc
            if status_code >= 500:
                raise ProviderUnavailableError(provider="qwen") from exc
            raise ProviderExecutionError(provider="qwen") from exc

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            return None

        try:
            seconds = float(normalized)
        except ValueError:
            seconds = -1.0

        if math.isfinite(seconds) and seconds >= 0:
            return seconds

        try:
            retry_at = parsedate_to_datetime(normalized)
        except (TypeError, ValueError, OverflowError):
            return None

        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        return max(0.0, (retry_at - now).total_seconds())

    @staticmethod
    def _parse_structured_output(content: str) -> dict[str, Any]:
        try:
            parsed: object = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("Qwen structured response is not valid JSON") from exc

        if not isinstance(parsed, dict):
            raise ValueError("Qwen structured response must be a JSON object")
        return parsed

    @staticmethod
    def _build_usage(usage: object) -> ModelUsage | None:
        if usage is None:
            return None
        if not isinstance(usage, dict):
            raise ValueError("Qwen usage must be an object")

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        prompt_details = usage.get("prompt_tokens_details", {})
        cached_tokens = 0

        if isinstance(prompt_details, dict):
            cached_tokens = prompt_details.get("cached_tokens", 0)

        return ModelUsage(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            cached_input_tokens=cached_tokens,
        )
