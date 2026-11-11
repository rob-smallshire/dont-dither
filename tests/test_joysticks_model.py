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
    FLAG_MESSAGES,
    SPITFIRE_TEXT,
    joystick_marker,
    spitfire_line,
    stick_slots,
    switch_channel,
    switch_direction,
)
from spitfire_config import (
    BITSTIK,
    DUAL,
    KIND_POSITION,
    SINGLE,
    TWIN,
    XY_READINGS,
    Joystick,
    SpitfireConfig,
    twins,
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


def line(config: SpitfireConfig) -> str:
    return spitfire_line(config.identify(), config.summary(), config.keyword)


def slots(config: SpitfireConfig) -> int:
    return stick_slots(config.identify(), config.summary(), config.describe)


def test_the_sticks_are_the_joysticks_a_game_plays_with():
    assert slots(SpitfireConfig()) == 0b1111
    assert slots(SpitfireConfig(joysticks=twins(2))) == 0b0011
    assert slots(SpitfireConfig(present=False)) == 0               # no SPItFIRE
    for flag in (1, 2, 4, 8):                                       # not ready
        assert slots(SpitfireConfig(flags=flag)) == 0
    position = Joystick(port=0, handset=0, type=BITSTIK, kind=KIND_POSITION, capabilities=XY_READINGS)
    assert slots(SpitfireConfig(joysticks=[position, *twins(2)[1:]])) == 0b0010
    no_directions = Joystick(port=0, handset=0, type=TWIN, capabilities=XY_READINGS)
    assert slots(SpitfireConfig(joysticks=[no_directions])) == 0


@pytest.mark.parametrize("config, expected", [
    (SpitfireConfig(present=False), ""),                            # not mentioned at all
    (SpitfireConfig(), "SPItFIRE: A 3BT J1 J2, B 3BT J3 J4"),
    (SpitfireConfig(joysticks=twins(2)), "SPItFIRE: A 3BT J1 J2"),
    (SpitfireConfig(joysticks=[*twins(2), Joystick(1, 0, SINGLE)]), "SPItFIRE: A 3BT J1 J2, B SINGLE J3"),
    (SpitfireConfig(joysticks=[Joystick(1, 0, SINGLE)]), "SPItFIRE: B SINGLE J1"),
    (SpitfireConfig(joysticks=[]), "SPItFIRE: no joysticks"),
    (SpitfireConfig(joysticks=[Joystick(0, 0, 40)]), "SPItFIRE: A ? J1"),
    (SpitfireConfig(flags=1), "SPItFIRE: press Ctrl-Break to start"),
    (SpitfireConfig(flags=2), "SPItFIRE: hardware not responding"),
    (SpitfireConfig(flags=4), "SPItFIRE: type *SPITFIRE JOYSTICK ON"),
    (SpitfireConfig(flags=8), "SPItFIRE: stopped: type *FX16,4"),
    (SpitfireConfig(flags=3), "SPItFIRE: press Ctrl-Break to start"),
    (SpitfireConfig(flags=12), "SPItFIRE: type *SPITFIRE JOYSTICK ON"),
], ids=["absent", "two-twins", "one-twin", "twin-and-single", "port-b-only", "none", "unknown-type",
        "ctrl-break", "not-answering", "handling-off", "updates-stopped", "flags-1-2", "flags-4-8"])
def test_the_title_screen_says_what_spitfire_gave(config, expected):
    assert line(config) == expected


def test_the_longest_spitfire_line_fits_from_column_4_to_the_last():
    duals = [Joystick(j // 2, j % 2, DUAL) for j in range(4)]
    text = line(SpitfireConfig(joysticks=duals))
    assert text == "SPItFIRE: A DUAL J1 J2, B DUAL J3 J4"
    assert 4 + len(text) <= 40
    for _, message in FLAG_MESSAGES:
        assert 4 + len(SPITFIRE_TEXT + message) <= 40, message


def test_players_keys_are_marked_with_their_joystick():
    assert [joystick_marker(slot) for slot in range(4)] == ["J1", "J2", "J3", "J4"]
