"""Tests for the library files."""

import os
import re
from pathlib import Path
from typing import Any, cast

import pytest
import requests
import responses

from catalog.factories import AlbumFactory, ArtistFactory, TrackArtistFactory, TrackFactory
from catalog.models import AlbumArtist, Track
from catalog.services import library
from integrations.audio import Loudness, PathIds, ReplayGain, Tags
from preferences.models import Preference

pytestmark = pytest.mark.django_db

TEMPLATE = "{albumartist}/{album}/{disc}-{track}-{title}"


@pytest.fixture
def written(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, Tags]]:
    """Replaces tag writing and records calls."""
    calls: list[tuple[Path, Tags]] = []
    monkeypatch.setattr(library, "write_tags", lambda path, tags: calls.append((path, tags)))
    return calls


def _track(cover_url: str = "https://img/c") -> Track:
    album = AlbumFactory(title="MOTOMAMI", cover_url=cover_url, credit=None)
    rosalia = ArtistFactory(name="Rosalía")
    AlbumArtist.objects.create(album=album, artist=rosalia, position=0)
    track = TrackFactory(album=album, title="La Fama", track_number=2, disc_number=1, credit=None)
    TrackArtistFactory(track=track, artist=rosalia, position=0)
    TrackArtistFactory(track=track, artist=ArtistFactory(name="The Weeknd"), position=1)
    return cast(Track, track)


def _audio(tmp_path: Path, content: bytes = b"audio") -> Path:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    audio = work / "track.opus"
    audio.write_bytes(content)
    return audio


def test_ids_for_uses_the_first_credited_artists() -> None:
    track = _track()
    rosalia = track.credits.get(position=0).artist
    assert library.ids_for(track) == PathIds(
        track=track.pk, album=track.album.pk, artist=rosalia.pk, album_artist=rosalia.pk
    )


def test_ids_for_without_credits() -> None:
    track = TrackFactory(credit=None, album=AlbumFactory(credit=None))
    ids = library.ids_for(track)
    assert (ids.artist, ids.album_artist) == (None, None)


def test_store_names_tags_and_places_the_file_with_its_album_cover(
    tmp_path: Path, written: list[tuple[Path, Tags]]
) -> None:
    track = _track()
    folder = tmp_path / "library"
    audio = _audio(tmp_path)

    stored = library.store(
        track, audio, folder=folder, template=TEMPLATE, fetch_cover=lambda url: b"jpeg"
    )

    rosalia = track.credits.get(position=0).artist
    assert stored == f"rosalia-{rosalia.pk}/motomami-{track.album.pk}/01-02-la-fama-{track.pk}.opus"
    assert re.fullmatch(r"[a-z0-9._/-]+", stored)
    assert (folder / stored).read_bytes() == b"audio"
    assert (folder / stored).parent.joinpath("cover.jpg").read_bytes() == b"jpeg"
    assert [p.name for p in (folder / stored).parent.iterdir() if p.name.startswith(".")] == []
    assert written[0][1].title == "La Fama"
    assert written[0][1].cover is None  # not embedded by default


def test_store_fetches_the_cover_once_per_album(
    tmp_path: Path, written: list[tuple[Path, Tags]]
) -> None:
    track = _track()
    other = TrackFactory(album=track.album, title="Bulerías", track_number=1, disc_number=1)
    fetched: list[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return b"jpeg"

    for item in (track, other):
        library.store(item, _audio(tmp_path), folder=tmp_path / "lib", template=TEMPLATE,
                      fetch_cover=fetch)  # fmt: skip

    assert fetched == ["https://img/c"]


def test_store_embeds_the_cover_when_asked(
    tmp_path: Path, written: list[tuple[Path, Tags]]
) -> None:
    Preference.objects.create(key="tags.embed_cover", value=True)
    track = _track()
    for _ in range(2):
        library.store(track, _audio(tmp_path), folder=tmp_path / "lib", template=TEMPLATE,
                      fetch_cover=lambda url: b"jpeg")  # fmt: skip
    assert [tags.cover for _, tags in written] == [b"jpeg", b"jpeg"]


def test_store_without_cover_or_when_it_fails_still_stores_the_audio(
    tmp_path: Path, written: list[tuple[Path, Tags]]
) -> None:
    def fail(url: str) -> bytes:
        raise requests.ConnectionError("down")

    for track in (_track(cover_url=""), TrackFactory(album=AlbumFactory(cover_url="https://x"))):
        stored = library.store(
            track, _audio(tmp_path), folder=tmp_path / "lib", template=TEMPLATE, fetch_cover=fail
        )
        assert (tmp_path / "lib" / stored).is_file()
        assert not (tmp_path / "lib" / stored).parent.joinpath("cover.jpg").exists()


def test_store_writes_the_replaygain_of_the_given_measure(
    tmp_path: Path, written: list[tuple[Path, Tags]]
) -> None:
    library.store(
        _track(),
        _audio(tmp_path),
        folder=tmp_path / "lib",
        template=TEMPLATE,
        fetch_cover=lambda url: b"jpeg",
        loudness=Loudness(lufs=-8.0, peak=1.0),
    )
    assert written[0][1].replaygain == ReplayGain(track_gain_db=-10.0, track_peak=1.0)


def test_place_writes_through_a_hidden_part_file_and_replaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "album" / "song.opus"
    dest.parent.mkdir()
    dest.write_bytes(b"old")
    seen: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src: Any, dst: Any) -> None:
        seen.append((Path(src).name, Path(dst).name))
        real_replace(src, dst)

    monkeypatch.setattr(library.os, "replace", spy)
    library.place(dest, b"new")
    library.place(dest, _audio(tmp_path, b"newer"))

    assert seen == [(".song.opus.part", "song.opus")] * 2
    assert dest.read_bytes() == b"newer"
    assert sorted(p.name for p in dest.parent.iterdir()) == ["song.opus"]


def test_place_removes_the_part_file_when_it_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(src: Any, dst: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(library.os, "replace", broken)
    with pytest.raises(OSError, match="disk full"):
        library.place(tmp_path / "song.opus", b"data")
    assert list(tmp_path.iterdir()) == []


def test_absolute_resolves_stored_paths_against_the_library(tmp_path: Path) -> None:
    Preference.objects.create(key="download.folder", value=str(tmp_path / "lib"))
    assert library.absolute("a-1/b-2/c-3.mp3") == tmp_path / "lib" / "a-1" / "b-2" / "c-3.mp3"


# --- Artist images ---


def _with_images(track: Track) -> Track:
    """Gives every credited artist an image."""
    for credit in track.credits.select_related("artist"):
        credit.artist.image_url = f"https://img/{credit.artist.name}"
        credit.artist.save()
    return track


def _artist_folder(folder: Path, track: Track) -> Path:
    rosalia = track.credits.get(position=0).artist
    return folder / f"rosalia-{rosalia.pk}"


def test_store_saves_the_album_artist_image_as_artist_jpg(
    tmp_path: Path, written: list[tuple[Path, Tags]]
) -> None:
    track = _with_images(_track())
    folder = tmp_path / "lib"

    library.store(track, _audio(tmp_path), folder=folder, template=TEMPLATE,
                  fetch_cover=lambda url: url.encode())  # fmt: skip

    assert (
        _artist_folder(folder, track) / "artist.jpg"
    ).read_bytes() == b"https://img/Rosal\xc3\xada"
    assert not (folder / "_artistas").exists()  # carpeta central desactivada / central folder off


def test_store_fetches_the_artist_image_again_only_when_its_url_changes(
    tmp_path: Path, written: list[tuple[Path, Tags]]
) -> None:
    track = _with_images(_track(cover_url=""))
    folder = tmp_path / "lib"
    fetched: list[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return url.encode()

    def store() -> None:
        library.store(track, _audio(tmp_path), folder=folder, template=TEMPLATE, fetch_cover=fetch)

    store()
    store()
    assert fetched == ["https://img/Rosalía"]

    rosalia = track.credits.get(position=0).artist
    rosalia.image_url = "https://img/new"
    rosalia.save()
    store()
    assert fetched == ["https://img/Rosalía", "https://img/new"]
    assert (_artist_folder(folder, track) / "artist.jpg").read_bytes() == b"https://img/new"


def test_store_skips_the_artist_image_for_various_artists(
    tmp_path: Path, written: list[tuple[Path, Tags]]
) -> None:
    track = _with_images(_track(cover_url=""))
    various = ArtistFactory(name="Various Artists", ytmusic_id=None, image_url="https://img/va")
    AlbumArtist.objects.filter(album=track.album).update(artist=various)
    folder = tmp_path / "lib"

    library.store(track, _audio(tmp_path), folder=folder, template=TEMPLATE,
                  fetch_cover=lambda url: b"jpeg")  # fmt: skip

    assert not (folder / f"various-artists-{various.pk}" / "artist.jpg").exists()


def test_store_does_not_create_an_artist_folder_the_template_does_not_use(
    tmp_path: Path, written: list[tuple[Path, Tags]]
) -> None:
    track = _with_images(_track(cover_url=""))
    folder = tmp_path / "lib"

    library.store(track, _audio(tmp_path), folder=folder, template="{album}/{title}",
                  fetch_cover=lambda url: b"jpeg")  # fmt: skip

    assert not _artist_folder(folder, track).exists()


def test_a_failed_artist_image_still_stores_the_audio(
    tmp_path: Path, written: list[tuple[Path, Tags]]
) -> None:
    track = _with_images(_track(cover_url=""))
    folder = tmp_path / "lib"

    def fail(url: str) -> bytes:
        raise requests.ConnectionError("down")

    stored = library.store(track, _audio(tmp_path), folder=folder, template=TEMPLATE,
                           fetch_cover=fail)  # fmt: skip

    assert (folder / stored).is_file()
    assert sorted(p.name for p in _artist_folder(folder, track).iterdir()) == [
        f"motomami-{track.album.pk}"
    ]


PUBLIC_V4 = "93.184.215.14"


@pytest.fixture
def resolve(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Fake DNS with chosen addresses per host."""
    hosts: dict[str, list[str]] = {}

    def getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any) -> Any:
        if host not in hosts:
            raise OSError("no address")
        return [(0, 0, 0, "", (address, port)) for address in hosts[host]]

    monkeypatch.setattr(library, "getaddrinfo", getaddrinfo)
    return hosts


@responses.activate
def test_download_cover_fetches_a_public_https_image(resolve: dict[str, list[str]]) -> None:
    resolve["img.example.com"] = [PUBLIC_V4]
    responses.get("https://img.example.com/c.jpg", body=b"jpeg")

    assert library.download_cover("https://img.example.com/c.jpg") == b"jpeg"


@responses.activate
@pytest.mark.parametrize(
    ("url", "addresses"),
    [
        ("http://img.example.com/c.jpg", [PUBLIC_V4]),
        ("ftp://img.example.com/c.jpg", [PUBLIC_V4]),
        ("https://127.0.0.1:8000/api/health/", []),
        ("https://[::1]/c.jpg", []),
        ("https://intranet.example.com/c.jpg", ["10.0.0.5"]),
        ("https://intranet.example.com/c.jpg", ["192.168.1.10"]),
        ("https://intranet.example.com/c.jpg", ["169.254.169.254"]),
        ("https://intranet.example.com/c.jpg", ["fd00::1"]),
        ("https://intranet.example.com/c.jpg", [PUBLIC_V4, "127.0.0.1"]),
        ("https://unknown.example.com/c.jpg", None),
    ],
    ids=[
        "http",
        "ftp",
        "loopback-literal",
        "ipv6-loopback-literal",
        "private-10",
        "private-192",
        "link-local-metadata",
        "ipv6-unique-local",
        "one-private-address",
        "does-not-resolve",
    ],
)
def test_download_cover_refuses_non_public_targets(
    resolve: dict[str, list[str]], url: str, addresses: list[str] | None
) -> None:
    if addresses is not None:
        resolve["img.example.com"] = addresses
        resolve["intranet.example.com"] = addresses

    with pytest.raises(requests.RequestException):
        library.download_cover(url)
    assert not responses.calls


@responses.activate
def test_download_cover_follows_redirects_only_to_public_hosts(
    resolve: dict[str, list[str]],
) -> None:
    resolve["img-a.example.com"] = [PUBLIC_V4]
    resolve["archive.example.com"] = [PUBLIC_V4]
    resolve["intranet.example.com"] = ["10.0.0.5"]
    responses.get(
        "https://img-a.example.com/ok",
        status=307,
        headers={"Location": "https://archive.example.com/c.jpg"},
    )
    responses.get("https://archive.example.com/c.jpg", body=b"jpeg")
    responses.get(
        "https://img-a.example.com/bad",
        status=302,
        headers={"Location": "https://intranet.example.com/secret"},
    )
    responses.get("https://intranet.example.com/secret", body=b"secret")

    assert library.download_cover("https://img-a.example.com/ok") == b"jpeg"
    with pytest.raises(requests.RequestException):
        library.download_cover("https://img-a.example.com/bad")
    assert all("intranet" not in (call.request.url or "") for call in responses.calls)


@responses.activate
def test_download_cover_refuses_images_over_25_mb(resolve: dict[str, list[str]]) -> None:
    resolve["img.example.com"] = [PUBLIC_V4]
    responses.get("https://img.example.com/big.jpg", body=b"x" * (25 * 1024 * 1024 + 1))
    responses.get("https://img.example.com/max.jpg", body=b"x" * (25 * 1024 * 1024))

    with pytest.raises(requests.RequestException):
        library.download_cover("https://img.example.com/big.jpg")
    assert len(library.download_cover("https://img.example.com/max.jpg")) == 25 * 1024 * 1024


def test_a_refused_cover_still_stores_the_audio(
    tmp_path: Path, written: list[tuple[Path, Tags]], resolve: dict[str, list[str]]
) -> None:
    resolve["intranet.example.com"] = ["10.0.0.5"]
    track = _track(cover_url="https://intranet.example.com/c.jpg")

    relative = library.store(track, _audio(tmp_path), folder=tmp_path / "music", template=TEMPLATE)

    assert (tmp_path / "music" / relative).read_bytes() == b"audio"
    assert not (tmp_path / "music" / relative).with_name("cover.jpg").exists()


@responses.activate
def test_download_cover_gives_up_after_too_many_redirects(resolve: dict[str, list[str]]) -> None:
    resolve["img.example.com"] = [PUBLIC_V4]
    responses.get(
        "https://img.example.com/loop",
        status=302,
        headers={"Location": "https://img.example.com/loop"},
    )

    with pytest.raises(requests.TooManyRedirects):
        library.download_cover("https://img.example.com/loop")
    assert len(responses.calls) == library.MAX_REDIRECTS + 1
