"""Fixtures shared by every test."""

import socket
from collections.abc import Callable
from typing import Any

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from proxies import routing

USERNAME = "owner"
PASSWORD = "a-long-and-unusual-password-9"


@pytest.fixture
def owner(db: None) -> User:
    """The application's single account."""
    return User.objects.create_user(USERNAME, password=PASSWORD)


@pytest.fixture
def anonymous() -> APIClient:
    """API client without a session."""
    return APIClient()


@pytest.fixture
def api(owner: User) -> APIClient:
    """API client signed in as the owner."""
    client = APIClient()
    client.force_login(owner)
    return client


@pytest.fixture(autouse=True)
def dns(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[tuple[str, int]]]:
    """Fake DNS: no host resolves unless a test registers it, so nothing reaches the network.

    Returns a function ``dns(host, *families)``. The list it returns records every lookup
    as ``(host, family)``.
    """
    records: dict[str, set[int]] = {}
    lookups: list[tuple[str, int]] = []

    def getaddrinfo(host: str, port: Any, family: int = 0, *args: Any, **kwargs: Any) -> Any:
        lookups.append((host, family))
        if family not in records.get(host, set()):
            raise socket.gaierror("no address")
        address = ("192.0.2.1", 443) if family == socket.AF_INET else ("2001:db8::1", 443, 0, 0)
        return [(family, socket.SOCK_STREAM, 6, "", address)]

    monkeypatch.setattr(routing, "getaddrinfo", getaddrinfo)

    def register(host: str, *families: int) -> list[tuple[str, int]]:
        records[host] = set(families)
        return lookups

    return register
