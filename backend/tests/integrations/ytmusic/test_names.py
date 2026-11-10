"""Credit and "feat." rules."""

import pytest

from integrations.ytmusic.models import ArtistRef
from integrations.ytmusic.names import merge_artists, split_featured


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Plain Song", ("Plain Song", ())),
        ("Song (feat. Ana)", ("Song", ("Ana",))),
        ("Song [ft. Ana & Luis]", ("Song", ("Ana", "Luis"))),
        ("Song (Featuring Ana, Luis and Eva)", ("Song", ("Ana", "Luis", "Eva"))),
        ("Song (feat. Ana) (Live)", ("Song (Live)", ("Ana",))),
        ("Song (Remastered)", ("Song (Remastered)", ())),
        ("Song feat. Ana", ("Song feat. Ana", ())),
    ],
)
def test_split_featured(title: str, expected: tuple[str, tuple[str, ...]]) -> None:
    assert split_featured(title) == expected


def test_merge_keeps_order_and_drops_case_insensitive_duplicates() -> None:
    merged = merge_artists([ArtistRef("Ana", "UC1"), ArtistRef("Luis")], [ArtistRef("ANA")])
    assert merged == (ArtistRef("Ana", "UC1"), ArtistRef("Luis"))


def test_merge_prefers_the_credit_that_has_an_id() -> None:
    merged = merge_artists([ArtistRef("Ana")], [ArtistRef("ana", "UC1")])
    assert merged == (ArtistRef("ana", "UC1"),)
