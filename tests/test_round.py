"""A round: the clock counts down, play stops at zero, and the territory is
tallied and revealed exactly as the model scores it.

Tests shorten the round by writing round_length_ticks and re-entering the
level.
"""

import random

import pytest

from conftest import align_to_tick, boot_game, enter_level, step_ticks
from dontdither.game import FIRE_BIT, NO_DIRECTION, Game
from dontdither.hud_font import DIGITS, glyph_bytes
from dontdither.walls import full_byte
from dontdither.levels import load_levels
from dontdither.screen import MODE1_ROW_BYTES, MODE1_SCREEN_BASE, MODE1_SCREEN_SIZE

CONTROL_SCRIPTED = 3
BAR_BASE_LINE = 239
LABEL_LINE = 242


def start_short_round(bbc, labels, level_number, ticks):
    bus = bbc.memory.address.bus
    bus[labels["round_length_ticks"]] = ticks & 0xFF
    bus[labels["round_length_ticks"] + 1] = ticks >> 8
    enter_level(bbc, labels, level_number)
    level = load_levels()[level_number]
    model = Game.start(level)
    model.round_ticks_left = ticks
    for p in range(len(model.players)):
        bus[labels["player_control"] + p] = CONTROL_SCRIPTED
        model.players[p].ai = False
    return model


@pytest.fixture
def game(launch_bbc, game_build):
    bbc = launch_bbc()
    boot_game(bbc, game_build)
    labels = game_build.labels["DITHER"]
    align_to_tick(bbc, labels)
    return bbc, labels


def play(bbc, labels, model, ticks, seed):
    rng = random.Random(seed)
    count = len(model.players)
    inputs = [NO_DIRECTION] * count
    for tick in range(ticks):
        if tick % 10 == 0:
            inputs = [rng.randrange(8) | FIRE_BIT for _ in range(count)]
        for p, byte in enumerate(inputs):
            bbc.memory.address.bus[labels["player_input"] + p] = byte
        if tick < ticks - 1:
            step_ticks(bbc, labels)
        model.tick(inputs)


def bar_lines(screen, slot):
    """Raster lines drawn in a bar's left byte column."""
    column = 64 + 4 * slot + 1
    lines = 0
    for y in range(BAR_BASE_LINE, -1, -1):
        address = (y // 8) * MODE1_ROW_BYTES + column * 8 + y % 8
        if screen[address] == 0 and screen[address + 8] == 0:
            break
        lines += 1
    return lines


def test_clock_starts_at_the_round_length(game):
    bbc, labels = game
    start_short_round(bbc, labels, 0, 25 * 83)          # 1:23
    step_ticks(bbc, labels, 1)
    bbc.run_for_emulated_seconds(0.05)
    assert "1:23" in bbc.video.screen_text().text
    step_ticks(bbc, labels, 25)
    bbc.run_for_emulated_seconds(0.05)
    assert "1:22" in bbc.video.screen_text().text


def test_default_round_is_five_minutes(game):
    bbc, labels = game
    assert "5:00" in bbc.video.screen_text().text


@pytest.mark.parametrize("level_number", [0, 2])       # four players, two players
def test_the_tally_matches_the_model(game, level_number):
    bbc, labels = game
    ticks = 150
    model = start_short_round(bbc, labels, level_number, ticks)
    play(bbc, labels, model, ticks, seed=level_number)
    assert model.round_over
    bbc.debugger.step(1)
    bbc.debugger.run_to(labels["round_over"], timeout=120)

    peek = bbc.memory.address.peek
    count = len(model.players)
    quanta = model.ink_quanta()
    expected_quanta = [quanta["CMYK".index(p.ink)] for p in model.players]
    actual_quanta = [peek[labels["player_quanta_lo"] + p] | peek[labels["player_quanta_hi"] + p] << 8
                     for p in range(count)]
    assert actual_quanta == expected_quanta
    assert [peek[labels["player_percent"] + p] for p in range(count)] == model.percentages()
    assert peek.word(labels["total_quanta"]) == 4 * len(model.cells)

    screen = bytes(peek[MODE1_SCREEN_BASE:MODE1_SCREEN_BASE + MODE1_SCREEN_SIZE])
    for p, percent in enumerate(model.percentages()):
        slot = p if count == 4 else p + 1
        height = percent + percent // 2
        # A bar is `height` body lines topped by a cap line in the contrast
        # ink, which only shows (is non-zero) for the black player's yellow.
        cap_visible = model.players[p].ink == "K"
        expected = height + (1 if height and cap_visible else 0)
        assert bar_lines(screen, slot) == expected, f"player {p}"

    # Labels: each percentage in the tiny font, in the player's colour (the
    # black player's in yellow), tens and units under the bar's two columns.
    percentages = model.percentages()
    for p, percent in enumerate(percentages):
        slot = p if count == 4 else p + 1
        ink = model.players[p].ink
        colour = full_byte("Y" if ink == "K" else ink)
        tens, units = divmod(percent, 10)
        digits = [(64 + 4 * slot + 1, tens if tens else None), (64 + 4 * slot + 2, units)]
        for column, digit in digits:
            glyph = glyph_bytes(DIGITS[str(digit)]) if digit is not None else bytes(5)
            for row in range(5):
                y = LABEL_LINE + row
                address = (y // 8) * MODE1_ROW_BYTES + column * 8 + y % 8
                assert screen[address] == glyph[row] & colour, f"player {p} label"

    # The reveal must not have scrolled the screen (MODE 1 starts at &3000,
    # which the CRTC addresses as &3000 / 8).
    assert bbc.crtc.state.screen_start == 0x3000 // 8
