from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import Evidence
from app.models.learning_plan import LearningPlan, PlanVersion
from app.models.learning_task import LearningTask, TaskStatus
from app.models.user import User
from app.schemas.learning_plan import PlanCreate
from app.schemas.learning_task import LearningTaskCreate
from app.services import learning_plan_service, learning_task_service


def login(client: TestClient, username: str) -> dict[str, str]:
    password = "day144-password"
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


def context(
    client: TestClient,
    db: Session,
    username: str,
    *,
    activate: bool = True,
) -> tuple[dict[str, str], User, LearningPlan, PlanVersion, LearningTask]:
    headers = login(client, username)
    project_response = client.post(
        "/projects",
        headers=headers,
        json={
            "name": f"{username} project",
            "goal": "verify evidence acceptance",
            "current_level": "beginner",
        },
    )
    assert project_response.status_code == 201
    user = db.scalar(select(User).where(User.username == username))
    assert user is not None
    plan, version = learning_plan_service.create_plan_with_first_draft(
        db,
        project_id=project_response.json()["id"],
        user_id=user.id,
        payload=PlanCreate(
            name=f"{username} plan",
            goal="submit evidence",
            content={},
        ),
    )
    task = learning_task_service.create_task(
        db,
        plan_version_id=version.id,
        user_id=user.id,
        payload=LearningTaskCreate(
            position=1,
            title="Evidence task",
            objective="Submit evidence",
            instructions="Complete and submit",
            steps=["complete"],
            estimated_minutes=20,
            deliverable="answer",
            acceptance_criteria=["accepted"],
        ),
    )
    if activate:
        learning_plan_service.publish_version(
            db, plan_id=plan.id, version_id=version.id, user_id=user.id
        )
        for target in (TaskStatus.READY, TaskStatus.IN_PROGRESS):
            task = learning_task_service.transition_task_status(
                db,
                plan_version_id=version.id,
                task_id=task.id,
                user_id=user.id,
                target_status=target,
            )
    return headers, user, version, task


def submit(
    client: TestClient,
    headers: dict[str, str],
    version_id: int,
    task_id: int,
    payload: dict[str, object],
):
    return client.post(
        f"/plan-versions/{version_id}/tasks/{task_id}/evidence",
        headers=headers,
        json=payload,
    )


def evaluate(
    client: TestClient,
    headers: dict[str, str],
    version_id: int,
    task_id: int,
):
    return client.post(
        f"/plan-versions/{version_id}/tasks/{task_id}/evaluate",
        headers=headers,
    )


def test_text_answer_passes(client: TestClient, db_session: Session) -> None:
    headers, _, version, task = context(client, db_session, "day144-text")
    response = submit(
        client,
        headers,
        version.id,
        task.id,
        {"evidence_type": "TEXT_ANSWER", "text_content": "已完成并验证。"},
    )
    assert response.status_code == 201
    assert response.json()["source_kind"] == "USER"
    result = evaluate(client, headers, version.id, task.id)
    assert result.status_code == 200
    assert result.json()["evaluation"]["rule_status"] == "PASS"
    assert result.json()["task_status"] == "PASSED"


def test_test_report_failure_then_success(
    client: TestClient, db_session: Session
) -> None:
    headers, user, version, task = context(client, db_session, "day144-report")
    failed = submit(
        client,
        headers,
        version.id,
        task.id,
        {
            "evidence_type": "TEST_REPORT",
            "test_report": {
                "command": "python -c 'raise SystemExit(99)'",
                "exit_code": 1,
                "summary": "失败",
                "checks": [{"name": "tests", "status": "FAILED"}],
            },
        },
    )
    assert failed.status_code == 201
    assert (
        evaluate(client, headers, version.id, task.id).json()["task_status"]
        == "REVISION_REQUIRED"
    )

    learning_task_service.transition_task_status(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        user_id=user.id,
        target_status=TaskStatus.IN_PROGRESS,
    )
    passed = submit(
        client,
        headers,
        version.id,
        task.id,
        {
            "evidence_type": "TEST_REPORT",
            "test_report": {
                "command": "pytest -q",
                "exit_code": 0,
                "summary": "通过",
                "checks": [{"name": "tests", "status": "PASSED"}],
            },
        },
    )
    assert passed.status_code == 201
    result = evaluate(client, headers, version.id, task.id)
    assert result.json()["evaluation"]["rule_status"] == "PASS"
    assert result.json()["task_status"] == "PASSED"


def test_retry_keeps_first_attempt(client: TestClient, db_session: Session) -> None:
    headers, user, version, task = context(client, db_session, "day144-retry")
    first = submit(
        client,
        headers,
        version.id,
        task.id,
        {
            "evidence_type": "TEST_REPORT",
            "test_report": {
                "command": "pytest -q",
                "exit_code": 1,
                "summary": "失败",
                "checks": [{"name": "tests", "status": "FAILED"}],
            },
        },
    )
    assert first.status_code == 201
    assert (
        evaluate(client, headers, version.id, task.id).json()["task_status"]
        == "REVISION_REQUIRED"
    )
    learning_task_service.transition_task_status(
        db_session,
        plan_version_id=version.id,
        task_id=task.id,
        user_id=user.id,
        target_status=TaskStatus.IN_PROGRESS,
    )
    second = submit(
        client,
        headers,
        version.id,
        task.id,
        {"evidence_type": "TEXT_ANSWER", "text_content": "修正后通过。"},
    )
    assert second.status_code == 201
    assert second.json()["attempt_number"] == 2
    assert (
        evaluate(client, headers, version.id, task.id).json()["task_status"] == "PASSED"
    )
    rows = list(
        db_session.scalars(
            select(Evidence)
            .where(Evidence.task_id == task.id)
            .order_by(Evidence.attempt_number)
        ).all()
    )
    assert [row.attempt_number for row in rows] == [1, 2]


def test_draft_and_ready_reject_evidence(
    client: TestClient, db_session: Session
) -> None:
    headers, user, version, task = context(
        client, db_session, "day144-draft-ready", activate=False
    )
    draft = submit(
        client,
        headers,
        version.id,
        task.id,
        {"evidence_type": "TEXT_ANSWER", "text_content": "too early"},
    )
    assert draft.status_code == 409
    assert draft.json()["detail"]["code"] == "PLAN_VERSION_NOT_ACTIVE"
    learning_plan_service.publish_version(
        db_session,
        plan_id=version.plan_id,
        version_id=version.id,
        user_id=user.id,
    )
    ready = submit(
        client,
        headers,
        version.id,
        task.id,
        {"evidence_type": "TEXT_ANSWER", "text_content": "still too early"},
    )
    assert ready.status_code == 409
    assert ready.json()["detail"]["code"] == "TASK_NOT_ACCEPTING_EVIDENCE"


def test_state_gates_and_passed_is_immutable(
    client: TestClient, db_session: Session
) -> None:
    headers, _, version, task = context(client, db_session, "day144-state")
    no_evidence = evaluate(client, headers, version.id, task.id)
    assert no_evidence.status_code == 409
    assert no_evidence.json()["detail"]["code"] == "EVIDENCE_NOT_SUBMITTED"
    assert (
        submit(
            client,
            headers,
            version.id,
            task.id,
            {"evidence_type": "TEXT_ANSWER", "text_content": "通过"},
        ).status_code
        == 201
    )
    assert (
        evaluate(client, headers, version.id, task.id).json()["task_status"] == "PASSED"
    )
    again = submit(
        client,
        headers,
        version.id,
        task.id,
        {"evidence_type": "TEXT_ANSWER", "text_content": "再次提交"},
    )
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "TASK_NOT_ACCEPTING_EVIDENCE"


def test_invalid_payload_and_source_override(
    client: TestClient, db_session: Session
) -> None:
    headers, _, version, task = context(client, db_session, "day144-input")
    assert (
        submit(
            client,
            headers,
            version.id,
            task.id,
            {"evidence_type": "TEXT_ANSWER", "text_content": " "},
        ).status_code
        == 422
    )
    assert (
        submit(
            client,
            headers,
            version.id,
            task.id,
            {
                "evidence_type": "TEST_REPORT",
                "test_report": {
                    "command": "pytest",
                    "exit_code": 0,
                    "summary": "empty",
                    "checks": [],
                },
            },
        ).status_code
        == 422
    )
    assert (
        submit(
            client,
            headers,
            version.id,
            task.id,
            {"evidence_type": "UNKNOWN", "text_content": "bad"},
        ).status_code
        == 422
    )
    spoofed = submit(
        client,
        headers,
        version.id,
        task.id,
        {
            "evidence_type": "TEXT_ANSWER",
            "text_content": "服务端固定来源",
            "source_kind": "AUTOMATION",
            "source_ref": "client",
        },
    )
    assert spoofed.status_code == 201
    assert spoofed.json()["source_kind"] == "USER"
    assert spoofed.json()["source_ref"] is None


def test_authentication_and_ownership(client: TestClient, db_session: Session) -> None:
    owner_headers, _, version, task = context(client, db_session, "day144-owner")
    anonymous = submit(
        client,
        {},
        version.id,
        task.id,
        {"evidence_type": "TEXT_ANSWER", "text_content": "anonymous"},
    )
    assert anonymous.status_code == 401
    outsider = submit(
        client,
        login(client, "day144-outsider"),
        version.id,
        task.id,
        {"evidence_type": "TEXT_ANSWER", "text_content": "cross user"},
    )
    assert outsider.status_code == 404
    assert outsider.json()["detail"]["code"] == "PLAN_VERSION_NOT_FOUND"
    assert (
        submit(
            client,
            owner_headers,
            version.id,
            task.id,
            {"evidence_type": "TEXT_ANSWER", "text_content": "owner"},
        ).status_code
        == 201
    )
