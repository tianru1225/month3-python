from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.learning_plan import LearningPlan, PlanVersion
from app.models.learning_project import LearningProject
from app.models.replan import AuditEvent, ReplanProposal


def get_owned_project(
    db: Session, *, project_id: int, user_id: int
) -> LearningProject | None:
    return db.scalar(
        select(LearningProject).where(
            LearningProject.id == project_id,
            LearningProject.user_id == user_id,
        )
    )


def get_owned_current_published_version(
    db: Session, *, project_id: int, user_id: int
) -> PlanVersion | None:
    return db.scalar(
        select(PlanVersion)
        .join(LearningPlan, LearningPlan.id == PlanVersion.plan_id)
        .join(LearningProject, LearningProject.id == LearningPlan.project_id)
        .where(
            LearningProject.id == project_id,
            LearningProject.user_id == user_id,
            PlanVersion.status == "PUBLISHED",
            PlanVersion.is_current.is_(True),
        )
    )


def get_owned_proposal(
    db: Session, *, proposal_id: int, user_id: int
) -> ReplanProposal | None:
    return db.scalar(
        select(ReplanProposal)
        .join(LearningProject, LearningProject.id == ReplanProposal.project_id)
        .where(
            ReplanProposal.id == proposal_id,
            LearningProject.user_id == user_id,
        )
    )


def list_owned_proposals(
    db: Session, *, project_id: int, user_id: int
) -> list[ReplanProposal]:
    return list(
        db.scalars(
            select(ReplanProposal)
            .join(LearningProject, LearningProject.id == ReplanProposal.project_id)
            .where(
                ReplanProposal.project_id == project_id,
                LearningProject.user_id == user_id,
            )
            .order_by(ReplanProposal.created_at.asc(), ReplanProposal.id.asc())
        ).all()
    )


def add_proposal(
    db: Session,
    *,
    project_id: int,
    base_plan_version_id: int,
    created_by_user_id: int,
    trigger_code: str,
    reason: str,
    proposed_content: dict[str, object],
    diff: dict[str, object],
) -> ReplanProposal:
    proposal = ReplanProposal(
        project_id=project_id,
        base_plan_version_id=base_plan_version_id,
        created_by_user_id=created_by_user_id,
        trigger_code=trigger_code,
        reason=reason,
        proposed_content=proposed_content,
        diff=diff,
    )
    db.add(proposal)
    db.flush()
    return proposal


def set_decision(
    db: Session,
    proposal: ReplanProposal,
    *,
    status: str,
    decided_by_user_id: int,
    decided_at: datetime,
    decision_note: str,
) -> ReplanProposal:
    proposal.status = status
    proposal.decided_by_user_id = decided_by_user_id
    proposal.decided_at = decided_at
    proposal.decision_note = decision_note
    db.flush()
    return proposal


def add_audit_event(
    db: Session,
    *,
    project_id: int,
    proposal_id: int,
    actor_user_id: int | None,
    event_type: str,
    payload: dict[str, object],
) -> AuditEvent:
    event = AuditEvent(
        project_id=project_id,
        proposal_id=proposal_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(event)
    db.flush()
    return event


def list_owned_audit_events(
    db: Session, *, project_id: int, user_id: int
) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent)
            .join(LearningProject, LearningProject.id == AuditEvent.project_id)
            .where(
                AuditEvent.project_id == project_id,
                LearningProject.user_id == user_id,
            )
            .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        ).all()
    )