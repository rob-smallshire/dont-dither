"""Level parsing, validation, symmetry and bytecode. No emulator needed."""

import pytest

from dontdither.inks import InkTable
from dontdither.levels import (
    FACINGS,
    LevelError,
    LevelOp,
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
MOVE 0 0
DRAW 3 0
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
    assert code[-1] == LevelOp.END


def test_minimal_level_parses():
    level = parse_level(MINIMAL)
    assert level.name == "TEST"
    assert level.symmetry is Symmetry.ROT4
    assert level.start == Start(10, 10, FACINGS.index("SE"))
    assert level.stored_cells() == [(0, 0), (1, 0), (2, 0), (3, 0)]


def test_rot4_repeats_four_times():
    cells = parse_level(MINIMAL).wall_cells()
    assert {(0, 0), (31, 0), (31, 31), (0, 31)} <= cells   # the corner cell, rotated
    assert len(cells) == 16


def test_rot2_repeats_twice():
    cells = parse_level(MINIMAL.replace("ROT4", "ROT2")).wall_cells()
    assert cells == {(0, 0), (1, 0), (2, 0), (3, 0), (31, 31), (30, 31), (29, 31), (28, 31)}


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
    text = MINIMAL.replace("MOVE 0 0\nDRAW 3 0", "") + bad
    with pytest.raises(LevelError, match=message):
        parse_level(text)


def test_missing_directives_are_rejected():
    with pytest.raises(LevelError, match="missing START"):
        parse_level(MINIMAL.replace("START 10 10 SE", ""))
