"""Catalogue API: reading, editing, history, deleting, blocking and artist lookup."""

from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from activity.models import ActivityLog
from catalog import views
from catalog.factories import (
    AlbumArtistFactory,
    AlbumFactory,
    ArtistFactory,
    DownloadFactory,
    TrackFactory,
)
from catalog.models import Album, Artist, BlockedItem, Download, Recording, Track
from integrations import ytmusic as ytm
from integrations.ytmusic import YTMusicError
from preferences.models import Preference

pytestmark = pytest.mark.django_db

BASE = "/api/v1/catalog"
CHANNEL = "UCmMUZbaYdNH0bEd1PAlAqsA"


def _results(api: APIClient, path: str, **query: Any) -> list[dict[str, Any]]:
    response = api.get(f"{BASE}/{path}/", query)
    assert response.status_code == 200, response.content
    return response.json()["results"]


def _actions() -> list[str]:
    return list(ActivityLog.objects.order_by("pk").values_list("action", flat=True))


# --- Access ---


@pytest.mark.parametrize(
    "path",
    ["artists", "albums", "tracks", "recordings", "blocked", "summary", "ytmusic/artists"],
)
def test_a_session_is_required(anonymous: APIClient, path: str) -> None:
    assert anonymous.get(f"{BASE}/{path}/").status_code == 403


def test_anonymous_cannot_change_anything(anonymous: APIClient) -> None:
    artist = ArtistFactory(name="Before")
    response = anonymous.patch(f"{BASE}/artists/{artist.pk}/", {"name": "After"}, format="json")
    assert response.status_code == 403
    assert Artist.objects.get().name == "Before"


# --- Reading ---


def test_artist_has_profile_and_counters(api: APIClient) -> None:
    artist = ArtistFactory(
        name="Los Cometas",
        ytmusic_id=CHANNEL,
        image_url="https://img/a.jpg",
        description="A band.",
        monthly_listeners=12_400_000,
        subscribers=1_200_000,
    )
    album = AlbumFactory(credit=None)
    AlbumArtistFactory(album=album, artist=artist)
    done = TrackFactory(album=album, credit=None)
    pending = TrackFactory(album=album, credit=None)
    for track in (done, pending):
        track.recording.credits.create(artist=artist, position=0)
    DownloadFactory(track=done)

    assert api.get(f"{BASE}/artists/{artist.pk}/").json() == {
        "id": artist.pk,
        "name": "Los Cometas",
        "image_url": "https://img/a.jpg",
        "description": "A band.",
        "ytmusic_id": CHANNEL,
        "monthly_listeners": 12_400_000,
        "subscribers": 1_200_000,
        "album_count": 1,
        "track_count": 2,
        "pending_count": 1,
        "suggest_import": False,
    }


def test_album_lists_its_artists_in_credit_order(api: APIClient) -> None:
    album = AlbumFactory(credit=None, title="Atlas", year=2020, record_type="ep")
    second, first = ArtistFactory(name="Second"), ArtistFactory(name="First")
    AlbumArtistFactory(album=album, artist=second, position=1)
    AlbumArtistFactory(album=album, artist=first, position=0)

    body = api.get(f"{BASE}/albums/{album.pk}/").json()

    assert (body["title"], body["year"], body["record_type"]) == ("Atlas", 2020, "ep")
    assert body["ytmusic_id"] == album.ytmusic_id
    assert [a["name"] for a in body["artists"]] == ["First", "Second"]
    assert (body["track_count"], body["pending_count"]) == (0, 0)


def test_track_carries_recording_data_and_download_state(api: APIClient) -> None:
    track = TrackFactory(
        title="Uno", video_id="aaaaaaaaaaa", duration=201, explicit=True, track_number=3
    )
    type(track.album).objects.filter(pk=track.album.pk).update(cover_url="https://img/c.jpg")
    DownloadFactory(track=track)

    body = api.get(f"{BASE}/tracks/{track.pk}/").json()

    assert body["title"] == "Uno"
    assert (body["video_id"], body["duration"], body["explicit"]) == ("aaaaaaaaaaa", 201, True)
    assert (body["album"], body["recording"]) == (track.album_id, track.recording_id)
    assert (body["track_number"], body["disc_number"]) == (3, 1)
    assert (body["downloaded"], body["copyable"], body["also_on"]) == (True, False, 0)
    assert body["cover_url"] == "https://img/c.jpg"
    assert len(body["artists"]) == 1


def test_lists_are_paginated(api: APIClient) -> None:
    for index in range(3):
        ArtistFactory(name=f"Artist {index}")
    body = api.get(f"{BASE}/artists/", {"page_size": 2}).json()
    assert (body["count"], len(body["results"])) == (3, 2)
    assert body["next"] is not None


def test_search_and_ordering(api: APIClient) -> None:
    ArtistFactory(name="Zeta", monthly_listeners=10)
    ArtistFactory(name="Alpha Zeta", monthly_listeners=30)
    ArtistFactory(name="Other")
    found = _results(api, "artists", search="zeta", ordering="-monthly_listeners")
    assert [a["name"] for a in found] == ["Alpha Zeta", "Zeta"]


def test_tracks_can_be_ordered_by_duration(api: APIClient) -> None:
    TrackFactory(title="Long", duration=300)
    TrackFactory(title="Short", duration=100)
    assert [t["title"] for t in _results(api, "tracks", ordering="duration")] == ["Short", "Long"]
    assert [t["title"] for t in _results(api, "tracks", ordering="-duration")] == ["Long", "Short"]


def test_summary_counts_the_library(api: APIClient) -> None:
    track = TrackFactory()
    TrackFactory(recording=track.recording, credit=None)
    ArtistFactory(name="Profile only")
    DownloadFactory(track=track)
    DownloadFactory(track=track)

    assert api.get(f"{BASE}/summary/").json() == {
        "artists": 3,  # one per album and one on the shared recording
        "related_artists": 1,
        "albums": 2,
        "recordings": 1,
        "tracks": 2,
        "downloaded": 1,
    }


# --- Related artists and import suggestions ---


def test_profiles_and_artists_with_music_are_listed_apart(api: APIClient) -> None:
    with_music = TrackFactory().credits.get().artist
    profile = ArtistFactory(name="Profile")
    names = {a["name"] for a in _results(api, "artists", profile_only="true")}
    assert names == {"Profile"}
    names = {a["id"] for a in _results(api, "artists", profile_only="false")}
    assert with_music.pk in names and profile.pk not in names


def test_related_to_lists_the_artists_related_to_one(api: APIClient) -> None:
    main, related, other = ArtistFactory(), ArtistFactory(name="Related"), ArtistFactory()
    main.related.add(related)
    other.related.add(ArtistFactory(name="Unrelated"))
    assert [a["name"] for a in _results(api, "artists", related_to=main.pk)] == ["Related"]


@pytest.mark.parametrize(
    ("fields", "suggested"),
    [
        ({"monthly_listeners": 1_000_000}, True),
        ({"monthly_listeners": 999_999}, False),
        ({"subscribers": 2_000_000}, True),
        # Monthly listeners win over subscribers when both are known.
        ({"monthly_listeners": 10, "subscribers": 5_000_000}, False),
        ({}, False),
        ({"monthly_listeners": 5_000_000, "ytmusic_id": None}, False),
    ],
)
def test_import_is_suggested_for_big_profiles(
    api: APIClient, fields: dict[str, Any], suggested: bool
) -> None:
    artist = ArtistFactory(**fields)
    assert api.get(f"{BASE}/artists/{artist.pk}/").json()["suggest_import"] is suggested


def test_import_is_not_suggested_for_artists_that_already_have_music(api: APIClient) -> None:
    artist = TrackFactory().credits.get().artist
    Artist.objects.filter(pk=artist.pk).update(monthly_listeners=9_000_000)
    assert api.get(f"{BASE}/artists/{artist.pk}/").json()["suggest_import"] is False


def test_suggestion_threshold_is_a_setting(api: APIClient) -> None:
    artist = ArtistFactory(monthly_listeners=500)
    Preference.objects.create(key="import.suggestion_threshold", value=100)
    assert api.get(f"{BASE}/artists/{artist.pk}/").json()["suggest_import"] is True


# --- Editing ---


def test_editing_an_artist_is_logged_and_kept_in_history(api: APIClient, owner: User) -> None:
    artist = ArtistFactory(name="Before")
    response = api.patch(
        f"{BASE}/artists/{artist.pk}/", {"name": "After", "description": "Bio"}, format="json"
    )
    assert response.status_code == 200
    artist.refresh_from_db()
    assert (artist.name, artist.description) == ("After", "Bio")
    assert artist.history.first().history_user == owner
    entry = ActivityLog.objects.get(action="catalog.artist.updated")
    assert entry.detail == {"fields": ["description", "name"]}


def test_identifiers_and_audience_are_read_only(api: APIClient) -> None:
    artist = ArtistFactory(ytmusic_id=CHANNEL, monthly_listeners=5)
    body = {"ytmusic_id": "UCother", "monthly_listeners": 99, "subscribers": 99}
    assert api.patch(f"{BASE}/artists/{artist.pk}/", body, format="json").status_code == 200
    artist.refresh_from_db()
    assert (artist.ytmusic_id, artist.monthly_listeners, artist.subscribers) == (CHANNEL, 5, None)


def test_album_title_year_and_cover_are_editable(api: APIClient) -> None:
    album = AlbumFactory()
    body = {
        "title": "New",
        "year": 1999,
        "cover_url": "https://img.example/n.jpg",
        "record_type": "ep",
    }
    assert api.patch(f"{BASE}/albums/{album.pk}/", body, format="json").status_code == 200
    album.refresh_from_db()
    assert (album.title, album.year, album.cover_url) == ("New", 1999, "https://img.example/n.jpg")
    assert album.record_type == "album"


def test_track_cannot_take_a_position_that_is_in_use(api: APIClient) -> None:
    first = TrackFactory(track_number=1)
    second = TrackFactory(album=first.album, track_number=2)
    response = api.patch(f"{BASE}/tracks/{second.pk}/", {"track_number": 1}, format="json")
    assert response.status_code == 400
    assert response.json()["track_number"] == [
        "Another track of the album already has that position."
    ]
    assert (
        api.patch(
            f"{BASE}/tracks/{second.pk}/", {"track_number": 1, "disc_number": 2}, format="json"
        ).status_code
        == 200
    )


def test_items_cannot_be_created_through_the_api(api: APIClient) -> None:
    for path in ("artists", "albums", "tracks", "recordings"):
        assert (
            api.post(f"{BASE}/{path}/", {"name": "x", "title": "x"}, format="json").status_code
            == 405
        )


def test_artists_cannot_be_deleted(api: APIClient) -> None:
    artist = ArtistFactory()
    assert api.delete(f"{BASE}/artists/{artist.pk}/").status_code == 405


# --- Credits ---


@pytest.mark.parametrize("kind", ["albums", "tracks"])
def test_artists_are_replaced_in_the_order_given(api: APIClient, owner: User, kind: str) -> None:
    item = AlbumFactory() if kind == "albums" else TrackFactory()
    first, second = ArtistFactory(name="First"), ArtistFactory(name="Second")

    response = api.put(
        f"{BASE}/{kind}/{item.pk}/artists/", {"artists": [first.pk, second.pk]}, format="json"
    )

    assert response.status_code == 200
    assert [a["name"] for a in response.json()["artists"]] == ["First", "Second"]
    assert list(item.credits.values_list("artist", "position")) == [(first.pk, 0), (second.pk, 1)]
    assert {c.history.first().history_user for c in item.credits.all()} == {owner}
    assert f"catalog.{kind[:-1]}.artists_changed" in _actions()


def test_changing_a_track_changes_every_release_of_its_recording(api: APIClient) -> None:
    single = TrackFactory()
    on_album = TrackFactory(recording=single.recording, credit=None)
    artist = ArtistFactory()
    api.put(f"{BASE}/tracks/{on_album.pk}/artists/", {"artists": [artist.pk]}, format="json")
    assert list(single.credits.values_list("artist", flat=True)) == [artist.pk]


@pytest.mark.parametrize("artists", [[], "x", [999_999], None])
def test_invalid_artist_lists_are_refused(api: APIClient, artists: Any) -> None:
    album = AlbumFactory()
    before = list(album.credits.values_list("artist", flat=True))
    response = api.put(f"{BASE}/albums/{album.pk}/artists/", {"artists": artists}, format="json")
    assert response.status_code == 400
    assert list(album.credits.values_list("artist", flat=True)) == before


def test_repeated_artist_is_refused(api: APIClient) -> None:
    album, artist = AlbumFactory(), ArtistFactory()
    body = {"artists": [artist.pk, artist.pk]}
    response = api.put(f"{BASE}/albums/{album.pk}/artists/", body, format="json")
    assert response.json()["artists"] == ["An artist is listed twice."]


# --- History and revert ---


def test_history_lists_versions_newest_first(api: APIClient) -> None:
    album = AlbumFactory(title="One")
    api.patch(f"{BASE}/albums/{album.pk}/", {"title": "Two"}, format="json")
    history = api.get(f"{BASE}/albums/{album.pk}/history/").json()
    assert [(h["history_type"], h["changes"]["title"]) for h in history] == [
        ("~", "Two"),
        ("+", "One"),
    ]
    assert history[0]["history_user"] == "owner"
    assert set(history[0]["changes"]) == {"title", "year", "cover_url"}


def test_revert_restores_the_editable_fields_of_a_version(api: APIClient) -> None:
    track = TrackFactory(title="One", track_number=1)
    api.patch(f"{BASE}/tracks/{track.pk}/", {"title": "Two", "track_number": 5}, format="json")
    first = api.get(f"{BASE}/tracks/{track.pk}/history/").json()[-1]

    response = api.post(
        f"{BASE}/tracks/{track.pk}/revert/", {"history_id": first["history_id"]}, format="json"
    )

    assert response.status_code == 200
    assert (response.json()["title"], response.json()["track_number"]) == ("One", 1)
    assert track.history.count() == 3
    assert ActivityLog.objects.filter(action="catalog.track.reverted").count() == 1


def test_revert_to_a_version_of_another_item_is_a_404(api: APIClient) -> None:
    mine, other = ArtistFactory(), ArtistFactory()
    foreign = other.history.first().history_id
    response = api.post(f"{BASE}/artists/{mine.pk}/revert/", {"history_id": foreign}, format="json")
    assert response.status_code == 404


# --- Deleting and blocking ---


@pytest.fixture
def library(tmp_path: Path) -> Path:
    Preference.objects.create(key="download.folder", value=str(tmp_path))
    return tmp_path


def _downloaded_track(library: Path, **fields: Any) -> Track:
    track = TrackFactory(**fields)
    path = library / f"artist/{track.pk}.mp3"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"audio")
    DownloadFactory(track=track, file_path=f"artist/{track.pk}.mp3")
    return track


def test_deleting_a_track_removes_its_file_and_download(api: APIClient, library: Path) -> None:
    track = _downloaded_track(library, title="Gone", video_id="vid-gone")

    assert api.delete(f"{BASE}/tracks/{track.pk}/").status_code == 204

    assert not Track.objects.exists() and not Download.objects.exists()
    assert not Recording.objects.exists()
    assert not (library / f"artist/{track.pk}.mp3").exists()
    assert not BlockedItem.objects.exists()
    entry = ActivityLog.objects.get(action="catalog.track.deleted")
    assert entry.detail == {
        "title": "Gone",
        "external_id": "vid-gone",
        "files": [f"artist/{track.pk}.mp3"],
        "blocked": False,
    }


def test_deleting_an_album_deletes_its_tracks(api: APIClient, library: Path) -> None:
    track = _downloaded_track(library)
    TrackFactory(album=track.album)
    assert api.delete(f"{BASE}/albums/{track.album_id}/").status_code == 204
    assert not Album.objects.exists() and not Track.objects.exists()
    assert ActivityLog.objects.get(action="catalog.album.deleted").detail["tracks"] == 2


def test_a_missing_file_does_not_stop_the_deletion(api: APIClient, library: Path) -> None:
    track = TrackFactory()
    DownloadFactory(track=track, file_path="never/there.mp3")
    assert api.delete(f"{BASE}/tracks/{track.pk}/").status_code == 204
    assert not Track.objects.exists()


@pytest.mark.parametrize("kind", ["album", "track"])
def test_deleting_with_block_adds_the_item_to_the_block_list(api: APIClient, kind: str) -> None:
    track = TrackFactory(title="Song", video_id="vid-1", album__title="Album")
    item, external_id = (
        (track.album, track.album.ytmusic_id) if kind == "album" else (track, "vid-1")
    )
    assert api.delete(f"{BASE}/{kind}s/{item.pk}/?block=true").status_code == 204
    blocked = BlockedItem.objects.get()
    assert (blocked.kind, blocked.external_id, blocked.name) == (kind, external_id, item.title)


def test_item_that_did_not_come_from_youtube_music_cannot_be_blocked(api: APIClient) -> None:
    track = TrackFactory(video_id=None)
    response = api.delete(f"{BASE}/tracks/{track.pk}/?block=true")
    assert response.status_code == 400
    assert Track.objects.exists()


def test_block_list_is_listed_extended_and_trimmed(api: APIClient) -> None:
    body = {"kind": "artist", "external_id": CHANNEL, "name": "Los Cometas"}
    created = api.post(f"{BASE}/blocked/", body, format="json")
    assert created.status_code == 201
    assert [b["external_id"] for b in _results(api, "blocked", kind="artist")] == [CHANNEL]
    assert _results(api, "blocked", kind="album") == []

    assert api.post(f"{BASE}/blocked/", body, format="json").status_code == 400

    assert api.delete(f"{BASE}/blocked/{created.json()['id']}/").status_code == 204
    assert not BlockedItem.objects.exists()
    assert _actions() == ["catalog.blocked.added", "catalog.blocked.removed"]


def test_block_kind_must_be_known(api: APIClient) -> None:
    body = {"kind": "playlist", "external_id": "x"}
    assert api.post(f"{BASE}/blocked/", body, format="json").status_code == 400


# --- Artist lookup on YouTube Music ---


class FakeLookup:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.error: Exception | None = None

    def search_artists(self, query: str) -> tuple[ytm.Artist, ...]:
        self.calls.append(("search", query))
        if self.error:
            raise self.error
        return (
            ytm.Artist(CHANNEL, "Los Cometas", "https://img/a.jpg", subscribers=1_200_000),
            ytm.Artist("UCother", "Cometas Tribute"),
        )

    def get_artist(self, channel_id: str) -> ytm.ArtistPage:
        self.calls.append(("artist", channel_id))
        releases = (
            ytm.ReleaseRef("a1", "A1", "album"),
            ytm.ReleaseRef("a2", "A2", "album"),
            ytm.ReleaseRef("s1", "S1", "single"),
            ytm.ReleaseRef("e1", "E1", "ep"),
        )
        artist = ytm.Artist(channel_id, "Los Cometas", None, None, 12_400_000, 1_200_000)
        return ytm.ArtistPage(artist, releases)


@pytest.fixture
def lookup(monkeypatch: pytest.MonkeyPatch) -> FakeLookup:
    fake = FakeLookup()
    monkeypatch.setattr(views, "ytmusic_client", lambda: fake)
    return fake


def test_lookup_by_name_searches(api: APIClient, lookup: FakeLookup) -> None:
    found = _results(api, "ytmusic/artists", q="cometas")
    assert lookup.calls == [("search", "cometas")]
    assert found[0] == {
        "ytmusic_id": CHANNEL,
        "name": "Los Cometas",
        "image_url": "https://img/a.jpg",
        "monthly_listeners": None,
        "subscribers": 1_200_000,
        "album_count": None,
        "single_count": None,
        "in_library": False,
        "blocked": False,
    }
    assert [r["name"] for r in found] == ["Los Cometas", "Cometas Tribute"]


@pytest.mark.parametrize("query", [CHANNEL, f"https://music.youtube.com/channel/{CHANNEL}?si=x"])
def test_lookup_by_link_or_id_returns_that_artist_with_its_discography_size(
    api: APIClient, lookup: FakeLookup, query: str
) -> None:
    (found,) = _results(api, "ytmusic/artists", q=query)
    assert lookup.calls == [("artist", CHANNEL)]
    assert (found["ytmusic_id"], found["monthly_listeners"]) == (CHANNEL, 12_400_000)
    assert (found["album_count"], found["single_count"]) == (2, 2)


def test_lookup_marks_artists_in_the_library_and_blocked_ones(
    api: APIClient, lookup: FakeLookup
) -> None:
    artist = TrackFactory().credits.get().artist
    Artist.objects.filter(pk=artist.pk).update(ytmusic_id=CHANNEL)
    BlockedItem.objects.create(kind="artist", external_id="UCother")
    first, second = _results(api, "ytmusic/artists", q="cometas")
    assert (first["in_library"], first["blocked"]) == (True, False)
    assert (second["in_library"], second["blocked"]) == (False, True)


def test_a_profile_without_music_is_not_in_the_library_yet(
    api: APIClient, lookup: FakeLookup
) -> None:
    ArtistFactory(ytmusic_id=CHANNEL)
    assert _results(api, "ytmusic/artists", q="cometas")[0]["in_library"] is False


@pytest.mark.parametrize("query", [{}, {"q": ""}, {"q": "x" * 301}])
def test_lookup_needs_a_query(api: APIClient, lookup: FakeLookup, query: dict[str, str]) -> None:
    assert api.get(f"{BASE}/ytmusic/artists/", query).status_code == 400
    assert lookup.calls == []


def test_lookup_failure_is_a_502(api: APIClient, lookup: FakeLookup) -> None:
    lookup.error = YTMusicError("search failed: timeout")
    response = api.get(f"{BASE}/ytmusic/artists/", {"q": "cometas"})
    assert response.status_code == 502
    assert response.json() == {"detail": "YouTube Music is not responding."}
