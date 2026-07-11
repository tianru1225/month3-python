from fastapi import APIRouter,BackgroundTasks,status
from pydantic import BaseModel
from app.tasks.audit import write_audit_log
from app.utils.response import ok

router = APIRouter(prefix="/tasks",tags=["tasks"])
class AuditEvent(BaseModel):
    event: str
@router.post(
    "/audit",
    status_code = status.HTTP_202_ACCEPTED,
    summary="写入审计日志",
    description="使用 FastAPI BackgroundTasks 在响应返回后写入本地审计日志。该任务绑定当前 Web 进程,不具备 RQ 那样的持久化队列能力。",
    responses={
        202: {"description": "审计事件已接收,后台写入日志"},
    },
)
def create_audit_event(payload: AuditEvent,background_tasks: BackgroundTasks):
    background_tasks.add_task(write_audit_log,payload.event)
    return ok({
        "status":"accepted",
        "event": payload.event,
    })
