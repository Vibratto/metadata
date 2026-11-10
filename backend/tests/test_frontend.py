"""Serving the built frontend."""

from pathlib import Path
from typing import Any

import pytest
from django.test import Client

# A request that fails is logged to the database.
pytestmark = pytest.mark.django_db

PAGE = b"<div id=app></div>"


@pytest.fixture
def dist(tmp_path: Path, settings: Any) -> Path:
    """A minimal built frontend."""
    (tmp_path / "index.html").write_bytes(PAGE)
    settings.FRONTEND_DIST = tmp_path
    return tmp_path


@pytest.mark.parametrize("path", ["/", "/library", "/settings/profile"])
def test_every_path_gets_the_entry_page(client: Client, dist: Path, path: str) -> None:
    # A direct link loads the same page; the frontend's router picks the view.
    response = client.get(path)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == PAGE


def test_without_a_built_frontend_there_is_no_page(client: Client, dist: Path) -> None:
    (dist / "index.html").unlink()
    assert client.get("/").status_code == 404


def test_unknown_api_path_is_a_404_not_the_entry_page(client: Client, dist: Path) -> None:
    response = client.get("/api/does-not-exist/")
    assert response.status_code == 404
    assert b"id=app" not in response.content


def test_entry_page_is_read_only(client: Client, dist: Path) -> None:
    assert client.post("/library").status_code == 405
