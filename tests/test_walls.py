"""The wall tile model and the test card layout. No emulator needed."""

import pytest

from dontdither.inks import LOGICAL_COLOUR, mode1_pixels
from dontdither.testcard import (
    SWATCH_COLUMNS,
    state_at,
    swatch_states,
    wall_cells,
)
from dontdither.walls import (
    COLOURINGS,
    DEFAULT_COLOURING,
    EAST,
    NORTH,
    SOUTH,
    WEST,
    Colouring,
    colour_tile_byte,
    neighbour_mask,
    render_wall_cell,
    tile_bytes,
    tile_inks,
    tile_rim_mask,
    wall_bitmap,
)

CORE_INK, RIM_INK = DEFAULT_COLOURING

INK_OF_LOGICAL = {v: k for k, v in LOGICAL_COLOUR.items()}


def decode_tile(data: bytes) -> list[list[str]]:
    rows = []
    for y in range(8):
        pixels = mode1_pixels(data[y]) + mode1_pixels(data[8 + y])
        rows.append([INK_OF_LOGICAL[p] for p in pixels])
    return rows


@pytest.mark.parametrize("mask", range(16))
def test_tile_rim_is_on_exactly_the_unjoined_sides(mask):
    inks = tile_inks(mask)
    edges = {
        NORTH: [inks[0][i] for i in range(1, 7)],
        SOUTH: [inks[7][i] for i in range(1, 7)],
        WEST: [inks[i][0] for i in range(1, 7)],
        EAST: [inks[i][7] for i in range(1, 7)],
    }
    for side, pixels in edges.items():
        expected = CORE_INK if mask & side else RIM_INK
        assert set(pixels) == {expected}, (mask, side)
    assert {inks[y][x] for y in range(1, 7) for x in range(1, 7)} == {CORE_INK}


@pytest.mark.parametrize("mask", range(16))
def test_tile_bytes_decode_to_tile_inks(mask):
    assert decode_tile(tile_bytes(tile_inks(mask))) == tile_inks(mask)


def test_there_are_twelve_colourings():
    assert len(COLOURINGS) == len(set(COLOURINGS)) == 12
    assert all(c.core != c.rim for c in COLOURINGS)


@pytest.mark.parametrize("colouring", COLOURINGS)
@pytest.mark.parametrize("mask", range(16))
def test_rim_mask_colouring_draws_the_tile(mask, colouring):
    """What the 6502 does: core EOR ((core EOR rim) AND mask) per byte."""
    drawn = bytes(colour_tile_byte(m, colouring) for m in tile_rim_mask(mask))
    assert drawn == tile_bytes(tile_inks(mask, colouring))


@pytest.mark.parametrize("ink", "KCMY")
def test_rim_matching_core_is_rejected(ink):
    with pytest.raises(ValueError):
        tile_inks(0, Colouring(core=ink, rim=ink))


def test_inner_corner_is_patched_with_rim():
    # An L joining north and east, with the north-east diagonal open.
    cells = frozenset({(5, 5), (5, 4), (6, 5)})
    assert neighbour_mask(cells, 5, 5) == NORTH | EAST
    inks = decode_tile(render_wall_cell(cells, 5, 5))
    assert inks[0][7] == RIM_INK              # the inner corner
    assert inks[0][0] == RIM_INK              # west rim meets the top edge
    assert inks[0][6] == CORE_INK             # north side is joined


def test_no_inner_corner_when_diagonal_is_wall():
    cells = frozenset({(5, 5), (5, 4), (6, 5), (6, 4)})
    inks = decode_tile(render_wall_cell(cells, 5, 5))
    assert inks[0][7] == CORE_INK


def test_outside_the_arena_counts_as_wall():
    assert neighbour_mask(frozenset({(0, 0)}), 0, 0) == NORTH | WEST


def test_wall_bitmap_is_msb_first():
    bitmap = wall_bitmap([(0, 0), (9, 1), (31, 31)])
    assert bitmap[0] == 0x80
    assert bitmap[1 * 4 + 1] == 0x40
    assert bitmap[31 * 4 + 3] == 0x01
    assert len(bitmap) == 128


def test_testcard_shows_every_colouring_three_times():
    from collections import Counter

    from dontdither.testcard import cell_colouring

    features = {}
    for cx, cy in wall_cells():
        if cx not in (0, 31) and cy not in (0, 31):
            features[((cx - 1) // 5, (cy - 1) // 5)] = cell_colouring(cx, cy)
    assert Counter(features.values()) == {c: 3 for c in COLOURINGS}


def test_testcard_shows_every_ink_state():
    assert set(swatch_states()) == {state for state in swatch_states()}
    assert len(set(swatch_states())) == 35


def test_testcard_has_a_complete_border():
    cells = wall_cells()
    for i in range(32):
        assert {(i, 0), (i, 31), (0, i), (31, i)} <= cells


def test_testcard_features_stay_inside_their_swatches():
    # Feature walls never touch a swatch edge, so each swatch's ink region is
    # connected and every feature is surrounded by its own swatch's ink.
    for cx, cy in wall_cells():
        if cx in (0, 31) or cy in (0, 31):
            continue
        assert (cx - 1) % 5 in (1, 2, 3) and (cy - 1) % 5 in (1, 2, 3), (cx, cy)


def test_testcard_swatch_lookup_matches_layout():
    states = swatch_states()
    # Superpixel (6, 6) is in swatch (0, 0); superpixel 4 + 20*c + 10 is in column c.
    assert state_at(6, 6) == states[0]
    for column in range(SWATCH_COLUMNS):
        for row in range(SWATCH_COLUMNS):
            assert state_at(4 + 20 * column + 10, 4 + 20 * row + 10) == states[row * SWATCH_COLUMNS + column]
