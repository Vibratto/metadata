"""Artist import against an in-memory YouTube Music."""

from typing import Any

import pytest
import requests

from activity.models import ActivityLog
from catalog.factories import ArtistFactory
from catalog.models import Album, Artist, BlockedItem, Recording, Track
from catalog.services.importing import Importer
from integrations import ytmusic as ytm
from integrations.ytmusic import YTMusicError
from jobs import registry, runner
from jobs.models import JobRun, JobRunLine

pytestmark = pytest.mark.django_db

MAIN, OTHER, GUEST, RELATED, SMALL = "UCmain", "UCother", "UCguest", "UCrelated", "UCsmall"
MAIN_REF, GUEST_REF = ytm.ArtistRef("Main", MAIN), ytm.ArtistRef("Guest", GUEST)


class FakeYTMusic:
    """Serves a small catalogue and records which pages were requested."""

    def __init__(self) -> None:
        self.artists = {
            MAIN: ytm.Artist(MAIN, "Main", "http://img/main.jpg", "Bio.", 5_000_000, 900_000),
            OTHER: ytm.Artist(OTHER, "Other"),
            GUEST: ytm.Artist(GUEST, "Guest", "http://img/guest.jpg"),
            RELATED: ytm.Artist(RELATED, "Related", "http://img/rel.jpg", None, 8_000_000),
            SMALL: ytm.Artist(SMALL, "Small", None, None, None, 400),
        }
        self.releases: dict[str, list[ytm.ReleaseRef]] = {
            MAIN: [
                ytm.ReleaseRef("first", "First", "single", 2020, "http://img/ref.jpg"),
                ytm.ReleaseRef("second", "Second"),
            ],
            OTHER: [],
        }
        self.related = {MAIN: (ytm.ArtistRef("Related", RELATED), ytm.ArtistRef("Small", SMALL))}
        self.albums = {
            "first": ytm.Album(
                "first",
                "First",
                (MAIN_REF,),
                kind="single",
                year=2020,
                cover_url="http://img/a.jpg",
                tracks=(
                    ytm.Track(
                        "One",
                        (MAIN_REF, GUEST_REF, ytm.ArtistRef("Title Guest")),
                        video_id="vid-one",
                        position=1,
                        explicit=True,
                    ),
                    ytm.Track("Two", (MAIN_REF,), video_id="vid-two", position=2, duration=30),
                ),
            ),
            # "Three" is the same video as "One": one recording on two releases.
            "second": ytm.Album(
                "second",
                "Second",
                (MAIN_REF,),
                tracks=(ytm.Track("Three", (MAIN_REF,), video_id="vid-one"),),
            ),
        }
        self.calls: list[tuple[str, str]] = []
        self.failing: set[str] = set()

    def _fetch(self, kind: str, key: str, source: dict[str, Any]) -> Any:
        self.calls.append((kind, key))
        if key in self.failing or key not in source:
            raise YTMusicError(f"{kind} failed: no data")
        return source[key]

    def get_artist(self, channel_id: str) -> ytm.ArtistPage:
        artist = self._fetch("artist", channel_id, self.artists)
        return ytm.ArtistPage(
            artist, tuple(self.releases.get(channel_id, ())), self.related.get(channel_id, ())
        )

    def get_artist_profile(self, channel_id: str) -> ytm.Artist:
        return self._fetch("profile", channel_id, self.artists)

    def get_album(self, browse_id: str) -> ytm.Album:
        return self._fetch("album", browse_id, self.albums)


@pytest.fixture
def run() -> JobRun:
    return JobRun.objects.create(kind="import", status=JobRun.Status.RUNNING)


@pytest.fixture
def ytmusic() -> FakeYTMusic:
    return FakeYTMusic()


def _import(run: JobRun, ytmusic: FakeYTMusic, ids: list[str]) -> Importer:
    importer = Importer(run, ytmusic)
    importer.import_artists(ids)
    return importer


def _track(video_id: str, album: str) -> Track:
    return Track.objects.get(recording__video_id=video_id, album__ytmusic_id=album)


def _messages(run: JobRun) -> list[str]:
    return list(run.lines.values_list("message", flat=True))


def _snapshot() -> tuple[list[Any], ...]:
    return (
        list(Artist.objects.values_list("ytmusic_id", "name", "image_url")),
        list(Album.objects.values_list("ytmusic_id", "title")),
        list(Track.objects.values_list("album__ytmusic_id", "title", "recording__video_id")),
        list(Artist.history.values_list("id", "history_type")),
    )


def test_imports_artist_profile(run: JobRun, ytmusic: FakeYTMusic) -> None:
    _import(run, ytmusic, [MAIN])
    main = Artist.objects.get(ytmusic_id=MAIN)
    assert (main.name, main.image_url, main.description) == ("Main", "http://img/main.jpg", "Bio.")
    assert (main.monthly_listeners, main.subscribers, main.audience) == (
        5_000_000,
        900_000,
        5_000_000,
    )


def test_imports_releases_tracks_and_credits(run: JobRun, ytmusic: FakeYTMusic) -> None:
    importer = _import(run, ytmusic, [MAIN])

    first = Album.objects.get(ytmusic_id="first")
    assert (first.title, first.year, first.cover_url, first.record_type) == (
        "First",
        2020,
        "http://img/a.jpg",
        "single",
    )
    assert list(first.credits.values_list("artist__name", flat=True)) == ["Main"]
    assert Album.objects.get(ytmusic_id="second").record_type == "album"

    one, two = _track("vid-one", "first"), _track("vid-two", "first")
    # The guest named only in the title has no channel and is created by name.
    assert list(one.credits.values_list("artist__name", "position")) == [
        ("Main", 0),
        ("Guest", 1),
        ("Title Guest", 2),
    ]
    assert Artist.objects.get(name="Title Guest").ytmusic_id is None
    assert Artist.objects.get(ytmusic_id=GUEST).image_url == "http://img/guest.jpg"
    assert (one.track_number, one.explicit) == (1, True)
    assert (two.track_number, two.duration, two.explicit) == (2, 30, False)

    assert _track("vid-one", "second").recording == one.recording
    assert Recording.objects.count() == 2
    assert dict(importer.counts) == {
        "artists": 1,
        "related_artists": 2,
        "albums": 2,
        "tracks": 3,
        "reused_recordings": 1,
    }


def test_release_falls_back_to_the_artist_page_for_year_and_cover(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    ytmusic.albums["first"] = ytm.Album("first", "First", (MAIN_REF,))
    _import(run, ytmusic, [MAIN])
    first = Album.objects.get(ytmusic_id="first")
    assert (first.year, first.cover_url) == (2020, "http://img/ref.jpg")


def test_track_without_position_takes_its_place_in_the_list(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    ytmusic.albums["second"] = ytm.Album(
        "second",
        "Second",
        (MAIN_REF,),
        tracks=(ytm.Track("A", (MAIN_REF,), "vid-a"), ytm.Track("B", (MAIN_REF,), "vid-b")),
    )
    _import(run, ytmusic, [MAIN])
    assert [_track(v, "second").track_number for v in ("vid-a", "vid-b")] == [1, 2]


def test_repeated_position_moves_the_track_to_the_next_free_one(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    ytmusic.albums["second"] = ytm.Album(
        "second",
        "Second",
        (MAIN_REF,),
        tracks=(
            ytm.Track("A", (MAIN_REF,), "vid-a", position=1),
            ytm.Track("B", (MAIN_REF,), "vid-b", position=1),
        ),
    )
    _import(run, ytmusic, [MAIN])
    assert _track("vid-b", "second").track_number == 2
    assert "Position 1 was taken, so “B” is now track 2." in _messages(run)


def test_unplayable_tracks_are_kept_as_separate_recordings(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    ytmusic.albums["second"] = ytm.Album(
        "second",
        "Second",
        (MAIN_REF,),
        tracks=(ytm.Track("A", (MAIN_REF,)), ytm.Track("B", (MAIN_REF,))),
    )
    _import(run, ytmusic, [MAIN])
    recordings = Recording.objects.filter(tracks__album__ytmusic_id="second")
    assert list(recordings.values_list("title", "video_id")) == [("A", None), ("B", None)]


def test_related_artists_are_saved_as_profiles_without_music(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    _import(run, ytmusic, [MAIN])
    main = Artist.objects.get(ytmusic_id=MAIN)
    related = Artist.objects.get(ytmusic_id=RELATED)
    assert set(main.related.values_list("ytmusic_id", flat=True)) == {RELATED, SMALL}
    assert (related.image_url, related.monthly_listeners) == ("http://img/rel.jpg", 8_000_000)
    assert Artist.objects.get(ytmusic_id=SMALL).audience == 400
    assert not related.albums.exists() and not related.recordings.exists()
    # Only the profile was requested: no discography, no albums.
    assert ("artist", RELATED) not in ytmusic.calls
    assert set(Artist.objects.profiles_only().values_list("ytmusic_id", flat=True)) == {
        RELATED,
        SMALL,
    }
    assert set(Artist.objects.with_music().values_list("name", flat=True)) == {
        "Main",
        "Guest",
        "Title Guest",
    }


def test_related_artist_already_in_the_library_is_linked_not_fetched(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    ArtistFactory(ytmusic_id=RELATED, name="Edited by hand")
    importer = _import(run, ytmusic, [MAIN])
    assert ("profile", RELATED) not in ytmusic.calls
    assert importer.counts["related_artists"] == 1
    assert Artist.objects.get(ytmusic_id=MAIN).related.filter(ytmusic_id=RELATED).exists()


def test_related_profile_that_cannot_be_fetched_is_kept_by_name(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    ytmusic.failing.add(RELATED)
    importer = _import(run, ytmusic, [MAIN])
    assert Artist.objects.get(ytmusic_id=RELATED).image_url == ""
    assert importer.counts["failed_artists"] == 0
    warning = run.lines.get(level=JobRunLine.Level.WARNING)
    assert warning.message == "Artist “Related” left incomplete: profile failed: no data"


def test_blocked_related_artist_is_not_saved(run: JobRun, ytmusic: FakeYTMusic) -> None:
    BlockedItem.objects.create(kind="artist", external_id=RELATED)
    _import(run, ytmusic, [MAIN])
    assert not Artist.objects.filter(ytmusic_id=RELATED).exists()


def test_progress_and_log_lines(run: JobRun, ytmusic: FakeYTMusic) -> None:
    _import(run, ytmusic, [MAIN])
    run.refresh_from_db()
    assert (run.done, run.total) == (2, 2)
    messages = _messages(run)
    assert messages[0] == "Artist “Main”."
    assert "Album “First”: 2 tracks." in messages
    assert "Track 1 is the same recording as on “First”." in messages


def test_second_import_changes_nothing(run: JobRun, ytmusic: FakeYTMusic) -> None:
    _import(run, ytmusic, [MAIN])
    before = _snapshot()
    ytmusic.calls.clear()

    importer = _import(run, ytmusic, [MAIN])

    assert _snapshot() == before
    # Stored releases are not fetched again, and neither are known profiles.
    assert ytmusic.calls == [("artist", MAIN)]
    assert dict(importer.counts) == {"skipped_albums": 2}


def test_second_import_adds_only_the_new_release(run: JobRun, ytmusic: FakeYTMusic) -> None:
    _import(run, ytmusic, [MAIN])
    ytmusic.releases[MAIN].append(ytm.ReleaseRef("third", "Third"))
    ytmusic.albums["third"] = ytm.Album(
        "third", "Third", (MAIN_REF,), tracks=(ytm.Track("New", (MAIN_REF,), "vid-new"),)
    )
    importer = _import(run, ytmusic, [MAIN])
    assert dict(importer.counts) == {"skipped_albums": 2, "albums": 1, "tracks": 1}


def test_hand_edits_survive_but_audience_figures_are_refreshed(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    ArtistFactory(
        ytmusic_id=MAIN,
        name="Edited by hand",
        image_url="http://mine.jpg",
        description="Mine.",
        monthly_listeners=1,
    )
    _import(run, ytmusic, [MAIN])
    artist = Artist.objects.get(ytmusic_id=MAIN)
    assert (artist.name, artist.image_url, artist.description) == (
        "Edited by hand",
        "http://mine.jpg",
        "Mine.",
    )
    assert artist.monthly_listeners == 5_000_000
    assert Album.objects.count() == 2


def test_missing_audience_figures_do_not_erase_known_ones(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    ArtistFactory(ytmusic_id=OTHER, subscribers=77)
    _import(run, ytmusic, [OTHER])
    assert Artist.objects.get(ytmusic_id=OTHER).subscribers == 77


def test_blocked_artist_is_skipped(run: JobRun, ytmusic: FakeYTMusic) -> None:
    BlockedItem.objects.create(kind="artist", external_id=MAIN)
    importer = _import(run, ytmusic, [MAIN])
    assert not Artist.objects.exists()
    assert importer.counts["blocked"] == 1
    assert ytmusic.calls == []


def test_blocked_album_is_skipped(run: JobRun, ytmusic: FakeYTMusic) -> None:
    BlockedItem.objects.create(kind="album", external_id="first")
    _import(run, ytmusic, [MAIN])
    assert list(Album.objects.values_list("ytmusic_id", flat=True)) == ["second"]
    assert ("album", "first") not in ytmusic.calls


def test_blocked_track_is_skipped(run: JobRun, ytmusic: FakeYTMusic) -> None:
    BlockedItem.objects.create(kind="track", external_id="vid-two")
    _import(run, ytmusic, [MAIN])
    assert sorted(Track.objects.values_list("title", flat=True)) == ["One", "Three"]


def test_blocked_credited_artist_gets_no_credit(run: JobRun, ytmusic: FakeYTMusic) -> None:
    BlockedItem.objects.create(kind="artist", external_id=GUEST)
    _import(run, ytmusic, [MAIN])
    assert not Artist.objects.filter(ytmusic_id=GUEST).exists()
    assert list(_track("vid-one", "first").credits.values_list("artist__name", "position")) == [
        ("Main", 0),
        ("Title Guest", 1),
    ]


def test_block_applies_only_to_its_own_kind(run: JobRun, ytmusic: FakeYTMusic) -> None:
    BlockedItem.objects.create(kind="track", external_id=MAIN)
    BlockedItem.objects.create(kind="artist", external_id="first")
    _import(run, ytmusic, [MAIN])
    assert Artist.objects.filter(ytmusic_id=MAIN).exists()
    assert Album.objects.filter(ytmusic_id="first").exists()


def test_title_guest_reuses_artist_with_same_name(run: JobRun, ytmusic: FakeYTMusic) -> None:
    existing = Artist.objects.create(name="title guest")
    _import(run, ytmusic, [MAIN])
    assert Artist.objects.filter(name__iexact="title guest").count() == 1
    assert _track("vid-one", "first").artists.filter(pk=existing.pk).exists()


def test_failing_artist_does_not_stop_the_others(run: JobRun, ytmusic: FakeYTMusic) -> None:
    importer = _import(run, ytmusic, ["UCmissing", MAIN])
    assert importer.counts["failed_artists"] == 1
    assert Album.objects.count() == 2
    error = run.lines.get(level=JobRunLine.Level.ERROR)
    assert error.message == "Artist UCmissing: artist failed: no data"


def test_network_failure_counts_as_a_failed_artist(
    run: JobRun, ytmusic: FakeYTMusic, monkeypatch: pytest.MonkeyPatch
) -> None:
    def offline(channel_id: str) -> ytm.ArtistPage:
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(ytmusic, "get_artist", offline)
    assert _import(run, ytmusic, [MAIN]).counts["failed_artists"] == 1


def test_failing_album_saves_nothing_of_it_and_does_not_stop_the_rest(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    ytmusic.failing.add("first")
    importer = _import(run, ytmusic, [MAIN])
    assert list(Album.objects.values_list("ytmusic_id", flat=True)) == ["second"]
    assert (importer.counts["failed_albums"], importer.counts["failed_artists"]) == (1, 0)
    error = run.lines.get(level=JobRunLine.Level.ERROR)
    assert error.message == "Album “First”: album failed: no data"


def test_stop_between_releases(
    run: JobRun, ytmusic: FakeYTMusic, monkeypatch: pytest.MonkeyPatch
) -> None:
    stops = iter([False, False, True])  # before the artist, the first release, the second
    monkeypatch.setattr(runner, "should_stop", lambda _run: next(stops))
    assert Importer(run, ytmusic).import_artists([MAIN, OTHER]) is False
    assert list(Album.objects.values_list("ytmusic_id", flat=True)) == ["first"]


def test_stop_before_next_artist(
    run: JobRun, ytmusic: FakeYTMusic, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "should_stop", lambda _run: True)
    assert Importer(run, ytmusic).import_artists([MAIN]) is False
    assert not Artist.objects.exists()


def test_album_before_single_gives_the_same_recordings(run: JobRun, ytmusic: FakeYTMusic) -> None:
    ytmusic.releases[MAIN].reverse()
    _import(run, ytmusic, [MAIN])
    assert Track.objects.filter(album__ytmusic_id="first").count() == 2
    assert Track.objects.filter(album__ytmusic_id="second").count() == 1
    assert Recording.objects.count() == 2


def test_complete_album_adds_only_the_missing_tracks(run: JobRun, ytmusic: FakeYTMusic) -> None:
    _import(run, ytmusic, [MAIN])
    first = ytmusic.albums["first"]
    ytmusic.albums["first"] = ytm.Album(
        "first",
        "First",
        (MAIN_REF,),
        tracks=(*first.tracks, ytm.Track("Late", (MAIN_REF,), "vid-late", position=3)),
    )
    created = Importer(run, ytmusic).complete_album(Album.objects.get(ytmusic_id="first"))
    assert [(t.title, t.track_number) for t in created] == [("Late", 3)]
    assert Track.objects.filter(album__ytmusic_id="first").count() == 3


def test_complete_album_ignores_albums_that_did_not_come_from_youtube_music(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    album = Album.objects.create(title="From a folder")
    assert Importer(run, ytmusic).complete_album(album) == []
    assert ytmusic.calls == []


def test_complete_artist_leaves_artists_without_a_channel_alone(
    run: JobRun, ytmusic: FakeYTMusic
) -> None:
    Importer(run, ytmusic).complete_artist(Artist.objects.create(name="Main"))
    assert ytmusic.calls == []


def test_task_imports_logs_activity_and_reports_summary(
    ytmusic: FakeYTMusic, monkeypatch: pytest.MonkeyPatch
) -> None:
    from catalog.tasks import importing

    monkeypatch.setattr(importing, "ytmusic_client", lambda: ytmusic)
    registry.get("import")

    run = runner.start("import", {"artist_ids": [MAIN]}, None)

    assert run.status == JobRun.Status.SUCCEEDED
    assert run.summary["albums"] == 2 and run.summary["completed"] is True
    entry = ActivityLog.objects.get(action="catalog.import")
    assert entry.detail["artist_ids"] == [MAIN]


@pytest.mark.parametrize(
    "params",
    [{}, {"artist_ids": []}, {"artist_ids": MAIN}, {"artist_ids": [MAIN, 2]}, {"artist_ids": [""]}],
)
def test_task_rejects_invalid_params(params: dict[str, Any]) -> None:
    run = runner.start("import", params, None)
    assert run.status == JobRun.Status.FAILED
