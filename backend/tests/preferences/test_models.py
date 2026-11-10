"""Tests for ``preferences``."""

from typing import Any

import pytest
from django.core.exceptions import ValidationError

from preferences import defaults
from preferences.models import Preference, get_value

pytestmark = pytest.mark.django_db


@pytest.fixture
def declared_keys(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Declares two test keys."""
    keys: dict[str, Any] = {"tema": "claro", "puntos": 3}
    monkeypatch.setattr(defaults, "DEFAULTS", keys)
    monkeypatch.setattr("preferences.models.DEFAULTS", keys)
    return keys


def test_get_value_returns_default_without_row(declared_keys: dict[str, Any]) -> None:
    assert get_value("tema") == "claro"


def test_get_value_returns_stored_value(declared_keys: dict[str, Any]) -> None:
    Preference.objects.create(key="tema", value="oscuro")
    assert get_value("tema") == "oscuro"


def test_stored_null_is_a_real_value(declared_keys: dict[str, Any]) -> None:
    Preference.objects.create(key="tema", value=None)
    assert get_value("tema") is None


def test_get_value_rejects_undeclared_key(declared_keys: dict[str, Any]) -> None:
    with pytest.raises(KeyError):
        get_value("desconocida")


def test_clean_accepts_declared_key(declared_keys: dict[str, Any]) -> None:
    Preference(key="tema", value="oscuro").clean()


def test_clean_rejects_undeclared_key(declared_keys: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Preference(key="desconocida", value=1).clean()


def test_change_is_recorded_in_history(declared_keys: dict[str, Any]) -> None:
    pref = Preference.objects.create(key="puntos", value=3)
    pref.value = 5
    pref.save()
    assert pref.history.count() == 2


def test_preference_str_is_its_key() -> None:
    assert str(Preference(key="tema", value="claro")) == "tema"
