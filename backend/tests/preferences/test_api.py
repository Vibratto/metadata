"""Settings API tests."""

from collections.abc import Iterator

import pytest
from rest_framework.test import APIClient

from activity.models import ActivityLog
from preferences.defaults import DEFAULTS
from preferences.models import Preference

pytestmark = pytest.mark.django_db

URL = "/api/v1/preferences/"


@pytest.fixture
def declared(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Declares two test settings."""
    monkeypatch.setitem(DEFAULTS, "demo.flag", True)
    monkeypatch.setitem(DEFAULTS, "demo.count", 3)
    yield


def test_anonymous_is_forbidden(declared: None) -> None:
    assert APIClient().get(URL).status_code == 403


def test_list_shows_defaults_until_overridden(api: APIClient, declared: None) -> None:
    rows = {row["key"]: row for row in api.get(URL).json()}
    assert rows["demo.flag"] == {"key": "demo.flag", "value": True, "default": True}
    assert rows["demo.count"]["value"] == 3


def test_unknown_key_is_404(api: APIClient, declared: None) -> None:
    assert api.get(f"{URL}no.existe/").status_code == 404
    assert api.put(f"{URL}no.existe/", {"value": 1}, format="json").status_code == 404


def test_put_changes_value_and_logs_it(api: APIClient, declared: None) -> None:
    response = api.put(f"{URL}demo.count/", {"value": 7}, format="json")
    assert response.status_code == 200
    assert response.json()["value"] == 7
    assert api.get(f"{URL}demo.count/").json()["value"] == 7
    assert ActivityLog.objects.filter(action="preferences.updated").exists()


def test_second_put_updates_the_same_row(api: APIClient, declared: None) -> None:
    api.put(f"{URL}demo.count/", {"value": 1}, format="json")
    api.put(f"{URL}demo.count/", {"value": 2}, format="json")
    assert Preference.objects.filter(key="demo.count").count() == 1
    assert api.get(f"{URL}demo.count/").json()["value"] == 2


@pytest.mark.parametrize(
    "value",
    ["siete", True, 1.5, None, [1]],
)
def test_put_rejects_a_different_type(api: APIClient, declared: None, value: object) -> None:
    response = api.put(f"{URL}demo.count/", {"value": value}, format="json")
    assert response.status_code == 400
    assert Preference.objects.filter(key="demo.count").count() == 0


def test_put_accepts_a_bool_for_a_bool_setting(api: APIClient, declared: None) -> None:
    response = api.put(f"{URL}demo.flag/", {"value": False}, format="json")
    assert response.status_code == 200
    assert response.json()["value"] is False


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("download.format", "wma"),
        ("download.name_template", "{artist}/{desconocido}"),
        ("download.name_template", "{artist"),
        ("download.name_template", "/"),
        # Each folder must hold a single album.
        ("download.name_template", "{year}/{title}"),
        ("download.name_template", "{albumartist}/{disc}-{track}-{title}"),
        ("download.name_template", "{album}"),
        # The name must tell tracks apart.
        ("download.name_template", "{albumartist}/{album}/{year}"),
        ("download.name_template", "{album}/{artist}"),
        # Meets the rule but cannot be filled.
        ("download.name_template", "{album}/{desconocido}-{title}"),
        ("download.name_template", "{album}/{title"),
    ],
)
def test_put_rejects_values_downloads_cannot_use(api: APIClient, key: str, value: str) -> None:
    """A value that would break every download is refused when it is saved."""
    response = api.put(f"{URL}{key}/", {"value": value}, format="json")
    assert response.status_code == 400
    assert not Preference.objects.filter(key=key).exists()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("download.format", "flac"),
        ("download.name_template", "{albumartist}/{album}/{disc}-{track}-{title}"),
        ("download.name_template", "{year}/{album}/{title}"),
        ("download.name_template", "{album}/{track}"),
        ("download.name_template", "{artist}/{year} {album}/{disc}{track}"),
    ],
)
def test_put_accepts_valid_download_values(api: APIClient, key: str, value: str) -> None:
    assert api.put(f"{URL}{key}/", {"value": value}, format="json").status_code == 200


def test_cover_is_not_embedded_by_default(api: APIClient) -> None:
    """The cover is stored once as cover.jpg; embedding it is opt-in."""
    values = {item["key"]: item for item in api.get(URL).json()}
    assert values["tags.embed_cover"]["value"] is False
    assert api.put(f"{URL}tags.embed_cover/", {"value": True}, format="json").status_code == 200


SEPARATORS = "tags.artist_separators"


def test_artist_separators_default_to_navidromes(api: APIClient) -> None:
    row = api.get(f"{URL}{SEPARATORS}/").json()
    assert row["value"] == [" / ", " feat. ", " feat ", " ft. ", " ft ", "; "]


@pytest.mark.parametrize(
    "value",
    [
        [],
        [""],
        ["   "],
        ["/", "/"],
        [1],
        [" / ", None],
        ["x" * 11],
        [f"{n}" for n in range(21)],
        " / ",
    ],
)
def test_put_rejects_invalid_artist_separators(api: APIClient, value: object) -> None:
    response = api.put(f"{URL}{SEPARATORS}/", {"value": value}, format="json")
    assert response.status_code == 400
    assert not Preference.objects.filter(key=SEPARATORS).exists()


def test_put_keeps_the_spaces_around_each_separator(api: APIClient) -> None:
    value = ["; ", "/", " / ", "x" * 10, *(f"<{n}>" for n in range(16))]
    response = api.put(f"{URL}{SEPARATORS}/", {"value": value}, format="json")
    assert response.status_code == 200
    assert Preference.objects.get(key=SEPARATORS).value == value


def test_lyrics_are_looked_up_by_default(api: APIClient) -> None:
    values = {item["key"]: item for item in api.get(URL).json()}
    assert values["lyrics.enabled"]["value"] is True
    assert api.put(f"{URL}lyrics.enabled/", {"value": False}, format="json").status_code == 200
