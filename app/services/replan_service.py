from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.replan import (
    AuditEvent,
    AuditEventType,
    ReplanProposal,
    ReplanProposalStatus,
)
from app.repositories import replan_repository


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def create_replan_proposal(
    db: Session,
    *,
    project_id: int,
    user_id: int,
    base_plan_version_id: int,
    trigger_code: str,
    reason: str,
    proposed_content: dict[str, object],
    diff: dict[str, object],
) -> tuple[ReplanProposal, AuditEvent]:
    if (
        replan_repository.get_owned_project(db, project_id=project_id, user_id=user_id)
        is None
    ):
        raise _error(404, "PROJECT_NOT_FOUND", "project not found")

    current = replan_repository.get_owned_current_published_version(
        db, project_id=project_id, user_id=user_id
    )
    if current is None or current.id != base_plan_version_id:
        raise _error(
            409,
            "PLAN_VERSION_NOT_ACTIVE",
            "base plan version is not the current published version",
        )

    try:
        proposal = replan_repository.add_proposal(
            db,
            project_id=project_id,
            base_plan_version_id=base_plan_version_id,
            created_by_user_id=user_id,
            trigger_code=trigger_code,
            reason=reason,
            proposed_content=proposed_content,
            diff=diff,
        )
        event = replan_repository.add_audit_event(
            db,
            project_id=project_id,
            proposal_id=proposal.id,
            actor_user_id=user_id,
            event_type=AuditEventType.PROPOSAL_CREATED.value,
            payload={
                "base_plan_version_id": base_plan_version_id,
                "trigger_code": trigger_code,
                "reason": reason,
                "diff": diff,
            },
        )
        db.commit()
        db.refresh(proposal)
        db.refresh(event)
        return proposal, event
    except IntegrityError as exc:
        db.rollback()
        raise _error(
            409,
            "REPLAN_PROPOSAL_CONFLICT",
            "replan proposal could not be created",
        ) from exc
    except Exception:
        db.rollback()
        raise


def get_replan_proposal(
    db: Session, *, proposal_id: int, user_id: int
) -> ReplanProposal:
    proposal = replan_repository.get_owned_proposal(
        db, proposal_id=proposal_id, user_id=user_id
    )
    if proposal is None:
        raise _error(404, "REPLAN_PROPOSAL_NOT_FOUND", "replan proposal not found")
    return proposal


def list_replan_proposals(
    db: Session, *, project_id: int, user_id: int
) -> list[ReplanProposal]:
    if (
        replan_repository.get_owned_project(db, project_id=project_id, user_id=user_id)
        is None
    ):
        raise _error(404, "PROJECT_NOT_FOUND", "project not found")
    return replan_repository.list_owned_proposals(
        db, project_id=project_id, user_id=user_id
    )


def _decide(
    db: Session,
    *,
    proposal_id: int,
    user_id: int,
    status: ReplanProposalStatus,
    decision_note: str,
) -> tuple[ReplanProposal, AuditEvent]:
    proposal = get_replan_proposal(db, proposal_id=proposal_id, user_id=user_id)
    if proposal.status != ReplanProposalStatus.PENDING.value:
        raise _error(
            409,
            "REPLAN_PROPOSAL_STATE_CONFLICT",
            "only a pending proposal can be decided",
        )

    try:
        replan_repository.set_decision(
            db,
            proposal,
            status=status.value,
            decided_by_user_id=user_id,
            decided_at=utc_now(),
            decision_note=decision_note,
        )
        event_type = (
            AuditEventType.PROPOSAL_ACCEPTED
            if status == ReplanProposalStatus.ACCEPTED
            else AuditEventType.PROPOSAL_REJECTED
        )
        event = replan_repository.add_audit_event(
            db,
            project_id=proposal.project_id,
            proposal_id=proposal.id,
            actor_user_id=user_id,
            event_type=event_type.value,
            payload={
                "status": status.value,
                "decision_note": decision_note,
                "base_plan_version_id": proposal.base_plan_version_id,
            },
        )
        db.commit()
        db.refresh(proposal)
        db.refresh(event)
        return proposal, event
    except IntegrityError as exc:
        db.rollback()
        raise _error(
            409,
            "REPLAN_PROPOSAL_CONFLICT",
            "replan proposal decision could not be saved",
        ) from exc
    except Exception:
        db.rollback()
        raise


def accept_replan_proposal(
    db: Session, *, proposal_id: int, user_id: int, decision_note: str
) -> tuple[ReplanProposal, AuditEvent]:
    return _decide(
        db,
        proposal_id=proposal_id,
        user_id=user_id,
        status=ReplanProposalStatus.ACCEPTED,
        decision_note=decision_note,
    )


def reject_replan_proposal(
    db: Session, *, proposal_id: int, user_id: int, decision_note: str
) -> tuple[ReplanProposal, AuditEvent]:
    return _decide(
        db,
        proposal_id=proposal_id,
        user_id=user_id,
        status=ReplanProposalStatus.REJECTED,
        decision_note=decision_note,
    )


def list_audit_events(
    db: Session, *, project_id: int, user_id: int
) -> list[AuditEvent]:
    if (
        replan_repository.get_owned_project(db, project_id=project_id, user_id=user_id)
        is None
    ):
        raise _error(404, "PROJECT_NOT_FOUND", "project not found")
    return replan_repository.list_owned_audit_events(
        db, project_id=project_id, user_id=user_id
    )
