"""New-release API tests."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from activity.models import ActivityLog
from catalog.models import Artist
from watches.models import Watch, WatchArtist, WatchRun

pytestmark = pytest.mark.django_db

URL = "/api/v1/watches/"


@pytest.fixture
def watch() -> Watch:
    return Watch.objects.create(name="Rosalía releases")


def test_anonymous_is_forbidden() -> None:
    assert APIClient().get(URL).status_code == 403


def test_creates_lists_and_logs(api: APIClient) -> None:
    response = api.post(URL, {"name": "New releases"}, format="json")
    assert response.status_code == 201
    assert response.json()["enabled"] is True
    assert api.get(URL).json()["results"][0]["name"] == "New releases"
    assert ActivityLog.objects.filter(
        action="watches.created", username="owner", object_id=str(response.json()["id"])
    ).exists()


def test_duplicate_name_is_rejected(api: APIClient, watch: Watch) -> None:
    response = api.post(URL, {"name": watch.name}, format="json")
    assert response.status_code == 400


def test_updates_enabled_flag(api: APIClient, watch: Watch) -> None:
    response = api.patch(f"{URL}{watch.pk}/", {"enabled": False}, format="json")
    assert response.json()["enabled"] is False
    assert ActivityLog.objects.filter(
        action="watches.updated", username="owner", object_id=str(watch.pk)
    ).exists()


def test_deletes_a_watch_without_checks(api: APIClient, watch: Watch) -> None:
    assert api.delete(f"{URL}{watch.pk}/").status_code == 204
    assert not Watch.objects.exists()
    assert ActivityLog.objects.filter(
        action="watches.deleted", username="owner", object_id=str(watch.pk)
    ).exists()


def test_refuses_to_delete_a_watch_with_checks(api: APIClient, watch: Watch) -> None:
    WatchRun.objects.create(watch=watch, status=WatchRun.Status.SUCCEEDED)
    response = api.delete(f"{URL}{watch.pk}/")
    assert response.status_code == 409
    assert Watch.objects.filter(pk=watch.pk).exists()
    # The transaction rolls back the log row of the refused delete.
    assert not ActivityLog.objects.filter(action="watches.deleted").exists()


def test_runs_are_listed_newest_first(api: APIClient, watch: Watch) -> None:
    now = timezone.now()
    WatchRun.objects.create(
        watch=watch,
        status=WatchRun.Status.SUCCEEDED,
        started_at=now - timedelta(hours=2),
        finished_at=now - timedelta(hours=2),
        found=1,
    )
    WatchRun.objects.create(
        watch=watch,
        status=WatchRun.Status.FAILED,
        started_at=now,
        finished_at=now,
        detail="YouTube Music did not answer",
    )
    results = api.get(f"{URL}{watch.pk}/runs/").json()["results"]
    assert [row["status"] for row in results] == ["failed", "succeeded"]
    assert results[0]["detail"] == "YouTube Music did not answer"


def test_runs_of_unknown_watch_is_404(api: APIClient) -> None:
    assert api.get(f"{URL}999/runs/").status_code == 404


def test_creates_with_ordered_artists_and_settings(api: APIClient) -> None:
    second, first = Artist.objects.create(name="B"), Artist.objects.create(name="A")
    body = {
        "name": "New releases",
        "artist_ids": [first.pk, second.pk],
        "interval_hours": 6,
        "auto_download": True,
    }
    data = api.post(URL, body, format="json").json()
    assert [(a["id"], a["name"]) for a in data["artists"]] == [(first.pk, "A"), (second.pk, "B")]
    assert (data["interval_hours"], data["auto_download"]) == (6, True)
    assert "artist_ids" not in data


def test_replaces_artists_in_new_order(api: APIClient, watch: Watch) -> None:
    a, b = Artist.objects.create(name="A"), Artist.objects.create(name="B")
    api.patch(f"{URL}{watch.pk}/", {"artist_ids": [a.pk, b.pk]}, format="json")
    response = api.patch(f"{URL}{watch.pk}/", {"artist_ids": [b.pk]}, format="json")
    assert [x["name"] for x in response.json()["artists"]] == ["B"]


def test_patch_without_artist_ids_keeps_artists(api: APIClient, watch: Watch) -> None:
    artist = Artist.objects.create(name="A")
    WatchArtist.objects.create(watch=watch, artist=artist)
    response = api.patch(f"{URL}{watch.pk}/", {"enabled": False}, format="json")
    assert [x["id"] for x in response.json()["artists"]] == [artist.pk]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"artist_ids": [999]}, "artist_ids"),
        ({"interval_hours": 0}, "interval_hours"),
    ],
)
def test_rejects_invalid_fields(api: APIClient, body: dict[str, object], field: str) -> None:
    response = api.post(URL, {"name": "N", **body}, format="json")
    assert response.status_code == 400
    assert set(response.json()) == {field, "detail"}


def test_rejects_repeated_artists(api: APIClient) -> None:
    artist = Artist.objects.create(name="A")
    body = {"name": "N", "artist_ids": [artist.pk, artist.pk]}
    response = api.post(URL, body, format="json")
    assert set(response.json()) == {"artist_ids", "detail"}


def test_watches_filters_search_and_ordering(api: APIClient) -> None:
    ana, bea = Artist.objects.create(name="Ana"), Artist.objects.create(name="Bea")
    on = Watch.objects.create(name="Alfa", enabled=True, auto_download=True)
    off = Watch.objects.create(name="Beta", enabled=False)
    WatchArtist.objects.create(watch=on, artist=ana)
    WatchArtist.objects.create(watch=on, artist=bea)
    WatchArtist.objects.create(watch=off, artist=bea)

    def ids(query: str) -> list[int]:
        response = api.get(f"{URL}?{query}")
        assert response.status_code == 200
        return [w["id"] for w in response.json()["results"]]

    assert ids("enabled=true") == [on.pk]
    assert ids("enabled=false") == [off.pk]
    assert ids("auto_download=true") == [on.pk]
    assert ids(f"enabled=true&artist={ana.pk}") == [on.pk]
    assert sorted(ids(f"artist={ana.pk},{bea.pk}")) == sorted([on.pk, off.pk])
    assert api.get(f"{URL}?artist={ana.pk},{bea.pk}").json()["count"] == 2
    assert ids("search=beta") == [off.pk]
    assert ids("search=ana") == [on.pk]
    assert ids("ordering=-name") == [off.pk, on.pk]
    assert api.get(f"{URL}?ordering=next_run_at").status_code == 200
    assert api.get(f"{URL}?artist=x").status_code == 400
