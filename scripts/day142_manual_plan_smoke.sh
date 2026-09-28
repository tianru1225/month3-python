#!/usr/bin/env bash
set -euo pipefail
umask 077

USERNAME="${SMOKE_USERNAME:?Set SMOKE_USERNAME to the Day141 account}"
PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to the Day141 project}"
export SMOKE_USERNAME PROJECT_ID

docker compose exec -T \
  -e SMOKE_USERNAME="$SMOKE_USERNAME" \
  -e PROJECT_ID="$PROJECT_ID" \
  api python - <<'PY'
import json
import os
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.learning_project import LearningProject
from app.models.learning_task import TaskStatus
from app.models.user import User
from app.schemas.learning_plan import PlanCreate
from app.schemas.learning_task import LearningTaskCreate
from app.services import learning_plan_service, learning_task_service
from app.services.material_gate import require_ready_materials_or_raise
from app.services.material_service import MATERIAL_STORAGE_DIR


def task_payload(
    *,
    position: int,
    scheduled_date: date,
    title: str,
    objective: str,
    instructions: str,
    deliverable: str,
) -> LearningTaskCreate:
    return LearningTaskCreate(
        position=position,
        scheduled_date=scheduled_date,
        title=title,
        objective=objective,
        instructions=instructions,
        steps=[f"Read the relevant section", f"Write a small example for task {position}"],
        estimated_minutes=45,
        deliverable=deliverable,
        acceptance_criteria=[
            "The learner can explain the main idea in their own words",
            "The learner can provide a runnable small example",
        ],
    )


username = os.environ["SMOKE_USERNAME"]
project_id = int(os.environ["PROJECT_ID"])

with SessionLocal() as db:
    user = db.scalar(select(User).where(User.username == username))
    assert user is not None, "Day141 user was not found"

    project = db.get(LearningProject, project_id)
    assert project is not None, "project was not found"
    assert project.user_id == user.id, "project does not belong to the smoke user"

    ready_versions = require_ready_materials_or_raise(
        db,
        project_id=project.id,
        user_id=user.id,
        storage_dir=MATERIAL_STORAGE_DIR,
    )
    assert ready_versions, "READY material is required before creating a plan"
    material_version = ready_versions[0]
    assert material_version.content_hash
    assert material_version.source_metadata is not None

    source_snapshot = {
        "material_version_id": material_version.id,
        "original_filename": material_version.original_filename,
        "content_hash": material_version.content_hash,
        "normalized_format": material_version.normalized_format,
    }
    plan_content = {
        "source_materials": [source_snapshot],
        "schedule_policy": {
            "kind": "MANUAL",
            "description": "Fixed three-day sequence for Day142 verification",
        },
    }

    plan, draft = learning_plan_service.create_plan_with_first_draft(
        db,
        project_id=project.id,
        user_id=user.id,
        payload=PlanCreate(
            name=f"Python notes manual plan {date.today().isoformat()}",
            goal="Build a small Python foundation from the user's READY Markdown notes",
            content=plan_content,
        ),
    )
    assert draft.status == "DRAFT"
    assert draft.is_current is False
    assert draft.source_kind == "MANUAL"
    assert draft.provider_name is None
    assert draft.model_name is None

    start = date.today()
    task_one = learning_task_service.create_task(
        db,
        plan_version_id=draft.id,
        user_id=user.id,
        payload=task_payload(
            position=1,
            scheduled_date=start,
            title="Read the Python syntax section",
            objective="Explain variables, basic types, operators, and indentation",
            instructions="Read the corresponding notes and write a short explanation with examples",
            deliverable="A one-page syntax summary and three small examples",
        ),
    )
    task_two = learning_task_service.create_task(
        db,
        plan_version_id=draft.id,
        user_id=user.id,
        payload=task_payload(
            position=2,
            scheduled_date=start + timedelta(days=1),
            title="Practice collections and control flow",
            objective="Use lists, dictionaries, conditions, and loops in a small script",
            instructions="Implement a small script that reads data, branches, and aggregates a result",
            deliverable="One runnable collection-processing script",
        ),
    )
    task_three = learning_task_service.create_task(
        db,
        plan_version_id=draft.id,
        user_id=user.id,
        payload=task_payload(
            position=3,
            scheduled_date=start + timedelta(days=2),
            title="Practice functions and modules",
            objective="Explain function parameters, return values, and simple module organization",
            instructions="Refactor the previous exercise into two functions and describe the data flow",
            deliverable="A two-function Python exercise with a short explanation",
        ),
    )

    edge_two, created_two = learning_task_service.add_task_prerequisite(
        db,
        plan_version_id=draft.id,
        task_id=task_two.id,
        prerequisite_task_id=task_one.id,
        user_id=user.id,
    )
    edge_three, created_three = learning_task_service.add_task_prerequisite(
        db,
        plan_version_id=draft.id,
        task_id=task_three.id,
        prerequisite_task_id=task_two.id,
        user_id=user.id,
    )
    assert created_two is True
    assert created_three is True
    assert edge_two.plan_version_id == draft.id
    assert edge_three.plan_version_id == draft.id

    published = learning_plan_service.publish_version(
        db,
        plan_id=plan.id,
        version_id=draft.id,
        user_id=user.id,
    )
    assert published.status == "PUBLISHED"
    assert published.is_current is True
    assert published.published_at is not None
    assert published.confirmed_by_user_id == user.id
    assert published.rejection_reason is None

    current = learning_plan_service.get_current_published_version(
        db,
        plan_id=plan.id,
        user_id=user.id,
    )
    assert current is not None
    assert current.id == published.id

    versions = learning_plan_service.list_plan_versions(
        db,
        plan_id=plan.id,
        user_id=user.id,
    )
    assert [version.version_number for version in versions] == [1]
    assert versions[0].source_kind == "MANUAL"

    tasks = learning_task_service.list_version_tasks(
        db,
        plan_version_id=published.id,
        user_id=user.id,
    )
    assert [task.position for task in tasks] == [1, 2, 3]
    assert [task.status for task in tasks] == [TaskStatus.DRAFT.value] * 3
    assert [task.scheduled_date for task in tasks] == [
        start,
        start + timedelta(days=1),
        start + timedelta(days=2),
    ]

    try:
        learning_task_service.create_task(
            db,
            plan_version_id=published.id,
            user_id=user.id,
            payload=task_payload(
                position=4,
                scheduled_date=start + timedelta(days=3),
                title="Must be rejected after publish",
                objective="This task must not be added to a published version",
                instructions="This call exists only to verify the immutability gate",
                deliverable="No task should be persisted",
            ),
        )
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail["code"] == "PLAN_VERSION_IMMUTABLE"
    else:
        raise AssertionError("published plan version accepted a new task")

    print(
        json.dumps(
            {
                "result": "passed",
                "username": username,
                "user_id": user.id,
                "project_id": project.id,
                "material_version_id": material_version.id,
                "plan_id": plan.id,
                "plan_version_id": published.id,
                "version_number": published.version_number,
                "source_kind": published.source_kind,
                "status": published.status,
                "task_ids": [task_one.id, task_two.id, task_three.id],
                "task_dates": [
                    start.isoformat(),
                    (start + timedelta(days=1)).isoformat(),
                    (start + timedelta(days=2)).isoformat(),
                ],
                "prerequisite_edges": 2,
            },
            ensure_ascii=False,
        )
    )
PY