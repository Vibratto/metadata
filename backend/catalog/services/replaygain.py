"""ReplayGain of the library.

The track gain is measured when a file is stored. The album gain is measured once the
album's tracks are on disk, over all of them played back to back. Files are retagged in
place and never moved.
"""

from dataclasses import replace
from pathlib import Path
from typing import cast

from catalog.models import Album, AlbumLoudness, Download, DownloadLoudness
from catalog.services.library import COVER, absolute
from catalog.services.tagging import tags_for
from integrations.audio import Loudness, measure_loudness, write_tags
from preferences.models import get_value


def measure(path: Path) -> Loudness | None:
    """Measure ``path``, or return ``None`` when ReplayGain is turned off.

    Raises:
        AudioError: ffmpeg could not measure the file.
    """
    return measure_loudness([path]) if get_value("replaygain.enabled") else None


def remember(download: Download, loudness: Loudness | None) -> None:
    """Store the measurement of the file of ``download``."""
    if loudness is not None:
        DownloadLoudness.objects.update_or_create(
            download=download, defaults={"lufs": loudness.lufs, "peak": loudness.peak}
        )


def _latest_on_disk(album: Album) -> list[tuple[Download, Path]]:
    """The newest file of each album track that is still on disk, in album order.

    Older downloads of a track were replaced and are no longer what plays.
    """
    # ``Download.objects`` is typed on the append-only base class; the cast keeps the model.
    downloads = cast(
        list[Download],
        list(
            Download.objects.filter(track__in=album.tracks.all()).order_by(
                "track__disc_number", "track__track_number", "-pk"
            )
        ),
    )
    latest: dict[int, Download] = {}
    for download in downloads:
        latest.setdefault(download.track_id, download)
    found = [(download, absolute(download.file_path)) for download in latest.values()]
    return [(download, path) for download, path in found if path.is_file()]


def update_album(album: Album, *, remeasure: bool = False) -> int:
    """Compute the album gain and rewrite the tags of the album's files.

    Args:
        album: Catalogue album.
        remeasure: Measure again the tracks that already have a measurement.

    Returns:
        Number of files rewritten.

    Raises:
        AudioError: ffmpeg or tagging failed.
        OSError: A file could not be read or written.
    """
    files = _latest_on_disk(album)
    if not files:
        return 0
    for download, path in files:
        if remeasure or not DownloadLoudness.objects.filter(download=download).exists():
            remember(download, measure_loudness([path]))
    union = measure_loudness([path for _, path in files])
    AlbumLoudness.objects.update_or_create(
        album=album, defaults={"lufs": union.lufs, "peak": union.peak}
    )
    embed = get_value("tags.embed_cover")
    for download, path in files:
        tags = tags_for(download.track)
        cover = path.parent / COVER
        # Rewriting replaces every tag, so the embedded cover is read back from cover.jpg.
        write_tags(
            path, replace(tags, cover=cover.read_bytes()) if embed and cover.is_file() else tags
        )
    return len(files)
