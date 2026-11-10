"""Library backup: export, preview and restore."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import QuerySet
from rest_framework.test import APIClient

from activity.models import ActivityLog
from catalog.backup import LIBRARY_MODELS, UPLOAD_PREFIX, BackupError, upload_path
from catalog.factories import ArtistFactory, DownloadFactory, TrackArtistFactory, TrackFactory
from catalog.models import Artist, BlockedItem, Download, Recording, Track
from jobs import runner
from jobs.models import JobRun

pytestmark = pytest.mark.django_db

BASE = "/api/v1/catalog/backup"


@pytest.fixture(autouse=True)
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary folder of our own, to see which files are left behind."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


def _library() -> None:
    """A library with every kind of row a backup holds."""
    track = TrackFactory()
    TrackArtistFactory(track=track, position=1)
    DownloadFactory(track=track)
    TrackFactory(album=track.album)
    main = track.credits.get(position=0).artist
    main.related.add(ArtistFactory(name="Related profile"))
    BlockedItem.objects.create(kind="album", external_id="MPREb_bad", name="Bad")


def _export(api: APIClient) -> list[dict[str, Any]]:
    response = api.get(f"{BASE}/")
    assert response.status_code == 200
    return json.loads(response.content)


def _instants(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The backup with its timestamps as instants rather than text.

    ``dumpdata`` writes a time with 1 to 999 microseconds as ``…59.000Z`` and the restored
    one, with none, as ``…59Z``: the same instant at the format's millisecond precision.
    """

    def instant(value: Any) -> Any:
        if isinstance(value, str) and value.endswith("Z"):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return value
        return value

    return [{**e, "fields": {k: instant(v) for k, v in e["fields"].items()}} for e in entries]


def _file(entries: Any, raw: bytes | None = None) -> SimpleUploadedFile:
    content = raw if raw is not None else json.dumps(entries).encode()
    return SimpleUploadedFile("library.json", content, content_type="application/json")


def _empty_library() -> None:
    """Empty the library tables, the append-only ones included."""
    QuerySet(Artist.related.through)._raw_delete("default")
    for label in reversed(LIBRARY_MODELS):
        QuerySet(apps.get_model(label))._raw_delete("default")


def _preview(api: APIClient, entries: Any) -> Any:
    return api.post(f"{BASE}/preview/", {"file": _file(entries)}, format="multipart")


def _restore(api: APIClient, entries: Any) -> Any:
    return api.post(f"{BASE}/restore/", {"file": _file(entries)}, format="multipart")


def _entry(entries: list[dict[str, Any]], model: str) -> dict[str, Any]:
    return next(e for e in entries if e["model"] == model)


# --- Access ---


def test_a_session_is_required(anonymous: APIClient) -> None:
    assert anonymous.get(f"{BASE}/").status_code == 403
    assert anonymous.post(f"{BASE}/preview/").status_code == 403
    assert anonymous.post(f"{BASE}/restore/").status_code == 403


# --- Export ---


def test_export_is_a_json_attachment_with_the_library_models_only(api: APIClient) -> None:
    _library()
    response = api.get(f"{BASE}/")
    assert response["Content-Type"] == "application/json"
    assert response["Content-Disposition"].startswith('attachment; filename="vibratto-metadata-')
    # No history tables and no users: they mean nothing on another installation.
    assert {entry["model"] for entry in _export(api)} == set(LIBRARY_MODELS)


def test_export_keeps_related_artists(api: APIClient) -> None:
    _library()
    related = Artist.objects.get(name="Related profile")
    owners = [e for e in _export(api) if e["model"] == "catalog.artist" and e["fields"]["related"]]
    assert [e["fields"]["related"] for e in owners] == [[related.pk]]


# --- Preview ---


def test_preview_counts_what_the_backup_holds_and_what_already_exists(api: APIClient) -> None:
    _library()
    entries = _export(api)
    entries.append({"model": "catalog.artist", "pk": 999, "fields": {"name": "New"}})

    response = _preview(api, entries)

    assert response.status_code == 200
    assert response.json() == {
        "artists": {"total": Artist.objects.count() + 1, "existing": Artist.objects.count()},
        "albums": {"total": 1, "existing": 1},
        "tracks": {"total": 2, "existing": 2},
        "downloads": {"total": 1, "existing": 1},
    }


def test_preview_changes_nothing(api: APIClient, upload_dir: Path) -> None:
    _library()
    entries = _export(api)
    _empty_library()
    assert _preview(api, entries).status_code == 200
    assert not Artist.objects.exists()
    assert list(upload_dir.iterdir()) == []


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b'{"model": "catalog.artist"}',
        b'[{"model": "auth.user", "pk": 1, "fields": {"username": "x"}}]',
        b'[{"model": "catalog.artist", "pk": 1}]',
        b'[{"model": "catalog.artist", "pk": 1, "fields": {"no_such_field": 1}}]',
        b'[{"model": "catalog.album", "pk": 1, "fields": {"title": "x", "year": "soon"}}]',
    ],
    ids=["not-json", "not-a-list", "other-model", "no-fields", "unknown-field", "bad-value"],
)
def test_invalid_files_are_refused_by_preview_and_restore(api: APIClient, raw: bytes) -> None:
    for action in ("preview", "restore"):
        response = api.post(f"{BASE}/{action}/", {"file": _file(None, raw)}, format="multipart")
        assert response.status_code == 400, action
        assert response.json()["detail"]
    assert not JobRun.objects.exists()


def test_missing_file_is_a_400(api: APIClient) -> None:
    assert api.post(f"{BASE}/preview/", {}, format="multipart").status_code == 400
    assert api.post(f"{BASE}/restore/", {}, format="multipart").status_code == 400


# --- Restore ---


def test_restore_into_an_empty_library_brings_everything_back(
    api: APIClient, owner: User, upload_dir: Path
) -> None:
    _library()
    entries = _export(api)
    _empty_library()

    response = _restore(api, entries)

    assert response.status_code == 201
    run = JobRun.objects.get(kind="library_restore")
    assert (run.status, run.user) == (JobRun.Status.SUCCEEDED, owner)
    assert run.summary == {"created": len(entries), "skipped": 0}
    assert run.lines.get().message == f"{len(entries)} items added, 0 already existed."
    assert _instants(_export(api)) == _instants(entries)
    # The uploaded copy is deleted once the job is done.
    assert list(upload_dir.iterdir()) == []
    assert ActivityLog.objects.filter(action="catalog.library.restore_started").count() == 1


def test_restore_twice_adds_nothing_the_second_time(api: APIClient) -> None:
    _library()
    entries = _export(api)
    _restore(api, entries)
    run = JobRun.objects.latest("pk")
    assert run.summary == {"created": 0, "skipped": len(entries)}
    assert _export(api) == entries


def test_restore_adds_only_what_is_missing_and_keeps_edits(api: APIClient) -> None:
    _library()
    entries = _export(api)
    kept = Artist.objects.order_by("pk").first()
    assert kept is not None
    Artist.objects.filter(pk=kept.pk).update(name="Edited by hand")
    QuerySet(Download)._raw_delete("default")
    BlockedItem.objects.all().delete()

    _restore(api, entries)

    assert JobRun.objects.latest("pk").summary == {"created": 2, "skipped": len(entries) - 2}
    assert Artist.objects.get(pk=kept.pk).name == "Edited by hand"
    assert Download.objects.count() == 1 and BlockedItem.objects.count() == 1


def test_new_ids_continue_after_the_restored_ones(api: APIClient) -> None:
    _library()
    entries = _export(api)
    highest = max(e["pk"] for e in entries if e["model"] == "catalog.artist")
    _empty_library()
    _restore(api, entries)
    assert Artist.objects.create(name="Later").pk > highest


def test_second_restore_is_refused_while_one_is_running(api: APIClient, upload_dir: Path) -> None:
    JobRun.objects.create(kind="library_restore", status=JobRun.Status.RUNNING)
    response = _restore(api, [])
    assert response.status_code == 409
    assert response.json() == {"detail": "A job of this kind is already running."}
    assert list(upload_dir.iterdir()) == []


def test_restore_job_deletes_its_file_even_when_it_fails(upload_dir: Path) -> None:
    name = f"{UPLOAD_PREFIX}broken.json"
    (upload_dir / name).write_text("not json")
    run = runner.start("library_restore", {"file": name}, None)
    assert run.status == JobRun.Status.FAILED
    assert list(upload_dir.iterdir()) == []


@pytest.mark.parametrize(
    "name", [None, 3, "library.json", f"../{UPLOAD_PREFIX}x.json", f"sub/{UPLOAD_PREFIX}x.json"]
)
def test_restore_job_only_reads_files_the_api_uploaded(name: object) -> None:
    with pytest.raises(BackupError):
        upload_path(name)


# --- Backups from another installation ---


def test_backup_whose_ids_belong_to_other_items_here_is_refused(api: APIClient) -> None:
    _library()
    entries = _export(api)
    # On this installation the same primary keys now belong to different items.
    for index, artist in enumerate(Artist.objects.exclude(ytmusic_id=None)):
        Artist.objects.filter(pk=artist.pk).update(ytmusic_id=f"UCsomeone-else-{index}")
    artists = list(Artist.objects.values_list("pk", "ytmusic_id"))

    for response in (_preview(api, entries), _restore(api, entries)):
        assert response.status_code == 400
        assert "clashes with this library" in response.json()["detail"]
    assert list(Artist.objects.values_list("pk", "ytmusic_id")) == artists
    assert not JobRun.objects.exists()


def test_external_id_held_by_another_row_is_a_clash(api: APIClient) -> None:
    artist = ArtistFactory(ytmusic_id="UCsame")
    entries = [
        {
            "model": "catalog.artist",
            "pk": artist.pk + 50,
            "fields": {"name": "Twin", "ytmusic_id": "UCsame"},
        }
    ]
    assert _preview(api, entries).status_code == 400


def test_id_assigned_after_the_backup_was_made_still_fits(api: APIClient) -> None:
    guest = Artist.objects.create(name="Guest")
    entries = _export(api)
    guest.ytmusic_id = "UCguest"
    guest.save()
    assert _preview(api, entries).json()["artists"] == {"total": 1, "existing": 1}


def test_credits_recreated_since_the_backup_are_not_duplicated(api: APIClient) -> None:
    track = TrackFactory()
    entries = _export(api)
    credit = track.recording.credits.get()
    artist, position = credit.artist, credit.position
    credit.delete()
    track.recording.credits.create(artist=artist, position=position)  # same credit, new pk

    _restore(api, entries)

    assert track.recording.credits.count() == 1
    assert JobRun.objects.latest("pk").summary["created"] == 0


# --- Download paths ---


@pytest.mark.parametrize(
    "path",
    ["/var/lib/vibratto-metadata/db.sqlite3", "../outside.mp3", "Artist/../../outside.mp3", "", 5,
     "C:\\Windows\\x.mp3", "\\\\server\\share\\x.mp3"],
)  # fmt: skip
def test_download_paths_must_stay_inside_the_library(api: APIClient, path: Any) -> None:
    DownloadFactory()
    entries = _export(api)
    download = _entry(entries, "catalog.download")
    download["fields"]["file_path"] = path
    _empty_library()

    for response in (_preview(api, entries), _restore(api, entries)):
        assert response.status_code == 400
        assert response.json() == {"detail": "The backup has download paths outside the library."}
    assert not Download.objects.exists()


def test_odd_but_harmless_file_names_are_accepted(api: APIClient) -> None:
    DownloadFactory()
    entries = _export(api)
    _entry(entries, "catalog.download")["fields"]["file_path"] = "Artist/Álbum/01 - Song..mp3"
    _empty_library()
    assert _restore(api, entries).status_code == 201
    assert Download.objects.get().file_path == "Artist/Álbum/01 - Song..mp3"


def test_restored_rows_are_the_same_rows(api: APIClient) -> None:
    _library()
    before = (
        list(Track.objects.values_list("pk", "album", "recording", "track_number")),
        list(Recording.objects.values_list("pk", "video_id")),
    )
    entries = _export(api)
    _empty_library()
    _restore(api, entries)
    after = (
        list(Track.objects.values_list("pk", "album", "recording", "track_number")),
        list(Recording.objects.values_list("pk", "video_id")),
    )
    assert after == before
