from fastapi import APIRouter,BackgroundTasks,status
from pydantic import BaseModel
from app.tasks.audit import write_audit_log

router = APIRouter(prefix="/tasks",tags=["tasks"])
class AuditEvent(BaseModel):
    event: str
@router.post(
    "/audit",
    status_code = status.HTTP_202_ACCEPTED,
)
def create_audit_event(payload: AuditEvent,background_tasks: BackgroundTasks):
    background_tasks.add_task(write_audit_log,payload.event)
    return{
        "status":"accepted",
        "event": payload.event,
    }
