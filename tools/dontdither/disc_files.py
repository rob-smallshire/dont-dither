"""What the disc images say about themselves: their names, titles and the
two small text files that make the version evident from a *CAT.

- The images are named for the version: dont-dither-v0.2.0.ssd and .adl.
- The DFS title is DFS_TITLE (DFS allows 12 characters, too few for the
  version too); the ADFS disc's root directory title, which ADFS's *CAT
  shows first, is "Don't Dither! 0.2.0" (19 characters, ADFS's limit),
  losing the "!", then the "'", then the space, as two-digit version
  components need the room (adfs_title).
- A file named for the version, version_filename(): "0_2_0" (an Acorn
  name has no dots), or, if that would not fit DFS's seven characters,
  zero-padded "v001203" (for 0.12.3). *TYPE it for the version in full.
- README: what the game is and how to play, short enough lines for a
  40-column *TYPE, and where it comes from: its GitHub repository.
- LICENSE: the project's licence (the repository's LICENSE file).

Text is in the Acorn character set (oaknut's "acorn" codec), lines ending
with CR, as *TYPE expects.
"""

from __future__ import annotations

from dontdither._version import __version__

DISC_FILENAME_STEM = "dont-dither"
DFS_TITLE = "Don't Dither"          # 12 characters: DFS's limit
DFS_NAME_LIMIT = 7
ADFS_TITLE_LIMIT = 19
README_FILENAME = "README"
LICENSE_FILENAME = "LICENSE"
README_WIDTH = 39                   # characters: a MODE 7 line, short of wrapping
PROJECT_URL = "github.com/rob-smallshire/dont-dither"   # 37 characters: fits a line


def disc_filename(suffix: str, version: str = __version__) -> str:
    """The disc image's file name, e.g. dont-dither-v0.2.0.ssd."""
    return f"{DISC_FILENAME_STEM}-v{version}{suffix}"


def version_parts(version: str = __version__) -> tuple[int, int, int]:
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch


def version_filename(version: str = __version__) -> str:
    """The name of the file that carries the version: "x_y_z", or, if that
    is longer than a DFS name may be, "vXXYYZZ"."""
    major, minor, patch = version_parts(version)
    name = f"{major}_{minor}_{patch}"
    if len(name) > DFS_NAME_LIMIT:
        name = f"v{major:02}{minor:02}{patch:02}"
    if len(name) > DFS_NAME_LIMIT:
        raise ValueError(f"version {version} has no DFS file name")
    return name


# The game's name, losing its punctuation a step at a time to make room
# for longer versions in a title: one two-digit component, then two, then
# three.
TITLE_NAMES = ("Don't Dither!", "Don't Dither", "Dont Dither", "DontDither")


def adfs_title(version: str = __version__) -> str:
    """The ADFS root directory title: the game and its version, in the
    first form of the name that leaves room for the version."""
    for name in TITLE_NAMES:
        title = f"{name} {version}"
        if len(title) <= ADFS_TITLE_LIMIT:
            return title
    raise ValueError(f"version {version} does not fit an ADFS title")


def version_text(version: str = __version__) -> str:
    return f"Don't Dither! version {version}\n{PROJECT_URL}\n"


def readme_text(version: str = __version__) -> str:
    """The README file's text."""
    from dontdither.gen_tables import key_line

    lines = [
        f"Don't Dither! {version}",
        "",
        "A paint-the-arena game for two or four",
        "players on a BBC Micro Model B or a",
        "Master Compact. Source code, releases",
        "and the latest version are on GitHub:",
        f"  {PROJECT_URL}",
        "",
        "SHIFT-BREAK to start. On the title",
        "screen choose 2 or 4 players, then",
        "press fire to join. If nobody joins,",
        "the computer plays a demo.",
        "",
        "Keys (f1-f4 on the title screen",
        "change them):",
        *(f"  {key_line(ink)}" for ink in "CMYK"),
        "",
        "Joysticks: on a Master Compact with",
        "SPItFIRE, press a joystick's fire",
        "button to join with it.",
        "",
        "Firing uses ink. Release fire on your",
        "own colour to refill and speed up.",
        "",
        "Hold ESCAPE to end a game.",
        "",
        "Free software under the MIT licence:",
        "*TYPE LICENSE. Report problems at",
        f"  {PROJECT_URL}",
    ]
    return "\n".join(lines) + "\n"


def license_text() -> str:
    """The project's licence, as in the repository."""
    from dontdither.inks import PROJECT_DIRPATH

    return (PROJECT_DIRPATH / "LICENSE").read_text()


def acorn_text(text: str) -> bytes:
    """Text as an Acorn machine reads it: the Acorn character set, lines
    ending with CR."""
    import oaknut.codecs  # noqa: F401  (registers the "acorn" codec)

    return text.replace("\n", "\r").encode("acorn")
