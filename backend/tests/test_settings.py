"""Settings that depend on environment variables."""

from pathlib import Path
from runpy import run_path

import pytest

BASE_SETTINGS = str(Path(__file__).resolve().parents[1] / "config" / "settings" / "base.py")


def test_forwarded_for_is_trusted_only_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DJANGO_AXES_TRUST_FORWARDED_FOR", raising=False)
    assert "AXES_IPWARE_PROXY_ORDER" not in run_path(BASE_SETTINGS)

    monkeypatch.setenv("DJANGO_AXES_TRUST_FORWARDED_FOR", "1")
    settings = run_path(BASE_SETTINGS)
    assert settings["AXES_IPWARE_PROXY_ORDER"] == "right-most"
    assert settings["AXES_IPWARE_META_PRECEDENCE_ORDER"] == ["HTTP_X_FORWARDED_FOR"]


def test_plain_http_is_allowed_only_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DJANGO_ALLOW_INSECURE_HTTP", raising=False)
    settings = run_path(BASE_SETTINGS)
    assert settings["SESSION_COOKIE_SECURE"] is True
    assert settings["CSRF_COOKIE_SECURE"] is True
    assert settings["SECURE_SSL_REDIRECT"] is True
    assert settings["SECURE_HSTS_SECONDS"] > 0

    monkeypatch.setenv("DJANGO_ALLOW_INSECURE_HTTP", "1")
    settings = run_path(BASE_SETTINGS)
    assert settings["SESSION_COOKIE_SECURE"] is False
    assert settings["CSRF_COOKIE_SECURE"] is False
    assert settings["SECURE_SSL_REDIRECT"] is False
    assert settings["SECURE_HSTS_SECONDS"] == 0


def test_frontend_is_served_only_when_it_has_been_built(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIBRATTO_FRONTEND_DIR", str(tmp_path))
    settings = run_path(BASE_SETTINGS)
    assert settings["FRONTEND_DIST"] == tmp_path
    assert settings["WHITENOISE_ROOT"] == tmp_path

    monkeypatch.setenv("VIBRATTO_FRONTEND_DIR", str(tmp_path / "missing"))
    assert "WHITENOISE_ROOT" not in run_path(BASE_SETTINGS)


def test_database_lives_in_the_data_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIBRATTO_DATA_DIR", str(tmp_path))
    database = run_path(BASE_SETTINGS)["DATABASES"]["default"]
    assert database["ENGINE"] == "django.db.backends.sqlite3"
    assert database["NAME"] == tmp_path / "db.sqlite3"


def test_setup_code_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIBRATTO_SETUP_CODE", raising=False)
    assert run_path(BASE_SETTINGS)["VIBRATTO_SETUP_CODE"] == ""
    monkeypatch.setenv("VIBRATTO_SETUP_CODE", "abc")
    assert run_path(BASE_SETTINGS)["VIBRATTO_SETUP_CODE"] == "abc"
