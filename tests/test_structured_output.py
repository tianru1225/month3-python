import asyncio
import json

import pytest

from app.schemas.structured_output import (
    LearningPlanItem,
)
from app.services.errors import (
    StructuredOutputValidationError,
)
from app.services.structured_output import (
    build_json_schema,
    validate_structured_output,
)


def valid_json() -> str:
    return json.dumps(
        {
            "title": "Learn async boundaries",
            "objective": ("Understand cancellation and retry ownership"),
            "estimated_minutes": 60,
            "acceptance_criteria": [
                "Explain timeout types",
                "Explain retry boundaries",
            ],
        }
    )


def test_valid_output_is_accepted() -> None:
    result = asyncio.run(
        validate_structured_output(
            valid_json(),
            LearningPlanItem,
        )
    )

    assert result.outcome == "validated"
    assert result.repairs_used == 0
    assert result.value.title == ("Learn async boundaries")

    schema = build_json_schema(LearningPlanItem)
    assert "title" in schema["properties"]
    assert "estimated_minutes" in (schema["properties"])


def test_invalid_output_is_repaired_once() -> None:
    repair_calls: list[tuple[str, str]] = []

    async def repair(
        candidate: str,
        instruction: str,
    ) -> str:
        repair_calls.append((candidate, instruction))
        assert "estimated_minutes" in instruction
        return valid_json()

    result = asyncio.run(
        validate_structured_output(
            '{"title":"missing fields"}',
            LearningPlanItem,
            repair=repair,
            max_repairs=1,
        )
    )

    assert result.outcome == "repaired"
    assert result.repairs_used == 1
    assert result.value.estimated_minutes == 60
    assert len(repair_calls) == 1


def test_repair_budget_ends_in_final_failure() -> None:
    repair_calls = 0

    async def repair(
        candidate: str,
        instruction: str,
    ) -> str:
        nonlocal repair_calls
        repair_calls += 1
        return '{"still":"invalid"}'

    with pytest.raises(StructuredOutputValidationError) as exc_info:
        asyncio.run(
            validate_structured_output(
                '{"invalid":true}',
                LearningPlanItem,
                repair=repair,
                max_repairs=1,
            )
        )

    assert repair_calls == 1
    assert exc_info.value.code == ("STRUCTURED_OUTPUT_INVALID")
    assert exc_info.value.repairs_used == 1
