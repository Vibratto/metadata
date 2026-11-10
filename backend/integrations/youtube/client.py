"""Audio search and download with yt-dlp, used as a library."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from integrations.youtube.errors import YoutubeError

# A video id is 11 chars of this alphabet; validating it keeps arbitrary values
# out of URLs and iframes.
#: Service yt-dlp connects to.
YOUTUBE_URL = "https://www.youtube.com"
_VIDEO_ID = re.compile(r"[\w-]{11}")

# YoutubeDL factory; tests inject a double so nothing hits the network.
YdlFactory = Callable[[Any], Any]


@dataclass(frozen=True)
class VideoMatch:
    """Candidate video for a track.

    Attributes:
        video_id: YouTube id.
        title: Video title.
        duration: Duration in seconds.
    """

    video_id: str
    title: str
    duration: float


@dataclass(frozen=True)
class DownloadProgress:
    """Download progress.

    Attributes:
        downloaded_bytes: Bytes downloaded so far.
        total_bytes: Total size, or
            ``None`` when unknown.
        finished: ``True`` once the
            file is complete.
    """

    downloaded_bytes: int
    total_bytes: int | None
    finished: bool


def preview_embed_url(video_id: str) -> str:
    """Embed URL on ``youtube-nocookie.com``.

    Args:
        video_id: YouTube id.

    Returns:
        URL for an ``iframe``.

    Raises:
        ValueError: If the id does not look like a YouTube id.
    """
    if not _VIDEO_ID.fullmatch(video_id):
        raise ValueError(f"Invalid YouTube video id: {video_id!r}")
    return f"https://www.youtube-nocookie.com/embed/{video_id}"


def find_best_video(
    title: str,
    artists: list[str],
    duration: float,
    *,
    tolerance: float = 10.0,
    candidates: int = 5,
    proxy: str | None = None,
    ydl_factory: YdlFactory = YoutubeDL,
) -> VideoMatch | None:
    """Finds the video that best matches a track. Among the first results, it takes
    the first whose duration is within ``tolerance`` of the track's: YouTube
    already ranks by relevance, and the duration discards live sets and mixes.

    Args:
        title: Track title.
        artists: Artists, in order.
        duration: Expected duration in seconds.
        tolerance: Maximum accepted
            difference in seconds.
        candidates: Results to inspect.
        proxy: Proxy URL to use.
        ydl_factory: ``YoutubeDL`` factory.

    Returns:
        The chosen video, or
        ``None`` when none fits.

    Raises:
        YoutubeError: If yt-dlp fails.
    """
    query = f"ytsearch{candidates}:{', '.join(artists)} - {title}"
    # extract_flat skips resolving each video: only id, title and duration are needed.
    options: dict[str, Any] = {"quiet": True, "extract_flat": True, "proxy": proxy}
    try:
        with ydl_factory(options) as ydl:
            info = ydl.extract_info(query, download=False)
    except DownloadError as exc:
        raise YoutubeError(str(exc)) from exc
    for entry in info.get("entries") or []:
        entry_duration = entry.get("duration")
        if entry_duration is not None and abs(entry_duration - duration) <= tolerance:
            return VideoMatch(entry["id"], entry["title"], float(entry_duration))
    return None


def download_audio(
    video_id: str,
    dest_dir: Path,
    *,
    on_progress: Callable[[DownloadProgress], None] | None = None,
    proxy: str | None = None,
    ydl_factory: YdlFactory = YoutubeDL,
) -> Path:
    """Downloads the best audio stream as-is; conversion and tagging belong to the
    audio integration.

    Args:
        video_id: YouTube id.
        dest_dir: Destination folder.
        on_progress: Called on every progress update.
        proxy: Proxy URL to use.
        ydl_factory: ``YoutubeDL`` factory.

    Returns:
        Path of the downloaded file.

    Raises:
        ValueError: If the id is invalid.
        YoutubeError: If yt-dlp fails.
    """
    preview_embed_url(video_id)  # validates the id

    def hook(data: dict[str, Any]) -> None:
        """Translates yt-dlp's progress dict."""
        if on_progress is None or data["status"] not in ("downloading", "finished"):
            return
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        on_progress(
            DownloadProgress(
                downloaded_bytes=data["downloaded_bytes"],
                total_bytes=total,
                finished=data["status"] == "finished",
            )
        )

    options: dict[str, Any] = {
        "quiet": True,
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
        "progress_hooks": [hook],
        "proxy": proxy,
    }
    try:
        with ydl_factory(options) as ydl:
            info = ydl.extract_info(f"{YOUTUBE_URL}/watch?v={video_id}", download=True)
            return Path(ydl.prepare_filename(info))
    except DownloadError as exc:
        raise YoutubeError(str(exc)) from exc
