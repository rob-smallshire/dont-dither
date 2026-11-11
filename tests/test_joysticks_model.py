"""Joystick readings to input bytes, and SPItFIRE detection
(tools/dontdither/joysticks.py). No emulator needed."""

import pytest

from dontdither.game import FIRE_BIT, NO_DIRECTION
from dontdither.joysticks import (
    FIRE_CHANNELS,
    FIRE_MASKS,
    X_CHANNELS,
    Y_CHANNELS,
    input_of_joystick,
    joysticks_available,
)

CENTRE, FULL = 0x8000, 0xFFFF
N, NE, E, SE, S, SW, W, NW = range(8)


@pytest.mark.parametrize("x, y, direction", [
    (CENTRE, CENTRE, NO_DIRECTION),
    (CENTRE, FULL, N),            # Y high is up
    (CENTRE, 0, S),
    (FULL, CENTRE, W),            # X high is left
    (0, CENTRE, E),
    (0, FULL, NE),
    (0, 0, SE),
    (FULL, 0, SW),
    (FULL, FULL, NW),
])
def test_stick_positions_give_directions(x, y, direction):
    assert input_of_joystick(x, y, False) == direction


def test_a_quarter_of_full_scale_from_the_centre_is_the_threshold():
    assert input_of_joystick(CENTRE, 0xBFFF, False) == NO_DIRECTION      # just short of up
    assert input_of_joystick(CENTRE, 0xC000, False) == N
    assert input_of_joystick(CENTRE, 0x4000, False) == NO_DIRECTION      # just short of down
    assert input_of_joystick(CENTRE, 0x3FFF, False) == S


def test_fire_adds_the_fire_bit():
    assert input_of_joystick(CENTRE, CENTRE, True) == NO_DIRECTION | FIRE_BIT
    assert input_of_joystick(0, CENTRE, True) == E | FIRE_BIT


def test_the_channel_map_is_spitfires():
    assert X_CHANNELS == (1, 3, 17, 19) and Y_CHANNELS == (2, 4, 18, 20)
    assert FIRE_CHANNELS == (0, 0, 16, 16) and FIRE_MASKS == (1, 2, 1, 2)


def block(signature=0x53, joysticks=4, flags=0):
    b = bytearray(16)
    b[0], b[4], b[10] = signature, joysticks, flags
    return bytes(b)


def test_detection():
    assert joysticks_available(block()) == 4
    assert joysticks_available(block(joysticks=2)) == 2
    assert joysticks_available(block(signature=0)) == 0          # no SPItFIRE: unchanged
    assert joysticks_available(block(flags=1)) == 0              # needs Ctrl-Break
    assert joysticks_available(block(flags=2)) == 0              # hardware not answering
