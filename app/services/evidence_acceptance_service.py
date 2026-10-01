from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.evidence import Evidence, EvidenceType
from app.models.evaluation import EvaluationDecision, RuleEvaluationStatus
from app.models.learning_plan import PlanVersionStatus
from app.models.learning_task import TaskStatus
from app.repositories.evaluation_repository import (
    get_latest_evidence_for_task,
)
from app.repositories.learning_task_repository import (
    get_owned_plan_version,
    get_task,
)
from app.schemas.evaluation import HumanDecisionCreate, RuleEvaluationCreate
from app.schemas.evidence_acceptance import EvidenceAcceptanceResponse
from app.schemas.evidence import EvidenceResponse
from app.schemas.evaluation import EvaluationResponse
from app.services.evaluation_service import (
    confirm_evaluation,
    create_evaluation,
    finalize_evaluation,
)


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _rule_for(
    evidence: Evidence,
) -> tuple[RuleEvaluationStatus, dict[str, object], EvaluationDecision]:
    if EvidenceType(evidence.evidence_type) is EvidenceType.TEXT_ANSWER:
        return (
            RuleEvaluationStatus.PASS,
            {
                "evidence_type": EvidenceType.TEXT_ANSWER.value,
                "passed": True,
                "reason": "text answer is non-empty",
            },
            EvaluationDecision.PASSED,
        )

    report = evidence.test_report
    if not isinstance(report, dict):
        return (
            RuleEvaluationStatus.FAIL,
            {
                "evidence_type": EvidenceType.TEST_REPORT.value,
                "passed": False,
                "reason": "test report is missing",
            },
            EvaluationDecision.REVISION_REQUIRED,
        )

    raw_checks = report.get("checks")
    checks = raw_checks if isinstance(raw_checks, list) else []
    failed_checks: list[str] = []
    for raw_check in checks:
        if not isinstance(raw_check, dict):
            failed_checks.append("invalid-check")
            continue
        if raw_check.get("status") != "PASSED":
            failed_checks.append(str(raw_check.get("name", "unnamed-check")))

    exit_code = report.get("exit_code")
    passed = bool(checks) and exit_code == 0 and not failed_checks
    result: dict[str, object] = {
        "evidence_type": EvidenceType.TEST_REPORT.value,
        "passed": passed,
        "exit_code": exit_code,
        "check_count": len(checks),
        "failed_checks": failed_checks,
        "reason": (
            "exit code is 0 and every check passed"
            if passed
            else "exit code must be 0 and every check must pass"
        ),
    }
    return (
        RuleEvaluationStatus.PASS if passed else RuleEvaluationStatus.FAIL,
        result,
        EvaluationDecision.PASSED if passed else EvaluationDecision.REVISION_REQUIRED,
    )


def evaluate_latest_evidence(
    db: Session,
    *,
    plan_version_id: int,
    task_id: int,
    user_id: int,
) -> EvidenceAcceptanceResponse:
    version = get_owned_plan_version(
        db,
        plan_version_id=plan_version_id,
        user_id=user_id,
    )
    if version is None:
        raise _error(
            "PLAN_VERSION_NOT_FOUND",
            "plan version not found",
            status.HTTP_404_NOT_FOUND,
        )

    task = get_task(
        db,
        plan_version_id=plan_version_id,
        task_id=task_id,
    )
    if task is None:
        raise _error(
            "LEARNING_TASK_NOT_FOUND",
            "learning task not found in this plan version",
            status.HTTP_404_NOT_FOUND,
        )
    if version.status != PlanVersionStatus.PUBLISHED.value or not version.is_current:
        raise _error(
            "PLAN_VERSION_NOT_ACTIVE",
            "evaluation requires the current published plan version",
            status.HTTP_409_CONFLICT,
        )
    if task.status != TaskStatus.SUBMITTED.value:
        raise _error(
            "EVIDENCE_NOT_SUBMITTED",
            "task must be submitted before evaluation",
            status.HTTP_409_CONFLICT,
        )

    evidence = get_latest_evidence_for_task(db, task_id=task.id)
    if evidence is None:
        raise _error(
            "EVIDENCE_NOT_FOUND",
            "task has no evidence to evaluate",
            status.HTTP_409_CONFLICT,
        )

    rule_status, rule_result, decision = _rule_for(evidence)
    evaluation = create_evaluation(
        db,
        evidence_id=evidence.id,
        user_id=user_id,
        payload=RuleEvaluationCreate(
            evidence_id=evidence.id,
            rule_status=rule_status,
            rule_result=rule_result,
        ),
    )
    evaluation = confirm_evaluation(
        db,
        evaluation_id=evaluation.id,
        user_id=user_id,
        payload=HumanDecisionCreate(
            decision=decision,
            note=str(rule_result["reason"]),
        ),
    )
    evaluation = finalize_evaluation(
        db,
        evaluation_id=evaluation.id,
        user_id=user_id,
    )
    return EvidenceAcceptanceResponse(
        evidence=EvidenceResponse.model_validate(evidence),
        evaluation=EvaluationResponse.model_validate(evaluation),
        task_status=TaskStatus(task.status),
    )
