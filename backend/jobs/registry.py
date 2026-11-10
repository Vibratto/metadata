"""Task type registry.

Each app adds its tasks in its own ``<app>/tasks/`` modules; they are imported
once at startup (see ``JobsConfig.ready``), so nothing shared has to change.
"""

from collections.abc import Callable
from typing import Any

from jobs.models import JobRun

#: A task takes its run and params and returns the final summary.
TaskFunc = Callable[[JobRun, dict[str, Any]], dict[str, Any] | None]

_tasks: dict[str, TaskFunc] = {}


class UnknownJobKind(KeyError):
    """No task is registered under that kind."""


def register(kind: str) -> Callable[[TaskFunc], TaskFunc]:
    """Decorator registering a function as the task of type ``kind``.

    Args:
        kind: Stable type identifier (stored in ``JobRun.kind``).

    Raises:
        ValueError: If the kind is already registered.
    """

    def decorator(func: TaskFunc) -> TaskFunc:
        if kind in _tasks:
            raise ValueError(f"The job kind “{kind}” is already registered.")
        _tasks[kind] = func
        return func

    return decorator


def get(kind: str) -> TaskFunc:
    """Returns the function for a kind.

    Raises:
        UnknownJobKind: If the kind does not exist.
    """
    try:
        return _tasks[kind]
    except KeyError:
        raise UnknownJobKind(kind) from None


def kinds() -> list[str]:
    """Lists registered kinds, sorted."""
    return sorted(_tasks)
