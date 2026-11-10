"""YouTube (yt-dlp) integration."""

from integrations.youtube.client import (
    YOUTUBE_URL,
    DownloadProgress,
    VideoMatch,
    download_audio,
    find_best_video,
    preview_embed_url,
)
from integrations.youtube.errors import YoutubeError
from integrations.youtube.proxies import NoProxyAvailable, ProxyPool

__all__ = [
    "DownloadProgress",
    "NoProxyAvailable",
    "ProxyPool",
    "VideoMatch",
    "YOUTUBE_URL",
    "YoutubeError",
    "download_audio",
    "find_best_video",
    "preview_embed_url",
]
