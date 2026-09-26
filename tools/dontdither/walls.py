"""Wall tiles: 8x8-pixel MODE 1 character cells drawn from a 32x32 wall map.

Walls are static and unpaintable. They live on the character-cell grid
(4x4 superpixels per cell), so the arena is a 32x32 grid of wall cells.
Which cells are walls is held in a 128-byte bitmap (one bit per cell), not
inferred from the screen.

A wall tile has a solid core and a one-pixel rim on every side that does not
join a neighbouring wall. A wall colouring is a (core, rim) pair of distinct
inks, chosen per level: 4 x 3 = 12 colourings. The rim is what marks a wall
out from solid territory of the core's ink, so rim and core must differ.

Tiles are stored as rim masks (rim pixels all ones, core pixels zero). The
screen byte for a mask byte m is
    core EOR ((core EOR rim) AND m)
taking rim pixels where m is set and core pixels elsewhere.

The tile for a cell is chosen by its 4-bit neighbour mask (N=1, E=2, S=4,
W=8). Where two joined arms meet at a corner whose diagonal neighbour is not
a wall (an inner corner), the corner pixel is set to the rim ink too, so
outlines stay continuous. Cells outside the arena count as walls.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple

from dontdither.inks import INKS, LOGICAL_COLOUR, mode1_byte

WALL_GRID_CELLS = 32
TILE_PIXELS = 8

NORTH, EAST, SOUTH, WEST = 1, 2, 4, 8
DIRECTIONS = {NORTH: (0, -1), EAST: (1, 0), SOUTH: (0, 1), WEST: (-1, 0)}

# Inner-corner patches: (arms that must both join, diagonal offset,
# tile byte offset, pixel mask within that byte). A tile's 16 bytes are the
# left byte column's 8 raster lines, then the right byte column's.
CORNERS = (
    (NORTH | WEST, (-1, -1), 0, 0x88),   # top-left pixel: left column, line 0, pixel 0
    (NORTH | EAST, (1, -1), 8, 0x11),    # top-right: right column, line 0, pixel 3
    (SOUTH | WEST, (-1, 1), 7, 0x88),    # bottom-left: left column, line 7, pixel 0
    (SOUTH | EAST, (1, 1), 15, 0x11),    # bottom-right: right column, line 7, pixel 3
)

WallCells = frozenset[tuple[int, int]]


class Colouring(NamedTuple):
    core: str
    rim: str


DEFAULT_COLOURING = Colouring(core="K", rim="Y")

# Every valid colouring, grouped by core ink in K, C, M, Y order.
COLOURINGS = tuple(
    Colouring(core, rim) for core in "KCMY" for rim in "KCMY" if rim != core
)


def check_colouring(colouring: Colouring) -> None:
    core, rim = colouring
    if core not in INKS or rim not in INKS:
        raise ValueError(f"Unknown ink in {colouring}")
    if core == rim:
        raise ValueError(f"Rim and core must differ, not both {core!r}")


def tile_inks(mask: int, colouring: Colouring = DEFAULT_COLOURING) -> list[list[str]]:
    """The 8x8 inks of the tile for a neighbour mask, indexed [y][x]."""
    check_colouring(colouring)
    rows = [[colouring.core] * TILE_PIXELS for _ in range(TILE_PIXELS)]
    last = TILE_PIXELS - 1
    for i in range(TILE_PIXELS):
        if not mask & NORTH:
            rows[0][i] = colouring.rim
        if not mask & SOUTH:
            rows[last][i] = colouring.rim
        if not mask & WEST:
            rows[i][0] = colouring.rim
        if not mask & EAST:
            rows[i][last] = colouring.rim
    return rows


def _encode(pixels: list[list[int]]) -> bytes:
    """Encode 8x8 logical colours as 16 screen bytes in character-cell order:
    the left byte column's 8 raster lines, then the right byte column's."""
    return bytes(
        mode1_byte(pixels[y][byte_column * 4:byte_column * 4 + 4])
        for byte_column in range(2)
        for y in range(TILE_PIXELS)
    )


def tile_bytes(inks: list[list[str]]) -> bytes:
    """Encode 8x8 inks as 16 screen bytes in character-cell order."""
    return _encode([[LOGICAL_COLOUR[c] for c in row] for row in inks])


def tile_rim_mask(mask: int) -> bytes:
    """The tile for a neighbour mask as 16 bytes with rim pixels all ones
    (logical colour 3) and core pixels zero."""
    shape = tile_inks(mask, Colouring(core="K", rim="C"))
    return _encode([[3 if ink == "C" else 0 for ink in row] for row in shape])


def full_byte(ink: str) -> int:
    """A screen byte with all four pixels in one ink."""
    return mode1_byte([LOGICAL_COLOUR[ink]] * 4)


def colour_tile_byte(mask_byte: int, colouring: Colouring) -> int:
    """What the 6502 draws for one rim-mask byte: core EOR ((core EOR rim) AND mask)."""
    core, rim = full_byte(colouring.core), full_byte(colouring.rim)
    return core ^ ((core ^ rim) & mask_byte)


def is_wall(cells: WallCells, cx: int, cy: int) -> bool:
    if not (0 <= cx < WALL_GRID_CELLS and 0 <= cy < WALL_GRID_CELLS):
        return True
    return (cx, cy) in cells


def neighbour_mask(cells: WallCells, cx: int, cy: int) -> int:
    return sum(bit for bit, (dx, dy) in DIRECTIONS.items() if is_wall(cells, cx + dx, cy + dy))


def render_wall_cell(
    cells: WallCells, cx: int, cy: int, colouring: Colouring = DEFAULT_COLOURING
) -> bytes:
    """The 16 screen bytes the renderer draws for wall cell (cx, cy)."""
    mask = neighbour_mask(cells, cx, cy)
    data = bytearray(tile_bytes(tile_inks(mask, colouring)))
    rim_byte = full_byte(colouring.rim)
    for arms, (dx, dy), offset, pixel_mask in CORNERS:
        if mask & arms == arms and not is_wall(cells, cx + dx, cy + dy):
            data[offset] = (data[offset] & ~pixel_mask & 0xFF) | (rim_byte & pixel_mask)
    return bytes(data)


def wall_bitmap(cells: Iterable[tuple[int, int]]) -> bytes:
    """Pack wall cells into 128 bytes: 4 bytes per row, most significant bit leftmost."""
    bitmap = bytearray(WALL_GRID_CELLS * WALL_GRID_CELLS // 8)
    for cx, cy in cells:
        bitmap[cy * 4 + cx // 8] |= 0x80 >> (cx % 8)
    return bytes(bitmap)
