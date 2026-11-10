"""Tests for tagging."""

import base64
from pathlib import Path

import mutagen
import pytest
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, TCOM
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus

from integrations.audio import AudioError, ReplayGain, Tags, convert, write_tags

JPEG = b"\xff\xd8\xff\xe0jpeg"
PNG = b"\x89PNG\r\n\x1a\npng"
FULL = Tags(
    title="La Fama",
    artists=("Rosalía", "The Weeknd"),
    album="Motomami",
    album_artists=("Rosalía", "Various"),
    track_number=3,
    track_total=12,
    disc_number=2,
    disc_total=2,
    year=2022,
    compilation=True,
    album_version="Deluxe Edition",
    release_type="album",
    explicit=True,
    cover=JPEG,
)
MINIMAL = Tags(title="Song", artists=("A",))
MP4_KEY = "----:com.apple.iTunes:"


def _make(wav: Path, tmp_path: Path, fmt: str) -> Path:
    return convert(wav, tmp_path, fmt, stem="t")


def _freeform(mp4: MP4, name: str) -> list[str]:
    return [bytes(value).decode("utf-8") for value in mp4[MP4_KEY + name]]


def test_mp3_full(wav: Path, tmp_path: Path) -> None:
    path = _make(wav, tmp_path, "mp3")
    write_tags(path, FULL)
    id3 = ID3(path)
    assert id3.version[:2] == (2, 4)
    assert id3["TIT2"].text == ["La Fama"]
    assert id3["TPE1"].text == ["Rosalía / The Weeknd"]
    assert id3["TXXX:ARTISTS"].text == ["Rosalía", "The Weeknd"]
    assert id3["TALB"].text == ["Motomami"]
    assert id3["TPE2"].text == ["Rosalía / Various"]
    # Sin espacio: Without a space: Navidrome ignores it.
    assert id3["TXXX:ALBUMARTISTS"].text == ["Rosalía", "Various"]
    assert id3["TRCK"].text == ["3/12"]
    assert id3["TPOS"].text == ["2/2"]
    assert str(id3["TDRL"].text[0]) == "2022"
    assert str(id3["TDRC"].text[0]) == "2022"
    assert id3["TCMP"].text == ["1"]
    assert id3["TXXX:ALBUMVERSION"].text == ["Deluxe Edition"]
    assert id3["TXXX:RELEASETYPE"].text == ["album"]
    assert id3["TXXX:ITUNESADVISORY"].text == ["1"]
    assert (id3["APIC:Cover"].mime, id3["APIC:Cover"].type, id3["APIC:Cover"].data) == (
        "image/jpeg",
        3,
        JPEG,
    )
    # UTF-8 in every text frame: some players misread UTF-16.
    assert {frame.encoding for frame in id3.values() if hasattr(frame, "encoding")} == {3}


def test_mp3_minimal_and_replaces_every_previous_tag(wav: Path, tmp_path: Path) -> None:
    path = _make(wav, tmp_path, "mp3")
    write_tags(path, FULL)
    id3 = ID3(path)
    id3.add(TCOM(encoding=3, text=["Old composer"]))
    id3.save()
    write_tags(path, Tags(title="Song", artists=("A",), track_number=4, cover=PNG))
    id3 = ID3(path)
    assert id3["APIC:Cover"].mime == "image/png"
    assert id3["TRCK"].text == ["4"]
    assert set(id3.keys()) == {"TIT2", "TPE1", "TXXX:ARTISTS", "TRCK", "APIC:Cover"}


@pytest.mark.parametrize("fmt", ["flac", "opus"])
def test_vorbis_full(wav: Path, tmp_path: Path, fmt: str) -> None:
    path = _make(wav, tmp_path, fmt)
    write_tags(path, FULL)
    tags = mutagen.File(path).tags
    assert {key: tags[key] for key in tags.keys() if key != "metadata_block_picture"} == {
        "title": ["La Fama"],
        "artist": ["Rosalía / The Weeknd"],
        "artists": ["Rosalía", "The Weeknd"],
        "album": ["Motomami"],
        "albumartist": ["Rosalía / Various"],
        "albumartists": ["Rosalía", "Various"],
        "tracknumber": ["3"],
        "tracktotal": ["12"],
        "discnumber": ["2"],
        "disctotal": ["2"],
        "releasedate": ["2022"],
        "date": ["2022"],
        "compilation": ["1"],
        "albumversion": ["Deluxe Edition"],
        "releasetype": ["album"],
        "itunesadvisory": ["1"],
    }


def test_flac_cover_and_minimal(wav: Path, tmp_path: Path) -> None:
    path = _make(wav, tmp_path, "flac")
    write_tags(path, FULL)
    flac = FLAC(path)
    assert (flac.pictures[0].mime, flac.pictures[0].type) == ("image/jpeg", 3)
    write_tags(path, MINIMAL)
    flac = FLAC(path)
    assert dict(flac) == {"title": ["Song"], "artist": ["A"], "artists": ["A"]}
    assert not flac.pictures


def test_opus_cover_and_minimal(wav: Path, tmp_path: Path) -> None:
    path = _make(wav, tmp_path, "opus")
    write_tags(path, FULL)
    picture = Picture(base64.b64decode(OggOpus(path)["metadata_block_picture"][0]))
    assert picture.data == JPEG
    write_tags(path, MINIMAL)
    assert "metadata_block_picture" not in OggOpus(path)


def test_m4a_full(wav: Path, tmp_path: Path) -> None:
    path = _make(wav, tmp_path, "m4a")
    write_tags(path, Tags(**{**FULL.__dict__, "cover": PNG}))
    mp4 = MP4(path)
    assert mp4["\xa9nam"] == ["La Fama"]
    assert mp4["\xa9ART"] == ["Rosalía / The Weeknd"]
    assert _freeform(mp4, "ARTISTS") == ["Rosalía", "The Weeknd"]
    assert mp4["\xa9alb"] == ["Motomami"]
    # m4a has no plural tag: Navidrome splits an aART that holds several values.
    assert mp4["aART"] == ["Rosalía", "Various"]
    assert mp4["trkn"] == [(3, 12)] and mp4["disk"] == [(2, 2)]
    assert mp4["\xa9day"] == ["2022"]
    assert mp4["cpil"] is True
    assert _freeform(mp4, "ALBUMVERSION") == ["Deluxe Edition"]
    assert mp4["rtng"] == [1]
    assert mp4["covr"][0].imageformat == mp4["covr"][0].FORMAT_PNG
    write_tags(path, Tags(**{**FULL.__dict__, "cover": JPEG}))
    assert MP4(path)["covr"][0].imageformat == MP4(path)["covr"][0].FORMAT_JPEG


def test_m4a_minimal(wav: Path, tmp_path: Path) -> None:
    path = _make(wav, tmp_path, "m4a")
    write_tags(path, FULL)
    write_tags(path, Tags(title="Song", artists=("A",), disc_number=1))
    mp4 = MP4(path)
    assert set(mp4.keys()) - {"\xa9too"} == {"\xa9nam", "\xa9ART", MP4_KEY + "ARTISTS", "disk"}
    assert mp4["disk"] == [(1, 0)]


def test_untagged_file_gets_tags_without_prior_header(wav: Path, tmp_path: Path) -> None:
    path = _make(wav, tmp_path, "mp3")
    ID3(path).delete()
    write_tags(path, MINIMAL)
    assert mutagen.File(path).tags["TIT2"].text == ["Song"]


def test_unsupported_extension(wav: Path) -> None:
    with pytest.raises(AudioError):
        write_tags(wav, MINIMAL)
    with pytest.raises(AudioError, match="without extension"):
        write_tags(wav.with_suffix(""), MINIMAL)


RG = ReplayGain(track_gain_db=-3.214, track_peak=0.98765432, album_gain_db=1.5, album_peak=0.5)
RG_FULL = Tags(title="Song", artists=("A",), replaygain=RG)
RG_TRACK = Tags(title="Song", artists=("A",), replaygain=ReplayGain(-8.3, 0.5))
RG_TEXT = {
    "replaygain_track_gain": "-3.21 dB",
    "replaygain_track_peak": "0.987654",
    "replaygain_album_gain": "1.50 dB",
    "replaygain_album_peak": "0.500000",
}


def test_flac_replaygain(wav: Path, tmp_path: Path) -> None:
    path = _make(wav, tmp_path, "flac")
    write_tags(path, RG_FULL)
    flac = FLAC(path)
    assert {key: flac[key] for key in RG_TEXT} == {key: [value] for key, value in RG_TEXT.items()}
    write_tags(path, RG_TRACK)
    flac = FLAC(path)
    assert (flac["replaygain_track_gain"], flac["replaygain_track_peak"]) == (
        ["-8.30 dB"],
        ["0.500000"],
    )
    assert "replaygain_album_gain" not in flac
    assert "replaygain_album_peak" not in flac


def test_opus_replaygain_is_r128_only(wav: Path, tmp_path: Path) -> None:
    path = _make(wav, tmp_path, "opus")
    write_tags(path, RG_FULL)
    opus = OggOpus(path)
    # Q7.8 relative to −23 LUFS (RFC 7845).
    assert opus["r128_track_gain"] == ["-2103"]
    assert opus["r128_album_gain"] == ["-896"]
    assert not [key for key in opus.keys() if key.startswith("replaygain")]
    write_tags(path, RG_TRACK)
    assert "r128_album_gain" not in OggOpus(path)


def test_mp3_replaygain(wav: Path, tmp_path: Path) -> None:
    path = _make(wav, tmp_path, "mp3")
    write_tags(path, RG_FULL)
    id3 = ID3(path)
    assert {key: id3[f"TXXX:{key.upper()}"].text for key in RG_TEXT} == {
        key: [value] for key, value in RG_TEXT.items()
    }
    write_tags(path, RG_TRACK)
    assert "TXXX:REPLAYGAIN_ALBUM_GAIN" not in ID3(path)


def test_m4a_replaygain(wav: Path, tmp_path: Path) -> None:
    path = _make(wav, tmp_path, "m4a")
    write_tags(path, RG_FULL)
    mp4 = MP4(path)
    assert {key: _freeform(mp4, key) for key in RG_TEXT} == {
        key: [value] for key, value in RG_TEXT.items()
    }
    write_tags(path, RG_TRACK)
    assert MP4_KEY + "replaygain_album_gain" not in MP4(path)


def test_no_replaygain_writes_none(wav: Path, tmp_path: Path) -> None:
    for fmt in ("flac", "opus", "mp3", "m4a"):
        path = _make(wav, tmp_path, fmt)
        write_tags(path, MINIMAL)
        keys = " ".join(mutagen.File(path).tags.keys()).lower()
        assert "replaygain" not in keys
        assert "r128" not in keys
