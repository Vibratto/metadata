"""The .deb version derived from a release tag."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "packaging" / "deb-version.sh"


def _version(tag: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), tag],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("tag", "expected"),
    [("v1.2.0", "1.2.0"), ("v1.2.0-rc.1", "1.2.0~rc.1"), ("v10.0.3-beta2", "10.0.3~beta2")],
)
def test_valid_tag_gives_a_debian_version(tag: str, expected: str) -> None:
    result = _version(tag)
    assert result.returncode == 0
    assert result.stdout.strip() == expected


@pytest.mark.parametrize(
    "tag", ["1.2.0", "v1.2", "v1.2.0foo", "v1.2.0-", "v1.2.0-rc_1", "v1.2.0-rc/1"]
)
def test_invalid_tag_fails_without_output(tag: str) -> None:
    result = _version(tag)
    assert result.returncode != 0
    assert result.stdout == ""


@pytest.mark.skipif(shutil.which("dpkg") is None, reason="dpkg is not installed")
def test_release_candidate_sorts_before_the_final_release() -> None:
    candidate, final = _version("v1.2.0-rc.1").stdout.strip(), _version("v1.2.0").stdout.strip()
    order = subprocess.run(  # noqa: S603
        ["dpkg", "--compare-versions", candidate, "lt", final],  # noqa: S607
        check=False,
    )
    assert order.returncode == 0
