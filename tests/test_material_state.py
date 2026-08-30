import pytest

from app.models.material import MaterialVersion, ParseStatus
from app.core.material_state import (
    InvalidMaterialStateTransition,
    ensure_transition_allowed,
    transition_parse_status,
)

_ALLOWED_PAIRS = {
    (ParseStatus.UPLOADED, ParseStatus.QUEUED),
    (ParseStatus.QUEUED, ParseStatus.PARSING),
    (ParseStatus.PARSING, ParseStatus.READY),
    (ParseStatus.PARSING, ParseStatus.FAILED),
    (ParseStatus.FAILED, ParseStatus.QUEUED),
}


@pytest.mark.parametrize(
    ("current", "target"),
    sorted(_ALLOWED_PAIRS, key=lambda pair: (pair[0].value, pair[1].value)),
)
def test_allowed_transitions(current: ParseStatus, target: ParseStatus) -> None:
    ensure_transition_allowed(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (current, target)
        for current in ParseStatus
        for target in ParseStatus
        if (current, target) not in _ALLOWED_PAIRS
    ],
)
def test_invalid_transitions_are_rejected(
    current: ParseStatus,
    target: ParseStatus,
) -> None:
    with pytest.raises(
        InvalidMaterialStateTransition,
        match=f"{current.value} -> {target.value}",
    ):
        ensure_transition_allowed(current, target)


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(
        InvalidMaterialStateTransition,
        match="unknown material parse current status",
    ):
        ensure_transition_allowed("UNKNOWN", ParseStatus.QUEUED)


def test_unknown_target_status_is_rejected() -> None:
    with pytest.raises(
        InvalidMaterialStateTransition,
        match="unknown material parse target status",
    ):
        ensure_transition_allowed(ParseStatus.UPLOADED, "UNKNOWN")


def test_transition_applies_value_without_database_commit() -> None:
    version = MaterialVersion(parse_status=ParseStatus.UPLOADED.value)

    transition_parse_status(version, ParseStatus.QUEUED)

    assert version.parse_status == ParseStatus.QUEUED.value


def test_transition_does_not_apply_invalid_target() -> None:
    version = MaterialVersion(parse_status=ParseStatus.READY.value)

    with pytest.raises(InvalidMaterialStateTransition):
        transition_parse_status(version, ParseStatus.QUEUED)

    assert version.parse_status == ParseStatus.READY.value
