from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.evaluation import EvaluationDecision
from app.models.mastery import MasteryLevel, ReviewItemStatus


class MasteryApplyRequest(BaseModel):
    knowledge_node_id: int = Field(gt=0)


class MasteryRecordResponse(BaseModel):
    id: int
    project_id: int
    knowledge_node_id: int
    evaluation_id: int
    score_before: int
    score_after: int
    level_after: MasteryLevel
    decision: EvaluationDecision
    interval_days: int
    next_review_at: datetime
    algorithm_version: str
    calculation: dict[str, object]
    reason: str
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewItemResponse(BaseModel):
    id: int
    project_id: int
    knowledge_node_id: int
    last_record_id: int
    mastery_score: int
    mastery_level: MasteryLevel
    status: ReviewItemStatus
    interval_days: int
    next_review_at: datetime
    review_count: int
    last_reviewed_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MasteryApplyResponse(BaseModel):
    record: MasteryRecordResponse
    review_item: ReviewItemResponse
    created: bool
