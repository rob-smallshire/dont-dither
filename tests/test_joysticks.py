"""Joysticks through SPItFIRE, on the machine.

Beebium emulates neither the Master Compact nor SPItFIRE, so these tests run
the game on a Model B with a fake SPItFIRE (tests/fake_spitfire.asm): a
sideways ROM in slot 13 answering OSWORD &3F reasons 0-3, as SPItFIRE's
does, and a hook answering OSBYTE &80 on channels 12 and 28 with the
joysticks' switch bytes. Its configuration (tests/spitfire_config.py) lives
in main RAM; the tests write it as the title screen starts, before anything
asks SPItFIRE, then move the sticks and press the buttons by poking the
switch bytes.
"""

import random
import subprocess

import pytest

from conftest import boot_game, load_game, step_ticks, to_title
from dontdither.build import BUILD_DIRPATH, PROJECT_DIRPATH, find_beebasm, parse_labels
from dontdither.game import Game
from dontdither.gen_tables import key_line
from dontdither.joysticks import (
    SWITCH_DOWN,
    SWITCH_FIRE,
    SWITCH_LEFT,
    SWITCH_RIGHT,
    SWITCH_UP,
    input_of_switch_byte,
    joystick_marker,
    spitfire_line,
    stick_slots,
)
from dontdither.levels import level_set
from spitfire_config import (
    BITSTIK,
    DIRECTIONS,
    KIND_POSITION,
    NONE,
    SINGLE,
    TWIN,
    XY_READINGS,
    Joystick,
    SpitfireConfig,
    names_source,
    twins,
)

CONTROL_KEYS, CONTROL_JOYSTICK, CONTROL_SCRIPTED = 1, 2, 3
BYTEV = 0x020A
FAKE_SLOT = 13
FAKE_SOURCE_FILEPATH = PROJECT_DIRPATH / "tests" / "fake_spitfire.asm"
FAKE_NAMES_FILEPATH = BUILD_DIRPATH / "fake_spitfire_names.asm"
FAKE_HOOK_FILEPATH = BUILD_DIRPATH / "fake_spitfire_hook.bin"
FAKE_ROM_FILEPATH = BUILD_DIRPATH / "fake_spitfire.rom"
FAKE_LABELS_FILEPATH = BUILD_DIRPATH / "labels" / "FAKE_SPITFIRE.txt"
SCREENSHOT_DIRPATH = BUILD_DIRPATH / "screenshots"


@pytest.fixture(scope="session")
def fake():
    """The fake SPItFIRE, assembled: (its hook's bytes, its labels). The ROM
    is at FAKE_ROM_FILEPATH."""
    FAKE_LABELS_FILEPATH.parent.mkdir(parents=True, exist_ok=True)
    FAKE_NAMES_FILEPATH.write_text(names_source())
    subprocess.run([find_beebasm(), "-i", str(FAKE_SOURCE_FILEPATH.relative_to(PROJECT_DIRPATH)),
                    "-d", "-labels", str(FAKE_LABELS_FILEPATH.relative_to(PROJECT_DIRPATH))],
                   cwd=PROJECT_DIRPATH, check=True, capture_output=True)
    return FAKE_HOOK_FILEPATH.read_bytes(), parse_labels(FAKE_LABELS_FILEPATH.read_text())


@pytest.fixture
def bbc(launch_bbc, fake):
    """A Model B with the fake SPItFIRE's ROM in slot 13 -- silent, as if
    absent, until a test configures it."""
    return launch_bbc(extra_args=("--sideways", f"slot={FAKE_SLOT}:type=rom:image={FAKE_ROM_FILEPATH}"))


class FakeSpitfire:
    """Drives the fake in a machine."""

    def __init__(self, bbc, labels):
        self.bbc, self.labels = bbc, labels

    def switches(self, joystick: int, value: int) -> None:
        """Joystick 0-3's switch byte (fire bit 0, directions bits 4-7)."""
        self.bbc.memory.address.bus[self.labels["cfg_switches"] + joystick] = value

    def fire(self, joystick: int, held: bool) -> None:
        address = self.labels["cfg_switches"] + joystick
        bus, peek = self.bbc.memory.address.bus, self.bbc.memory.address.peek
        bus[address] = (peek[address] | SWITCH_FIRE) if held else (peek[address] & ~SWITCH_FIRE & 0xFF)


def installer(fake, config: SpitfireConfig | None = None):
    """A function configuring the fake SPItFIRE (by default two Delta 3B
    Twins; sticks centred and buttons up) in a machine and hooking BYTEV;
    for to_title's, load_game's and boot_game's at_title."""
    hook, labels = fake
    config = config or SpitfireConfig()

    def install(bbc):
        bus, peek = bbc.memory.address.bus, bbc.memory.address.peek
        ram = config.ram()
        bus[labels["cfg_present"]:labels["cfg_present"] + len(ram)] = ram
        bus[labels["cfg_switches"]:labels["cfg_switches"] + 4] = bytes(4)
        bus[labels["byte_hook"]:labels["byte_hook"] + len(hook)] = hook
        bus[labels["cfg_old_bytev"]:labels["cfg_old_bytev"] + 2] = bytes(peek[BYTEV:BYTEV + 2])
        bus[BYTEV:BYTEV + 2] = labels["byte_hook"].to_bytes(2, "little")

    return install


def expected_slots(config: SpitfireConfig) -> int:
    return stick_slots(config.identify(), config.summary(), config.describe)


# Configurations, by name.
CONFIGS = {
    "two-twins": SpitfireConfig(),
    "one-twin": SpitfireConfig(port_types=(TWIN, NONE), joysticks=twins(2)),
    "twin-and-single": SpitfireConfig(port_types=(TWIN, SINGLE),
                                      joysticks=[*twins(2), Joystick(port=1, handset=0, type=SINGLE)]),
    "port-b-only": SpitfireConfig(port_types=(NONE, SINGLE), joysticks=[Joystick(port=1, handset=0, type=SINGLE)]),
    "none": SpitfireConfig(port_types=(NONE, NONE), joysticks=[]),
    "bitstik-and-twin": SpitfireConfig(port_types=(BITSTIK, TWIN), joysticks=[
        # (A position device whose switch byte had directions would still
        # not be a stick: the kind decides.)
        Joystick(port=0, handset=0, type=BITSTIK, kind=KIND_POSITION, capabilities=XY_READINGS | DIRECTIONS),
        Joystick(port=0, handset=1, type=BITSTIK, kind=3, capabilities=0),
        Joystick(port=1, handset=0, type=TWIN), Joystick(port=1, handset=1, type=TWIN)]),
    "stick-without-directions": SpitfireConfig(port_types=(TWIN, NONE), joysticks=[
        Joystick(port=0, handset=0, type=TWIN, capabilities=XY_READINGS), Joystick(port=0, handset=1, type=TWIN)]),
    "unknown-type": SpitfireConfig(port_types=(9, NONE), joysticks=[Joystick(port=0, handset=0, type=9)]),
    "ctrl-break": SpitfireConfig(flags=1),
    "not-answering": SpitfireConfig(flags=2),
    "handling-off": SpitfireConfig(flags=4),
    "updates-stopped": SpitfireConfig(flags=8),
}


# ---- Detection ---------------------------------------------------------------------

def test_without_spitfire_there_are_no_joysticks(bbc, game_build):
    labels = load_game(bbc, game_build)
    assert bbc.memory.address.peek[labels["joystick_slots"]] == 0


@pytest.mark.parametrize("name", CONFIGS)
def test_the_game_plays_with_spitfires_sticks(bbc, game_build, fake, name):
    config = CONFIGS[name]
    labels = load_game(bbc, game_build, at_title=installer(fake, config))
    assert bbc.memory.address.peek[labels["joystick_slots"]] == expected_slots(config)


def test_the_expected_slots_are_the_sticks():
    """(The model, for the cases above.)"""
    assert expected_slots(CONFIGS["two-twins"]) == 0b1111
    assert expected_slots(CONFIGS["twin-and-single"]) == 0b0111
    assert expected_slots(CONFIGS["bitstik-and-twin"]) == 0b1100
    assert expected_slots(CONFIGS["stick-without-directions"]) == 0b0010
    assert all(expected_slots(CONFIGS[n]) == 0 for n in ("none", "ctrl-break", "not-answering",
                                                         "handling-off", "updates-stopped"))


# ---- The title screen -------------------------------------------------------------

TITLE_SECONDS = 0.1


def title_lines(bbc) -> list[str]:
    bbc.run_for_emulated_seconds(TITLE_SECONDS)
    return bbc.video.screen_text().text.splitlines()


def test_without_spitfire_the_title_screen_does_not_mention_it(bbc, game_build):
    to_title(bbc, game_build)
    lines = title_lines(bbc)
    assert not any("SPItFIRE" in line for line in lines)
    assert not any("J1" in line for line in lines)


@pytest.mark.parametrize("name", CONFIGS)
def test_the_title_screen_lists_spitfires_joysticks_against_the_players(bbc, game_build, fake, name):
    config = CONFIGS[name]
    to_title(bbc, game_build, at_title=installer(fake, config))
    lines = title_lines(bbc)
    expected = spitfire_line(config.identify(), config.summary(), config.keyword)
    assert any(line.strip() == expected.strip() for line in lines), expected
    slots = expected_slots(config)
    for slot, ink in enumerate("CMYK"):
        keys = key_line(ink)
        line = next(line for line in lines if keys in line)
        margin = f" {joystick_marker(slot)} " if slots >> slot & 1 else "    "
        assert line.startswith(margin + keys), line
    if name == "two-twins":
        SCREENSHOT_DIRPATH.mkdir(parents=True, exist_ok=True)
        bbc.video.capture_frame().save_png(SCREENSHOT_DIRPATH / "title_spitfire.png")


def test_the_title_lines_say_what_we_mean():
    """(The model's lines for some of the cases above.)"""
    def line(name):
        config = CONFIGS[name]
        return spitfire_line(config.identify(), config.summary(), config.keyword)
    assert line("two-twins") == "SPItFIRE: A 3BT J1 J2, B 3BT J3 J4"
    assert line("twin-and-single") == "SPItFIRE: A 3BT J1 J2, B SINGLE J3"
    assert line("unknown-type") == "SPItFIRE: A ? J1"
    assert line("none") == "SPItFIRE: no joysticks"
    assert line("handling-off") == "SPItFIRE: type *SPITFIRE JOYSTICK ON"
    assert line("updates-stopped") == "SPItFIRE: stopped: type *FX16,4"


def test_redefining_keys_keeps_the_joystick_mark(bbc, game_build, fake):
    from test_keys import redefine
    from dontdither.gen_tables import layout_line

    to_title(bbc, game_build, at_title=installer(fake))
    redefine(bbc, "f1", ["Q", "Z", "X", "E", "TAB"])
    lines = title_lines(bbc)
    expected = f" J1 {layout_line('C', ['Q', 'Z', 'X', 'E', 'TAB'])}"
    assert any(line.startswith(expected) for line in lines), expected


# ---- Joining -----------------------------------------------------------------------

def test_a_joystick_fire_button_joins_its_player_on_the_joystick(bbc, game_build, fake):
    labels = load_game(bbc, game_build, at_title=installer(fake))
    stick = FakeSpitfire(bbc, fake[1])
    bbc.debugger.run_to(labels["select_field"])
    stick.fire(2, True)                                       # joystick 3: yellow
    bbc.run_for_emulated_seconds(0.2)
    stick.fire(2, False)
    peek = bbc.memory.address.peek
    assert peek[labels["session_joined"]] == 0b0100
    assert peek[labels["session_controls"] + 2] == CONTROL_JOYSTICK
    assert "Y JOY" in bbc.video.screen_text().text


def test_four_joysticks_join_and_play_starts_at_once(bbc, game_build, fake):
    labels = load_game(bbc, game_build, at_title=installer(fake))
    stick = FakeSpitfire(bbc, fake[1])
    bbc.debugger.run_to(labels["select_field"])
    for j in range(4):
        stick.fire(j, True)
    bbc.debugger.run_to(labels["select_start"], timeout=10)
    for j in range(4):
        stick.fire(j, False)
    peek = bbc.memory.address.peek
    assert peek[labels["session_joined"]] == 0b1111
    assert [peek[labels["session_controls"] + p] for p in range(4)] == [CONTROL_JOYSTICK] * 4
    bbc.debugger.run_to(labels["main_loop"], timeout=30)
    assert [peek[labels["player_control"] + p] for p in range(4)] == [CONTROL_JOYSTICK] * 4


def test_a_slot_without_a_joystick_still_joins_on_its_keys(bbc, game_build, fake):
    """With fewer joysticks than players, the others join on the keyboard."""
    from dontdither.controls import LAYOUTS, matrix_position

    labels = load_game(bbc, game_build, at_title=installer(fake, CONFIGS["one-twin"]))
    bbc.debugger.run_to(labels["select_field"])
    key = matrix_position(LAYOUTS["K"]["fire"])
    bbc.keyboard.matrix_down(*key)
    bbc.run_for_emulated_seconds(0.2)
    bbc.keyboard.matrix_up(*key)
    peek = bbc.memory.address.peek
    assert peek[labels["session_controls"] + 3] == CONTROL_KEYS
    assert "K YOU" in bbc.video.screen_text().text


def test_a_joystick_fire_button_ends_the_demo(bbc, game_build, fake):
    labels = load_game(bbc, game_build, at_title=installer(fake))
    bbc.memory.address.bus[labels["session_seconds"]] = 1     # nobody joins: the demo
    bbc.debugger.run_to(labels["main_loop"], timeout=60)
    step_ticks(bbc, labels, 10)
    FakeSpitfire(bbc, fake[1]).fire(3, True)
    bbc.debugger.step(1)
    bbc.debugger.run_to(labels["select_players"], timeout=10)


# ---- Playing -----------------------------------------------------------------------

DIRECTIONS = [0, SWITCH_UP, SWITCH_UP | SWITCH_RIGHT, SWITCH_RIGHT, SWITCH_DOWN | SWITCH_RIGHT,
              SWITCH_DOWN, SWITCH_DOWN | SWITCH_LEFT, SWITCH_LEFT, SWITCH_UP | SWITCH_LEFT]


def test_joysticks_drive_and_fire_exactly_as_the_model_says(bbc, game_build, fake):
    """Four players on joysticks, random directions and buttons: the tanks,
    reservoirs and input bytes follow the model fed the same switch bytes."""
    boot_game(bbc, game_build, at_title=installer(fake))
    labels = game_build.labels["DITHER"]
    stick = FakeSpitfire(bbc, fake[1])
    level = level_set(4)[0]
    model = Game.start(level)
    bus, peek = bbc.memory.address.bus, bbc.memory.address.peek
    for p, player in enumerate(model.players):
        bus[labels["player_control"] + p] = CONTROL_JOYSTICK
        player.ai = False
    rng = random.Random(5)
    switches = [0] * 4
    for tick in range(200):
        if tick % 10 == 0:
            switches = [rng.choice(DIRECTIONS) | (SWITCH_FIRE if rng.random() < 0.5 else 0)
                        for _ in range(4)]
            for j, value in enumerate(switches):
                stick.switches(j, value)
        step_ticks(bbc, labels)
        model.tick([input_of_switch_byte(value) for value in switches])
        fields = ("player_sx", "player_sy", "player_facing", "player_reservoir")
        actual = [tuple(peek[labels[f] + p] for f in fields) for p in range(4)]
        expected = [(p.sx, p.sy, p.facing, p.reservoir) for p in model.players]
        assert actual == expected, f"tick {tick}"
        assert [peek[labels["player_input"] + p] for p in range(4)] == \
            [input_of_switch_byte(value) for value in switches], f"tick {tick}"


def test_every_switch_byte_gives_the_models_input(bbc, game_build, fake):
    """Every combination of direction bits, with and without fire -- even
    those SPItFIRE never sends (opposite directions; bits 1-3, which are
    always 0) -- decodes as the model says."""
    boot_game(bbc, game_build, at_title=installer(fake))
    labels = game_build.labels["DITHER"]
    bus, peek = bbc.memory.address.bus, bbc.memory.address.peek
    bus[labels["player_control"] + 1] = CONTROL_JOYSTICK
    stick = FakeSpitfire(bbc, fake[1])
    values = [nibble << 4 | fire for nibble in range(16) for fire in (0, SWITCH_FIRE)] + [0x0E, 0xFF]
    for value in values:
        stick.switches(1, value)
        step_ticks(bbc, labels)
        assert peek[labels["player_input"] + 1] == input_of_switch_byte(value), hex(value)


def test_the_game_keeps_25_hz_with_four_joysticks(bbc, game_build, fake):
    boot_game(bbc, game_build, at_title=installer(fake))
    labels = game_build.labels["DITHER"]
    stick = FakeSpitfire(bbc, fake[1])
    for p, value in enumerate([SWITCH_DOWN | SWITCH_RIGHT, SWITCH_DOWN | SWITCH_LEFT,
                               SWITCH_UP | SWITCH_LEFT, SWITCH_UP | SWITCH_RIGHT]):
        bbc.memory.address.bus[labels["player_control"] + p] = CONTROL_JOYSTICK
        stick.switches(p, value | SWITCH_FIRE)
    peek = bbc.memory.address.peek
    start = peek.word(labels["tick_count"])
    bbc.run_for_emulated_seconds(2.0)
    ticks = (peek.word(labels["tick_count"]) - start) & 0xFFFF
    assert 49 <= ticks <= 51


def test_a_slot_whose_joystick_is_not_a_stick_does_not_join_with_it(bbc, game_build, fake):
    """A Bitstik's halves are joysticks 1 and 2 but not sticks: their buttons
    join nobody; joystick 3, a stick, joins slot Y."""
    labels = load_game(bbc, game_build, at_title=installer(fake, CONFIGS["bitstik-and-twin"]))
    stick = FakeSpitfire(bbc, fake[1])
    bbc.debugger.run_to(labels["select_field"])
    for j in (0, 1, 2):
        stick.fire(j, True)
    bbc.run_for_emulated_seconds(0.2)
    assert bbc.memory.address.peek[labels["session_joined"]] == 0b0100
