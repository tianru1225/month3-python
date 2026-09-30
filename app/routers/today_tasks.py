from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps.auth import get_current_user
from app.deps.db import get_db
from app.models.user import User
from app.schemas.today_task import TodayTasksResponse
from app.services.today_task_service import list_today_tasks_or_raise

router = APIRouter(prefix="/projects", tags=["today-tasks"])


@router.get(
    "/{project_id}/plan-versions/{plan_version_id}/today-tasks",
    response_model=TodayTasksResponse,
    summary="查询指定日期的学习任务",
)
def list_today_tasks(
    project_id: int,
    plan_version_id: int,
    target_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TodayTasksResponse:
    return list_today_tasks_or_raise(
        db,
        project_id=project_id,
        plan_version_id=plan_version_id,
        user_id=current_user.id,
        target_date=target_date,
    )
