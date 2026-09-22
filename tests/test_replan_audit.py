from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.learning_plan import (
    LearningPlan,
    PlanSourceKind,
    PlanVersion,
    PlanVersionStatus,
)
from app.models.learning_project import LearningProject
from app.models.replan import (
    AuditEvent,
    AuditEventType,
    ReplanProposal,
    ReplanProposalStatus,
)
from app.models.user import User
from app.repositories import replan_repository
from app.schemas.replan import ReplanDecisionCreate, ReplanProposalCreate
from app.services import replan_service


def now() -> datetime:
    return datetime.now(timezone.utc)


def context(
    db: Session, suffix: str
) -> tuple[User, LearningProject, LearningPlan, PlanVersion]:
    user = User(username=f"{suffix}-user", password_hash="test-password")
    db.add(user)
    db.flush()
    project = LearningProject(
        user_id=user.id,
        name=f"{suffix}-project",
        goal="replan test",
        current_level="beginner",
    )
    db.add(project)
    db.flush()
    plan = LearningPlan(project_id=project.id, name=f"{suffix}-plan")
    db.add(plan)
    db.flush()
    version = PlanVersion(
        plan_id=plan.id,
        version_number=1,
        status=PlanVersionStatus.PUBLISHED.value,
        goal="test goal",
        content={"tasks": [{"title": "read"}]},
        source_kind=PlanSourceKind.MANUAL.value,
        published_at=now(),
        confirmed_by_user_id=user.id,
        is_current=True,
    )
    db.add(version)
    db.commit()
    return user, project, plan, version


def payload() -> tuple[dict[str, object], dict[str, object]]:
    return (
        {"tasks": [{"task_key": "t1", "title": "functions", "position": 1}]},
        {
            "added": [{"task_key": "t2", "title": "scope", "position": 2}],
            "removed": [],
            "moved": [],
            "changed": [],
        },
    )


def create_proposal(
    db: Session, user: User, project: LearningProject, version: PlanVersion
) -> ReplanProposal:
    content, diff = payload()
    proposal, _ = replan_service.create_replan_proposal(
        db,
        project_id=project.id,
        user_id=user.id,
        base_plan_version_id=version.id,
        trigger_code="MASTERY_DROP",
        reason="mastery decreased",
        proposed_content=content,
        diff=diff,
    )
    return proposal


def test_schema_and_diff() -> None:
    content, diff = payload()
    request = ReplanProposalCreate(
        base_plan_version_id=1,
        trigger_code="MASTERY_DROP",
        reason="failed twice",
        proposed_content=content,
        diff=diff,
    )
    assert request.diff.added[0].task_key == "t2"
    assert ReplanDecisionCreate(note="reviewed").note == "reviewed"
    with pytest.raises(ValidationError):
        ReplanProposalCreate(
            base_plan_version_id=1,
            trigger_code="MASTERY_DROP",
            reason=" ",
            proposed_content=content,
            diff={"added": [], "removed": [], "moved": [], "changed": []},
        )


def test_create_and_created_audit(db_session: Session) -> None:
    user, project, _, version = context(db_session, "create")
    proposal, event = replan_service.create_replan_proposal(
        db_session,
        project_id=project.id,
        user_id=user.id,
        base_plan_version_id=version.id,
        trigger_code="MASTERY_DROP",
        reason="mastery decreased",
        proposed_content=payload()[0],
        diff=payload()[1],
    )
    assert proposal.status == ReplanProposalStatus.PENDING.value
    assert proposal.diff["added"][0]["task_key"] == "t2"
    assert event.event_type == AuditEventType.PROPOSAL_CREATED.value


def test_current_version_gate_and_ownership(db_session: Session) -> None:
    user, project, plan, current = context(db_session, "gate")
    old = PlanVersion(
        plan_id=plan.id,
        version_number=2,
        status=PlanVersionStatus.DRAFT.value,
        goal="draft",
        content={"tasks": []},
        source_kind=PlanSourceKind.MANUAL.value,
        is_current=False,
    )
    db_session.add(old)
    db_session.commit()
    with pytest.raises(HTTPException) as error:
        create_proposal(db_session, user, project, old)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "PLAN_VERSION_NOT_ACTIVE"

    outsider = User(username="replan-outsider", password_hash="test-password")
    db_session.add(outsider)
    db_session.commit()
    with pytest.raises(HTTPException) as error:
        replan_service.create_replan_proposal(
            db_session,
            project_id=project.id,
            user_id=outsider.id,
            base_plan_version_id=current.id,
            trigger_code="MANUAL",
            reason="cross user",
            proposed_content=payload()[0],
            diff=payload()[1],
        )
    assert error.value.status_code == 404


def test_accept_reject_and_no_new_version(db_session: Session) -> None:
    user, project, plan, version = context(db_session, "decision")
    proposal = create_proposal(db_session, user, project, version)
    before = db_session.scalar(
        select(func.count()).select_from(PlanVersion).where(PlanVersion.plan_id == plan.id)
    )
    accepted, accepted_event = replan_service.accept_replan_proposal(
        db_session,
        proposal_id=proposal.id,
        user_id=user.id,
        decision_note="accept later publish",
    )
    after = db_session.scalar(
        select(func.count()).select_from(PlanVersion).where(PlanVersion.plan_id == plan.id)
    )
    assert accepted.status == ReplanProposalStatus.ACCEPTED.value
    assert accepted_event.event_type == AuditEventType.PROPOSAL_ACCEPTED.value
    assert after == before

    user2, project2, _, version2 = context(db_session, "reject")
    proposal2 = create_proposal(db_session, user2, project2, version2)
    rejected, rejected_event = replan_service.reject_replan_proposal(
        db_session,
        proposal_id=proposal2.id,
        user_id=user2.id,
        decision_note="keep current",
    )
    assert rejected.status == ReplanProposalStatus.REJECTED.value
    assert rejected_event.event_type == AuditEventType.PROPOSAL_REJECTED.value


def test_decided_proposal_and_queries(db_session: Session) -> None:
    user, project, _, version = context(db_session, "query")
    proposal = create_proposal(db_session, user, project, version)
    replan_service.accept_replan_proposal(
        db_session,
        proposal_id=proposal.id,
        user_id=user.id,
        decision_note="accepted",
    )
    with pytest.raises(HTTPException) as error:
        replan_service.reject_replan_proposal(
            db_session,
            proposal_id=proposal.id,
            user_id=user.id,
            decision_note="repeat",
        )
    assert error.value.detail["code"] == "REPLAN_PROPOSAL_STATE_CONFLICT"
    assert replan_service.list_replan_proposals(
        db_session, project_id=project.id, user_id=user.id
    )[0].id == proposal.id


def test_database_constraints(db_session: Session) -> None:
    user, project, _, version = context(db_session, "constraints")
    db_session.add(
        ReplanProposal(
            project_id=project.id,
            base_plan_version_id=version.id,
            created_by_user_id=user.id,
            trigger_code="MANUAL",
            reason="invalid pending",
            proposed_content={"tasks": []},
            diff={"added": [], "removed": [], "moved": [], "changed": []},
            status=ReplanProposalStatus.PENDING.value,
            decided_by_user_id=user.id,
            decided_at=now(),
            decision_note="must be empty",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        ReplanProposal(
            project_id=project.id,
            base_plan_version_id=version.id,
            created_by_user_id=user.id,
            trigger_code="MANUAL",
            reason="invalid status",
            proposed_content={"tasks": []},
            diff={"added": [], "removed": [], "moved": [], "changed": []},
            status="UNKNOWN",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_audit_event_constraint(db_session: Session) -> None:
    user, project, _, version = context(db_session, "event")
    proposal = create_proposal(db_session, user, project, version)
    db_session.add(
        AuditEvent(
            project_id=project.id,
            proposal_id=proposal.id,
            actor_user_id=user.id,
            event_type="UNKNOWN",
            payload={"bad": True},
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_audit_is_append_only() -> None:
    assert not hasattr(replan_repository, "update_audit_event")
    assert not hasattr(replan_repository, "delete_audit_event")
    assert not hasattr(replan_service, "update_audit_event")
    assert not hasattr(replan_service, "delete_audit_event")


def test_create_transaction_rolls_back(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, project, _, version = context(db_session, "rollback-create")

    def fail_audit(*args: object, **kwargs: object) -> object:
        raise RuntimeError("audit failed")

    monkeypatch.setattr(replan_repository, "add_audit_event", fail_audit)
    with pytest.raises(RuntimeError):
        create_proposal(db_session, user, project, version)
    assert db_session.scalar(select(ReplanProposal)) is None
    assert db_session.scalar(select(AuditEvent)) is None


def test_decision_transaction_rolls_back(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, project, _, version = context(db_session, "rollback-decision")
    proposal = create_proposal(db_session, user, project, version)

    def fail_audit(*args: object, **kwargs: object) -> object:
        raise RuntimeError("audit failed")

    monkeypatch.setattr(replan_repository, "add_audit_event", fail_audit)
    with pytest.raises(RuntimeError):
        replan_service.accept_replan_proposal(
            db_session,
            proposal_id=proposal.id,
            user_id=user.id,
            decision_note="rollback",
        )
    db_session.expire_all()
    stored = db_session.get(ReplanProposal, proposal.id)
    assert stored is not None
    assert stored.status == ReplanProposalStatus.PENDING.value
    assert db_session.scalar(
        select(func.count()).select_from(AuditEvent).where(
            AuditEvent.proposal_id == proposal.id
        )
    ) == 1


def test_audit_query_ownership(db_session: Session) -> None:
    owner, project, _, version = context(db_session, "audit-owner")
    outsider, other_project, _, other_version = context(db_session, "audit-other")
    _create = create_proposal
    _create(db_session, owner, project, version)
    _create(db_session, outsider, other_project, other_version)
    assert len(
        replan_service.list_audit_events(
            db_session, project_id=project.id, user_id=owner.id
        )
    ) == 1