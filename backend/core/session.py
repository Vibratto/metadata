"""Keeps background polling from renewing the session."""

from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest, HttpResponse

# Sent by the frontend on automatic polling, never on something the user did.
BACKGROUND_HEADER = "X-Background-Poll"


class IdleSessionMiddleware(SessionMiddleware):
    """Neither saves nor renews the session on a polling GET.

    Otherwise a page left open would keep an idle session alive for ever.
    """

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        if request.method == "GET" and request.headers.get(BACKGROUND_HEADER) == "1":
            return response
        return super().process_response(request, response)
