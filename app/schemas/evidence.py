from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.models.evidence import EvidenceSourceKind, EvidenceType


EvidenceText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)
]
SourceReference = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
TestCommand = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
TestSummary = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]
CheckName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]
CheckDetails = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]


class TestCheckStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class TestCheck(BaseModel):
    name: CheckName
    status: TestCheckStatus
    details: CheckDetails | None = None


class StructuredTestReport(BaseModel):
    command: TestCommand
    exit_code: int = Field(ge=0, le=255)
    summary: TestSummary
    checks: list[TestCheck] = Field(min_length=1, max_length=200)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)


class TextEvidenceCreate(BaseModel):
    evidence_type: Literal[EvidenceType.TEXT_ANSWER] = EvidenceType.TEXT_ANSWER
    text_content: EvidenceText


class TestReportEvidenceCreate(BaseModel):
    evidence_type: Literal[EvidenceType.TEST_REPORT] = EvidenceType.TEST_REPORT
    test_report: StructuredTestReport


EvidenceCreate = Annotated[
    TextEvidenceCreate | TestReportEvidenceCreate,
    Field(discriminator="evidence_type"),
]


class EvidenceSourceContext(BaseModel):
    kind: EvidenceSourceKind
    reference: SourceReference | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> "EvidenceSourceContext":
        if self.kind == EvidenceSourceKind.USER and self.reference is not None:
            raise ValueError("USER evidence cannot have a source reference")
        if self.kind == EvidenceSourceKind.AUTOMATION and self.reference is None:
            raise ValueError("AUTOMATION evidence requires a source reference")
        return self


class EvidenceResponse(BaseModel):
    id: int
    plan_version_id: int
    task_id: int
    attempt_number: int
    evidence_type: EvidenceType
    source_kind: EvidenceSourceKind
    source_ref: str | None
    text_content: str | None
    test_report: dict[str, object] | None
    submitted_by_user_id: int
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)
