"""Joysticks through SPItFIRE, on the machine.

Beebium emulates neither the Master Compact nor SPItFIRE, so these tests run
the game on a Model B with a fake SPItFIRE (tests/fake_spitfire.asm)
standing in for its ROM's documented interface: OSWORD &3F to detect it,
OSBYTE &80 to read the sticks. The tests install it at the title screen,
before the game starts and looks for joysticks, then move the sticks and
press the buttons by poking its tables.
"""

import random
import subprocess

import pytest

from conftest import boot_game, load_game, step_ticks, to_title
from dontdither.build import BUILD_DIRPATH, PROJECT_DIRPATH, find_beebasm, parse_labels
from dontdither.game import FIRE_BIT, NO_DIRECTION, Game
from dontdither.gen_tables import key_line
from dontdither.joysticks import (
    FIRE_CHANNELS,
    FIRE_MASKS,
    X_CHANNELS,
    Y_CHANNELS,
    input_of_joystick,
    joystick_marker,
    spitfire_line,
)
from dontdither.levels import level_set

CONTROL_KEYS, CONTROL_JOYSTICK, CONTROL_SCRIPTED = 1, 2, 3
BYTEV, WORDV = 0x020A, 0x020C
CENTRE = 0x8000
FAKE_SOURCE_FILEPATH = PROJECT_DIRPATH / "tests" / "fake_spitfire.asm"
FAKE_BINARY_FILEPATH = BUILD_DIRPATH / "fake_spitfire.bin"
FAKE_LABELS_FILEPATH = BUILD_DIRPATH / "labels" / "FAKE_SPITFIRE.txt"
SCREENSHOT_DIRPATH = BUILD_DIRPATH / "screenshots"


@pytest.fixture(scope="session")
def fake():
    """The fake SPItFIRE, assembled: (its bytes, its labels)."""
    FAKE_LABELS_FILEPATH.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([find_beebasm(), "-i", str(FAKE_SOURCE_FILEPATH.relative_to(PROJECT_DIRPATH)),
                    "-d", "-labels", str(FAKE_LABELS_FILEPATH.relative_to(PROJECT_DIRPATH))],
                   cwd=PROJECT_DIRPATH, check=True, capture_output=True)
    return FAKE_BINARY_FILEPATH.read_bytes(), parse_labels(FAKE_LABELS_FILEPATH.read_text())


class FakeSpitfire:
    """Drives the fake installed in a machine."""

    def __init__(self, bbc, labels):
        self.bbc, self.labels = bbc, labels

    def set_channel(self, channel: int, value: int) -> None:
        bus = self.bbc.memory.address.bus
        bus[self.labels["fake_lo"] + channel] = value & 0xFF
        bus[self.labels["fake_hi"] + channel] = value >> 8

    def stick(self, joystick: int, x: int, y: int) -> None:
        """Joystick 0-3's position (16-bit readings: X high is left, Y high
        is up)."""
        self.set_channel(X_CHANNELS[joystick], x)
        self.set_channel(Y_CHANNELS[joystick], y)

    def fire(self, joystick: int, held: bool) -> None:
        channel, mask = FIRE_CHANNELS[joystick], FIRE_MASKS[joystick]
        address = self.labels["fake_lo"] + channel
        bus, peek = self.bbc.memory.address.bus, self.bbc.memory.address.peek
        bus[address] = (peek[address] | mask) if held else (peek[address] & ~mask & 0xFF)


TWIN, SINGLE = 4, 1                # SPItFIRE port types
PORT_B = 0x80


def spitfire_block(joysticks=4, flags=0, signature=0x53, sticks=None) -> bytes:
    """What SPItFIRE's OSWORD &3F answers (11 bytes): by default two Delta
    3B Twins, on ports A and B, giving `joysticks` joysticks."""
    if sticks is None:
        sticks = [TWIN, TWIN, PORT_B | TWIN, PORT_B | TWIN][:joysticks]
    block = bytearray(11)
    block[0], block[1], block[4], block[10] = signature, 1, joysticks, flags
    block[6:10] = bytes(sticks) + bytes([0xFF] * (4 - len(sticks)))
    return bytes(block)


def installer(fake, joysticks=4, flags=0, signature=0x53, sticks=None):
    """A function installing the fake SPItFIRE (describing `joysticks`
    joysticks, sticks centred, buttons up) into a machine; for to_title's,
    load_game's and boot_game's at_title."""
    code, labels = fake
    block = spitfire_block(joysticks, flags, signature, sticks)

    def install(bbc):
        bus, peek = bbc.memory.address.bus, bbc.memory.address.peek
        bus[labels["fake_block"]:labels["fake_block"] + len(code)] = code
        bus[labels["fake_block"]:labels["fake_block"] + 11] = block
        stick = FakeSpitfire(bbc, labels)
        for channel in range(21):
            stick.set_channel(channel, 0)
        for j in range(joysticks):
            stick.stick(j, CENTRE, CENTRE)
        bus[labels["old_bytev"]:labels["old_bytev"] + 2] = bytes(peek[BYTEV:BYTEV + 2])
        bus[labels["old_wordv"]:labels["old_wordv"] + 2] = bytes(peek[WORDV:WORDV + 2])
        bus[BYTEV:BYTEV + 2] = labels["byte_hook"].to_bytes(2, "little")
        bus[WORDV:WORDV + 2] = labels["word_hook"].to_bytes(2, "little")

    return install


@pytest.fixture
def bbc(launch_bbc):
    return launch_bbc()


# ---- Detection ---------------------------------------------------------------------

def test_without_spitfire_there_are_no_joysticks(bbc, game_build):
    labels = load_game(bbc, game_build)
    assert bbc.memory.address.peek[labels["joysticks_available"]] == 0


@pytest.mark.parametrize("joysticks, flags, signature, expected", [
    (4, 0, 0x53, 4),
    (2, 0, 0x53, 2),
    (4, 1, 0x53, 0),          # no workspace: the user must press Ctrl-Break
    (4, 2, 0x53, 0),          # the hardware did not answer
], ids=["four", "two", "needs-ctrl-break", "not-answering"])
def test_spitfire_is_detected(bbc, game_build, fake, joysticks, flags, signature, expected):
    labels = load_game(bbc, game_build, at_title=installer(fake, joysticks, flags, signature))
    assert bbc.memory.address.peek[labels["joysticks_available"]] == expected


# ---- The title screen -------------------------------------------------------------

TITLE_SECONDS = 0.1


def title_lines(bbc) -> list[str]:
    bbc.run_for_emulated_seconds(TITLE_SECONDS)
    return bbc.video.screen_text().text.splitlines()


def test_the_title_screen_says_there_is_no_spitfire(bbc, game_build):
    to_title(bbc, game_build)
    lines = title_lines(bbc)
    assert any(line.strip() == "No SPItFIRE: keyboard only" for line in lines)
    assert not any("J1" in line for line in lines)


@pytest.mark.parametrize("joysticks, flags, sticks, marked", [
    (4, 0, None, 4),
    (2, 0, None, 2),
    (3, 0, [TWIN, TWIN, PORT_B | SINGLE], 3),
    (1, 0, [PORT_B | SINGLE], 1),
    (0, 0, [], 0),
    (0, 1, [], 0),
    (0, 2, [], 0),
], ids=["two-twins", "one-twin", "twin-and-single", "port-b-only", "none", "ctrl-break",
        "not-answering"])
def test_the_title_screen_lists_spitfires_joysticks_against_the_players(
        bbc, game_build, fake, joysticks, flags, sticks, marked):
    to_title(bbc, game_build, at_title=installer(fake, joysticks, flags, sticks=sticks))
    lines = title_lines(bbc)
    expected = spitfire_line(spitfire_block(joysticks, flags, sticks=sticks))
    assert any(line.strip() == expected for line in lines), expected
    for slot, ink in enumerate("CMYK"):
        keys = key_line(ink)
        line = next(line for line in lines if keys in line)
        margin = f" {joystick_marker(slot)} " if slot < marked else "    "
        assert line.startswith(margin + keys), line
    if joysticks == 4:
        SCREENSHOT_DIRPATH.mkdir(parents=True, exist_ok=True)
        bbc.video.capture_frame().save_png(SCREENSHOT_DIRPATH / "title_spitfire.png")


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


def test_without_spitfire_a_slot_still_joins_on_its_keys(bbc, game_build, fake):
    """With fewer joysticks than players, the others join on the keyboard."""
    from dontdither.controls import LAYOUTS, matrix_position

    labels = load_game(bbc, game_build, at_title=installer(fake, joysticks=2))
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

def test_joysticks_drive_and_fire_exactly_as_the_model_says(bbc, game_build, fake):
    """Four players on joysticks, random stick positions and buttons: the
    tanks, reservoirs and arena follow the model fed the same readings."""
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
    readings = [(CENTRE, CENTRE, False)] * 4
    for tick in range(200):
        if tick % 10 == 0:
            readings = [(rng.choice([0x0000, 0x3FFF, 0x4000, CENTRE, 0xBFFF, 0xC000, 0xFFFF]),
                         rng.choice([0x0000, 0x3FFF, 0x4000, CENTRE, 0xBFFF, 0xC000, 0xFFFF]),
                         rng.random() < 0.5) for _ in range(4)]
            for j, (x, y, fire) in enumerate(readings):
                stick.stick(j, x, y)
                stick.fire(j, fire)
        step_ticks(bbc, labels)
        model.tick([input_of_joystick(*r) for r in readings])
        fields = ("player_sx", "player_sy", "player_facing", "player_reservoir")
        actual = [tuple(peek[labels[f] + p] for f in fields) for p in range(4)]
        expected = [(p.sx, p.sy, p.facing, p.reservoir) for p in model.players]
        assert actual == expected, f"tick {tick}"
        assert [peek[labels["player_input"] + p] for p in range(4)] == \
            [input_of_joystick(*r) for r in readings], f"tick {tick}"


def test_the_game_keeps_25_hz_with_four_joysticks(bbc, game_build, fake):
    boot_game(bbc, game_build, at_title=installer(fake))
    labels = game_build.labels["DITHER"]
    stick = FakeSpitfire(bbc, fake[1])
    for p, (x, y) in enumerate([(0, 0), (0xFFFF, 0), (0xFFFF, 0xFFFF), (0, 0xFFFF)]):
        bbc.memory.address.bus[labels["player_control"] + p] = CONTROL_JOYSTICK
        stick.stick(p, x, y)
        stick.fire(p, True)
    peek = bbc.memory.address.peek
    start = peek.word(labels["tick_count"])
    bbc.run_for_emulated_seconds(2.0)
    ticks = (peek.word(labels["tick_count"]) - start) & 0xFFFF
    assert 49 <= ticks <= 51
