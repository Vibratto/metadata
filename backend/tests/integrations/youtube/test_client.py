"""Search and download tests, fake yt-dlp."""

import json
from pathlib import Path
from typing import Any

import pytest
from yt_dlp.utils import DownloadError

from integrations.youtube import (
    DownloadProgress,
    VideoMatch,
    YoutubeError,
    download_audio,
    find_best_video,
    preview_embed_url,
)

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


class FakeYdl:
    """``YoutubeDL`` double: no network."""

    def __init__(self, options: dict[str, Any], info: dict[str, Any] | Exception) -> None:
        """Stores options and the canned reply."""
        self.options = options
        self.info = info
        self.queries: list[str] = []

    def __enter__(self) -> "FakeYdl":
        """Enters the context."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Leaves the context."""

    def extract_info(self, url: str, download: bool) -> dict[str, Any]:
        """Returns the reply, faking progress."""
        self.queries.append(url)
        if isinstance(self.info, Exception):
            raise self.info
        for hook in self.options.get("progress_hooks", []):
            hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes_estimate": 100})
            hook({"status": "downloading", "downloaded_bytes": 80, "total_bytes": 160})
            hook({"status": "error", "downloaded_bytes": 0})
            hook({"status": "finished", "downloaded_bytes": 160, "total_bytes": 160})
        return self.info

    def prepare_filename(self, info: dict[str, Any]) -> str:
        """File name from the template."""
        return str(self.options["outtmpl"]) % {"id": info["id"], "ext": info["ext"]}


def _factory(info: dict[str, Any] | Exception) -> tuple[list[FakeYdl], Any]:
    """Factory that remembers what it builds."""
    made: list[FakeYdl] = []

    def factory(options: dict[str, Any]) -> FakeYdl:
        made.append(FakeYdl(options, info))
        return made[-1]

    return made, factory


@pytest.fixture
def search_info() -> dict[str, Any]:
    """Recorded yt-dlp search result."""
    return json.loads((FIXTURES / "youtube_search.json").read_text())


def test_find_best_video_skips_wrong_duration_and_unknown(search_info: dict[str, Any]) -> None:
    made, factory = _factory(search_info)
    match = find_best_video(
        "Get Lucky",
        ["Daft Punk", "Pharrell Williams"],
        369,
        ydl_factory=factory,
        proxy="http://p:1",
    )
    assert match == VideoMatch("5NV6Rdv1a3I", "Daft Punk - Get Lucky (Official Audio)", 369.0)
    assert made[0].queries == ["ytsearch5:Daft Punk, Pharrell Williams - Get Lucky"]
    assert made[0].options["proxy"] == "http://p:1"


def test_find_best_video_none_fits(search_info: dict[str, Any]) -> None:
    _, factory = _factory(search_info)
    assert find_best_video("Get Lucky", ["Daft Punk"], 200, ydl_factory=factory) is None


def test_find_best_video_without_entries() -> None:
    _, factory = _factory({})
    assert find_best_video("x", ["y"], 100, ydl_factory=factory) is None


def test_find_best_video_wraps_errors() -> None:
    _, factory = _factory(DownloadError("boom"))
    with pytest.raises(YoutubeError, match="boom"):
        find_best_video("x", ["y"], 100, ydl_factory=factory)


def test_download_audio_reports_progress(tmp_path: Path) -> None:
    made, factory = _factory({"id": "5NV6Rdv1a3I", "ext": "webm"})
    seen: list[DownloadProgress] = []
    path = download_audio("5NV6Rdv1a3I", tmp_path, on_progress=seen.append, ydl_factory=factory)
    assert path == tmp_path / "5NV6Rdv1a3I.webm"
    assert seen == [
        DownloadProgress(50, 100, False),
        DownloadProgress(80, 160, False),
        DownloadProgress(160, 160, True),
    ]
    assert made[0].queries == ["https://www.youtube.com/watch?v=5NV6Rdv1a3I"]


def test_download_audio_without_callback(tmp_path: Path) -> None:
    _, factory = _factory({"id": "5NV6Rdv1a3I", "ext": "m4a"})
    assert download_audio("5NV6Rdv1a3I", tmp_path, ydl_factory=factory).suffix == ".m4a"


def test_download_audio_wraps_errors(tmp_path: Path) -> None:
    _, factory = _factory(DownloadError("blocked"))
    with pytest.raises(YoutubeError, match="blocked"):
        download_audio("5NV6Rdv1a3I", tmp_path, ydl_factory=factory)


def test_download_audio_rejects_bad_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        download_audio("../etc", tmp_path)


def test_preview_embed_url() -> None:
    assert preview_embed_url("5NV6Rdv1a3I") == "https://www.youtube-nocookie.com/embed/5NV6Rdv1a3I"


@pytest.mark.parametrize("bad", ["", "short", "a" * 12, "bad id!!!!!!", '"><script>x'])
def test_preview_embed_url_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        preview_embed_url(bad)
