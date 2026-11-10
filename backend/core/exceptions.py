"""One format for every API error."""

from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler


def _messages(value: object) -> list[str]:
    if isinstance(value, dict):
        return [m for v in value.values() for m in _messages(v)]
    if isinstance(value, list):
        return [m for v in value for m in _messages(v)]
    return [str(value)]


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Make every error response carry a ``detail`` text.

    Validation errors keep their per-field keys as well, which the frontend uses to mark
    each field.
    """
    response = exception_handler(exc, context)
    if response is not None and not (
        isinstance(response.data, dict) and isinstance(response.data.get("detail"), str)
    ):
        body = (
            response.data
            if isinstance(response.data, dict)
            else {"non_field_errors": response.data}
        )
        response.data = {**body, "detail": " ".join(_messages(body))}
    return response
