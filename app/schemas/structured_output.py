from pydantic import BaseModel,Field

class LearningPlanItem(BaseModel):
    title: str = Field(min_length=1,max_length=120)
    objective: str = Field(min_length=1,max_length=1000)
    estimated_minutes: int = Field(ge=5,le=480)
    acceptance_criteria: list[str] = Field(min_length=1,max_length=8)