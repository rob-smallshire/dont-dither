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


# ---------------------------------------------------------------------------
# MODE 1 frames for the 6502
# ---------------------------------------------------------------------------
#
# A sprite at superpixel (sx, sy) covers pixel columns 2*sx .. 2*sx + 11 and
# raster lines 2*sy .. 2*sy + 11. Its first pixel falls 0 (even sx) or 2 (odd
# sx) pixels into screen byte column sx DIV 2, so every frame is stored 4
# bytes wide in two alignments. Each frame holds 48 mask bytes and 48 select
# bytes in drawing order: for each of the 6 superpixel rows, the top raster
# line's 4 bytes then the bottom raster line's 4 bytes. Mask pixels are all
# ones (logical colour 3) where the sprite is opaque; select pixels are all
# ones where it shows the player's ink rather than the contrast ink.

from dontdither.inks import LOGICAL_COLOUR, mode1_byte

FRAME_BYTES_WIDE = 4
FRAME_BYTES = 6 * 2 * FRAME_BYTES_WIDE          # 48 per plane


def frame_order() -> list[tuple[int, int]]:
    """(raster line within sprite, byte within line) for each frame index."""
    return [(row * 2 + half, byte) for row in range(6) for half in range(2) for byte in range(FRAME_BYTES_WIDE)]


def frame_planes(picture: Picture, alignment: int) -> tuple[bytes, bytes]:
    """The (mask, select) planes of a picture at alignment 0 (even sx) or 1."""
    offset = 2 * alignment
    mask, select = [], []
    for line, byte in frame_order():
        m, s = [], []
        for p in range(4):
            x = byte * 4 + p - offset
            ch = picture[line][x] if 0 <= x < SPRITE_PIXELS else TRANSPARENT
            m.append(3 if ch != TRANSPARENT else 0)
            s.append(3 if ch == PLAYER else 0)
        mask.append(mode1_byte(m))
        select.append(mode1_byte(s))
    return bytes(mask), bytes(select)


def draw_sprite_on_screen(screen: bytearray, sx: int, sy: int, picture: Picture, ink: str,
                          screen_base: int = 0x3000) -> None:
    """Model of the 6502 draw: composite a player's sprite into an image of
    MODE 1 screen memory (screen[0] is screen_base)."""
    from dontdither.screen import superpixel_address

    for (x, y), pixel_ink in coloured(picture, ink).items():
        px, line = 2 * sx + x, 2 * sy + y
        address = superpixel_address(px // 2, line // 2, screen_base) + (line % 2) - screen_base
        # superpixel_address gives the byte holding pixel columns 4*(px//4)..
        shift = px % 4
        colour = LOGICAL_COLOUR[pixel_ink]
        bits = ((colour >> 1) & 1) << (7 - shift) | (colour & 1) << (3 - shift)
        keep = ~((1 << (7 - shift)) | (1 << (3 - shift))) & 0xFF
        screen[address] = (screen[address] & keep) | bits
