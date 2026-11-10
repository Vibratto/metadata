"""Tests for portable file names."""

import re
from pathlib import PurePosixPath

import pytest

from integrations.audio import DEFAULT_TEMPLATE, PathIds, Tags, render_path, slug

TAGS = Tags(
    title="La Fama",
    artists=("Rosalía", "The Weeknd"),
    album="MOTOMAMI",
    album_artists=("Rosalía",),
    track_number=2,
    disc_number=1,
    year=2022,
)
IDS = PathIds(track=1002, album=100, artist=27, album_artist=27)
PORTABLE = re.compile(r"^[a-z0-9._/-]+$")


@pytest.mark.parametrize(
    ("text", "ident", "expected"),
    [
        ("Rosalía", 27, "rosalia-27"),
        ("君の名は。", 103, "103"),
        ("AC/DC", 9, "ac-dc-9"),
        ("  ¿Qué?  ", 1, "que-1"),
        ("Ærøskøbing", 2, "rskbing-2"),
        ("ﬁnal", 3, "final-3"),
        ("🎷🎷", 4, "4"),
        ("", 5, "5"),
    ],
)
def test_slug(text: str, ident: int, expected: str) -> None:
    assert slug(text, ident) == expected


def test_slug_is_the_same_for_nfc_and_nfd() -> None:
    assert slug("Rosalía", 27) == slug("Rosalía", 27)


def test_slug_cuts_the_text_at_60_characters_and_never_ends_in_a_dash() -> None:
    assert slug("a" * 70, 1) == "a" * 60 + "-1"
    assert slug("a" * 59 + " b", 1) == "a" * 59 + "-1"


def test_default_template() -> None:
    assert render_path(DEFAULT_TEMPLATE, TAGS, IDS, "opus") == PurePosixPath(
        "rosalia-27/motomami-100/01-02-la-fama-1002.opus"
    )


def test_artist_year_and_two_digit_numbers() -> None:
    tags = Tags(title="T", artists=("B", "C"), album="Al", track_number=12, disc_number=3,
                year=1999)  # fmt: skip
    ids = PathIds(track=5, album=6, artist=7, album_artist=8)
    assert render_path("{year}/{artist}/{album}/{disc}{track} {title}", tags, ids, "mp3") == (
        PurePosixPath("1999/b-7/al-6/0312-t-5.mp3")
    )


def test_album_artist_falls_back_to_the_first_artist() -> None:
    tags = Tags(title="T", artists=("B",), album="Al")
    ids = PathIds(track=5, album=6, artist=7, album_artist=None)
    assert render_path(DEFAULT_TEMPLATE, tags, ids, "mp3") == PurePosixPath("b-7/al-6/t-5.mp3")


def test_missing_numbers_leave_no_stray_dashes() -> None:
    tags = Tags(title="T", artists=("B",), album="Al", album_artists=("B",))
    assert render_path(DEFAULT_TEMPLATE, tags, IDS, "mp3").name == "t-1002.mp3"
    assert render_path("{album}/{year}-{title}", tags, IDS, "mp3").name == "t-1002.mp3"


def test_non_latin_names_keep_only_the_id() -> None:
    tags = Tags(title="夜に駆ける", artists=("YOASOBI",), album="THE BOOK",
                album_artists=("YOASOBI",), track_number=1)  # fmt: skip
    assert render_path(DEFAULT_TEMPLATE, tags, IDS, "flac") == PurePosixPath(
        "yoasobi-27/the-book-100/01-1002.flac"
    )


@pytest.mark.parametrize(
    "tags",
    [
        Tags(title="../../etc/passwd", artists=("AC/DC",), album=".."),
        Tags(title="Ça. ¡Sí!", artists=("Ñandú",), album="Ølé / Ñ"),
        Tags(title="名", artists=("名",), album="名"),
    ],
)
def test_every_path_is_portable_and_stays_inside(tags: Tags) -> None:
    for template in (DEFAULT_TEMPLATE, "{artist}/{album}/{title}", "Mis Discos/{album}/{title}"):
        path = render_path(template, tags, IDS, "mp3")
        assert PORTABLE.match(str(path)), path
        assert ".." not in path.parts and not path.is_absolute()


def test_literal_text_in_the_template_is_made_portable_too() -> None:
    path = render_path("Mis Discos/{album}/{track} - {title}", TAGS, IDS, "mp3")
    assert path == PurePosixPath("mis-discos/motomami-100/02-la-fama-1002.mp3")


def test_a_segment_left_empty_is_an_error() -> None:
    with pytest.raises(ValueError, match="empty"):
        render_path("{album}/{year}", Tags(title="T", artists=("A",)), IDS, "mp3")


def test_unknown_placeholder() -> None:
    with pytest.raises(KeyError):
        render_path("{nope}", TAGS, IDS, "mp3")
