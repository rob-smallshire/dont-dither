"""Properties of the canonical ink pattern table and its MODE 1 encodings.

These run without the emulator.
"""

import itertools

import pytest

from dontdither.gen_tables import superpixel_index
from dontdither.inks import (
    INKS,
    LOGICAL_COLOUR,
    InkTable,
    all_states,
    counts,
    cycle_inks,
    cycle_state,
    decode_superpixel,
    is_checkerboard,
    is_two_two,
    mode1_byte,
    mode1_pixels,
    pattern_rows_as_mode1_bytes,
    rotate_clockwise,
    translations,
)


@pytest.fixture(scope="module")
def table() -> InkTable:
    return InkTable.load()


def test_there_are_35_states():
    assert len(all_states()) == 35


def test_every_state_has_a_pattern_with_matching_counts(table):
    assert len(table.patterns) == 35
    for state, pattern in zip(table.states, table.patterns):
        assert counts(pattern) == state


def test_patterns_are_distinct(table):
    assert len(set(table.patterns)) == 35


def test_two_two_states_are_checkerboards(table):
    for state, pattern in zip(table.states, table.patterns):
        if is_two_two(state):
            assert is_checkerboard(pattern), (state, pattern)


def test_colour_cycling_is_clockwise_rotation_up_to_translation(table):
    for state, pattern in zip(table.states, table.patterns):
        image = table.pattern(cycle_state(state))
        assert image in translations(rotate_clockwise(cycle_inks(pattern))), (state, pattern, image)


def test_churn_is_the_proved_optimum(table):
    assert table.churn_histogram() == {1: 78, 2: 36, 3: 6, 4: 0}


def test_mode1_byte_round_trips():
    for colours in itertools.product(range(4), repeat=4):
        assert mode1_pixels(mode1_byte(list(colours))) == list(colours)


def test_mode1_leftmost_pixel_uses_bits_7_and_3():
    assert mode1_byte([3, 0, 0, 0]) == 0x88
    assert mode1_byte([0, 0, 0, 3]) == 0x11


@pytest.mark.parametrize("sx", [0, 1])
def test_decode_superpixel_recovers_every_pattern(table, sx):
    mask = 0xCC if sx % 2 == 0 else 0x33
    for pattern in table.patterns:
        top, bottom = pattern_rows_as_mode1_bytes(pattern)
        # Garbage in the neighbouring superpixel's half must not matter.
        assert decode_superpixel((top & mask) | (0x5A & ~mask), (bottom & mask) | (0xA5 & ~mask), sx) == pattern


@pytest.mark.parametrize("sx", [0, 1])
def test_6502_index_formula_matches_superpixel_index(table, sx):
    """The pattern_to_state index the 6502 computes from raster bytes."""
    for pattern in ("".join(p) for p in itertools.product(INKS, repeat=4)):
        top, bottom = pattern_rows_as_mode1_bytes(pattern)
        if sx % 2 == 0:
            index = (top & 0xCC) | ((bottom & 0xCC) >> 2)
        else:
            index = ((top & 0x33) << 2) | (bottom & 0x33)
        assert index == superpixel_index(pattern)


def test_superpixel_index_is_a_bijection():
    patterns = ["".join(p) for p in itertools.product(INKS, repeat=4)]
    assert sorted(superpixel_index(p) for p in patterns) == list(range(256))


def test_black_is_logical_colour_zero():
    assert LOGICAL_COLOUR["K"] == 0
