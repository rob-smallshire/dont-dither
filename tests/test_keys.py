"""The key layouts SPLASH leaves resident for the game (asm/handoff.asm).

SPLASH fills the block -- with the defaults, unless a sealed block survived
a BREAK -- shows each player's keys from it, and the game reads its keys
from it.
"""

import pytest

from conftest import load_game, step_ticks
from dontdither.controls import LAYOUT_KEYS, LAYOUTS, inkey_code, matrix_position
from dontdither.game import NO_DIRECTION, Game, input_of_keys
from dontdither.gen_tables import layout_line
from dontdither.levels import load_levels

HANDOFF_MAGIC = 0xDD
CONTROL_KEYS = 1
TITLE_SECONDS = 0.1


def layout_bytes(layouts: dict[str, dict[str, str]]) -> bytes:
    """The block's key bytes for layouts by ink: per slot, negative-INKEY
    codes in the stored order fire, right, left, down, up."""
    return bytes(inkey_code(layouts[ink][k]) for ink in "CMYK" for k in reversed(LAYOUT_KEYS))


def sealed(key_bytes: bytes) -> bytes:
    """The whole block: the keys, the magic and the checksum."""
    return key_bytes + bytes([HANDOFF_MAGIC, (sum(key_bytes) + HANDOFF_MAGIC) & 0xFF])


def block(bbc, labels) -> bytes:
    start = labels["key_layouts"]
    return bytes(bbc.memory.address.peek[start:start + 22])


def write_block(bbc, labels, data: bytes) -> None:
    bbc.memory.address.bus[labels["key_layouts"]:labels["key_layouts"] + len(data)] = data


def to_title_screen(bbc, game_build, again=False):
    """Boot (Shift-BREAK: a soft reset, RAM kept) and stop at the title
    screen's question, with the screen shown. Again: the disc is already in."""
    splash = game_build.labels["SPLASH"]
    if again:
        bbc.debugger.ensure_running()        # DFS must see Shift during the reset
        bbc.keyboard.shift_break()
    else:
        bbc.boot_disc(game_build.disc_filepath)
    bbc.debugger.run_to(splash["splash_key"], timeout=60)
    bbc.run_for_emulated_seconds(TITLE_SECONDS)
    return splash


@pytest.fixture
def bbc(launch_bbc):
    return launch_bbc()


def test_a_fresh_machine_gets_the_default_keys_sealed(bbc, game_build):
    splash = to_title_screen(bbc, game_build)
    assert block(bbc, splash) == sealed(layout_bytes(LAYOUTS))


def test_both_programs_agree_where_the_keys_are(game_build):
    for label in ("key_layouts", "handoff_magic", "handoff_checksum"):
        assert game_build.labels["SPLASH"][label] == game_build.labels["DITHER"][label]


CHANGED = {**LAYOUTS, "M": {**LAYOUTS["M"], "fire": "N"},
           "Y": {"up": "UP", "left": "LEFT", "down": "DOWN", "right": "RIGHT", "fire": "COPY"},
           "K": {"up": "SHIFT LOCK", "left": "CAPS LOCK", "down": "RETURN", "right": "DELETE",
                 "fire": "f0"}}


def test_changed_keys_survive_break_and_are_shown(bbc, game_build):
    splash = to_title_screen(bbc, game_build)
    write_block(bbc, splash, sealed(layout_bytes(CHANGED)))
    to_title_screen(bbc, game_build, again=True)            # BREAK and boot again
    assert block(bbc, splash) == sealed(layout_bytes(CHANGED))
    text = bbc.video.screen_text().text
    for ink in "CMYK":
        keys = [CHANGED[ink][k] for k in ("up", "left", "down", "right", "fire")]
        assert layout_line(ink, keys) in text, layout_line(ink, keys)


def test_long_key_lines_are_cut_short_of_the_last_column():
    line = layout_line("M", ["SHIFT LOCK", "CAPS LOCK", "RETURN", "DELETE", "COPY"])
    assert line == "Magenta: SLOCK CAPS RET DEL, COPY f"      # 35 characters


def test_a_damaged_block_gets_the_defaults(bbc, game_build):
    splash = to_title_screen(bbc, game_build)
    damaged = bytearray(sealed(layout_bytes(CHANGED)))
    damaged[3] ^= 0x01                                      # checksum no longer matches
    write_block(bbc, splash, bytes(damaged))
    to_title_screen(bbc, game_build, again=True)
    assert block(bbc, splash) == sealed(layout_bytes(LAYOUTS))


def test_the_game_drives_with_the_resident_keys(bbc, game_build):
    labels = load_game(bbc, game_build)
    q_for_up = {**LAYOUTS, "C": {**LAYOUTS["C"], "up": "Q"}}
    write_block(bbc, labels, sealed(layout_bytes(q_for_up)))
    boot_game_from_select(bbc, labels)
    model = Game.start(load_levels()[0])
    q = matrix_position("Q")
    bbc.keyboard.matrix_down(*q)
    step_ticks(bbc, labels, 20)
    bbc.keyboard.matrix_up(*q)
    for _ in range(20):
        model.tick([input_of_keys(0b00001), NO_DIRECTION, NO_DIRECTION, NO_DIRECTION])
    peek = bbc.memory.address.peek
    assert (peek[labels["player_sx"]], peek[labels["player_sy"]]) == (model.players[0].sx, model.players[0].sy)
    assert peek[labels["player_control"]] == CONTROL_KEYS


def boot_game_from_select(bbc, labels):
    """From player selection, enter level 0 with the default session, as
    boot_game does."""
    from dontdither.game import DEFAULT_RANDOM_STATE

    bbc.cpu.pc = labels["enter_level"]
    bbc.memory.address.bus[labels["zp_level"]] = 0
    bbc.memory.address.bus[labels["random_state"]] = DEFAULT_RANDOM_STATE
    bbc.debugger.run_to(labels["main_loop"])


# ---- Redefining keys on the title screen ---------------------------------------

def press(bbc, key: str, seconds: float = 0.1) -> None:
    bbc.keyboard.matrix_down(*matrix_position(key))
    bbc.run_for_emulated_seconds(seconds)
    bbc.keyboard.matrix_up(*matrix_position(key))
    bbc.run_for_emulated_seconds(seconds)


def redefine(bbc, function_key: str, keys: list[str]) -> None:
    """Press f1-f4, then the keys in the order asked: up, left, down, right,
    fire."""
    press(bbc, function_key)
    for key in keys:
        press(bbc, key)


def test_the_title_screen_says_how_to_change_keys(bbc, game_build):
    to_title_screen(bbc, game_build)
    assert "f1-f4 change a player's keys:" in bbc.video.screen_text().text


def test_f1_redefines_player_ones_keys(bbc, game_build):
    splash = to_title_screen(bbc, game_build)
    peek = bbc.memory.address.peek
    beyond = splash["handoff_end"]
    before = bytes(peek[beyond:0x0E00])       # up to and including DFS's page &0D
    redefine(bbc, "f1", ["Q", "Z", "X", "E", "TAB"])
    assert bytes(peek[beyond:0x0E00]) == before     # nothing written outside the block
    new = {**LAYOUTS, "C": {"up": "Q", "left": "Z", "down": "X", "right": "E", "fire": "TAB"}}
    assert block(bbc, splash) == sealed(layout_bytes(new))
    assert layout_line("C", ["Q", "Z", "X", "E", "TAB"]) in bbc.video.screen_text().text


def test_f4_redefines_player_four_and_it_survives_break(bbc, game_build):
    splash = to_title_screen(bbc, game_build)
    redefine(bbc, "f4", ["UP", "LEFT", "DOWN", "RIGHT", "RETURN"])
    new = {**LAYOUTS, "K": {"up": "UP", "left": "LEFT", "down": "DOWN", "right": "RIGHT", "fire": "RETURN"}}
    to_title_screen(bbc, game_build, again=True)
    assert block(bbc, splash) == sealed(layout_bytes(new))
    assert "Black: cursor keys, RET fires" in bbc.video.screen_text().text


def test_escape_and_other_players_keys_are_refused(bbc, game_build):
    splash = to_title_screen(bbc, game_build)
    press(bbc, "f2")                                        # magenta
    for refused in ("ESCAPE", "W", "SHIFT", "SPACE", "\\"):   # C's, C's, Y's, K's
        press(bbc, refused)
        assert "Magenta: press UP" in bbc.video.screen_text().text, refused
    for key in ["O", "K", "L", ";", "N"]:                   # its own old K and L are fine
        press(bbc, key)
    new = {**LAYOUTS, "M": {"up": "O", "left": "K", "down": "L", "right": ";", "fire": "N"}}
    assert block(bbc, splash) == sealed(layout_bytes(new))


def test_a_key_cannot_be_chosen_twice(bbc, game_build):
    splash = to_title_screen(bbc, game_build)
    press(bbc, "f3")
    press(bbc, "G")
    press(bbc, "G")                                         # refused: already up
    assert "Yellow: press LEFT" in bbc.video.screen_text().text
    for key in ["H", "Y", "U", "CTRL"]:
        press(bbc, key)
    new = {**LAYOUTS, "Y": {"up": "G", "left": "H", "down": "Y", "right": "U", "fire": "CTRL"}}
    assert block(bbc, splash) == sealed(layout_bytes(new))


def test_after_redefining_the_game_still_starts(bbc, game_build):
    to_title_screen(bbc, game_build)
    redefine(bbc, "f1", ["2", "4", "Q", "E", "TAB"])       # digits as keys...
    labels = game_build.labels["DITHER"]
    bbc.keyboard.type("4")                                  # ...do not answer
    bbc.debugger.run_to(labels["select_players"], timeout=60)
    assert bbc.memory.address.peek[labels["level_area"]] == 4
