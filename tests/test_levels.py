"""Level parsing, validation, symmetry and bytecode. No emulator needed."""

import pytest

from dontdither.inks import InkTable
from dontdither.levels import (
    FACINGS,
    DRAW_BIT,
    END,
    HEADER_SIZE,
    LevelError,
    border_cells,
    Start,
    Symmetry,
    level_filepaths,
    line_cells,
    load_levels,
    parse_level,
    rotate_cell,
    rotate_start,
)

MINIMAL = """
NAME TEST
SYMMETRY ROT4
WALLS K Y
START 10 10 SE
MOVE 2 3
DRAW 5 3
"""


def test_there_are_levels():
    assert level_filepaths()


@pytest.mark.parametrize("level", load_levels(), ids=lambda lv: lv.name)
def test_walls_have_the_level_symmetry(level):
    cells = level.wall_cells()
    turns = level.symmetry.value
    assert {rotate_cell(c, turns) for c in cells} == cells


@pytest.mark.parametrize("level", load_levels(), ids=lambda lv: lv.name)
def test_starts_are_symmetric_and_open(level):
    starts = level.starts()
    assert len(starts) == level.symmetry.copies
    cells = level.wall_cells()
    for start in starts:
        footprint = {((start.sx + dx) // 4, (start.sy + dy) // 4) for dx in range(6) for dy in range(6)}
        assert not footprint & cells, f"start {start} overlaps a wall"


@pytest.mark.parametrize("level", load_levels(), ids=lambda lv: lv.name)
def test_bytecode_fits_and_ends(level):
    code = level.bytecode(InkTable.load())
    assert len(code) <= 255
    assert code[-1] == END and END not in code[HEADER_SIZE:-1]


def test_minimal_level_parses():
    level = parse_level(MINIMAL)
    assert level.name == "TEST"
    assert level.symmetry is Symmetry.ROT4
    assert level.start == Start(10, 10, FACINGS.index("SE"))
    assert level.stored_cells() == [(2, 3), (3, 3), (4, 3), (5, 3)]


def inside(cells):
    return cells - border_cells()


def test_every_level_has_a_border():
    assert border_cells() <= parse_level(MINIMAL).wall_cells()
    assert len(border_cells()) == 4 * 31


def test_rot4_repeats_four_times():
    cells = inside(parse_level(MINIMAL).wall_cells())
    assert {(2, 3), (28, 2), (29, 28), (3, 29)} <= cells   # the first cell, rotated
    assert len(cells) == 16


def test_rot2_repeats_twice():
    cells = inside(parse_level(MINIMAL.replace("ROT4", "ROT2")).wall_cells())
    assert cells == {(2, 3), (3, 3), (4, 3), (5, 3), (29, 28), (28, 28), (27, 28), (26, 28)}


def test_commands_take_two_bytes_with_the_draw_bit_in_cx():
    code = parse_level(MINIMAL).bytecode(InkTable.load())
    assert code[HEADER_SIZE:] == bytes([2, 3, 5 | DRAW_BIT, 3, END])


def test_quarter_turn_is_clockwise_about_the_centre():
    assert rotate_cell((0, 0), 1) == (31, 0)
    assert rotate_cell((31, 0), 1) == (31, 31)
    assert rotate_cell((5, 7), 4) == (5, 7)


def test_start_rotation_keeps_the_footprint_top_left():
    # A footprint at the top-left corner, rotated clockwise, sits at the
    # top-right corner; facing turns by two eighths.
    assert rotate_start(Start(0, 0, 0), 1) == Start(122, 0, 2)


def test_line_cells_run_both_ways():
    assert line_cells((3, 5), (1, 5)) == [(3, 5), (2, 5), (1, 5)]
    assert line_cells((4, 4), (4, 4)) == [(4, 4)]


@pytest.mark.parametrize("bad, message", [
    ("MOVE 0 0\nDRAW 3 3", "not horizontal or vertical"),
    ("DRAW 3 0", "DRAW before any MOVE"),
    ("MOVE 32 0", "0..31"),
    ("WALLS K K", "must differ"),
    ("FILL 1 1 1 0", "summing to 4"),
    ("BOGUS 1", "Unknown directive"),
])
def test_invalid_levels_are_rejected(bad, message):
    text = MINIMAL.replace("MOVE 2 3\nDRAW 5 3", "") + bad
    with pytest.raises(LevelError, match=message):
        parse_level(text)


def test_missing_directives_are_rejected():
    with pytest.raises(LevelError, match="missing START"):
        parse_level(MINIMAL.replace("START 10 10 SE", ""))


# A tank's footprint plus two superpixels' clearance on each side: every gap
# must let a tank through with room to steer, not merely squeeze past.
REACH_FOOTPRINT = 6 + 2 * 2


def reachable_cells(level, footprint: int) -> set[tuple[int, int]]:
    """Open wall-grid cells covered by some position a tank of the given
    footprint can reach, by axial steps, from any player's start."""
    walls = level.wall_cells()
    limit = 128 - footprint

    def clear(x: int, y: int) -> bool:
        return 0 <= x <= limit and 0 <= y <= limit and not any(
            (cx, cy) in walls
            for cy in range(y // 4, (y + footprint - 1) // 4 + 1)
            for cx in range(x // 4, (x + footprint - 1) // 4 + 1))

    # Start from any position of the enlarged footprint that encloses a
    # player's (real) start footprint.
    spare = footprint - 6
    frontier = [(s.sx - dx, s.sy - dy) for s in level.starts()
                for dx in range(spare + 1) for dy in range(spare + 1)]
    seen = set()
    while frontier:
        x, y = frontier.pop()
        if (x, y) in seen or not clear(x, y):
            continue
        seen.add((x, y))
        frontier += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return {((x + dx) // 4, (y + dy) // 4)
            for x, y in seen for dx in range(footprint) for dy in range(footprint)}


@pytest.mark.parametrize("level", load_levels(), ids=lambda lv: lv.name)
def test_every_open_cell_is_reachable_with_room_to_spare(level):
    walls = level.wall_cells()
    open_cells = {(x, y) for x in range(32) for y in range(32)} - walls
    unreachable = open_cells - reachable_cells(level, REACH_FOOTPRINT)
    assert not unreachable, f"unreachable cells: {sorted(unreachable)}"
