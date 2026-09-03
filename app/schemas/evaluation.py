from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.evaluation import EvaluationDecision, RuleEvaluationStatus

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RuleEvaluationCreate(BaseModel):
    evidence_id: int = Field(gt=0)
    rule_status: RuleEvaluationStatus
    rule_result: dict[str, object] = Field(min_length=1)


class ModelSuggestionCreate(BaseModel):
    recommendation: EvaluationDecision
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
    ]
    confidence: float = Field(ge=0, le=1)
    model_name: NonEmptyText | None = None


class HumanDecisionCreate(BaseModel):
    decision: EvaluationDecision
    note: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
    ]


class EvaluationResponse(BaseModel):
    id: int
    evidence_id: int
    rule_status: RuleEvaluationStatus
    rule_result: dict[str, object]
    model_suggestion: dict[str, object] | None
    human_decision: EvaluationDecision | None
    human_note: str | None
    confirmed_by_user_id: int | None
    confirmed_at: datetime | None
    final_decision: EvaluationDecision | None
    finalized_by_user_id: int | None
    finalized_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
