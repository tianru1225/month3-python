from app.models.learning_task import TaskStatus
from app.schemas.evidence import EvidenceResponse
from app.schemas.evaluation import EvaluationResponse
from pydantic import BaseModel


class EvidenceAcceptanceResponse(BaseModel):
    evidence: EvidenceResponse
    evaluation: EvaluationResponse
    task_status: TaskStatus
