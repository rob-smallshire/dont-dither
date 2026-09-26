"""Layout of the texture and wall test card.

The arena is bordered by walls (character cells 0 and 31). Inside, cells
1..30 hold a 6x6 grid of swatches, each 5x5 character cells (20x20
superpixels). Rows group the ink states by partition family, and within a
row states follow the colour cycle C->M->Y->K:

    row 0     the four solids, then (1,1,1,1) twice (the last is a spare)
    rows 1-2  3+1 states
    row 3     2+2 states
    rows 4-5  2+1+1 states

Every swatch contains a wall feature that does not touch the swatch edge, so
every texture is seen against walls. The feature depends on the column:
pillar, horizontal bar, vertical bar, L, T, cross. The L and T are rotated by
the row number, to show different orientations.

Swatch i's feature uses wall colouring COLOURINGS[i mod 12], so each of the
12 (core, rim) colourings appears three times, against different textures.
The border uses DEFAULT_COLOURING.
"""

from __future__ import annotations

from dontdither.inks import State, all_states, cycle_state
from dontdither.walls import COLOURINGS, DEFAULT_COLOURING, WALL_GRID_CELLS, Colouring, WallCells

BORDER_COLOURING = DEFAULT_COLOURING

SWATCH_COLUMNS = 6
SWATCH_ROWS = 6
SWATCH_CELLS = 5            # character cells per swatch side
SWATCH_ORIGIN_CELL = 1      # first cell inside the border
SUPERPIXELS_PER_CELL = 4


def _orbit(state: State) -> list[State]:
    orbit = [state]
    while (nxt := cycle_state(orbit[-1])) != state:
        orbit.append(nxt)
    return orbit


def _family_in_cycle_order(partition: list[int]) -> list[State]:
    remaining = [s for s in all_states() if sorted(s, reverse=True)[:len(partition)] == partition
                 and sum(1 for v in s if v) == len(partition)]
    ordered: list[State] = []
    for s in sorted(remaining, reverse=True):
        if s not in ordered:
            ordered.extend(o for o in _orbit(s) if o not in ordered)
    return ordered


def swatch_states() -> list[State]:
    """The ink state of each swatch, row-major (36 entries)."""
    solids = _family_in_cycle_order([4])
    four_way = (1, 1, 1, 1)
    states = (
        solids + [four_way, four_way]
        + _family_in_cycle_order([3, 1])
        + _family_in_cycle_order([2, 2])
        + _family_in_cycle_order([2, 1, 1])
    )
    assert len(states) == SWATCH_COLUMNS * SWATCH_ROWS
    return states


def swatch_index_of_superpixel(coordinate: int) -> int:
    """The swatch column (or row) containing a superpixel column (or row).

    Superpixels in the border cells are clamped to the nearest swatch; walls
    cover them anyway.
    """
    cell = coordinate // SUPERPIXELS_PER_CELL
    return min(max((cell - SWATCH_ORIGIN_CELL) // SWATCH_CELLS, 0), SWATCH_COLUMNS - 1)


def state_at(sx: int, sy: int) -> State:
    return swatch_states()[swatch_index_of_superpixel(sy) * SWATCH_COLUMNS + swatch_index_of_superpixel(sx)]


def _rotate(offset: tuple[int, int], quarter_turns: int) -> tuple[int, int]:
    dx, dy = offset
    for _ in range(quarter_turns % 4):
        dx, dy = -dy, dx   # clockwise with y pointing down
    return dx, dy


def _feature(column: int, row: int) -> list[tuple[int, int]]:
    """Wall cells of a swatch's feature, relative to the swatch centre."""
    north, east, south, west = (0, -1), (1, 0), (0, 1), (-1, 0)
    if column == 0:
        return [(0, 0)]
    if column == 1:
        return [west, (0, 0), east]
    if column == 2:
        return [north, (0, 0), south]
    if column == 3:
        return [(0, 0)] + [_rotate(arm, row) for arm in (north, east)]
    if column == 4:
        return [(0, 0)] + [_rotate(arm, row) for arm in (west, north, east)]
    return [(0, 0), north, east, south, west]


def wall_cells() -> WallCells:
    cells = set()
    last = WALL_GRID_CELLS - 1
    for i in range(WALL_GRID_CELLS):
        cells.update({(i, 0), (i, last), (0, i), (last, i)})
    for row in range(SWATCH_ROWS):
        for column in range(SWATCH_COLUMNS):
            centre_x = SWATCH_ORIGIN_CELL + column * SWATCH_CELLS + SWATCH_CELLS // 2
            centre_y = SWATCH_ORIGIN_CELL + row * SWATCH_CELLS + SWATCH_CELLS // 2
            cells.update((centre_x + dx, centre_y + dy) for dx, dy in _feature(column, row))
    return frozenset(cells)


def swatch_colouring(index: int) -> Colouring:
    """The wall colouring of swatch `index`'s feature."""
    return COLOURINGS[index % len(COLOURINGS)]


def swatch_origin_cell(index: int) -> tuple[int, int]:
    """Top-left character cell of swatch `index`."""
    row, column = divmod(index, SWATCH_COLUMNS)
    return SWATCH_ORIGIN_CELL + column * SWATCH_CELLS, SWATCH_ORIGIN_CELL + row * SWATCH_CELLS


def cell_colouring(cx: int, cy: int) -> Colouring:
    """The colouring the test card draws wall cell (cx, cy) in."""
    last = WALL_GRID_CELLS - 1
    if cx in (0, last) or cy in (0, last):
        return BORDER_COLOURING
    column = (cx - SWATCH_ORIGIN_CELL) // SWATCH_CELLS
    row = (cy - SWATCH_ORIGIN_CELL) // SWATCH_CELLS
    return swatch_colouring(row * SWATCH_COLUMNS + column)
