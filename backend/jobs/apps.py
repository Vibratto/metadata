"""``jobs`` app configuration."""

import importlib
import pkgutil

from django.apps import AppConfig, apps


class JobsConfig(AppConfig):
    """``jobs`` app configuration."""

    name = "jobs"

    def ready(self) -> None:
        """Imports every ``<app>/tasks/`` module so its tasks register themselves."""
        for config in apps.get_app_configs():
            try:
                package = importlib.import_module(f"{config.name}.tasks")
            except ModuleNotFoundError as error:
                # Only a missing package is ignored; a failure inside one must surface.
                if error.name != f"{config.name}.tasks":
                    raise
                continue
            for module in pkgutil.iter_modules(package.__path__):
                importlib.import_module(f"{package.__name__}.{module.name}")
