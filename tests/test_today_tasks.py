from datetime import date, timedelta

from sqlalchemy import select

from app.models.user import User
from app.schemas.learning_plan import PlanCreate, PlanVersionCreate
from app.schemas.learning_task import LearningTaskCreate
from app.services import learning_plan_service, learning_task_service


def _login(client, username: str) -> dict[str, str]:
    password = "day143-test-password"
    assert (
        client.post(
            "/users", json={"username": username, "password": password}
        ).status_code
        == 201
    )
    response = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _payload(position: int, scheduled_date: date) -> LearningTaskCreate:
    return LearningTaskCreate(
        position=position,
        scheduled_date=scheduled_date,
        title=f"Day143 task {position}",
        objective=f"Objective {position}",
        instructions=f"Instructions {position}",
        steps=[f"Step {position}"],
        estimated_minutes=30,
        deliverable=f"Deliverable {position}",
        acceptance_criteria=[f"Criterion {position}"],
    )


def _context(client, db, username: str):
    headers = _login(client, username)
    project = client.post(
        "/projects",
        headers=headers,
        json={
            "name": f"{username} project",
            "goal": "test today's tasks",
            "current_level": "beginner",
        },
    ).json()
    user = db.scalar(select(User).where(User.username == username))
    assert user is not None
    plan, version = learning_plan_service.create_plan_with_first_draft(
        db,
        project_id=project["id"],
        user_id=user.id,
        payload=PlanCreate(name="Day143 plan", goal="query tasks", content={}),
    )
    start = date(2026, 9, 28)
    first = learning_task_service.create_task(
        db,
        plan_version_id=version.id,
        user_id=user.id,
        payload=_payload(1, start),
    )
    second = learning_task_service.create_task(
        db,
        plan_version_id=version.id,
        user_id=user.id,
        payload=_payload(2, start),
    )
    third = learning_task_service.create_task(
        db,
        plan_version_id=version.id,
        user_id=user.id,
        payload=_payload(3, start + timedelta(days=1)),
    )
    learning_task_service.add_task_prerequisite(
        db,
        plan_version_id=version.id,
        task_id=second.id,
        prerequisite_task_id=first.id,
        user_id=user.id,
    )
    learning_plan_service.publish_version(
        db, plan_id=plan.id, version_id=version.id, user_id=user.id
    )
    return headers, project["id"], version.id, first.id, second.id, third.id, plan.id


def test_returns_tasks_and_prerequisite_state(client, db_session):
    headers, project_id, version_id, first_id, second_id, third_id, _ = _context(
        client, db_session, "day143-query"
    )
    response = client.get(
        f"/projects/{project_id}/plan-versions/{version_id}/today-tasks",
        params={"target_date": "2026-09-28"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert [task["id"] for task in body["tasks"]] == [first_id, second_id]
    assert body["tasks"][0]["prerequisites_complete"] is True
    assert body["tasks"][1]["prerequisites"] == [
        {"task_id": first_id, "status": "DRAFT"}
    ]
    assert body["tasks"][1]["prerequisites_complete"] is False
    assert third_id not in [task["id"] for task in body["tasks"]]


def test_boundary_date_returns_empty(client, db_session):
    headers, project_id, version_id, *_ = _context(
        client, db_session, "day143-boundary"
    )
    response = client.get(
        f"/projects/{project_id}/plan-versions/{version_id}/today-tasks",
        params={"target_date": "2026-10-01"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["tasks"] == []


def test_draft_version_is_not_queryable(client, db_session):
    headers, project_id, _, *_rest, plan_id = _context(
        client, db_session, "day143-draft"
    )
    user = db_session.scalar(select(User).where(User.username == "day143-draft"))
    assert user is not None
    draft = learning_plan_service.create_next_draft(
        db_session,
        plan_id=plan_id,
        user_id=user.id,
        payload=PlanVersionCreate(goal="draft", content={}),
    )
    response = client.get(
        f"/projects/{project_id}/plan-versions/{draft.id}/today-tasks",
        params={"target_date": "2026-09-28"},
        headers=headers,
    )
    assert response.status_code == 404


def test_owner_and_auth_boundaries(client, db_session):
    _, project_id, version_id, *_ = _context(client, db_session, "day143-owner")
    other_headers = _login(client, "day143-other")
    response = client.get(
        f"/projects/{project_id}/plan-versions/{version_id}/today-tasks",
        params={"target_date": "2026-09-28"},
        headers=other_headers,
    )
    assert response.status_code == 404
    anonymous = client.get(
        f"/projects/{project_id}/plan-versions/{version_id}/today-tasks",
        params={"target_date": "2026-09-28"},
    )
    assert anonymous.status_code == 401


def test_invalid_date_returns_422(client):
    headers = _login(client, "day143-invalid-date")
    response = client.get(
        "/projects/1/plan-versions/1/today-tasks",
        params={"target_date": "not-a-date"},
        headers=headers,
    )
    assert response.status_code == 422
