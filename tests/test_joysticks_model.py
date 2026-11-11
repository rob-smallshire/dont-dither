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
    joystick_marker,
    joysticks_available,
    spitfire_line,
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


TWIN, SINGLE, DUAL = 4, 1, 2           # port types
PORT_B = 0x80


def block(signature=0x53, joysticks=4, flags=0, sticks=None):
    """An OSWORD &3F block as it comes back; sticks: joysticks 1-4's bytes
    (port and type), by default two Delta 3B Twins."""
    if sticks is None:
        sticks = [TWIN, TWIN, PORT_B | TWIN, PORT_B | TWIN][:joysticks]
    b = bytearray(16)
    b[0], b[4], b[10] = signature, joysticks, flags
    b[6:10] = bytes(sticks) + bytes([0xFF] * (4 - len(sticks)))
    return bytes(b)


def test_detection():
    assert joysticks_available(block()) == 4
    assert joysticks_available(block(joysticks=2)) == 2
    assert joysticks_available(block(signature=0)) == 0          # no SPItFIRE: unchanged
    assert joysticks_available(block(flags=1)) == 0              # needs Ctrl-Break
    assert joysticks_available(block(flags=2)) == 0              # hardware not answering


@pytest.mark.parametrize("found, line", [
    (block(signature=0), "No SPItFIRE: keyboard only"),
    (block(), "SPItFIRE: A 3BT J1 J2, B 3BT J3 J4"),
    (block(joysticks=2), "SPItFIRE: A 3BT J1 J2"),
    (block(joysticks=3, sticks=[TWIN, TWIN, PORT_B | SINGLE]), "SPItFIRE: A 3BT J1 J2, B SINGLE J3"),
    (block(joysticks=1, sticks=[PORT_B | SINGLE]), "SPItFIRE: B SINGLE J1"),
    (block(joysticks=0), "SPItFIRE: no joysticks"),
    (block(joysticks=0, flags=1), "SPItFIRE: press Ctrl-Break to start"),
    (block(joysticks=0, flags=2), "SPItFIRE: hardware not responding"),
    (block(joysticks=0, flags=3), "SPItFIRE: press Ctrl-Break to start"),
], ids=["absent", "two-twins", "one-twin", "twin-and-single", "port-b-only", "none",
        "ctrl-break", "not-answering", "both-flags"])
def test_the_title_screen_says_what_spitfire_gave(found, line):
    assert spitfire_line(found) == line


def test_the_longest_spitfire_line_fits_from_column_4_to_the_last():
    line = spitfire_line(block(sticks=[DUAL, DUAL, PORT_B | DUAL, PORT_B | DUAL]))
    assert line == "SPItFIRE: A DUAL J1 J2, B DUAL J3 J4"
    assert 4 + len(line) <= 40


def test_players_keys_are_marked_with_their_joystick():
    assert [joystick_marker(slot) for slot in range(4)] == ["J1", "J2", "J3", "J4"]
