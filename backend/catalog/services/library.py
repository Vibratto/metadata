"""Files of the music library.

Paths are stored relative to the ``download.folder`` setting, so the library can be moved
or mounted elsewhere without touching the database. Files are written atomically. Each
album folder gets its cover once, as ``cover.jpg``, and each artist folder its
``artist.jpg``.
"""

import ipaddress
import os
import shutil
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from socket import getaddrinfo
from urllib.parse import urljoin, urlsplit

import requests
from django.conf import settings

from catalog.models import Album, Track
from catalog.services.tagging import VARIOUS_ARTISTS, tags_for
from integrations.audio import Loudness, PathIds, render_path, slug, write_tags
from preferences.models import get_value
from proxies.routing import proxied_session

COVER = "cover.jpg"
ARTIST_IMAGE = "artist.jpg"

CoverFetcher = Callable[[str], bytes]

MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_REDIRECTS = 5


class UnsafeImageUrl(requests.RequestException):
    """The image is not served over https, or its host is not on the public internet."""


def _check_public(url: str) -> None:
    """Require https and a host that resolves only to public addresses.

    Image URLs can be edited by hand or restored from a backup; this keeps one from
    making the server fetch from itself or from its private network.

    shortcut: the name is resolved here and again when connecting, which leaves room for
    DNS rebinding. Closing that means connecting to the address that was checked.

    Raises:
        UnsafeImageUrl: If the URL does not qualify.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise UnsafeImageUrl(url)
    try:
        found = getaddrinfo(parts.hostname, parts.port or 443)
    except OSError:
        raise UnsafeImageUrl(url) from None
    addresses = {ipaddress.ip_address(str(info[4][0]).split("%")[0]) for info in found}
    if not addresses or not all(address.is_global for address in addresses):
        raise UnsafeImageUrl(url)


def download_cover(url: str) -> bytes:
    """Download a cover or artist image.

    Only https from public hosts, checked again after every redirect, and at most 25 MB.

    Raises:
        requests.RequestException: The download failed or is not allowed
            (``UnsafeImageUrl``).
    """
    with proxied_session() as session:
        for _hop in range(MAX_REDIRECTS + 1):
            _check_public(url)
            with session.get(url, allow_redirects=False, stream=True) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["Location"])
                    continue
                response.raise_for_status()
                content = response.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
                if len(content) > MAX_IMAGE_BYTES:
                    raise UnsafeImageUrl(url)
                return bytes(content)
    raise requests.TooManyRedirects(url)


def download_folder() -> Path:
    """The folder downloads go to. A relative setting hangs from the data folder."""
    return Path(settings.DATA_DIR) / str(get_value("download.folder"))


def absolute(file_path: str) -> Path:
    """On-disk path of a ``Download.file_path``."""
    return download_folder() / file_path


def place(dest: Path, content: Path | bytes) -> None:
    """Write ``dest`` atomically.

    The content goes to a hidden ``.<name>.part`` next to it and is then renamed, so a
    folder watcher such as Navidrome's never sees a half-written file.

    Args:
        dest: Final path; its folder must exist.
        content: A file to copy, or the bytes to write.
    """
    part = dest.with_name(f".{dest.name}.part")
    try:
        if isinstance(content, Path):
            shutil.copyfile(content, part)
        else:
            part.write_bytes(content)
        os.replace(part, dest)
    except BaseException:
        part.unlink(missing_ok=True)
        raise


def ids_for(track: Track) -> PathIds:
    """Catalogue ids that make the file and folder names of ``track`` unique."""
    credits = track.credits.order_by("position")
    album_credits = track.album.credits.order_by("position")
    return PathIds(
        track=track.pk,
        album=track.album.pk,
        artist=credits.values_list("artist_id", flat=True).first(),
        album_artist=album_credits.values_list("artist_id", flat=True).first(),
    )


def album_cover(album: Album, path: Path, fetch: CoverFetcher) -> bytes | None:
    """The cover already on disk, or a freshly downloaded one.

    ``None`` if the album has no cover or the download fails: a missing cover must not
    cost the track, and the album's next track tries again.
    """
    if path.is_file():
        return path.read_bytes()
    if not album.cover_url:
        return None
    try:
        return fetch(album.cover_url)
    except requests.RequestException:
        return None


def _refresh_image(dest: Path, url: str, fetch: CoverFetcher) -> None:
    """Store the image at ``url`` when it is missing or its URL has changed.

    The URL is remembered in a hidden ``.<name>.url`` file next to the image. Images are
    an extra: a failure is left for the next track or retag and never costs the audio.
    """
    stamp = dest.with_name(f".{dest.name}.url")
    if dest.is_file() and stamp.is_file() and stamp.read_text() == url:
        return
    try:
        image = fetch(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        place(dest, image)
        place(stamp, url.encode())
    except (requests.RequestException, OSError):
        return


def store_artist_image(track: Track, folder: Path, fetch: CoverFetcher = download_cover) -> None:
    """Put ``artist.jpg`` in the folder of the album's first artist.

    Only when the naming template created that folder, and never for "Various Artists".
    """
    first = track.album.credits.order_by("position").select_related("artist").first()
    if not first or not first.artist.image_url:
        return
    if first.artist.name.casefold() == VARIOUS_ARTISTS:
        return
    artist_folder = folder / slug(first.artist.name, first.artist.pk)
    if artist_folder.is_dir():
        _refresh_image(artist_folder / ARTIST_IMAGE, first.artist.image_url, fetch)


def store(
    track: Track,
    audio: Path,
    *,
    folder: Path,
    template: str,
    fetch_cover: CoverFetcher = download_cover,
    loudness: Loudness | None = None,
) -> str:
    """Tag ``audio`` and file it in the library.

    Args:
        track: Catalogue track.
        audio: Converted file, still outside the library.
        folder: Library folder.
        template: File naming template.
        fetch_cover: Image download; replaced in tests.
        loudness: Measurement of ``audio``, for its ReplayGain tags.

    Returns:
        Path relative to ``folder``, as stored in ``Download.file_path``.

    Raises:
        AudioError: Tagging failed.
        OSError: The file could not be written.
    """
    tags = tags_for(track, loudness=loudness)
    relative = render_path(template, tags, ids_for(track), audio.suffix.lstrip("."))
    dest = folder / relative
    cover_path = dest.parent / COVER
    embed = get_value("tags.embed_cover")
    cover = (
        album_cover(track.album, cover_path, fetch_cover)
        if embed or not cover_path.is_file()
        else None
    )
    write_tags(audio, replace(tags, cover=cover) if embed else tags)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if cover and not cover_path.is_file():
        place(cover_path, cover)
    place(dest, audio)
    store_artist_image(track, folder, fetch_cover)
    return str(relative)
