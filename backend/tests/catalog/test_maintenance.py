"""Catalogue maintenance operations and the job that runs them."""

from pathlib import Path
from typing import Any, cast

import pytest
import requests

from activity.models import ActivityLog
from catalog.factories import AlbumFactory, ArtistFactory, DownloadFactory, TrackFactory
from catalog.models import Album, Artist, BlockedItem, Download, DownloadLoudness, Track
from catalog.services import maintenance as service
from catalog.tasks import maintenance as task
from integrations import ytmusic as ytm
from integrations.audio import AudioError, Tags
from integrations.lrclib import Lyrics
from jobs import runner
from jobs.models import JobRun
from preferences.models import Preference

from .conftest import FakeLrclib
from .test_importing import MAIN, FakeYTMusic

pytestmark = pytest.mark.django_db

TEMPLATE = "{albumartist}/{album}/{track} {title}"


@pytest.fixture(autouse=True)
def library(tmp_path: Path) -> Path:
    """The library folder every stored path is relative to."""
    Preference.objects.create(key="download.folder", value=str(tmp_path))
    return tmp_path


@pytest.fixture
def written(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, Tags]]:
    """Replace tag writing and record what would have been written."""
    calls: list[tuple[Path, Tags]] = []
    monkeypatch.setattr(service, "write_tags", lambda path, tags: calls.append((path, tags)))
    return calls


@pytest.fixture
def ytmusic() -> FakeYTMusic:
    return FakeYTMusic()


def _run() -> JobRun:
    return JobRun.objects.create(kind="maintenance", status=JobRun.Status.RUNNING)


def _lines(run: JobRun) -> list[str]:
    """What the run could not do, as “item: reason”."""
    return [f"{p['item']}: {p['reason']}" for p in runner._problems.get(run.pk, [])]


def _download(library: Path, name: str = "a.mp3", track: Track | None = None) -> Download:
    """A download whose file exists."""
    path = library / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"audio")
    return cast(Download, DownloadFactory(file_path=name, track=track or TrackFactory()))


def _no_fetch(url: str) -> bytes:
    raise AssertionError(f"unexpected download of {url}")


# --- Retag ---


def test_retag_rewrites_the_tags_from_the_catalogue(
    library: Path, written: list[tuple[Path, Tags]]
) -> None:
    track = TrackFactory(title="Song", album=AlbumFactory(title="Album", year=2019), track_number=3)
    _download(library, "song.flac", track)

    run = _run()
    summary = service.retag_downloads(run, fetch_cover=_no_fetch)

    assert summary == {"retagged": 1, "failed": 0}
    [(path, tags)] = written
    assert path == library / "song.flac"
    assert (tags.title, tags.album, tags.year, tags.track_number) == ("Song", "Album", 2019, 3)
    assert tags.cover is None
    assert ActivityLog.objects.get(action="catalog.download.retagged").detail == {"count": 1}
    assert (run.done, run.total) == (1, 1)


def test_retag_embeds_the_cover_when_asked_fetching_it_once_per_album(
    library: Path, written: list[tuple[Path, Tags]]
) -> None:
    Preference.objects.create(key="tags.embed_cover", value=True)
    album = AlbumFactory(cover_url="https://img/c")
    for name in ("a.mp3", "b.mp3"):
        _download(library, name, TrackFactory(album=album))
    _download(library, "c.mp3", TrackFactory(album=AlbumFactory(cover_url="")))
    fetched: list[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return b"jpeg"

    service.retag_downloads(_run(), fetch_cover=fetch)

    assert fetched == ["https://img/c"]
    assert [tags.cover for _, tags in written] == [b"jpeg", b"jpeg", None]


def test_retag_uses_only_the_newest_download_of_each_track(
    library: Path, written: list[tuple[Path, Tags]]
) -> None:
    track = TrackFactory()
    _download(library, "old.mp3", track)
    _download(library, "new.mp3", track)
    service.retag_downloads(_run(), fetch_cover=_no_fetch)
    assert [path.name for path, _ in written] == ["new.mp3"]


def test_retag_reports_missing_and_failing_files_and_goes_on(
    library: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    DownloadFactory(file_path="gone.mp3")
    _download(library, "broken.mp3")
    _download(library, "fine.mp3")
    done: list[str] = []

    def write(path: Path, tags: Tags) -> None:
        if path.name == "broken.mp3":
            raise AudioError("cannot tag")
        done.append(path.name)

    monkeypatch.setattr(service, "write_tags", write)
    run = _run()

    assert service.retag_downloads(run, fetch_cover=_no_fetch) == {"retagged": 1, "failed": 2}
    assert done == ["fine.mp3"]
    assert _lines(run) == [
        "gone.mp3: The file is missing.",
        "broken.mp3: The audio file could not be processed.",
    ]


def test_retag_skips_the_file_when_its_cover_cannot_be_fetched(
    library: Path, written: list[tuple[Path, Tags]]
) -> None:
    Preference.objects.create(key="tags.embed_cover", value=True)
    _download(library, "a.mp3", TrackFactory(album=AlbumFactory(cover_url="https://img/c")))

    def fail(url: str) -> bytes:
        raise requests.ConnectionError("down")

    assert service.retag_downloads(_run(), fetch_cover=fail) == {"retagged": 0, "failed": 1}
    assert written == []
    assert not ActivityLog.objects.exists()


def test_retag_stores_the_artist_image_that_is_missing(
    library: Path, written: list[tuple[Path, Tags]]
) -> None:
    artist = ArtistFactory(name="Rosalía", image_url="https://img/r")
    album = AlbumFactory(credit=None, title="Motomami")
    album.credits.create(artist=artist, position=0)
    folder = f"rosalia-{artist.pk}"
    _download(library, f"{folder}/motomami/a.mp3", TrackFactory(album=album))

    service.retag_downloads(_run(), fetch_cover=lambda url: url.encode())

    assert (library / folder / "artist.jpg").read_bytes() == b"https://img/r"


def test_retag_stops_when_asked(
    library: Path, written: list[tuple[Path, Tags]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _download(library, "a.mp3")
    monkeypatch.setattr(runner, "should_stop", lambda run: True)
    assert service.retag_downloads(_run(), fetch_cover=_no_fetch) == {"retagged": 0, "failed": 0}


# --- ReplayGain ---


@pytest.fixture
def measured(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, bool]]:
    calls: list[tuple[int, bool]] = []

    def update_album(album: Album, *, remeasure: bool = False) -> int:
        calls.append((album.pk, remeasure))
        if album.title == "Broken":
            raise AudioError("ffmpeg failed")
        return 2

    monkeypatch.setattr(service.replaygain, "update_album", update_album)
    return calls


def test_replaygain_measures_again_every_album_that_has_downloads(
    library: Path, measured: list[tuple[int, bool]]
) -> None:
    first, second = AlbumFactory(), AlbumFactory()
    for album in (first, first, second):
        DownloadFactory(track=TrackFactory(album=album))
    AlbumFactory()  # nothing downloaded: not measured

    assert service.replaygain_albums(_run()) == {"albums": 2, "files": 4, "failed": 0}
    assert measured == [(first.pk, True), (second.pk, True)]


def test_replaygain_failure_of_one_album_does_not_stop_the_rest(
    measured: list[tuple[int, bool]],
) -> None:
    DownloadFactory(track=TrackFactory(album=AlbumFactory(title="Broken")))
    DownloadFactory(track=TrackFactory(album=AlbumFactory(title="Fine")))
    run = _run()
    assert service.replaygain_albums(run) == {"albums": 1, "files": 2, "failed": 1}
    assert _lines(run) == ["Broken: The audio file could not be processed."]


def test_replaygain_does_nothing_when_turned_off(measured: list[tuple[int, bool]]) -> None:
    Preference.objects.create(key="replaygain.enabled", value=False)
    DownloadFactory()
    run = _run()
    assert service.replaygain_albums(run) == {"albums": 0, "files": 0, "failed": 0}
    assert measured == []
    assert _lines(run) == ["ReplayGain: It is turned off in the settings."]


# --- Relocate ---


@pytest.fixture
def template() -> None:
    Preference.objects.create(key="download.name_template", value=TEMPLATE)


def _album_track() -> Track:
    artist = ArtistFactory(name="Main")
    album = AlbumFactory(credit=None, title="Album", cover_url="https://img/c")
    album.credits.create(artist=artist, position=0)
    return cast(Track, TrackFactory(album=album, title="Song", track_number=1))


def _expected(track: Track) -> str:
    artist = track.album.credits.get().artist
    return f"main-{artist.pk}/album-{track.album.pk}/01-song-{track.pk}.mp3"


@pytest.mark.usefixtures("template")
def test_relocate_moves_the_file_its_lyrics_and_the_cover(library: Path) -> None:
    track = _album_track()
    old = _download(library, "old/place.mp3", track)
    (library / "old" / "place.lrc").write_text("lyrics")
    (library / "old" / "cover.jpg").write_bytes(b"jpeg")
    DownloadLoudness.objects.create(download=old, lufs=-14.0, peak=0.9)

    summary = service.relocate_downloads(_run(), fetch_cover=_no_fetch)

    assert summary == {"moved": 1, "unchanged": 0, "failed": 0}
    new = library / _expected(track)
    assert new.read_bytes() == b"audio"
    assert new.with_suffix(".lrc").read_text() == "lyrics"
    assert (new.parent / "cover.jpg").read_bytes() == b"jpeg"
    assert not (library / "old" / "place.mp3").exists()
    # The old row stays, as history; the newest one has the new path and the loudness.
    latest = cast(Download, Download.objects.filter(track=track).latest("pk"))
    assert Download.objects.filter(track=track).count() == 2
    assert latest.file_path == _expected(track)
    assert (latest.loudness.lufs, latest.loudness.peak) == (-14.0, 0.9)
    assert ActivityLog.objects.get(action="catalog.download.relocated").detail == {"count": 1}


@pytest.mark.usefixtures("template")
def test_relocate_fetches_the_cover_when_the_old_folder_has_none(library: Path) -> None:
    track = _album_track()
    _download(library, "old/place.mp3", track)
    service.relocate_downloads(_run(), fetch_cover=lambda url: b"fetched")
    assert (library / _expected(track)).parent.joinpath("cover.jpg").read_bytes() == b"fetched"


@pytest.mark.usefixtures("template")
def test_relocate_leaves_files_that_are_already_in_place(library: Path) -> None:
    track = _album_track()
    _download(library, _expected(track), track)
    summary = service.relocate_downloads(_run(), fetch_cover=_no_fetch)
    assert summary == {"moved": 0, "unchanged": 1, "failed": 0}
    assert Download.objects.count() == 1
    assert not ActivityLog.objects.exists()


@pytest.mark.usefixtures("template")
def test_relocate_never_overwrites_and_reports_missing_files(library: Path) -> None:
    taken = _album_track()
    _download(library, "old/a.mp3", taken)
    occupied = library / _expected(taken)
    occupied.parent.mkdir(parents=True)
    occupied.write_bytes(b"someone else's")
    DownloadFactory(file_path="gone.mp3", track=_album_track())
    run = _run()

    summary = service.relocate_downloads(run, fetch_cover=_no_fetch)

    assert summary == {"moved": 0, "unchanged": 0, "failed": 2}
    assert occupied.read_bytes() == b"someone else's"
    assert (library / "old" / "a.mp3").exists()
    assert sorted(_lines(run)) == [
        "a.mp3: Another file already has the name it should take.",
        "gone.mp3: The file is missing.",
    ]


@pytest.mark.usefixtures("template")
def test_relocate_does_not_touch_the_tags(library: Path, written: list[tuple[Path, Tags]]) -> None:
    _download(library, "old/place.mp3", _album_track())
    service.relocate_downloads(_run(), fetch_cover=lambda url: b"jpeg")
    assert written == []


# --- Check files ---


def test_check_files_lists_the_downloads_whose_file_is_missing(library: Path) -> None:
    _download(library, "here.mp3")
    missing = DownloadFactory(file_path="gone.mp3")
    run = _run()

    assert service.check_download_files(run) == {"checked": 2, "missing": [missing.pk]}
    assert _lines(run) == ["gone.mp3: The file is missing."]
    assert Download.objects.count() == 2


# --- Complete albums ---


def test_complete_albums_recovers_the_tracks_an_album_lacks(ytmusic: FakeYTMusic) -> None:
    album = AlbumFactory(ytmusic_id="first", title="First")
    TrackFactory(album=album, title="One", video_id="vid-one", track_number=1)
    AlbumFactory(ytmusic_id=None)  # not from YouTube Music: left alone

    summary = service.complete_albums(_run(), ytmusic)

    assert summary == {"albums": 1, "tracks": 1, "reused_recordings": 0, "errors": 0}
    assert list(album.tracks.values_list("title", "track_number")) == [("One", 1), ("Two", 2)]
    assert ("album", "first") in ytmusic.calls


def test_complete_albums_leaves_blocked_tracks_out(ytmusic: FakeYTMusic) -> None:
    AlbumFactory(ytmusic_id="first")
    BlockedItem.objects.create(kind="track", external_id="vid-two")
    summary = service.complete_albums(_run(), ytmusic)
    assert summary["tracks"] == 1
    assert list(Track.objects.values_list("title", flat=True)) == ["One"]


def test_complete_albums_reports_an_album_that_fails_and_goes_on(ytmusic: FakeYTMusic) -> None:
    AlbumFactory(ytmusic_id="unknown", title="Lost")
    AlbumFactory(ytmusic_id="second")
    run = _run()
    summary = service.complete_albums(run, ytmusic)
    assert (summary["albums"], summary["tracks"], summary["errors"]) == (2, 1, 1)
    assert _lines(run) == ["Lost: YouTube Music did not answer as expected."]


# --- Complete artists ---


def test_complete_artists_fills_in_image_and_figures_without_importing_music(
    ytmusic: FakeYTMusic,
) -> None:
    incomplete = ArtistFactory(ytmusic_id=MAIN, name="Edited by hand")
    complete = ArtistFactory(image_url="https://img/x", subscribers=5)
    ArtistFactory(ytmusic_id=None)  # no channel: nothing to ask for

    summary = service.complete_artists(_run(), ytmusic)

    assert summary == {"reviewed": 1, "completed": 1, "unchanged": 0, "errors": 0}
    incomplete.refresh_from_db()
    assert incomplete.name == "Edited by hand"
    assert (incomplete.image_url, incomplete.monthly_listeners) == (
        "http://img/main.jpg",
        5_000_000,
    )
    assert ytmusic.calls == [("profile", MAIN)]
    assert not Album.objects.exists()
    assert Artist.objects.get(pk=complete.pk).image_url == "https://img/x"


def test_complete_artists_counts_unchanged_and_failed(ytmusic: FakeYTMusic) -> None:
    ytmusic.artists["UCempty"] = ytm.Artist("UCempty", "Empty")
    ArtistFactory(ytmusic_id="UCempty", name="Empty")
    ArtistFactory(ytmusic_id="UCgone", name="Gone")
    run = _run()
    summary = service.complete_artists(run, ytmusic)
    assert summary == {"reviewed": 2, "completed": 0, "unchanged": 1, "errors": 1}
    assert _lines(run) == ["Gone: YouTube Music did not answer as expected."]


# --- Lyrics ---


def test_lyrics_are_fetched_for_downloads_that_have_none(library: Path, lrclib: FakeLrclib) -> None:
    lrclib.answer = Lyrics(synced="[00:01.00] One\n", plain=None, instrumental=False)
    _download(library, "new.mp3", TrackFactory(duration=200))
    _download(library, "has.mp3", TrackFactory(duration=200))
    (library / "has.lrc").write_text("kept")
    DownloadFactory(file_path="gone.mp3", track=TrackFactory(duration=200))

    summary = service.fetch_missing_lyrics(_run())

    assert summary == {"found": 1, "not_found": 0, "failed": 0}
    assert (library / "new.lrc").read_text() == "[00:01.00] One\n"
    assert (library / "has.lrc").read_text() == "kept"
    assert len(lrclib.asked) == 1


def test_lyrics_not_found_and_failed_are_counted_apart(library: Path, lrclib: FakeLrclib) -> None:
    _download(library, "a.mp3", TrackFactory(title="Quiet", duration=200))
    assert service.fetch_missing_lyrics(_run()) == {"found": 0, "not_found": 1, "failed": 0}

    lrclib.answer = requests.ConnectionError("LRCLIB is down")
    run = _run()
    assert service.fetch_missing_lyrics(run) == {"found": 0, "not_found": 0, "failed": 1}
    assert _lines(run) == ["Quiet: The connection failed."]


# --- Job ---


@pytest.fixture
def steps(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace every operation with one that only records its name."""
    ran: list[str] = []
    for name in service.OPERATIONS:
        monkeypatch.setitem(
            task._STEPS, name, lambda run, name=name: ran.append(name) or {"ran": name}
        )
    return ran


def test_job_runs_the_default_operations_in_order(steps: list[str]) -> None:
    run = runner.start("maintenance", {}, None)
    assert run.status == JobRun.Status.SUCCEEDED
    assert steps == ["retag", "replaygain", "check_files", "complete_artists", "lyrics"]
    assert run.summary["retag"] == {"ran": "retag"}
    assert "relocate" not in run.summary and "complete_albums" not in run.summary


def test_job_runs_only_what_is_asked_always_in_the_same_order(steps: list[str]) -> None:
    runner.start("maintenance", {"operations": ["complete_albums", "check_files"]}, None)
    assert steps == ["check_files", "complete_albums"]


@pytest.mark.parametrize(
    "operations",
    [["nope"], "retag", ["relocate", "retag"], ["replaygain", "relocate"]],
)
def test_job_refuses_unknown_or_incompatible_operations(steps: list[str], operations: Any) -> None:
    run = runner.start("maintenance", {"operations": operations}, None)
    assert run.status == JobRun.Status.FAILED
    assert steps == []


def test_job_can_relocate_on_its_own(steps: list[str]) -> None:
    runner.start("maintenance", {"operations": ["relocate", "check_files"]}, None)
    assert steps == ["relocate", "check_files"]


def test_job_skips_the_remaining_operations_once_stopped(
    steps: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter([False, True])
    monkeypatch.setattr(runner, "should_stop", lambda run: next(answers, True))
    run = runner.start("maintenance", {}, None)
    assert steps == ["retag"]
    assert list(run.summary) == ["retag"]
