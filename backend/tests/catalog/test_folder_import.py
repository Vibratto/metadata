"""Folder import against an in-memory YouTube Music, with audio generated here."""

import math
import shutil
import struct
import wave
from pathlib import Path
from typing import Any

import mutagen
import pytest

from activity.models import ActivityLog
from catalog.factories import AlbumFactory, DownloadFactory, TrackFactory
from catalog.models import Album, BlockedItem, Download, Recording, Track
from catalog.services.folder_import import (
    AudioFile,
    FolderImporter,
    _is_match,
    find_remote,
    read_file,
    resolve_folder,
)
from catalog.tasks import folder_import as task
from integrations import ytmusic as ytm
from integrations.audio import Tags, convert, write_tags
from integrations.ytmusic import YTMusicError
from jobs import runner
from jobs.models import JobRun
from preferences.models import Preference

pytestmark = pytest.mark.django_db

MAIN = ytm.ArtistRef("Main", "UCmain")
ONE = ytm.SongHit("vid-one", "One", (MAIN,), "first", "First")
TWO = ytm.SongHit("vid-two", "Two", (MAIN,), "first", "First")


class FakeYTMusic:
    """Serves one album with two songs and answers searches from a fixed list."""

    def __init__(self) -> None:
        self.hits: list[ytm.SongHit] = [ONE, TWO]
        self.albums = {
            "first": ytm.Album(
                "first",
                "First",
                (MAIN,),
                year=2020,
                tracks=(
                    ytm.Track("One", (MAIN,), "vid-one", position=1),
                    ytm.Track("Two", (MAIN,), "vid-two", position=2),
                ),
            )
        }
        self.calls: list[str] = []
        self.error: Exception | None = None

    def search_songs(self, query: str) -> tuple[ytm.SongHit, ...]:
        self.calls.append(f"search:{query}")
        if self.error:
            raise self.error
        return tuple(self.hits)

    def get_album(self, browse_id: str) -> ytm.Album:
        self.calls.append(f"album:{browse_id}")
        if browse_id not in self.albums:
            raise YTMusicError("get_album failed: no data")
        return self.albums[browse_id]

    def get_artist_profile(self, channel_id: str) -> ytm.Artist:
        return ytm.Artist(channel_id, "Main", "https://img/main.jpg")


@pytest.fixture(scope="module")
def mp3(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A tiny untagged MP3, generated once."""
    work = tmp_path_factory.mktemp("audio")
    wav = work / "tone.wav"
    with wave.open(str(wav), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(
            b"".join(struct.pack("<h", int(8000 * math.sin(i / 5))) for i in range(800))
        )
    return convert(wav, work, "mp3")


@pytest.fixture
def ytmusic() -> FakeYTMusic:
    return FakeYTMusic()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An empty library folder."""
    folder = tmp_path / "music"
    folder.mkdir()
    return folder


def _audio(mp3: Path, path: Path, tags: Tags | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(mp3, path)
    if tags:
        write_tags(path, tags)
    return path


def _song(title: str = "One", **fields: Any) -> Tags:
    return Tags(title, ("Main",), **{"album": "First", **fields})


def _import(ytmusic: FakeYTMusic, root: Path, folder: str = "") -> FolderImporter:
    run = JobRun.objects.create(kind="folder_import", params={})
    importer = FolderImporter(run, ytmusic, root)
    assert importer.import_folder(folder) is True
    return importer


def _reasons(importer: FolderImporter) -> dict[str, str]:
    return {item["file"]: item["reason"] for item in importer.unlinked}


# --- resolve_folder ---


def test_resolve_folder_accepts_a_subfolder_and_the_root(root: Path) -> None:
    (root / "a" / "b").mkdir(parents=True)
    assert resolve_folder(root, "a/b") == (root / "a" / "b").resolve()
    assert resolve_folder(root, "") == root.resolve()


@pytest.mark.parametrize("folder", ["..", "a/../..", "/etc", "link"])
def test_resolve_folder_refuses_paths_outside_the_library(
    root: Path, tmp_path: Path, folder: str
) -> None:
    (root / "a").mkdir()
    (root / "link").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="outside the library folder"):
        resolve_folder(root, folder)


def test_resolve_folder_refuses_what_is_not_a_folder(root: Path) -> None:
    (root / "file.mp3").write_bytes(b"")
    for folder in ("missing", "file.mp3"):
        with pytest.raises(ValueError, match="does not exist"):
            resolve_folder(root, folder)


# --- read_file ---


def test_read_file_reads_title_artists_album_number_and_length(mp3: Path, tmp_path: Path) -> None:
    path = _audio(mp3, tmp_path / "a.mp3", Tags("One", ("Main", "Guest"), "First", track_number=3))
    file = read_file(path)
    assert file is not None
    assert file.tags == Tags("One", ("Main", "Guest"), "First", track_number=3)
    assert file.duration is not None and 0 < file.duration < 1


def test_read_file_takes_the_number_out_of_a_number_and_total(mp3: Path, tmp_path: Path) -> None:
    path = _audio(mp3, tmp_path / "a.mp3", Tags("One", ()))
    audio = mutagen.File(path, easy=True)
    audio["tracknumber"] = "4/12"
    audio.save()
    file = read_file(path)
    assert file is not None and file.tags == Tags("One", (), track_number=4)


def test_read_file_without_a_title_or_tags_is_none(mp3: Path, tmp_path: Path) -> None:
    assert read_file(_audio(mp3, tmp_path / "bare.mp3")) is None
    path = _audio(mp3, tmp_path / "untitled.mp3", Tags("x", ("Main",)))
    audio = mutagen.File(path, easy=True)
    del audio["title"]
    audio.save()
    assert read_file(path) is None
    (tmp_path / "unknown.ogg").write_bytes(b"not audio at all")
    assert read_file(tmp_path / "unknown.ogg") is None


@pytest.mark.parametrize(
    ("artist", "expected"),
    [
        ("Main / Guest", ("Main", "Guest")),
        ("Main FEAT. Guest", ("Main", "Guest")),
        ("Main; Guest", ("Main", "Guest")),
        ("AC/DC", ("AC/DC",)),
    ],
)
def test_lone_artist_tag_is_split_on_the_separators_like_navidrome_does(
    mp3: Path, tmp_path: Path, artist: str, expected: tuple[str, ...]
) -> None:
    path = _audio(mp3, tmp_path / "a.mp3", Tags("One", ("x",)))
    audio = mutagen.File(path, easy=True)
    del audio["artists"]
    audio["artist"] = artist
    audio.save()
    file = read_file(path)
    assert file is not None and file.tags.artists == expected


def test_separators_come_from_the_settings(mp3: Path, tmp_path: Path) -> None:
    Preference.objects.create(key="tags.artist_separators", value=[" x "])
    path = _audio(mp3, tmp_path / "a.mp3", Tags("One", ("x",)))
    audio = mutagen.File(path, easy=True)
    del audio["artists"]
    audio["artist"] = "Main x Guest / Other"
    audio.save()
    file = read_file(path)
    assert file is not None and file.tags.artists == ("Main", "Guest / Other")


# --- Matching a file to a song ---


def _hit(**fields: Any) -> ytm.SongHit:
    return ytm.SongHit(**{"video_id": "v", "title": "One", "artists": (MAIN,), **fields})


@pytest.mark.parametrize(
    ("hit", "file", "expected"),
    [
        (_hit(), AudioFile(_song()), True),
        (_hit(title="ONE (feat. Guest)"), AudioFile(_song("one")), True),
        (_hit(), AudioFile(_song("One (feat. Guest)")), True),
        (_hit(title="One (Live)"), AudioFile(_song()), False),
        (_hit(artists=(ytm.ArtistRef("Other"),)), AudioFile(_song()), False),
        (_hit(artists=(ytm.ArtistRef("Guest"), ytm.ArtistRef("MAIN"))), AudioFile(_song()), True),
        # A file without artist tags is judged on title and length alone.
        (_hit(artists=()), AudioFile(Tags("One", ())), True),
        (_hit(duration=200), AudioFile(_song(), 203.0), True),
        (_hit(duration=200), AudioFile(_song(), 203.5), False),
        (_hit(duration=200), AudioFile(_song(), 196.0), False),
        (_hit(duration=None), AudioFile(_song(), 203.5), True),
        (_hit(duration=200), AudioFile(_song(), None), True),
    ],
)
def test_a_song_matches_on_title_main_artist_and_length(
    hit: ytm.SongHit, file: AudioFile, expected: bool
) -> None:
    assert _is_match(hit, file) is expected


def test_the_search_asks_for_artist_and_title(ytmusic: FakeYTMusic) -> None:
    find_remote(ytmusic, AudioFile(_song()))
    find_remote(ytmusic, AudioFile(Tags("One", ())))
    assert ytmusic.calls == ["search:Main One", "search:One"]


def test_among_matches_the_one_on_the_album_the_file_names_wins(ytmusic: FakeYTMusic) -> None:
    on_single = ytm.SongHit("vid-single", "One", (MAIN,), "single", "One")
    ytmusic.hits = [on_single, ONE]
    assert find_remote(ytmusic, AudioFile(_song())) == ONE
    assert find_remote(ytmusic, AudioFile(_song(album=None))) == on_single
    assert find_remote(ytmusic, AudioFile(_song(album="Elsewhere"))) == on_single


def test_no_certain_match_is_none(ytmusic: FakeYTMusic) -> None:
    assert find_remote(ytmusic, AudioFile(_song("Three"))) is None


# --- Importing a folder ---


def test_links_files_and_imports_the_album_once(
    mp3: Path, root: Path, ytmusic: FakeYTMusic
) -> None:
    _audio(mp3, root / "Main" / "First" / "01 One.mp3", _song("One"))
    _audio(mp3, root / "Main" / "First" / "02 Two.mp3", _song("Two"))
    (root / "Main" / "First" / "cover.jpg").write_bytes(b"jpeg")

    importer = _import(ytmusic, root)

    assert (importer.linked, importer.already_linked, importer.unlinked) == (2, 0, [])
    assert Album.objects.get().ytmusic_id == "first"
    downloads = dict(Download.objects.values_list("track__title", "file_path"))
    assert downloads == {"One": "Main/First/01 One.mp3", "Two": "Main/First/02 Two.mp3"}
    assert set(Download.objects.values_list("audio_format", flat=True)) == {"mp3"}
    # The second file finds the album already in the catalogue.
    assert ytmusic.calls.count("album:first") == 1
    assert importer.counts["albums"] == 1 and importer.counts["tracks"] == 2


def test_files_are_left_exactly_as_they_were(mp3: Path, root: Path, ytmusic: FakeYTMusic) -> None:
    path = _audio(mp3, root / "odd name.mp3", _song())
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    _import(ytmusic, root)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert sorted(p.name for p in root.iterdir()) == ["odd name.mp3"]


def test_importing_twice_changes_nothing(mp3: Path, root: Path, ytmusic: FakeYTMusic) -> None:
    _audio(mp3, root / "one.mp3", _song())
    _import(ytmusic, root)
    ytmusic.calls.clear()

    again = _import(ytmusic, root)

    assert (again.linked, again.already_linked, again.unlinked) == (0, 1, [])
    assert Download.objects.count() == 1
    assert ytmusic.calls == []


def test_only_the_given_subfolder_is_imported(mp3: Path, root: Path, ytmusic: FakeYTMusic) -> None:
    _audio(mp3, root / "in" / "one.mp3", _song("One"))
    _audio(mp3, root / "out" / "two.mp3", _song("Two"))
    _import(ytmusic, root, "in")
    assert list(Download.objects.values_list("file_path", flat=True)) == ["in/one.mp3"]


def test_files_that_cannot_be_linked_are_reported_with_the_reason(
    mp3: Path, root: Path, ytmusic: FakeYTMusic
) -> None:
    _audio(mp3, root / "no-tags.mp3")
    _audio(mp3, root / "unknown.mp3", _song("Three"))
    (root / "broken.mp3").write_bytes(b"\xff\xfb" + b"\x00" * 10)
    (root / "notes.txt").write_text("ignored")

    importer = _import(ytmusic, root)

    reasons = _reasons(importer)
    assert reasons["no-tags.mp3"] == "no_tags"
    assert reasons["unknown.mp3"] == "not_found"
    assert reasons["broken.mp3"] in {"unreadable", "no_tags"}
    assert "notes.txt" not in reasons
    assert importer.linked == 0 and not Album.objects.exists()


def test_lookup_failure_is_reported_and_the_rest_goes_on(
    mp3: Path, root: Path, ytmusic: FakeYTMusic
) -> None:
    _audio(mp3, root / "a.mp3", _song("One"))
    ytmusic.albums.clear()
    importer = _import(ytmusic, root)
    assert _reasons(importer) == {"a.mp3": "error"}


def test_search_failure_is_reported(mp3: Path, root: Path, ytmusic: FakeYTMusic) -> None:
    _audio(mp3, root / "a.mp3", _song("One"))
    ytmusic.error = YTMusicError("search failed: timeout")
    assert _reasons(_import(ytmusic, root)) == {"a.mp3": "error"}


def test_symlink_to_a_file_outside_the_library_is_not_linked(
    mp3: Path, root: Path, tmp_path: Path, ytmusic: FakeYTMusic
) -> None:
    outside = _audio(mp3, tmp_path / "elsewhere" / "one.mp3", _song())
    (root / "link.mp3").symlink_to(outside)
    importer = _import(ytmusic, root)
    assert _reasons(importer) == {"link.mp3": "outside"}
    assert ytmusic.calls == []


def test_track_that_already_has_a_file_is_not_given_another(
    mp3: Path, root: Path, ytmusic: FakeYTMusic
) -> None:
    _audio(mp3, root / "a" / "one.mp3", _song())
    _audio(mp3, root / "b" / "one.mp3", _song())
    importer = _import(ytmusic, root)
    assert importer.linked == 1
    assert _reasons(importer) == {"b/one.mp3": "already_downloaded"}
    assert Download.objects.count() == 1


def test_blocked_album_is_not_imported(mp3: Path, root: Path, ytmusic: FakeYTMusic) -> None:
    BlockedItem.objects.create(kind="album", external_id="first")
    _audio(mp3, root / "one.mp3", _song())
    importer = _import(ytmusic, root)
    assert _reasons(importer) == {"one.mp3": "not_in_catalog"}
    assert not Album.objects.exists()


def test_blocked_track_is_not_linked(mp3: Path, root: Path, ytmusic: FakeYTMusic) -> None:
    BlockedItem.objects.create(kind="track", external_id="vid-one")
    _audio(mp3, root / "one.mp3", _song("One"))
    _audio(mp3, root / "two.mp3", _song("Two"))
    importer = _import(ytmusic, root)
    assert _reasons(importer) == {"one.mp3": "not_in_catalog"}
    assert list(Track.objects.values_list("title", flat=True)) == ["Two"]


# --- One recording on several releases ---


@pytest.fixture
def on_two_albums() -> Recording:
    """The recording of "One", already in the catalogue on "First" and on "Deluxe"."""
    first = TrackFactory(title="One", video_id="vid-one", album=AlbumFactory(title="First"))
    TrackFactory(
        title="One",
        recording=first.recording,
        credit=None,
        album=AlbumFactory(title="Deluxe"),
        track_number=7,
    )
    return first.recording


def test_album_tag_picks_the_release(
    mp3: Path, root: Path, ytmusic: FakeYTMusic, on_two_albums: Recording
) -> None:
    _audio(mp3, root / "one.mp3", _song(album="Deluxe"))
    _import(ytmusic, root)
    assert Download.objects.get().track.album.title == "Deluxe"
    assert not any(call.startswith("album:") for call in ytmusic.calls)


def test_without_an_album_tag_two_releases_are_ambiguous(
    mp3: Path, root: Path, ytmusic: FakeYTMusic, on_two_albums: Recording
) -> None:
    _audio(mp3, root / "one.mp3", _song(album=None))
    importer = _import(ytmusic, root)
    assert _reasons(importer) == {"one.mp3": "ambiguous"}
    assert not Download.objects.exists()


def test_without_an_album_tag_a_single_release_is_enough(
    mp3: Path, root: Path, ytmusic: FakeYTMusic
) -> None:
    track = TrackFactory(title="One", video_id="vid-one")
    _audio(mp3, root / "one.mp3", _song(album=None))
    _import(ytmusic, root)
    assert Download.objects.get().track == track


def test_file_of_an_album_the_catalogue_lacks_imports_that_album(
    mp3: Path, root: Path, ytmusic: FakeYTMusic
) -> None:
    # The recording is known from a single, but the file belongs to the album.
    TrackFactory(title="One", video_id="vid-one", album=AlbumFactory(title="One (Single)"))
    _audio(mp3, root / "one.mp3", _song(album="First"))
    _import(ytmusic, root)
    assert Download.objects.get().track.album.title == "First"
    assert Recording.objects.filter(video_id="vid-one").count() == 1


def test_track_number_breaks_a_tie_on_the_same_album(
    mp3: Path, root: Path, ytmusic: FakeYTMusic
) -> None:
    album = AlbumFactory(title="First")
    first = TrackFactory(title="One", video_id="vid-one", album=album, track_number=1)
    reprise = TrackFactory(
        title="One", recording=first.recording, credit=None, album=album, track_number=9
    )
    _audio(mp3, root / "one.mp3", _song(track_number=9))
    _import(ytmusic, root)
    assert Download.objects.get().track == reprise


# --- Job ---


@pytest.fixture
def job(monkeypatch: pytest.MonkeyPatch, root: Path, ytmusic: FakeYTMusic) -> FakeYTMusic:
    Preference.objects.create(key="download.folder", value=str(root))
    monkeypatch.setattr(task, "ytmusic_client", lambda: ytmusic)
    return ytmusic


def test_job_reports_counters_and_logs_activity(mp3: Path, root: Path, job: FakeYTMusic) -> None:
    _audio(mp3, root / "in" / "one.mp3", _song("One"))
    _audio(mp3, root / "in" / "unknown.mp3", _song("Three"))

    run = runner.start("folder_import", {"folder": "in"}, None)

    assert run.status == JobRun.Status.SUCCEEDED
    assert (run.summary["linked"], run.summary["completed"]) == (1, True)
    assert run.summary["unlinked"] == [{"file": "in/unknown.mp3", "reason": "not_found"}]
    assert (run.done, run.total) == (2, 2)
    entry = ActivityLog.objects.get(action="catalog.folder_import")
    assert entry.detail == {"folder": "in", "linked": 1, "unlinked": 1}


def test_job_without_a_folder_imports_the_whole_library(
    mp3: Path, root: Path, job: FakeYTMusic
) -> None:
    _audio(mp3, root / "deep" / "er" / "one.mp3", _song())
    assert runner.start("folder_import", {}, None).summary["linked"] == 1


@pytest.mark.parametrize("folder", [3, ["a"], "..", "missing"])
def test_job_fails_on_an_invalid_folder(job: FakeYTMusic, folder: Any) -> None:
    run = runner.start("folder_import", {"folder": folder}, None)
    assert run.status == JobRun.Status.FAILED
    assert not Download.objects.exists()


def test_job_stops_between_files(
    mp3: Path, root: Path, job: FakeYTMusic, monkeypatch: pytest.MonkeyPatch
) -> None:
    _audio(mp3, root / "a.mp3", _song("One"))
    _audio(mp3, root / "b.mp3", _song("Two"))
    answers = iter([False, True])
    monkeypatch.setattr(runner, "should_stop", lambda run: next(answers, True))
    run = runner.start("folder_import", {}, None)
    assert run.summary["completed"] is False
    assert run.summary["linked"] == 1


def test_downloads_of_other_tracks_are_untouched(
    mp3: Path, root: Path, ytmusic: FakeYTMusic
) -> None:
    other = DownloadFactory(file_path="elsewhere/x.mp3")
    _audio(mp3, root / "one.mp3", _song())
    _import(ytmusic, root)
    assert Download.objects.filter(pk=other.pk).exists()
    assert Download.objects.count() == 2
