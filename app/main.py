import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.core.limiter import limiter
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.debug import router as debug_router
from app.routers.health import router as health_router
from app.routers.items import router as items_router
from app.routers.materials import router as materials_router
from app.routers.projects import router as projects_router
from app.routers.rq_tasks import router as rq_tasks_router
from app.routers.tasks import router as tasks_router
from app.routers.users import router as users_router
from app.routers.project_materials import router as project_materials_router
from app.routers.knowledge_nodes import router as knowledge_nodes_router

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
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,  # type: ignore[arg-type]
)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    start = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or uuid4().hex[:8]
    request.state.request_id = request_id
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "[Day084][%s] %s %s -> %s (%.2f ms) client=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request.client.host if request.client else "-",
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
app.include_router(projects_router)
app.include_router(materials_router)
app.include_router(tasks_router)
app.include_router(rq_tasks_router)
app.include_router(items_router)
app.include_router(debug_router)
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(project_materials_router)
app.include_router(knowledge_nodes_router)
