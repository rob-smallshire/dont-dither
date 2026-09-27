"""Player selection, sessions, points and demo mode (asm/flow.asm).

The join window is shortened by writing session_seconds once the countdown
has started.
"""

import random

import pytest

from conftest import SET_LEVEL_IDS, SET_LEVELS, boot_game, enter_level, load_game, step_ticks
from dontdither.controls import LAYOUTS, matrix_position
from dontdither.game import (
    DEMO_ROUND_TICKS,
    FIRE_BIT,
    NO_DIRECTION,
    ROUND_TICKS,
    Game,
    round_points,
)
from dontdither.levels import level_set, load_levels

CONTROL_KEYS_A, CONTROL_SCRIPTED, CONTROL_AI = 1, 3, 4


@pytest.fixture
def bbc(launch_bbc):
    return launch_bbc()


def to_player_select(bbc, game_build, players=4):
    labels = load_game(bbc, game_build, players)
    bbc.debugger.run_to(labels["select_field"])          # the countdown has begun
    return labels


def shorten_window(bbc, labels, seconds=1):
    bbc.memory.address.bus[labels["session_seconds"]] = seconds


def controls(bbc, labels):
    return [bbc.memory.address.peek[labels["player_control"] + p] for p in range(4)]


def test_player_select_screen_invites_players_to_join(bbc, game_build):
    labels = to_player_select(bbc, game_build)
    bbc.run_for_emulated_seconds(0.2)
    text = bbc.video.screen_text().text
    for words in ("PRESS", "FIRE TO", "JOIN", "C CPU", "M CPU"):
        assert words in text


def test_pressing_fire_joins_player_one(bbc, game_build):
    labels = to_player_select(bbc, game_build)
    shift = matrix_position(LAYOUTS["A"]["fire"])
    bbc.keyboard.matrix_down(*shift)
    bbc.run_for_emulated_seconds(0.2)
    bbc.keyboard.matrix_up(*shift)
    assert "C YOU" in bbc.video.screen_text().text
    shorten_window(bbc, labels)
    bbc.debugger.run_to(labels["main_loop"], timeout=60)
    peek = bbc.memory.address.peek
    assert peek[labels["session_humans"]] == 0b0001
    assert controls(bbc, labels) == [CONTROL_KEYS_A, CONTROL_AI, CONTROL_AI, CONTROL_AI]
    assert peek.word(labels["round_length_ticks"]) == ROUND_TICKS


def test_nobody_joining_starts_a_demo_that_a_key_ends(bbc, game_build):
    labels = to_player_select(bbc, game_build)
    shorten_window(bbc, labels)
    bbc.debugger.run_to(labels["main_loop"], timeout=60)
    peek = bbc.memory.address.peek
    assert peek[labels["session_humans"]] == 0
    assert controls(bbc, labels) == [CONTROL_AI] * 4
    assert peek.word(labels["round_length_ticks"]) == DEMO_ROUND_TICKS

    step_ticks(bbc, labels, 20)                           # the demo plays
    w = matrix_position(LAYOUTS["A"]["up"])
    bbc.keyboard.matrix_down(*w)
    bbc.debugger.step(1)
    bbc.debugger.run_to(labels["select_players"], timeout=10)
    bbc.keyboard.matrix_up(*w)


@pytest.mark.parametrize("players, level_number", SET_LEVELS, ids=SET_LEVEL_IDS)
def test_points_are_awarded_by_rank(bbc, game_build, players, level_number):
    boot_game(bbc, game_build, players)
    labels = game_build.labels["DITHER"]
    bus = bbc.memory.address.bus
    ticks = 100
    bus[labels["round_length_ticks"]] = ticks
    bus[labels["round_length_ticks"] + 1] = 0
    for p in range(4):
        bus[labels["session_points"] + p] = 10 * p       # points from earlier levels
    bus[labels["session_level"]] = level_number
    enter_level(bbc, labels, level_number)
    model = Game.start(level_set(players)[level_number])
    model.round_ticks_left = ticks
    count = len(model.players)
    for p in range(count):
        bus[labels["player_control"] + p] = CONTROL_SCRIPTED
        model.players[p].ai = False
    rng = random.Random(level_number)
    inputs = [rng.randrange(8) | FIRE_BIT for _ in range(count)]
    for p, byte in enumerate(inputs):
        bus[labels["player_input"] + p] = byte
    step_ticks(bbc, labels, ticks - 1)
    for _ in range(ticks):
        model.tick(inputs)
    bbc.debugger.step(1)
    bbc.debugger.run_to(labels["points_awarded"], timeout=120)

    points = round_points(model.percentages())
    peek = bbc.memory.address.peek
    assert [peek[labels["session_points"] + p] for p in range(4)] == \
        [10 * p + (points[p] if p < count else 0) for p in range(4)]


def test_a_session_moves_to_the_next_level_then_back_to_player_select(bbc, game_build):
    boot_game(bbc, game_build)
    labels = game_build.labels["DITHER"]
    bus = bbc.memory.address.bus
    bus[labels["round_length_ticks"]] = 30     # must be set before entering a level
    bus[labels["round_length_ticks"] + 1] = 0
    bus[labels["session_level"]] = 0
    enter_level(bbc, labels, 0)
    step_ticks(bbc, labels, 29)
    bbc.debugger.step(1)
    bbc.debugger.run_to(labels["points_awarded"], timeout=120)
    bbc.debugger.run_to(labels["main_loop"], timeout=60)      # after the pause
    peek = bbc.memory.address.peek
    assert peek[labels["zp_level"]] == 1 and peek[labels["session_level"]] == 1

    # The last level ends the session: final totals, then player selection.
    last = len(level_set(4)) - 1
    bus[labels["session_level"]] = last
    enter_level(bbc, labels, last)
    step_ticks(bbc, labels, 29)
    bbc.debugger.step(1)
    bbc.debugger.run_to(labels["points_awarded"], timeout=120)
    bbc.debugger.run_to(labels["show_totals"])
    bbc.debugger.run_to(labels["pause_seconds"])
    bbc.run_for_emulated_seconds(0.1)
    assert "FINAL" in bbc.video.screen_text().text
    bbc.debugger.run_to(labels["select_players"], timeout=60)


def test_each_session_level_opens_with_its_title_card(bbc, game_build):
    labels = to_player_select(bbc, game_build)
    shorten_window(bbc, labels)
    bbc.debugger.run_to(labels["title_card_shown"], timeout=60)
    bbc.run_for_emulated_seconds(0.1)
    text = bbc.video.screen_text().text
    assert "LEVEL 1" in text and load_levels()[0].name in text


@pytest.mark.parametrize("players", [2, 4])
def test_the_loader_loads_the_chosen_level_set(bbc, game_build, players):
    labels = load_game(bbc, game_build, players)
    peek = bbc.memory.address.peek
    area = labels["level_area"]
    assert peek[area] == players
    assert peek[area + 1] == len(level_set(players))


def test_two_player_select_lists_two_players(bbc, game_build):
    labels = to_player_select(bbc, game_build, players=2)
    bbc.run_for_emulated_seconds(0.2)
    text = bbc.video.screen_text().text
    assert "C CPU" in text and "M CPU" in text and "Y CPU" not in text


def test_play_starts_as_soon_as_everyone_has_joined(bbc, game_build):
    labels = to_player_select(bbc, game_build)
    keys = [matrix_position(LAYOUTS["A"]["fire"]), matrix_position(LAYOUTS["B"]["fire"])]
    for key in keys:
        bbc.keyboard.matrix_down(*key)
    bbc.debugger.run_to(labels["select_start"], timeout=10)
    for key in keys:
        bbc.keyboard.matrix_up(*key)
    peek = bbc.memory.address.peek
    assert peek[labels["session_seconds"]] > 5            # well before time ran out
    assert peek[labels["session_joined"]] == 0b11
