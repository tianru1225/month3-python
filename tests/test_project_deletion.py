from datetime import date
from functools import partial

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.evaluation import Evaluation
from app.models.evidence import Evidence
from app.models.knowledge import KnowledgeNode
from app.models.learning_plan import LearningPlan, PlanVersion
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask, TaskStatus
from app.models.mastery import MasteryRecord, ReviewItem
from app.models.material import Material, MaterialVersion
from app.models.project_material import ProjectMaterialBinding
from app.models.replan import AuditEvent, ReplanProposal
from app.models.user import User
from app.schemas.learning_plan import PlanCreate, PlanVersionCreate
from app.schemas.learning_task import LearningTaskCreate
from app.services import (
    evaluation_service,
    learning_plan_service,
    learning_task_service,
    mastery_service,
    material_service,
    project_service,
    replan_service,
)


def _login(client, username: str) -> dict[str, str]:
    password = "project-deletion-test-password"
    assert client.post(
        "/users", json={"username": username, "password": password}
    ).status_code == 201
    response = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _project(client, headers, name: str) -> int:
    response = client.post("/projects", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _task_payload(position: int) -> LearningTaskCreate:
    return LearningTaskCreate(
        position=position,
        scheduled_date=date(2026, 10, 28),
        title=f"Deletion test task {position}",
        objective="Verify access to a retained task",
        instructions="Submit one text answer",
        steps=["write an answer"],
        estimated_minutes=20,
        deliverable="text answer",
        acceptance_criteria=["non-empty answer"],
    )


@pytest.fixture
def learning_context(client, db_session, tmp_path, monkeypatch):
    db = db_session
    headers = _login(client, "deletion-owner")
    user = db.scalar(select(User).where(User.username == "deletion-owner"))
    assert user is not None
    project_id = _project(client, headers, "Project to remove")
    other_id = _project(client, headers, "Project to retain")

    storage = tmp_path / "materials"
    monkeypatch.setattr(material_service, "MATERIAL_STORAGE_DIR", storage)
    uploaded = client.post(
        "/materials",
        headers=headers,
        data={"name": "Shared notes"},
        files={"file": ("notes.md", b"# Notes\n\nKeep this file.\n", "text/markdown")},
    )
    assert uploaded.status_code == 201
    material = uploaded.json()
    for project in (project_id, other_id):
        assert client.post(
            f"/projects/{project}/materials/{material['material_id']}",
            headers=headers,
        ).status_code == 201
    material_version = db.get(MaterialVersion, material["version_id"])
    assert material_version is not None
    original = storage / material_version.storage_object_key
    assert original.read_bytes() == b"# Notes\n\nKeep this file.\n"

    node_response = client.post(
        f"/projects/{project_id}/knowledge-nodes",
        headers=headers,
        json={"title": "Variables", "description": "Use a variable", "difficulty": 1},
    )
    assert node_response.status_code == 201
    node_id = node_response.json()["id"]

    plan, version = learning_plan_service.create_plan_with_first_draft(
        db, project_id=project_id, user_id=user.id,
        payload=PlanCreate(name="Learning plan", goal="Practice", content={}),
    )
    task = learning_task_service.create_task(
        db, plan_version_id=version.id, user_id=user.id, payload=_task_payload(1),
    )
    learning_plan_service.publish_version(
        db, plan_id=plan.id, version_id=version.id, user_id=user.id,
    )
    for state in (TaskStatus.READY, TaskStatus.IN_PROGRESS):
        learning_task_service.transition_task_status(
            db, plan_version_id=version.id, task_id=task.id,
            user_id=user.id, target_status=state,
        )
    task_path = f"/plan-versions/{version.id}/tasks/{task.id}"
    evidence = client.post(
        task_path + "/evidence", headers=headers,
        json={"evidence_type": "TEXT_ANSWER", "text_content": "A variable holds a value."},
    )
    assert evidence.status_code == 201
    evaluated = client.post(task_path + "/evaluate", headers=headers)
    assert evaluated.status_code == 200
    assert evaluated.json()["task_status"] == "PASSED"
    evaluation_id = evaluated.json()["evaluation"]["id"]
    record, review, created = mastery_service.record_evaluation_mastery(
        db, evaluation_id=evaluation_id, knowledge_node_id=node_id, user_id=user.id,
    )
    assert created is True
    proposal, event = replan_service.create_replan_proposal(
        db, project_id=project_id, user_id=user.id, base_plan_version_id=version.id,
        trigger_code="USER_REQUEST", reason="Add practice",
        proposed_content={"goal": "More practice"},
        diff={
            "added": [{"task_key": "t2", "title": "scope", "position": 2}],
            "removed": [], "moved": [], "changed": [],
        },
    )
    return {
        "headers": headers, "user_id": user.id, "project_id": project_id,
        "other_id": other_id, "material": material, "file": original,
        "node_id": node_id, "plan_id": plan.id, "version_id": version.id,
        "task_id": task.id, "task_path": task_path, "evaluation_id": evaluation_id,
        "record_id": record.id, "review_id": review.id,
        "proposal_id": proposal.id, "event_id": event.id,
    }


def test_delete_requires_owner_and_is_persistent_and_idempotent(client, db_session):
    owner = _login(client, "owner")
    outsider = _login(client, "outsider")
    project_id = _project(client, owner, "Remove this project")
    remaining_id = _project(client, owner, "Keep this project")
    path = f"/projects/{project_id}"

    assert client.delete(path).status_code == 401
    assert client.delete(path, headers=outsider).status_code == 404
    assert client.delete("/projects/999999", headers=owner).status_code == 404
    assert client.get(path, headers=owner).status_code == 200

    response = client.delete(path, headers=owner)
    assert response.status_code == 204
    assert response.content == b""
    db_session.expire_all()
    project = db_session.get(LearningProject, project_id)
    assert project is not None and project.deleted_at is not None
    deleted_at = project.deleted_at

    assert client.delete(path, headers=owner).status_code == 204
    db_session.expire_all()
    assert project.deleted_at == deleted_at
    assert client.delete(path, headers=outsider).status_code == 404
    assert client.get(path, headers=owner).status_code == 404
    projects = client.get("/projects", headers=owner)
    assert projects.status_code == 200
    assert [item["id"] for item in projects.json()] == [remaining_id]
    assert client.get(f"/projects/{remaining_id}", headers=owner).status_code == 200


def test_deleted_project_blocks_http_but_keeps_history_and_shared_files(
    client, db_session, learning_context,
):
    c = learning_context
    headers = c["headers"]
    base = f"/projects/{c['project_id']}"
    materials_path = base + "/materials"
    node_path = base + f"/knowledge-nodes/{c['node_id']}"
    today_path = (
        base + f"/plan-versions/{c['version_id']}/today-tasks?target_date=2026-10-28"
    )
    before_tasks = client.get(today_path, headers=headers)
    assert before_tasks.status_code == 200
    assert [item["id"] for item in before_tasks.json()["tasks"]] == [c["task_id"]]
    assert len(client.get(materials_path, headers=headers).json()) == 1
    assert client.get(node_path, headers=headers).status_code == 200
    models = (
        LearningProject, Material, MaterialVersion, ProjectMaterialBinding,
        KnowledgeNode, LearningPlan, PlanVersion, LearningTask,
        Evidence, Evaluation, MasteryRecord, ReviewItem, ReplanProposal, AuditEvent,
    )
    before_counts = [
        db_session.scalar(select(func.count()).select_from(model)) for model in models
    ]
    assert all(count > 0 for count in before_counts)

    assert client.delete(base, headers=headers).status_code == 204
    for path in (materials_path, base + "/knowledge-nodes", node_path, today_path):
        assert client.get(path, headers=headers).status_code == 404, path
    binding_path = materials_path + f"/{c['material']['material_id']}"
    assert client.post(binding_path, headers=headers).status_code == 404
    assert client.delete(binding_path, headers=headers).status_code == 404
    assert client.post(
        base + "/knowledge-nodes", headers=headers,
        json={"title": "New node", "description": "Rejected", "difficulty": 1},
    ).status_code == 404
    assert client.post(
        c["task_path"] + "/evidence", headers=headers,
        json={"evidence_type": "TEXT_ANSWER", "text_content": "Another answer"},
    ).status_code == 404
    assert client.post(c["task_path"] + "/evaluate", headers=headers).status_code == 404

    after_counts = [
        db_session.scalar(select(func.count()).select_from(model)) for model in models
    ]
    assert before_counts == after_counts
    assert c["file"].read_bytes() == b"# Notes\n\nKeep this file.\n"
    bindings = db_session.scalars(select(ProjectMaterialBinding)).all()
    assert len(bindings) == 2 and all(item.unbound_at is None for item in bindings)
    kept = client.get(f"/projects/{c['other_id']}/materials", headers=headers)
    assert kept.status_code == 200
    assert [item["material_id"] for item in kept.json()] == [c["material"]["material_id"]]
    material = c["material"]
    parse_path = f"/materials/{material['material_id']}/versions/{material['version_id']}/parse"
    assert client.get(parse_path, headers=headers).status_code == 200
    assert db_session.get(LearningTask, c["task_id"]).status == "PASSED"
    assert db_session.get(ReviewItem, c["review_id"]).status == "PENDING"
    assert db_session.get(ReplanProposal, c["proposal_id"]).status == "PENDING"


def test_deleted_project_blocks_service_access_by_old_related_ids(
    client, db_session, learning_context,
):
    c = learning_context
    db = db_session
    owner = {"user_id": c["user_id"]}
    project = {**owner, "project_id": c["project_id"]}
    plan = {**owner, "plan_id": c["plan_id"]}
    version = {**owner, "plan_version_id": c["version_id"]}
    evaluation = {**owner, "evaluation_id": c["evaluation_id"]}
    mastery = {**project, "knowledge_node_id": c["node_id"]}
    proposal = {**owner, "proposal_id": c["proposal_id"]}

    assert learning_plan_service.get_current_published_version(db, **plan).id == c["version_id"]
    assert learning_task_service.list_version_tasks(db, **version)[0].id == c["task_id"]
    assert evaluation_service.get_evaluation(db, **evaluation).id == c["evaluation_id"]
    assert mastery_service.get_mastery_history(db, **mastery)[0].id == c["record_id"]
    assert mastery_service.list_review_items(db, **project)[0].id == c["review_id"]
    assert replan_service.get_replan_proposal(db, **proposal).id == c["proposal_id"]
    assert replan_service.list_audit_events(db, **project)[0].id == c["event_id"]

    assert client.delete(
        f"/projects/{c['project_id']}", headers=c["headers"],
    ).status_code == 204
    operations = [
        partial(
            learning_plan_service.create_plan_with_first_draft, db, **project,
            payload=PlanCreate(name="Rejected", goal="No new plan", content={}),
        ),
        partial(learning_plan_service.list_plan_versions, db, **plan),
        partial(learning_plan_service.get_current_published_version, db, **plan),
        partial(
            learning_plan_service.create_next_draft, db, **plan,
            payload=PlanVersionCreate(goal="No new version", content={}),
        ),
        partial(
            learning_plan_service.publish_version, db, **plan,
            version_id=c["version_id"],
        ),
        partial(learning_task_service.list_version_tasks, db, **version),
        partial(
            learning_task_service.create_task, db, **version, payload=_task_payload(2),
        ),
        partial(
            learning_task_service.transition_task_status, db, **version,
            task_id=c["task_id"], target_status=TaskStatus.IN_PROGRESS,
        ),
        partial(evaluation_service.get_evaluation, db, **evaluation),
        partial(evaluation_service.finalize_evaluation, db, **evaluation),
        partial(
            mastery_service.record_evaluation_mastery, db, **evaluation,
            knowledge_node_id=c["node_id"],
        ),
        partial(mastery_service.get_mastery_history, db, **mastery),
        partial(mastery_service.list_review_items, db, **project),
        partial(mastery_service.list_due_review_items, db, **project),
        partial(
            mastery_service.complete_review_item, db, **owner,
            review_item_id=c["review_id"],
        ),
        partial(replan_service.get_replan_proposal, db, **proposal),
        partial(replan_service.list_replan_proposals, db, **project),
        partial(replan_service.list_audit_events, db, **project),
        partial(
            replan_service.accept_replan_proposal, db, **proposal, decision_note="No",
        ),
        partial(
            replan_service.reject_replan_proposal, db, **proposal, decision_note="No",
        ),
        partial(
            replan_service.create_replan_proposal, db, **project,
            base_plan_version_id=c["version_id"], trigger_code="USER_REQUEST",
            reason="Rejected", proposed_content={}, diff={},
        ),
    ]
    for operation in operations:
        with pytest.raises(HTTPException) as captured:
            operation()
        assert captured.value.status_code == 404, operation.func.__name__
    db.expire_all()
    assert db.get(ReviewItem, c["review_id"]).status == "PENDING"
    assert db.get(ReplanProposal, c["proposal_id"]).status == "PENDING"


def test_failed_delete_rolls_back_and_keeps_project_visible(
    client, db_session, monkeypatch,
):
    headers = _login(client, "rollback-owner")
    project_id = _project(client, headers, "Keep on failure")
    project = db_session.get(LearningProject, project_id)
    assert project is not None

    def fail_commit():
        raise RuntimeError("simulated storage failure")

    with monkeypatch.context() as patch:
        patch.setattr(db_session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated storage failure"):
            project_service.delete_project_or_raise(
                db_session, project_id=project_id, user_id=project.user_id,
            )
    db_session.expire_all()
    assert project.deleted_at is None
    assert client.get(f"/projects/{project_id}", headers=headers).status_code == 200