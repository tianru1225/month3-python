from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evaluation import Evaluation
from app.models.evidence import Evidence
from app.models.knowledge import KnowledgeNode
from app.models.learning_plan import LearningPlan, PlanVersion
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask
from app.models.mastery import MasteryRecord, ReviewItem


EvaluationContext = tuple[
    Evaluation,
    Evidence,
    LearningTask,
    PlanVersion,
    LearningProject,
]


def get_owned_evaluation_context(
    db: Session,
    *,
    evaluation_id: int,
    user_id: int,
) -> EvaluationContext | None:
    row = db.execute(
        select(
            Evaluation,
            Evidence,
            LearningTask,
            PlanVersion,
            LearningProject,
        )
        .join(Evidence, Evidence.id == Evaluation.evidence_id)
        .join(
            LearningTask,
            (LearningTask.id == Evidence.task_id)
            & (LearningTask.plan_version_id == Evidence.plan_version_id),
        )
        .join(PlanVersion, PlanVersion.id == Evidence.plan_version_id)
        .join(LearningPlan, LearningPlan.id == PlanVersion.plan_id)
        .join(LearningProject, LearningProject.id == LearningPlan.project_id)
        .where(
            Evaluation.id == evaluation_id,
            LearningProject.user_id == user_id,
        )
    ).one_or_none()
    if row is None:
        return None
    evaluation, evidence, task, version, project = row
    return evaluation, evidence, task, version, project


def get_project_node(
    db: Session,
    *,
    project_id: int,
    knowledge_node_id: int,
) -> KnowledgeNode | None:
    return db.scalar(
        select(KnowledgeNode).where(
            KnowledgeNode.id == knowledge_node_id,
            KnowledgeNode.project_id == project_id,
        )
    )


def get_record_by_evaluation_id(
    db: Session,
    *,
    evaluation_id: int,
) -> MasteryRecord | None:
    return db.scalar(
        select(MasteryRecord).where(MasteryRecord.evaluation_id == evaluation_id)
    )


def get_latest_record(
    db: Session,
    *,
    project_id: int,
    knowledge_node_id: int,
) -> MasteryRecord | None:
    return db.scalar(
        select(MasteryRecord)
        .where(
            MasteryRecord.project_id == project_id,
            MasteryRecord.knowledge_node_id == knowledge_node_id,
        )
        .order_by(MasteryRecord.recorded_at.desc(), MasteryRecord.id.desc())
        .limit(1)
    )


def list_records(
    db: Session,
    *,
    project_id: int,
    knowledge_node_id: int,
) -> list[MasteryRecord]:
    return list(
        db.scalars(
            select(MasteryRecord)
            .where(
                MasteryRecord.project_id == project_id,
                MasteryRecord.knowledge_node_id == knowledge_node_id,
            )
            .order_by(MasteryRecord.recorded_at.asc(), MasteryRecord.id.asc())
        ).all()
    )


def add_record(
    db: Session,
    *,
    project_id: int,
    knowledge_node_id: int,
    evaluation_id: int,
    score_before: int,
    score_after: int,
    level_after: str,
    decision: str,
    interval_days: int,
    next_review_at: datetime,
    algorithm_version: str,
    calculation: dict[str, object],
    reason: str,
    recorded_at: datetime,
) -> MasteryRecord:
    record = MasteryRecord(
        project_id=project_id,
        knowledge_node_id=knowledge_node_id,
        evaluation_id=evaluation_id,
        score_before=score_before,
        score_after=score_after,
        level_after=level_after,
        decision=decision,
        interval_days=interval_days,
        next_review_at=next_review_at,
        algorithm_version=algorithm_version,
        calculation=calculation,
        reason=reason,
        recorded_at=recorded_at,
    )
    db.add(record)
    db.flush()
    return record


def get_review_item(
    db: Session,
    *,
    project_id: int,
    knowledge_node_id: int,
) -> ReviewItem | None:
    return db.scalar(
        select(ReviewItem).where(
            ReviewItem.project_id == project_id,
            ReviewItem.knowledge_node_id == knowledge_node_id,
        )
    )


def get_owned_review_item(
    db: Session,
    *,
    review_item_id: int,
    user_id: int,
) -> ReviewItem | None:
    return db.scalar(
        select(ReviewItem)
        .join(LearningProject, LearningProject.id == ReviewItem.project_id)
        .where(
            ReviewItem.id == review_item_id,
            LearningProject.user_id == user_id,
        )
    )


def create_review_item(
    db: Session,
    *,
    project_id: int,
    knowledge_node_id: int,
    last_record_id: int,
    mastery_score: int,
    mastery_level: str,
    status: str,
    interval_days: int,
    next_review_at: datetime,
) -> ReviewItem:
    item = ReviewItem(
        project_id=project_id,
        knowledge_node_id=knowledge_node_id,
        last_record_id=last_record_id,
        mastery_score=mastery_score,
        mastery_level=mastery_level,
        status=status,
        interval_days=interval_days,
        next_review_at=next_review_at,
    )
    db.add(item)
    db.flush()
    return item


def refresh_review_item(
    db: Session,
    item: ReviewItem,
    *,
    last_record_id: int,
    mastery_score: int,
    mastery_level: str,
    status: str,
    interval_days: int,
    next_review_at: datetime,
    updated_at: datetime,
) -> ReviewItem:
    item.last_record_id = last_record_id
    item.mastery_score = mastery_score
    item.mastery_level = mastery_level
    item.status = status
    item.interval_days = interval_days
    item.next_review_at = next_review_at
    item.completed_at = None
    item.updated_at = updated_at
    db.flush()
    return item


def mark_review_completed(
    db: Session,
    item: ReviewItem,
    *,
    completed_at: datetime,
) -> ReviewItem:
    item.status = "COMPLETED"
    item.review_count += 1
    item.last_reviewed_at = completed_at
    item.completed_at = completed_at
    item.updated_at = completed_at
    db.flush()
    return item


def list_project_review_items(
    db: Session,
    *,
    project_id: int,
) -> list[ReviewItem]:
    return list(
        db.scalars(
            select(ReviewItem)
            .where(ReviewItem.project_id == project_id)
            .order_by(ReviewItem.next_review_at.asc(), ReviewItem.id.asc())
        ).all()
    )


def list_due_review_items(
    db: Session,
    *,
    project_id: int,
    due_at: datetime,
) -> list[ReviewItem]:
    return list(
        db.scalars(
            select(ReviewItem)
            .where(
                ReviewItem.project_id == project_id,
                ReviewItem.status == "PENDING",
                ReviewItem.next_review_at <= due_at,
            )
            .order_by(ReviewItem.next_review_at.asc(), ReviewItem.id.asc())
        ).all()
    )
