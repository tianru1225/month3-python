from fastapi import APIRouter,Depends,HTTPException,Request,status

from app.core.limiter import limiter
from app.deps.auth import verify_api_key
from app.schemas.item import ItemCreate,ItemResponse

router = APIRouter(tags=["items"])

@router.post(
    "/items",
    tags=["items"],
    response_model=ItemResponse,
    summary="创建演示条目",
    description="需要有效 API Key。请求体由 Pydantic 校验，限流命中时返回 429。",
    responses={
        401:{"description":"API Key缺失或错误"},
        422: {"description": "请求体字段校验失败(由Pydantic自动触发)"},
        429: {"description": "请求过于频繁"},
    },
)
@limiter.limit("2/minute")
def create_item(request: Request,item: ItemCreate,_: str = Depends(verify_api_key)):
    return {
        "name": item.name,
        "price": item.price,
        "message": "day70 ok",
    }
@router.get(
    "/items/{item_id}",
    tags=["items"],
    summary="查询演示条目",
    description="需要有效 API Key。目前只有 item_id=1 返回演示数据，其他 ID 返回 ITEM_NOT_FOUND。",
    responses={
        401: {"description":"API Key 缺失或错误"},
        404: {"description": "条目不存在"},
        429: {"description": "请求过于频繁"},
    },
)
@limiter.limit("2/minute")
def get_item(request: Request,item_id: int,_: str = Depends(verify_api_key)):
    if item_id!=1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ITEM_NOT_FOUND",
                "message": f"item {item_id} not found",
            }
        )
    return {"item_id": item_id, "name": "demo-item"}
