from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import Evidence
from app.models.evaluation import Evaluation
from app.models.learning_plan import LearningPlan, PlanVersion
from app.models.learning_project import LearningProject
from app.models.learning_task import LearningTask


def get_by_id(db: Session, *, evaluation_id: int) -> Evaluation | None:
    return db.scalar(select(Evaluation).where(Evaluation.id == evaluation_id))


def get_by_evidence_id(db: Session, *, evidence_id: int) -> Evaluation | None:
    return db.scalar(select(Evaluation).where(Evaluation.evidence_id == evidence_id))


def get_owned_evidence_context(
    db: Session,
    *,
    evidence_id: int,
    user_id: int,
) -> tuple[Evidence, LearningTask, PlanVersion] | None:
    row = db.execute(
        select(Evidence, LearningTask, PlanVersion)
        .join(
            LearningTask,
            (LearningTask.id == Evidence.task_id)
            & (LearningTask.plan_version_id == Evidence.plan_version_id),
        )
        .join(PlanVersion, PlanVersion.id == Evidence.plan_version_id)
        .join(LearningPlan, LearningPlan.id == PlanVersion.plan_id)
        .join(LearningProject, LearningProject.id == LearningPlan.project_id)
        .where(
            Evidence.id == evidence_id,
            LearningProject.user_id == user_id,
        )
    ).one_or_none()
    if row is None:
        return None
    evidence, task, version = row
    return evidence, task, version


def get_latest_evidence_for_task(
    db: Session,
    *,
    task_id: int,
) -> Evidence | None:
    return db.scalar(
        select(Evidence)
        .where(Evidence.task_id == task_id)
        .order_by(Evidence.attempt_number.desc(), Evidence.id.desc())
        .limit(1)
    )


def add_evaluation(
    db: Session,
    *,
    evidence_id: int,
    rule_status: str,
    rule_result: dict[str, object],
) -> Evaluation:
    evaluation = Evaluation(
        evidence_id=evidence_id,
        rule_status=rule_status,
        rule_result=rule_result,
    )
    db.add(evaluation)
    db.flush()
    return evaluation


def set_model_suggestion(
    db: Session,
    evaluation: Evaluation,
    *,
    suggestion: dict[str, object],
) -> Evaluation:
    evaluation.model_suggestion = suggestion
    db.flush()
    return evaluation


def set_human_decision(
    db: Session,
    evaluation: Evaluation,
    *,
    decision: str,
    note: str,
    user_id: int,
    confirmed_at: datetime,
) -> Evaluation:
    evaluation.human_decision = decision
    evaluation.human_note = note
    evaluation.confirmed_by_user_id = user_id
    evaluation.confirmed_at = confirmed_at
    db.flush()
    return evaluation


def set_final_decision(
    db: Session,
    evaluation: Evaluation,
    *,
    decision: str,
    user_id: int,
    finalized_at: datetime,
) -> Evaluation:
    evaluation.final_decision = decision
    evaluation.finalized_by_user_id = user_id
    evaluation.finalized_at = finalized_at
    db.flush()
    return evaluation
