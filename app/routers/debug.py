from fastapi import APIRouter,HTTPException,status

router = APIRouter(tags=["debug"])

@router.get(
    "/boom",
    tags=["debug"],
    summary="触发演示异常",
    description="用于验证统一异常响应格式，固定返回 418 TEAPOT。",
    responses={
        418: {"description":"Day066 teapot demo"},
    },
)
def boom():
    raise HTTPException(
        status_code=status.HTTP_418_IM_A_TEAPOT,
        detail={
            "code": "TEAPOT",
            "message": "day66 teapot",
        },
    )
