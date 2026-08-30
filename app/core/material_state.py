from app.models.material import MaterialVersion, ParseStatus


class InvalidMaterialStateTransition(ValueError):
    """Raised when a material version attempts an unsupported status change."""


_ALLOWED_TRANSITIONS: dict[ParseStatus, frozenset[ParseStatus]] = {
    ParseStatus.UPLOADED: frozenset({ParseStatus.QUEUED}),
    ParseStatus.QUEUED: frozenset({ParseStatus.PARSING}),
    ParseStatus.PARSING: frozenset({ParseStatus.READY, ParseStatus.FAILED}),
    ParseStatus.READY: frozenset(),
    ParseStatus.FAILED: frozenset({ParseStatus.QUEUED}),
}


def _as_status(value: str | ParseStatus, *, field: str) -> ParseStatus:
    try:
        return value if isinstance(value, ParseStatus) else ParseStatus(value)
    except ValueError as exc:
        raise InvalidMaterialStateTransition(
            f"unknown material parse {field}: {value!r}"
        ) from exc


def ensure_transition_allowed(
    current: str | ParseStatus,
    target: str | ParseStatus,
) -> None:
    current_status = _as_status(current, field="current status")
    target_status = _as_status(target, field="target status")
    if target_status not in _ALLOWED_TRANSITIONS[current_status]:
        raise InvalidMaterialStateTransition(
            "invalid material parse status transition: "
            f"{current_status.value} -> {target_status.value}"
        )


def transition_parse_status(
    version: MaterialVersion,
    target: ParseStatus,
) -> None:
    """Validate and apply a status change without committing the session."""
    current = _as_status(version.parse_status, field="current status")
    ensure_transition_allowed(current, target)
    version.parse_status = target.value
