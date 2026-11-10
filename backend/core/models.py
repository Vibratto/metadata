"""Base models shared by every app."""

from typing import Any, NoReturn

from django.db import models


class AppendOnlyError(Exception):
    """An append-only record was modified or deleted."""


class AppendOnlyQuerySet(models.QuerySet["AppendOnlyModel"]):
    """Rejects bulk writes that alter existing rows.

    ``bulk_update`` goes through ``update()``, so it is covered too.
    """

    def update(self, **kwargs: Any) -> NoReturn:
        raise AppendOnlyError("Append-only records cannot be updated.")

    def delete(self) -> NoReturn:
        raise AppendOnlyError("Append-only records cannot be deleted.")


class AppendOnlyModel(models.Model):
    """Base for tables that only accept inserts.

    Enforced in Python rather than with database triggers, so it needs no
    engine-specific migration.
    """

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AppendOnlyError("Append-only records cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise AppendOnlyError("Append-only records cannot be deleted.")
