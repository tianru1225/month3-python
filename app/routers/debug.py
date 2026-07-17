from fastapi import APIRouter,HTTPException,status,Request,Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.deps.db import get_db
from app.utils.response import ok

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

@router.get(
    "/debug/request-id",
    summary="查看当前请求ID",
    description="返回当前请求在中间件中生成或接收的X-Request-ID",
)
def get_request_id(request: Request):
    return ok({"request_id":request.state.request_id})

@router.get(
    "/debug/db-ping",
    summary="检查数据库连接",
    description="执行最小SQL查询,用于验证数据库连接是否可用"
)
def db_ping(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DB_UNAVAILABLE",
                "message": "database unavailable",
            }
        )
    return ok({"database": "ok"})