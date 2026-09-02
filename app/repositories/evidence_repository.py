from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.evidence import Evidence


def next_attempt_number(db: Session, *, task_id: int) -> int:
    current = db.scalar(
        select(func.max(Evidence.attempt_number)).where(Evidence.task_id == task_id)
    )
    return int(current or 0) + 1


def add_evidence(
    db: Session,
    *,
    plan_version_id: int,
    task_id: int,
    attempt_number: int,
    evidence_type: str,
    source_kind: str,
    source_ref: str | None,
    text_content: str | None,
    test_report: dict[str, object] | None,
    submitted_by_user_id: int,
) -> Evidence:
    evidence = Evidence(
        plan_version_id=plan_version_id,
        task_id=task_id,
        attempt_number=attempt_number,
        evidence_type=evidence_type,
        source_kind=source_kind,
        source_ref=source_ref,
        text_content=text_content,
        test_report=test_report,
        submitted_by_user_id=submitted_by_user_id,
    )
    db.add(evidence)
    db.flush()
    return evidence


def list_task_evidence(db: Session, *, task_id: int) -> list[Evidence]:
    return list(
        db.scalars(
            select(Evidence)
            .where(Evidence.task_id == task_id)
            .order_by(Evidence.attempt_number.asc(), Evidence.id.asc())
        ).all()
    )
