"""Player sprites: 12x12-pixel pictures in the player's ink and contrast ink.

A sprite file (sprites/*.spr) holds two pictures, facing E and NE; the other
six facings are exact clockwise quarter turns of them. Every player uses the
same pictures, told apart by colour: the 'p' pixels take the player's ink and
the 'o' pixels its contrast ink, so every sprite is two-tone and stays visible
over any texture, including its own colour.
"""

from __future__ import annotations

from pathlib import Path

from dontdither.inks import PROJECT_DIRPATH

SPRITES_DIRPATH = PROJECT_DIRPATH / "sprites"
TANK_FILEPATH = SPRITES_DIRPATH / "tank.spr"

SPRITE_PIXELS = 12
FACINGS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")   # clockwise from north

# The contrast ink drawn alongside each player's ink.
CONTRAST_INK = {"C": "K", "M": "K", "Y": "K", "K": "Y"}

PLAYER, CONTRAST, TRANSPARENT = "p", "o", "."

Picture = tuple[str, ...]   # SPRITE_PIXELS rows of SPRITE_PIXELS legend characters


class SpriteError(ValueError):
    pass


def parse_sprite(text: str, source: str = "<sprite>") -> dict[str, Picture]:
    """Parse the E and NE pictures from a sprite file."""
    pictures: dict[str, list[str]] = {}
    current = None
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line in ("E", "NE"):
            current = pictures.setdefault(line, [])
            continue
        if current is None:
            raise SpriteError(f"{source}:{number}: picture row before E or NE heading")
        if len(line) != SPRITE_PIXELS or set(line) - {PLAYER, CONTRAST, TRANSPARENT}:
            raise SpriteError(f"{source}:{number}: rows must be {SPRITE_PIXELS} of '.', 'p', 'o'")
        current.append(line)
    for facing in ("E", "NE"):
        rows = pictures.get(facing)
        if rows is None or len(rows) != SPRITE_PIXELS:
            raise SpriteError(f"{source}: facing {facing} needs {SPRITE_PIXELS} rows")
    return {facing: tuple(rows) for facing, rows in pictures.items()}


def rotate_clockwise(picture: Picture) -> Picture:
    n = len(picture)
    return tuple("".join(picture[n - 1 - x][y] for x in range(n)) for y in range(n))


def all_facings(pictures: dict[str, Picture]) -> dict[str, Picture]:
    """All eight facings: E and NE as drawn, the rest by quarter turns."""
    result = {}
    for base in ("E", "NE"):
        picture = pictures[base]
        index = FACINGS.index(base)
        for turn in range(4):
            result[FACINGS[(index + 2 * turn) % 8]] = picture
            picture = rotate_clockwise(picture)
    return {facing: result[facing] for facing in FACINGS}


def load_tank(filepath: Path = TANK_FILEPATH) -> dict[str, Picture]:
    return all_facings(parse_sprite(filepath.read_text(), filepath.name))


def coloured(picture: Picture, player_ink: str) -> dict[tuple[int, int], str]:
    """The picture's opaque pixels as {(x, y): ink} for one player."""
    ink = {PLAYER: player_ink, CONTRAST: CONTRAST_INK[player_ink]}
    return {
        (x, y): ink[ch]
        for y, row in enumerate(picture)
        for x, ch in enumerate(row)
        if ch != TRANSPARENT
    }
