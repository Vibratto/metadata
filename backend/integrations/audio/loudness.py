"""Loudness (EBU R128) and ReplayGain."""

import re
import subprocess  # noqa: S404  # called with an argument list, never through a shell
from dataclasses import dataclass
from pathlib import Path

from .errors import AudioError
from .tags import ReplayGain

DEFAULT_TIMEOUT = 600.0
#: ReplayGain 2.0 reference in LUFS.
REFERENCE_LUFS = -18.0

# The last match is the final summary.
_INTEGRATED = re.compile(r"^\s*I:\s+(-?[\d.]+|-inf) LUFS", re.MULTILINE)
_PEAK = re.compile(r"^\s*Peak:\s+(-?[\d.]+|-inf) dBFS", re.MULTILINE)


@dataclass(frozen=True)
class Loudness:
    """Integrated loudness and true peak.

    ``lufs`` is the integrated loudness; ``peak`` the true peak as a linear amplitude
    (1.0 = full scale), the form ReplayGain stores.
    """

    lufs: float
    peak: float


def measure_loudness(paths: list[Path], *, timeout: float = DEFAULT_TIMEOUT) -> Loudness:
    """Measures the loudness of ``paths`` played back to back: one file gives the track
    value and an album's files give the album value. The ``concat`` filter, unlike the
    demuxer, accepts files of different formats and needs no list file.

    Args:
        paths: Audio files, in order.
        timeout: Maximum seconds for ffmpeg.

    Returns:
        Integrated loudness and peak.

    Raises:
        AudioError: No files, missing or failing ffmpeg, or output without a measure.
    """
    if not paths:
        raise AudioError("nothing to measure")
    inputs = [arg for path in paths for arg in ("-i", str(path))]
    streams = "".join(f"[{index}:a]" for index in range(len(paths)))
    graph = f"{streams}concat=n={len(paths)}:v=0:a=1,ebur128=peak=true"
    cmd = ["ffmpeg", "-nostdin", "-nostats", *inputs, "-filter_complex", graph, "-f", "null", "-"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AudioError(str(exc)) from exc
    integrated = _INTEGRATED.findall(result.stderr)
    peak = _PEAK.findall(result.stderr)
    if result.returncode != 0 or not integrated or not peak:
        raise AudioError(f"cannot measure loudness: ffmpeg exited with {result.returncode}")
    return Loudness(lufs=float(integrated[-1]), peak=round(10 ** (float(peak[-1]) / 20), 6))


def replaygain(track: Loudness, album: Loudness | None) -> ReplayGain:
    """ReplayGain 2.0 of a track and, when known, of its album."""
    return ReplayGain(
        track_gain_db=REFERENCE_LUFS - track.lufs,
        track_peak=track.peak,
        album_gain_db=REFERENCE_LUFS - album.lufs if album else None,
        album_peak=album.peak if album else None,
    )
