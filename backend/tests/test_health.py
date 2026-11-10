"""Health check and OpenAPI schema."""

from pathlib import Path

from django.core.management import call_command
from django.test import Client


def test_health_answers_in_english_by_default(client: Client) -> None:
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "The service is working."}


def test_health_honours_accept_language(client: Client) -> None:
    response = client.get("/api/health/", headers={"accept-language": "es"})
    assert response.json()["message"] == "El servicio funciona."


def test_schema_validates_and_leaves_no_view_undescribed(tmp_path: Path) -> None:
    call_command("spectacular", file=str(tmp_path / "o.yaml"), validate=True, fail_on_warn=True)


def test_schema_is_served(client: Client) -> None:
    assert client.get("/api/schema/").status_code == 200
