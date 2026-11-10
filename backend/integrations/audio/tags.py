"""Audio tags with mutagen."""

import base64
from dataclasses import dataclass
from pathlib import Path

from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC,
    ID3,
    TALB,
    TCMP,
    TDRC,
    TDRL,
    TIT2,
    TPE1,
    TPE2,
    TPOS,
    TRCK,
    TXXX,
    ID3v1SaveOptions,
)
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
from mutagen.oggopus import OggOpus

from .errors import AudioError

_PNG = b"\x89PNG\r\n\x1a\n"
_ITUNES = "----:com.apple.iTunes:"


@dataclass(frozen=True)
class ReplayGain:
    """ReplayGain gain and peak."""

    track_gain_db: float
    track_peak: float
    album_gain_db: float | None = None
    album_peak: float | None = None


@dataclass(frozen=True)
class Tags:
    """Tags of a track.

    Tuples of artists and MBIDs keep the catalogue's credit order. ``joiner`` joins
    several names into the single display text.
    """

    title: str
    artists: tuple[str, ...]
    album: str | None = None
    track_number: int | None = None
    disc_number: int | None = None
    year: int | None = None
    cover: bytes | None = None  # JPEG or PNG
    album_artists: tuple[str, ...] = ()
    track_total: int | None = None
    disc_total: int | None = None
    compilation: bool = False
    release_type: str | None = None
    explicit: bool = False
    album_version: str | None = None
    replaygain: ReplayGain | None = None
    joiner: str = " / "

    def joined(self, names: tuple[str, ...]) -> str:
        """Names joined into one display text."""
        return self.joiner.join(names)

    @property
    def date_text(self) -> str | None:
        """Release date as players expect it; YouTube Music only gives the year."""
        return str(self.year) if self.year else None


def _of(number: int | None, total: int | None) -> str:
    """ID3 ``n/total``, or just ``n`` without one."""
    return f"{number}/{total}" if total else str(number)


def _mime(cover: bytes) -> str:
    return "image/png" if cover.startswith(_PNG) else "image/jpeg"


def _picture(cover: bytes) -> Picture:
    picture = Picture()
    picture.type = 3  # portada frontal / front cover
    picture.mime = _mime(cover)
    picture.data = cover
    return picture


def _replaygain_text(gain: ReplayGain | None) -> dict[str, str]:
    """Lower-case ``replaygain_*`` fields; only those with a value."""
    if gain is None:
        return {}
    fields = {
        "replaygain_track_gain": f"{gain.track_gain_db:.2f} dB",
        "replaygain_track_peak": f"{gain.track_peak:.6f}",
    }
    if gain.album_gain_db is not None and gain.album_peak is not None:
        fields["replaygain_album_gain"] = f"{gain.album_gain_db:.2f} dB"
        fields["replaygain_album_peak"] = f"{gain.album_peak:.6f}"
    return fields


def _r128(gain_db: float) -> str:
    """Opus gain: Q7.8 relative to −23 LUFS, 5 dB below the ReplayGain reference."""
    return str(round((gain_db - 5) * 256))


def _vorbis(tags: Tags) -> dict[str, list[str]]:
    """Vorbis comment fields.

    Single display texts plus the plural tags with one value per artist, which is
    what lets Navidrome split artists whatever the joiner is.
    """
    date = [tags.date_text] if tags.date_text else []
    fields = {
        "title": [tags.title],
        "artist": [tags.joined(tags.artists)] if tags.artists else [],
        "artists": list(tags.artists),
        "album": [tags.album] if tags.album else [],
        "albumartist": [tags.joined(tags.album_artists)] if tags.album_artists else [],
        "albumartists": list(tags.album_artists),
        "tracknumber": [str(tags.track_number)] if tags.track_number else [],
        "tracktotal": [str(tags.track_total)] if tags.track_total else [],
        "discnumber": [str(tags.disc_number)] if tags.disc_number else [],
        "disctotal": [str(tags.disc_total)] if tags.disc_total else [],
        # Navidrome reads DATE as the recording date; RELEASEDATE gives the release date.
        "releasedate": date,
        "date": date,
        "compilation": ["1"] if tags.compilation else [],
        "albumversion": [tags.album_version] if tags.album_version else [],
        "releasetype": [tags.release_type] if tags.release_type else [],
        "itunesadvisory": ["1"] if tags.explicit else [],
    }
    return {key: value for key, value in fields.items() if value}


def _write_mp3(path: Path, tags: Tags) -> None:
    # A fresh tag replaces the old one whole, as in the other formats.
    id3 = ID3()
    id3.add(TIT2(encoding=3, text=[tags.title]))
    if tags.artists:
        id3.add(TPE1(encoding=3, text=[tags.joined(tags.artists)]))
        id3.add(TXXX(encoding=3, desc="ARTISTS", text=list(tags.artists)))
    if tags.album:
        id3.add(TALB(encoding=3, text=[tags.album]))
    if tags.album_artists:
        id3.add(TPE2(encoding=3, text=[tags.joined(tags.album_artists)]))
        # Sin espacio: Navidrome ignores the spaced form.
        id3.add(TXXX(encoding=3, desc="ALBUMARTISTS", text=list(tags.album_artists)))
    if tags.track_number:
        id3.add(TRCK(encoding=3, text=[_of(tags.track_number, tags.track_total)]))
    if tags.disc_number:
        id3.add(TPOS(encoding=3, text=[_of(tags.disc_number, tags.disc_total)]))
    if tags.date_text:
        id3.add(TDRL(encoding=3, text=[tags.date_text]))
        id3.add(TDRC(encoding=3, text=[tags.date_text]))
    if tags.compilation:
        id3.add(TCMP(encoding=3, text=["1"]))
    if tags.album_version:
        id3.add(TXXX(encoding=3, desc="ALBUMVERSION", text=[tags.album_version]))
    if tags.release_type:
        id3.add(TXXX(encoding=3, desc="RELEASETYPE", text=[tags.release_type]))
    if tags.explicit:
        id3.add(TXXX(encoding=3, desc="ITUNESADVISORY", text=["1"]))
    for key, value in _replaygain_text(tags.replaygain).items():
        id3.add(TXXX(encoding=3, desc=key.upper(), text=[value]))
    if tags.cover:
        id3.add(APIC(encoding=3, mime=_mime(tags.cover), type=3, desc="Cover", data=tags.cover))
    id3.save(path, v1=ID3v1SaveOptions.REMOVE)


def _write_flac(path: Path, tags: Tags) -> None:
    flac = FLAC(path)
    flac.clear()
    flac.clear_pictures()
    flac.update(_vorbis(tags))
    flac.update({key: [value] for key, value in _replaygain_text(tags.replaygain).items()})
    if tags.cover:
        flac.add_picture(_picture(tags.cover))
    flac.save()


def _write_opus(path: Path, tags: Tags) -> None:
    opus = OggOpus(path)
    opus.clear()
    opus.update(_vorbis(tags))
    # Opus carries R128, not REPLAYGAIN_*: the decoder already applies its own gain.
    if tags.replaygain:
        opus["r128_track_gain"] = [_r128(tags.replaygain.track_gain_db)]
        if tags.replaygain.album_gain_db is not None:
            opus["r128_album_gain"] = [_r128(tags.replaygain.album_gain_db)]
    if tags.cover:
        # Ogg has no picture block: it travels base64-encoded inside a comment.
        opus["metadata_block_picture"] = [
            base64.b64encode(_picture(tags.cover).write()).decode("ascii")
        ]
    opus.save()


def _freeform(*values: str) -> list[MP4FreeForm]:
    return [MP4FreeForm(value.encode("utf-8")) for value in values]


def _write_m4a(path: Path, tags: Tags) -> None:
    mp4 = MP4(path)
    mp4.clear()
    mp4["\xa9nam"] = [tags.title]
    if tags.artists:
        mp4["\xa9ART"] = [tags.joined(tags.artists)]
        mp4[_ITUNES + "ARTISTS"] = _freeform(*tags.artists)
    if tags.album:
        mp4["\xa9alb"] = [tags.album]
    if tags.album_artists:
        # m4a has no plural tag: Navidrome splits a multi-valued aART.
        mp4["aART"] = list(tags.album_artists)
    if tags.track_number:
        mp4["trkn"] = [(tags.track_number, tags.track_total or 0)]
    if tags.disc_number:
        mp4["disk"] = [(tags.disc_number, tags.disc_total or 0)]
    if tags.date_text:
        mp4["\xa9day"] = [tags.date_text]
    if tags.compilation:
        mp4["cpil"] = True
    if tags.album_version:
        mp4[_ITUNES + "ALBUMVERSION"] = _freeform(tags.album_version)
    if tags.release_type:
        mp4[_ITUNES + "MusicBrainz Album Type"] = _freeform(tags.release_type)
    if tags.explicit:
        mp4["rtng"] = [1]  # explicit
    for key, value in _replaygain_text(tags.replaygain).items():
        mp4[_ITUNES + key] = _freeform(value)
    if tags.cover:
        fmt = MP4Cover.FORMAT_PNG if tags.cover.startswith(_PNG) else MP4Cover.FORMAT_JPEG
        mp4["covr"] = [MP4Cover(tags.cover, imageformat=fmt)]
    mp4.save()


_WRITERS = {".mp3": _write_mp3, ".flac": _write_flac, ".opus": _write_opus, ".m4a": _write_m4a}


def write_tags(path: Path, tags: Tags) -> None:
    """Replaces the file's tags with ``tags``.

    Args:
        path: An mp3, flac, opus or m4a file.
        tags: Tags to write.

    Raises:
        AudioError: Unsupported extension.
    """
    writer = _WRITERS.get(path.suffix.lower())
    if writer is None:
        raise AudioError(f"cannot tag {path.suffix or 'a file without extension'}")
    writer(path, tags)
