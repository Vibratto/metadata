"""``AppendOnlyModel`` accepts inserts and nothing else."""

import pytest

from core.models import AppendOnlyError
from tests.testapp.models import Entry

pytestmark = pytest.mark.django_db


def _create(text: str) -> Entry:
    entry = Entry(text=text)
    entry.save()
    return entry


def test_insert_and_read() -> None:
    entry = _create("a")
    entry.refresh_from_db()
    assert entry.text == "a"


def test_bulk_create_is_allowed() -> None:
    Entry.objects.bulk_create([Entry(text="a"), Entry(text="b")])
    assert Entry.objects.count() == 2


def test_save_on_existing_row_is_rejected() -> None:
    entry = _create("a")
    entry.text = "b"
    with pytest.raises(AppendOnlyError):
        entry.save()
    entry.refresh_from_db()
    assert entry.text == "a"


def test_instance_delete_is_rejected() -> None:
    entry = _create("a")
    with pytest.raises(AppendOnlyError):
        entry.delete()
    assert Entry.objects.count() == 1


def test_queryset_update_is_rejected() -> None:
    _create("a")
    with pytest.raises(AppendOnlyError):
        Entry.objects.all().update(**{"text": "b"})


def test_bulk_update_is_rejected() -> None:
    entry = _create("a")
    entry.text = "b"
    with pytest.raises(AppendOnlyError):
        Entry.objects.bulk_update([entry], ["text"])


def test_queryset_delete_is_rejected() -> None:
    _create("a")
    with pytest.raises(AppendOnlyError):
        Entry.objects.all().delete()
    assert Entry.objects.count() == 1
