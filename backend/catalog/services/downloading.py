"""Download of a single track: audio, conversion, tags and bookkeeping."""

import shutil
import tempfile
import time
from pathlib import Path
from typing import cast

from catalog.models import Download, DownloadLoudness, Track
from catalog.services import replaygain
from catalog.services.library import absolute, store
from catalog.services.tagging import tags_for
from integrations.audio import Loudness, convert
from integrations.youtube import (
    YOUTUBE_URL,
    ProxyPool,
    YoutubeError,
    download_audio,
    find_best_video,
)
from proxies import routing


class TrackNotDownloadable(Exception):  # noqa: N818
    """The track has no video of its own and no search result matches it."""


def build_pool() -> ProxyPool:
    """Enabled proxies that can reach YouTube; an empty pool means a direct connection."""
    return routing.build_pool(YOUTUBE_URL)


def _copy_from_sibling(track: Track, *, folder: Path, template: str) -> Download | None:
    """Reuse the file of another track of the same recording, if one is on disk.

    The copy is tagged for this track's album and keeps the loudness already measured,
    so the audio is fetched once per recording. Each album still gets a complete file.

    Returns:
        The new download, or ``None`` if no other track of the recording has a file.
    """
    # ``Download.objects`` is typed on the append-only base class; the cast keeps the model.
    sources = cast(
        list[Download],
        list(
            Download.objects.filter(
                track__in=Track.objects.filter(recording=track.recording_id).exclude(pk=track.pk)
            ).order_by("-pk")
        ),
    )
    for source in sources:
        origin = absolute(source.file_path)
        if not origin.is_file():
            continue
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / f"copy{origin.suffix}"
            shutil.copyfile(origin, audio)
            loudness = _loudness_of(source, audio)
            stored = store(track, audio, folder=folder, template=template, loudness=loudness)
        download = Download.objects.create(
            track=track,
            file_path=stored,
            audio_format=source.audio_format,
            source_url=source.source_url,
        )
        replaygain.remember(download, loudness)
        return download
    return None


def _loudness_of(source: Download, audio: Path) -> Loudness | None:
    """The loudness stored for ``source``; measured from ``audio`` if there is none."""
    stored = DownloadLoudness.objects.filter(download=source).first()
    if stored is not None:
        return Loudness(lufs=stored.lufs, peak=stored.peak)
    return replaygain.measure(audio)


def video_id_for(track: Track, proxy: str | None) -> str:
    """The video to download: the track's own, or the best search match without one.

    Tracks imported from YouTube Music carry their video id. Only tracks that came from
    a folder import, or that YouTube Music lists as unavailable, need the search.
    """
    if track.video_id:
        return track.video_id
    if not track.duration:
        raise TrackNotDownloadable("the track has neither a video nor a duration to search by")
    tags = tags_for(track)
    video = find_best_video(tags.title, list(tags.artists), float(track.duration), proxy=proxy)
    if video is None:
        raise TrackNotDownloadable("no video matches the track")
    return video.video_id


def download_track(
    track: Track, pool: ProxyPool, *, fmt: str, folder: Path, template: str
) -> Download:
    """Download a track, convert and tag it, and record the ``Download``.

    The work happens in a temporary folder and the finished file is moved into place in
    one step, so a failure never leaves a half-written file in the library.

    Args:
        track: Track to download.
        pool: Proxy pool shared by the whole job.
        fmt: Output format, a key of ``integrations.audio.FORMATS``.
        folder: Library folder.
        template: File naming template.

    Raises:
        TrackNotDownloadable: The track has no video and none could be found.
        NoProxyAvailable: Every proxy is cooling down.
        YoutubeError: yt-dlp failed.
        AudioError: Conversion or tagging failed.
    """
    if (copied := _copy_from_sibling(track, folder=folder, template=template)) is not None:
        return copied
    proxy = pool.acquire(time.monotonic())
    try:
        video_id = video_id_for(track, proxy)
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            raw = download_audio(video_id, work, proxy=proxy)
            converted = convert(raw, work, fmt)
            loudness = replaygain.measure(converted)
            stored = store(track, converted, folder=folder, template=template, loudness=loudness)
    except YoutubeError:
        # Only network failures count against the proxy; finding no video is not its fault.
        if proxy is not None:
            pool.report_failure(proxy, time.monotonic())
        routing.record_use(proxy, ok=False)
        raise
    if proxy is not None:
        pool.report_success(proxy)
    routing.record_use(proxy, ok=True)
    download = Download.objects.create(
        track=track,
        file_path=stored,
        audio_format=fmt,
        source_url=f"https://music.youtube.com/watch?v={video_id}",
    )
    replaygain.remember(download, loudness)
    return download
