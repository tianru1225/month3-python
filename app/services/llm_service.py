import json

import httpx
from pydantic import BaseModel,ValidationError

from app.config import settings
from app.schemas.chat import ChatMessage,ChatResult
from app.services.errors import LLMUpstreamError


class _OllamaChatResponse(BaseModel):
    model: str
    message: ChatMessage
    done_reason: str | None = None


async def _chat_with_client(messages: list[ChatMessage],*,client: httpx.AsyncClient) -> ChatResult:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"

    payload = {
        "model":settings.ollama_model,
        "messages": [message.model_dump() for message in messages],
        "stream": False,
        "options": {
            "num_ctx": settings.ollama_num_ctx,
            "num_predict": settings.ollama_num_predict,
        },
    }

    timeout = httpx.Timeout(
        connect=settings.ollama_connect_timeout_seconds,
        read = settings.ollama_read_timeout_seconds,
        write=30.0,
        pool = 10.0,
    )

    try:
        response = await client.post(
            url,
            json = payload,
            timeout = timeout,
        )
        response.raise_for_status()
        upstream = _OllamaChatResponse.model_validate(response.json())
    except(
     httpx.HTTPError,
     json.JSONDecodeError,
     ValidationError,   
    ) as exc:
        raise LLMUpstreamError("LLM upstream request failed") from exc

    return ChatResult(
        model = upstream.model,
        message = upstream.message,
        finish_reason = upstream.done_reason,
    )


async def chat_with_llm(messages: list[ChatMessage],*,client: httpx.AsyncClient | None = None) -> ChatResult:
    if client is not None:
        return await _chat_with_client(messages,client = client)
    async with httpx.AsyncClient() as owned_client:
        return await _chat_with_client(messages,client=owned_client)
