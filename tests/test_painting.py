"""Shots paint the arena exactly as the model says.

A freshly booted game (level 1, Colour Clash) is driven by scripted input. After each
check, every arena byte of screen memory must equal the model's: the arena
cells in their painted ink states, walls, and the tanks on top.
"""

import random

import pytest

from conftest import boot_game, enter_level, step_ticks
from dontdither.game import FIRE_BIT, FIRE_PERIOD, NO_DIRECTION, Game
from dontdither.levels import load_levels
from dontdither.render import arena_bytes, arena_screen, draw_players
from dontdither.screen import MODE1_SCREEN_BASE, MODE1_SCREEN_SIZE

LEVEL = load_levels()[0]
CONTROL_SCRIPTED = 3
STILL = NO_DIRECTION


@pytest.fixture
def game(launch_bbc, game_build):
    bbc = launch_bbc()
    boot_game(bbc, game_build)
    labels = game_build.labels["DITHER"]
    enter_level(bbc, labels, 0)          # exactly at the level's first tick
    model = Game.start(LEVEL)
    for p in range(4):
        bbc.memory.address.bus[labels["player_control"] + p] = CONTROL_SCRIPTED
        model.players[p].ai = False
    return bbc, labels, model


def run(bbc, labels, model, inputs, ticks=1):
    for p, byte in enumerate(inputs):
        bbc.memory.address.bus[labels["player_input"] + p] = byte
    step_ticks(bbc, labels, ticks)
    for _ in range(ticks):
        model.tick(inputs)


def player_state(bbc, labels):
    peek = bbc.memory.address.peek
    fields = ("player_sx", "player_sy", "player_facing", "player_accumulator",
              "player_cooldown", "player_variant", "player_last_victim")
    return [tuple(peek[labels[f] + p] for f in fields) for p in range(4)]


def model_player_state(model):
    return [(p.sx, p.sy, p.facing, p.accumulator, p.cooldown, p.variant, p.last_victim)
            for p in model.players]


def assert_arena_matches(bbc, model):
    expected = arena_screen(LEVEL, model.cells)
    draw_players(expected, [(p.sx, p.sy, p.facing, p.ink) for p in model.players])
    actual = bytes(bbc.memory.address.peek[MODE1_SCREEN_BASE:MODE1_SCREEN_BASE + MODE1_SCREEN_SIZE])
    a, e = arena_bytes(actual), arena_bytes(expected)
    wrong = [i for i, (x, y) in enumerate(zip(a, e)) if x != y]
    assert not wrong, f"{len(wrong)} arena bytes differ, first offsets {wrong[:8]}"


def test_one_shot_into_open_space(game):
    bbc, labels, model = game
    run(bbc, labels, model, [2, STILL, STILL, STILL])            # turn east
    run(bbc, labels, model, [STILL | FIRE_BIT, STILL, STILL, STILL])
    assert player_state(bbc, labels) == model_player_state(model)
    assert_arena_matches(bbc, model)


def test_a_shot_at_a_wall_is_shadowed(game):
    bbc, labels, model = game
    run(bbc, labels, model, [STILL | FIRE_BIT, STILL, STILL, STILL])   # SE, at the bracket
    assert_arena_matches(bbc, model)


def test_repeated_shots_turn_cells_solid(game):
    bbc, labels, model = game
    run(bbc, labels, model, [2, STILL, STILL, STILL])
    run(bbc, labels, model, [STILL | FIRE_BIT, STILL, STILL, STILL], ticks=4 * FIRE_PERIOD)
    assert any(s == (4, 0, 0, 0) for s in model.cells.values())
    assert player_state(bbc, labels) == model_player_state(model)
    assert_arena_matches(bbc, model)


def test_paint_under_a_tank_appears_when_it_moves_away(game):
    bbc, labels, model = game
    # Put player 1 in player 0's line of fire, 8 cells east of it.
    bbc.memory.address.bus[labels["player_sx"] + 1] = model.players[1].sx = 21
    bbc.memory.address.bus[labels["player_sy"] + 1] = model.players[1].sy = 13
    run(bbc, labels, model, [2, STILL, STILL, STILL])
    run(bbc, labels, model, [STILL | FIRE_BIT, STILL, STILL, STILL], ticks=2 * FIRE_PERIOD)
    assert_arena_matches(bbc, model)
    run(bbc, labels, model, [STILL, 4, STILL, STILL], ticks=20)     # player 1 drives off south
    assert_arena_matches(bbc, model)


def test_driving_and_firing_soak(game):
    bbc, labels, model = game
    rng = random.Random(99)
    inputs = [STILL] * 4
    for tick in range(160):
        if tick % 8 == 0:
            inputs = [rng.choice(list(range(8)) + [STILL]) | (FIRE_BIT if rng.random() < 0.6 else 0)
                      for _ in range(4)]
        run(bbc, labels, model, inputs)
        assert player_state(bbc, labels) == model_player_state(model), f"tick {tick}"
        if tick % 40 == 39:
            assert_arena_matches(bbc, model)
