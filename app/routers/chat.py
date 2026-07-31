from fastapi import APIRouter,Depends,HTTPException

from app.deps.auth import verify_api_key
from app.schemas.chat import ChatRequest,ChatResult
from app.schemas.response import ApiResponse
from app.services.errors import LLMUpstreamError
from app.services.llm_service import chat_with_llm
from app.utils.response import ok

router = APIRouter(prefix = "/v1",tags=["chat"])


@router.post(
    "/chat",
    response_model = ApiResponse[ChatResult],
    dependencies=[Depends(verify_api_key)],
)

async def create_chat(payload: ChatRequest) -> ApiResponse[ChatResult]:
    try:
        result =await chat_with_llm(payload.messages)
    except LLMUpstreamError as exc:
        raise HTTPException(
            status_code = 502,
            detail={
                "code":"LLM_UPSTREAM_ERROR",
                "message":"LLM upstream request failed"
            }
        ) from exc
    return ok(result)