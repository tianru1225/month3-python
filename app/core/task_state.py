from app.models.learning_task import TaskStatus


class InvalidTaskStatusTransition(ValueError):
    def __init__(self, current: TaskStatus, target: TaskStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"task status cannot transition from {current.value} to {target.value}"
        )


_ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.DRAFT: frozenset({TaskStatus.READY}),
    TaskStatus.READY: frozenset({TaskStatus.IN_PROGRESS}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.SUBMITTED}),
    TaskStatus.SUBMITTED: frozenset({TaskStatus.PASSED, TaskStatus.REVISION_REQUIRED}),
    TaskStatus.PASSED: frozenset(),
    TaskStatus.REVISION_REQUIRED: frozenset({TaskStatus.IN_PROGRESS}),
}


def allowed_task_status_targets(current: TaskStatus) -> frozenset[TaskStatus]:
    return _ALLOWED_TRANSITIONS[current]


def require_task_status_transition(
    current: TaskStatus,
    target: TaskStatus,
) -> None:
    if target not in allowed_task_status_targets(current):
        raise InvalidTaskStatusTransition(current, target)
