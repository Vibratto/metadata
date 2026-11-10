"""Where downloads live on disk."""

from pathlib import Path
from typing import Any

import pytest

from catalog.services.library import absolute, download_folder
from preferences.models import Preference

pytestmark = pytest.mark.django_db


def test_relative_folder_hangs_from_the_data_folder(settings: Any, tmp_path: Path) -> None:
    settings.DATA_DIR = tmp_path
    Preference.objects.create(key="download.folder", value="music")
    assert download_folder() == tmp_path / "music"
    assert absolute("artist/album/1.mp3") == tmp_path / "music" / "artist" / "album" / "1.mp3"


def test_absolute_folder_is_used_as_is(settings: Any, tmp_path: Path) -> None:
    settings.DATA_DIR = tmp_path / "data"
    Preference.objects.create(key="download.folder", value=str(tmp_path / "elsewhere"))
    assert download_folder() == tmp_path / "elsewhere"
