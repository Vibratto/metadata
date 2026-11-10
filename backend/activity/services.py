"""Activity services."""

from typing import Any

from django.contrib.auth.models import AnonymousUser, User
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model

from activity.logs import redact
from activity.models import ActivityLog


def log_activity(
    user: User | AnonymousUser | None,
    action: str,
    obj: Model | None = None,
    detail: dict[str, Any] | None = None,
) -> ActivityLog:
    """Records an action in the activity history.

    Args:
        user: The actor; ``None`` or anonymous for system actions.
        action: Action code, e.g. ``"catalog.artist.blocked"``.
        obj: Affected object, if any.
        detail: Extra JSON-serializable data; sensitive values are hidden.

    Returns:
        The created row.
    """
    actor = user if user is not None and user.is_authenticated else None
    return ActivityLog.objects.create(
        user=actor,
        username=actor.get_username() if actor else "",
        action=action,
        content_type=ContentType.objects.get_for_model(obj) if obj else None,
        # Assigned without ``target``: with ``None`` the GFK would null ``object_id``.
        object_id=str(obj.pk) if obj else "",
        detail=redact(detail or {}),
    )
