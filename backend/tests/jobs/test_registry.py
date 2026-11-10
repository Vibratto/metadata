"""Tests for the task registry."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.apps import apps

from jobs import registry
from jobs.models import JobRun


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolates the registry from real tasks."""
    monkeypatch.setattr(registry, "_tasks", {})
    yield


def test_register_and_get() -> None:
    @registry.register("demo")
    def task(run: JobRun, params: dict[str, Any]) -> None:
        return None

    assert registry.get("demo") is task
    assert registry.kinds() == ["demo"]


def test_duplicate_kind_is_rejected() -> None:
    registry.register("demo")(lambda run, params: None)
    with pytest.raises(ValueError, match="demo"):
        registry.register("demo")(lambda run, params: None)


def test_unknown_kind() -> None:
    with pytest.raises(registry.UnknownJobKind):
        registry.get("nope")


def test_ready_discovers_task_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """``tests.testapp.tasks.demo`` registers itself without anyone importing it by hand."""
    import sys

    sys.modules.pop("tests.testapp.tasks.demo", None)
    apps.get_app_config("jobs").ready()
    assert "testapp_demo" in registry.kinds()


def test_ready_surfaces_errors_inside_a_tasks_package(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    real_import = importlib.import_module

    def fake_import(name: str) -> object:
        if name == "catalog.tasks":
            raise ModuleNotFoundError("falta una dependencia", name="requests_nope")
        return real_import(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    with pytest.raises(ModuleNotFoundError, match="dependencia"):
        apps.get_app_config("jobs").ready()
