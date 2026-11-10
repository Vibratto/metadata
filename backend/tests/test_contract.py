"""API contract: no documented route answers 5xx to generated input."""

from collections.abc import Iterator
from typing import Any

import pytest
import schemathesis
from django.contrib.auth.models import User
from django.core import signals
from django.core.wsgi import get_wsgi_application
from django.db import close_old_connections
from django.test import Client
from hypothesis import settings
from pytest_django.fixtures import Settings
from schemathesis import Case
from schemathesis.checks import not_a_server_error
from schemathesis.specs.openapi.schemas import OpenApiSchema

CSRF = "a" * 32


@pytest.fixture
def headers(owner: User, client: Client) -> dict[str, str]:
    """A signed-in session and its CSRF token, so protected routes are exercised too."""
    client.force_login(owner)
    session = client.cookies["sessionid"].value
    return {"Cookie": f"sessionid={session}; csrftoken={CSRF}", "X-CSRFToken": CSRF}


@pytest.fixture
def api_schema(headers: dict[str, str], settings: Settings) -> Iterator[OpenApiSchema]:
    """The schema as served by the application itself."""
    settings.ALLOWED_HOSTS = ["localhost"]
    # The real WSGI application closes database connections around each request, which
    # would end the test's transaction. Django's test client disconnects these too.
    signals.request_started.disconnect(close_old_connections)
    signals.request_finished.disconnect(close_old_connections)
    yield schemathesis.openapi.from_wsgi("/api/schema/", get_wsgi_application())
    signals.request_started.connect(close_old_connections)
    signals.request_finished.connect(close_old_connections)


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.parametrize()
# derandomize: CI must not fail on examples that differ from one run to the next.
@settings(max_examples=5, deadline=None, derandomize=True)
def test_contract(case: Case[Any], headers: dict[str, str]) -> None:
    case.call_and_validate(headers=headers, checks=[not_a_server_error])
