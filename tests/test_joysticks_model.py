"""Joystick readings to input bytes, and SPItFIRE detection
(tools/dontdither/joysticks.py). No emulator needed."""

import pytest

from dontdither.controls import LAYOUT_KEYS
from dontdither.game import FIRE_BIT, NO_DIRECTION, direction_of_keys
from dontdither.joysticks import (
    SWITCH_CHANNELS,
    SWITCH_DOWN,
    SWITCH_FIRE,
    SWITCH_LEFT,
    SWITCH_RIGHT,
    SWITCH_UP,
    input_of_switch_byte,
    joystick_marker,
    joysticks_available,
    spitfire_line,
    switch_channel,
    switch_direction,
)

N, NE, E, SE, S, SW, W, NW = range(8)


@pytest.mark.parametrize("switches, direction", [
    (0, NO_DIRECTION),
    (SWITCH_UP, N),
    (SWITCH_UP | SWITCH_RIGHT, NE),
    (SWITCH_RIGHT, E),
    (SWITCH_DOWN | SWITCH_RIGHT, SE),
    (SWITCH_DOWN, S),
    (SWITCH_DOWN | SWITCH_LEFT, SW),
    (SWITCH_LEFT, W),
    (SWITCH_UP | SWITCH_LEFT, NW),
])
def test_switch_bytes_give_directions(switches, direction):
    assert input_of_switch_byte(switches) == direction


def test_the_switch_bits_are_spitfires():
    """Fire in bit 0; left, down, up, right in bits 4-7 (the guide's
    "Switch bytes")."""
    assert (SWITCH_FIRE, SWITCH_LEFT, SWITCH_DOWN, SWITCH_UP, SWITCH_RIGHT) == (1, 16, 32, 64, 128)


def test_fire_adds_the_fire_bit():
    assert input_of_switch_byte(SWITCH_FIRE) == NO_DIRECTION | FIRE_BIT
    assert input_of_switch_byte(SWITCH_RIGHT | SWITCH_FIRE) == E | FIRE_BIT


def test_a_joystick_steers_as_the_keys_do():
    """Each switch direction bit means what the matching key does, so any
    combination -- even opposite directions -- gives the keys' direction."""
    key_bit = {name: 1 << i for i, name in enumerate(LAYOUT_KEYS[:4])}     # the keys' mask
    switch_bit = {"up": SWITCH_UP, "down": SWITCH_DOWN, "left": SWITCH_LEFT, "right": SWITCH_RIGHT}
    for mask in range(16):
        switches = sum(switch_bit[k] for k in key_bit if mask & key_bit[k])
        assert input_of_switch_byte(switches) == direction_of_keys(mask)
        assert switch_direction()[switches >> 4] == direction_of_keys(mask)


def test_bits_1_to_3_are_ignored():
    for bits in (2, 4, 8, 14):
        assert input_of_switch_byte(SWITCH_UP | bits) == N


def test_the_channel_map_is_spitfires():
    assert SWITCH_CHANNELS == (12, 28)
    assert [switch_channel(slot) for slot in range(4)] == [(12, 0), (12, 1), (28, 0), (28, 1)]


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
    (block(signature=0), ""),     # not mentioned at all
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
