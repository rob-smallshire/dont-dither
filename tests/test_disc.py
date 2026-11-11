"""The disc images: named for the version, and saying it in their catalogues
(tools/dontdither/disc_files.py, tools/dontdither/build.py).
"""

import pytest

from dontdither._version import __version__
from dontdither.build import ADFS_DISC_FILEPATH, DISC_FILEPATH
from dontdither.disc_files import (
    LICENSE_FILENAME,
    README_FILENAME,
    acorn_text,
    adfs_title,
    disc_filename,
    license_text,
    readme_text,
    version_filename,
    version_text,
    README_WIDTH,
)


@pytest.fixture
def bbc(launch_bbc):
    return launch_bbc()


# ---- The model ---------------------------------------------------------------------

def test_the_images_are_named_for_the_version():
    assert disc_filename(".ssd", "0.2.0") == "dont-dither-v0.2.0.ssd"
    assert DISC_FILEPATH.name == f"dont-dither-v{__version__}.ssd"
    assert ADFS_DISC_FILEPATH.name == f"dont-dither-v{__version__}.adl"


@pytest.mark.parametrize("version, name", [
    ("0.2.0", "0_2_0"),
    ("1.12.3", "1_12_3"),
    ("10.11.12", "v101112"),        # x_y_z would be 8 characters: zero-padded
    ("0.12.13", "0_12_13"),         # just fits
])
def test_the_version_file_is_named_for_the_version(version, name):
    assert version_filename(version) == name
    assert len(name) <= 7 and "." not in name


def test_a_version_too_long_to_name_is_refused():
    with pytest.raises(ValueError):
        version_filename("100.100.0")   # 9 characters, or v1001000: 8


def test_the_readme_points_to_the_repository_and_the_licence():
    text = readme_text()
    assert "github.com/rob-smallshire/dont-dither" in text and "*TYPE LICENSE" in text


def test_the_adfs_title_is_the_game_and_its_version():
    assert adfs_title("0.2.0") == "Don't Dither! 0.2.0"
    assert len(adfs_title("10.11.12")) <= 19


def test_the_readme_fits_a_mode_7_line():
    for line in readme_text().splitlines():
        assert len(line) <= README_WIDTH, line


def test_text_is_acorn_text():
    assert acorn_text("A\nB\n") == b"A\rB\r"


# ---- The images --------------------------------------------------------------------

def dfs_files(disc_filepath):
    from oaknut.dfs.dfs import DFS

    with DFS.from_file(disc_filepath, read_only=True) as dfs:
        return dfs.title, {p.path.split(".", 1)[1]: p.read_bytes() for p in (dfs.root / "$").iterdir()}


def adfs_files(disc_filepath):
    from oaknut.adfs import ADFS

    with ADFS.from_file(disc_filepath, read_only=True) as adfs:
        return adfs.title, {p.path.split(".", 1)[1]: p.read_bytes() for p in adfs.root.iterdir()}


def test_both_discs_carry_the_version_file_the_readme_and_the_licence(game_build):
    _, dfs = dfs_files(DISC_FILEPATH)
    title, adfs = adfs_files(ADFS_DISC_FILEPATH)
    assert dfs[version_filename()] == acorn_text(version_text())
    assert dfs[README_FILENAME] == acorn_text(readme_text())
    assert dfs[LICENSE_FILENAME] == acorn_text(license_text())
    assert b"MIT License" in dfs[LICENSE_FILENAME]
    assert title == adfs_title()
    assert {name.upper(): data for name, data in adfs.items()} == \
        {name.upper(): data for name, data in dfs.items()}      # the same files


def mode_7(text: str) -> str:
    """Text as Beebium reads it back from the MODE 7 screen: the MOS stores
    "_" as &60 (which the teletext chip shows as a long dash), read back as
    "`"."""
    return text.replace("_", "`")


def test_star_cat_shows_the_version_and_star_type_says_it(bbc, game_build):
    """On the machine, from BASIC: *CAT lists the version file, the README
    and the LICENSE; *TYPE of the version file gives the version in full."""
    bbc.expect("BASIC")
    bbc.disc.drive(0).insert(str(game_build.disc_filepath))
    bbc.keyboard.type("*CAT")
    bbc.keyboard.press_return()
    bbc.run_for_emulated_seconds(3.0)
    text = bbc.video.screen_text().text
    assert "Don't Dither" in text
    for name in (version_filename(), README_FILENAME, LICENSE_FILENAME):
        assert mode_7(name) in text, name
    bbc.keyboard.type(f"*TYPE {version_filename()}")
    bbc.keyboard.press_return()
    bbc.run_for_emulated_seconds(3.0)
    assert f"Don't Dither! version {__version__}" in bbc.video.screen_text().text
