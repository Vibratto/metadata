"""Health check and the frontend's entry page."""

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest
from django.http.response import HttpResponseBase
from django.utils.translation import gettext as _
from django.views.decorators.http import require_safe
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from .serializers import HealthSerializer


@extend_schema(responses=HealthSerializer, tags=["core"])
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    """Report that the service is up. Used by the frontend and by deployments."""
    return Response({"status": "ok", "message": _("The service is working.")})


@require_safe
def spa(request: HttpRequest) -> HttpResponseBase:
    """Serve the frontend's entry page for any path outside the API.

    The frontend's router resolves the path in the browser, so a direct link such as
    ``/library`` has to load the same page.
    """
    index = settings.FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise Http404
    return FileResponse(index.open("rb"), content_type="text/html; charset=utf-8")
