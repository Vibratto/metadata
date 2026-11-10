"""Restricts the API to the application's own frontend."""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.translation import gettext as _

CLIENT_HEADER = "X-Vibratto-Client"
CLIENT_VALUE = "web"
# Deployments probe the health check without a client, and the schema feeds the frontend's
# type generator.
OPEN_PATHS = ("/api/health/", "/api/schema/", "/api/docs/")
# What a browser sends in Sec-Fetch-Site when the request does not come from another site.
OWN_ORIGIN = ("same-origin", "none")


class FrontendOnlyMiddleware:
    """Rejects with 403 any ``/api/`` request that does not come from the frontend.

    It requires the header the frontend adds to every request and, when the browser
    declares where the request comes from, that it is this very site. Someone imitating a
    browser by hand can still get through; the point is to stop casual use and to keep
    other websites from calling the API with the user's session.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if settings.API_FRONTEND_ONLY and self._is_foreign(request):
            return JsonResponse(
                {"detail": _("This API can only be used by the application's frontend.")},
                status=403,
            )
        return self.get_response(request)

    @staticmethod
    def _is_foreign(request: HttpRequest) -> bool:
        if not request.path.startswith("/api/") or request.path.startswith(OPEN_PATHS):
            return False
        if request.headers.get(CLIENT_HEADER) != CLIENT_VALUE:
            return True
        return request.headers.get("Sec-Fetch-Site", "same-origin") not in OWN_ORIGIN
