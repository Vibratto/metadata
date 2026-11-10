"""Global settings views.

Administrators only: settings affect the whole server.
"""

from typing import Any

from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from activity.services import log_activity

from .defaults import DEFAULTS
from .models import Preference, get_value
from .serializers import PreferenceSerializer, PreferenceWriteSerializer


def _entry(key: str) -> dict[str, Any]:
    """Effective and default value of a key."""
    return {"key": key, "value": get_value(key), "default": DEFAULTS[key]}


def _ensure_declared(key: str) -> None:
    """404 for undeclared keys.

    Raises:
        NotFound: If the key is not declared.
    """
    if key not in DEFAULTS:
        raise NotFound(_("Unknown setting."))


class PreferenceListView(APIView):
    """Settings list."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=PreferenceSerializer(many=True), tags=["preferences"])
    def get(self, request: Request) -> Response:
        """Lists every setting with its value and its default."""
        entries = [_entry(key) for key in DEFAULTS]
        return Response(PreferenceSerializer(entries, many=True).data)  # type: ignore[arg-type]


class PreferenceDetailView(APIView):
    """Reads and changes one setting."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=PreferenceSerializer, tags=["preferences"])
    def get(self, request: Request, key: str) -> Response:
        """Returns one setting."""
        _ensure_declared(key)
        return Response(PreferenceSerializer(_entry(key)).data)

    @extend_schema(
        request=PreferenceWriteSerializer,
        responses={200: PreferenceSerializer},
        tags=["preferences"],
    )
    def put(self, request: Request, key: str) -> Response:
        """Changes a setting and logs it."""
        _ensure_declared(key)
        serializer = PreferenceWriteSerializer(data=request.data, context={"key": key})
        serializer.is_valid(raise_exception=True)
        value = serializer.validated_data["value"]
        Preference.objects.update_or_create(key=key, defaults={"value": value})
        log_activity(request.user, "preferences.updated", detail={"setting": key, "value": value})
        return Response(PreferenceSerializer(_entry(key)).data)
