from fastapi import APIRouter,Request
from app.core.limiter import limiter
from app.utils.response import ok

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    tags = ["health"],
    summary="健康检查(目前是占位状态)",
    description = "将要增添的功能:存活探针,返回200表示服务在线,供负载均衡/监控探测",
    )
@limiter.limit("3/minute")
def health_check(request: Request):
    return ok({"status":"ok","source":"router"})
