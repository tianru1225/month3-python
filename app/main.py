import logging
import time
import uuid

from fastapi import FastAPI, Request
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

from app.config import settings
from app.core.limiter import limiter
from app.routers.health import router as health_router
from app.routers.users import router as users_router
from app.routers.tasks import router as tasks_router
from app.routers.rq_tasks import router as rq_tasks_router
from app.routers.debug import router as debug_router
from app.routers.items import router as items_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("app.access")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded,_rate_limit_exceeded_handler) #type: ignore[arg-type] # slowapi handler 签名比 Starlette 要求更窄，运行时安全
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    client_ip = request.client.host if request.client else "-"

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception(
            "[%s] %s %s -> 500 (%.2f ms) client=%s",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
            client_ip,
        )
        raise

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id

    logger.info(
        "[DAY068][%s] %s %s -> %d (%.2f ms) client=%s",
        request_id,
        request.method,
        request.url.path,
        status_code,
        duration_ms,
        client_ip,
    )
    return response


@app.get("/")
def read_root():
    return {
        "message": "day70 ok",
        "app_name": settings.app_name,
        "app_env": settings.app_env,
        "debug": settings.app_debug,
    }


app.include_router(health_router)
app.include_router(users_router)
app.include_router(tasks_router)
app.include_router(rq_tasks_router)
app.include_router(items_router)
app.include_router(debug_router)