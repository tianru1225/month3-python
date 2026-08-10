import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import settings
from app.services.errors import (
    StructuredOutputValidationError,
)

ModelT = TypeVar("ModelT", bound=BaseModel)

RepairCallback = Callable[
    [str, str],
    Awaitable[str],
]

ValidationOutcome = Literal[
    "validated",
    "repaired",
]


@dataclass(frozen=True)
class StructuredOutputResult(Generic[ModelT]):
    value: ModelT
    repairs_used: int
    outcome: ValidationOutcome


def build_json_schema(
    model_type: type[ModelT],
) -> dict[str, Any]:
    return model_type.model_json_schema()


def build_repair_instruction(
    model_type: type[ModelT],
    validation_message: str,
) -> str:
    schema = build_json_schema(model_type)
    schema_text = json.dumps(
        schema,
        ensure_ascii=False,
        indent=2,
    )

    return (
        "Return only one valid JSON object "
        "matching this JSON Schema.\n\n"
        f"{schema_text}\n\n"
        "Validation problem:\n"
        f"{validation_message}"
    )


def _validate_candidate(
    raw_text: str,
    model_type: type[ModelT],
) -> ModelT:
    try:
        parsed: object = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError("candidate is not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("candidate JSON must be an object")

    try:
        return model_type.model_validate(parsed)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


async def validate_structured_output(
    raw_text: str,
    model_type: type[ModelT],
    *,
    repair: RepairCallback | None = None,
    max_repairs: int | None = None,
) -> StructuredOutputResult[ModelT]:
    repair_limit = (
        settings.llm_structured_max_repairs if max_repairs is None else max_repairs
    )

    if repair_limit < 0:
        raise ValueError("max_repairs must not be negative")

    candidate = raw_text

    for repairs_used in range(repair_limit + 1):
        try:
            value = _validate_candidate(
                candidate,
                model_type,
            )

            outcome: ValidationOutcome = (
                "validated" if repairs_used == 0 else "repaired"
            )

            return StructuredOutputResult(
                value=value,
                repairs_used=repairs_used,
                outcome=outcome,
            )
        except ValueError as exc:
            if repair is None or repairs_used >= repair_limit:
                raise StructuredOutputValidationError(
                    "structured output validation failed",
                    repairs_used=repairs_used,
                ) from exc

            instruction = build_repair_instruction(
                model_type,
                str(exc),
            )
            candidate = await repair(
                candidate,
                instruction,
            )

    raise StructuredOutputValidationError(
        "structured output validation failed",
        repairs_used=repair_limit,
    )
