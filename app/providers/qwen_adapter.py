import json
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
from app.schemas.chat import ChatMessage


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
                    Capability.STRUCTURED_OUTPUT,
                    Capability.USAGE,
                }
            ),
            complete=self._complete,
        )

    @property
    def provider(self) -> ModelProvider:
        return self._provider

    def _build_payload(
        self,
        request: ModelRequest,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [message.model_dump() for message in request.messages],
            "stream": False,
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

        return payload

    async def _complete(
        self,
        request: ModelRequest,
    ) -> ModelResult:
        response = await self._client.post(
            f"{self._base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=self._build_payload(request),
            timeout=self._timeout,
        )
        response.raise_for_status()

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

        usage = self._build_usage(body.get("usage"))

        structured_output: dict[str, Any] | None = None

        if request.response_schema is not None:
            try:
                parsed: object = json.loads(content)
            except json.JSONDecodeError as exc:
                raise ValueError("Qwen structured response is not valid JSON") from exc

            if not isinstance(parsed, dict):
                raise ValueError("Qwen structured response must be a JSON object")

            structured_output = parsed

        return ModelResult(
            provider="qwen",
            model=body.get("model", request.model),
            message=ChatMessage(
                role=message["role"],
                content=content,
            ),
            finish_reason=choice.get("finish_reason"),
            usage=usage,
            structured_output=structured_output,
        )

    @staticmethod
    def _build_usage(
        usage: object,
    ) -> ModelUsage | None:
        if usage is None:
            return None

        if not isinstance(usage, dict):
            raise ValueError("Qwen usage must be an object")

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        prompt_details = usage.get(
            "prompt_tokens_details",
            {},
        )

        cached_tokens = 0

        if isinstance(prompt_details, dict):
            cached_tokens = prompt_details.get(
                "cached_tokens",
                0,
            )

        return ModelUsage(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            cached_input_tokens=cached_tokens,
        )
