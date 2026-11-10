"""YouTube integration errors."""


class YoutubeError(Exception):
    """Search or download failure reported by yt-dlp. It hides ``yt_dlp`` types so
    callers do not depend on the library.
    """
