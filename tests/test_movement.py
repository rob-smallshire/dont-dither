"""Tanks move and turn in the game exactly as the model says.

Players are driven by scripted input (written between ticks) and by real
keys held through Beebium's keyboard matrix; after every tick the 6502's
player state must equal the Python model's.
"""

import random

import pytest

from conftest import align_to_tick, step_ticks
from dontdither.controls import LAYOUTS, matrix_position
from dontdither.game import NO_DIRECTION, Game, input_of_keys
from dontdither.levels import load_levels
from dontdither.render import arena_bytes, arena_screen, draw_players
from dontdither.screen import MODE1_SCREEN_BASE, MODE1_SCREEN_SIZE

LEVEL = load_levels()[0]
CONTROL_NONE, CONTROL_KEYS_A, CONTROL_KEYS_B, CONTROL_SCRIPTED = range(4)


@pytest.fixture
def game(launch_bbc, game_build):
    """A freshly booted game, stopped before level 0's first tick, with a
    model in step with it."""
    from conftest import boot_game, enter_level

    bbc = launch_bbc()
    boot_game(bbc, game_build)
    labels = game_build.labels["DITHER"]
    enter_level(bbc, labels, 0)
    return bbc, labels, Game.start(LEVEL)


def state(bbc, labels):
    peek = bbc.memory.address.peek
    return [
        (peek[labels["player_sx"] + p], peek[labels["player_sy"] + p],
         peek[labels["player_facing"] + p], peek[labels["player_accumulator"] + p])
        for p in range(peek[labels["player_count"]])
    ]


def model_state(model):
    return [(p.sx, p.sy, p.facing, p.accumulator) for p in model.players]


def set_controls(bbc, labels, controls, model=None):
    """Set the game's control sources; with a model, mark its players as
    not AI-controlled to match (scripted or keyboard players)."""
    for p, control in enumerate(controls):
        bbc.memory.address.bus[labels["player_control"] + p] = control
        if model is not None:
            model.players[p].ai = control == 4


def test_starting_state_matches_the_model(game):
    bbc, labels, model = game
    assert state(bbc, labels) == model_state(model)


def test_scripted_inputs_match_the_model_every_tick(game):
    bbc, labels, model = game
    set_controls(bbc, labels, [CONTROL_SCRIPTED] * 4, model)
    rng = random.Random(42)
    for tick in range(60):
        inputs = [rng.choice(list(range(8)) + [NO_DIRECTION] * 2) for _ in range(4)]
        for p, byte in enumerate(inputs):
            bbc.memory.address.bus[labels["player_input"] + p] = byte
        step_ticks(bbc, labels)
        model.tick(inputs)
        assert state(bbc, labels) == model_state(model), f"after tick {tick + 1}"


def test_tanks_never_overlap_under_random_driving(game):
    bbc, labels, model = game
    set_controls(bbc, labels, [CONTROL_SCRIPTED] * 4, model)
    rng = random.Random(7)
    # Herd the tanks towards the centre, where they jostle.
    heading = [3, 5, 7, 1]
    for tick in range(120):
        inputs = [heading[p] if rng.random() < 0.7 else rng.randrange(8) for p in range(4)]
        for p, byte in enumerate(inputs):
            bbc.memory.address.bus[labels["player_input"] + p] = byte
        step_ticks(bbc, labels)
        model.tick(inputs)
        positions = [(x, y) for x, y, _, _ in state(bbc, labels)]
        for i in range(4):
            for j in range(i + 1, 4):
                (ax, ay), (bx, by) = positions[i], positions[j]
                assert not (abs(ax - bx) < 6 and abs(ay - by) < 6), f"tanks {i} and {j} overlap"
    assert state(bbc, labels) == model_state(model)


def test_screen_shows_the_tanks_where_the_model_puts_them(game):
    bbc, labels, model = game
    set_controls(bbc, labels, [CONTROL_SCRIPTED] * 4, model)
    inputs = [3, 5, 7, 1]      # every tank heads for the centre
    for p, byte in enumerate(inputs):
        bbc.memory.address.bus[labels["player_input"] + p] = byte
    step_ticks(bbc, labels, 30)
    for _ in range(30):
        model.tick(inputs)
    expected = arena_screen(LEVEL)
    draw_players(expected, [(p.sx, p.sy, p.facing, p.ink) for p in model.players])
    actual = bytes(bbc.memory.address.peek[MODE1_SCREEN_BASE:MODE1_SCREEN_BASE + MODE1_SCREEN_SIZE])
    assert arena_bytes(actual) == arena_bytes(expected)


@pytest.mark.parametrize("player, layout", [(0, "A"), (1, "B")])
@pytest.mark.parametrize("held", [("up",), ("right",), ("down", "left"), ("up", "right")])
def test_held_keys_drive_the_players(game, player, layout, held):
    bbc, labels, model = game
    keys = [LAYOUTS[layout][k] for k in held]
    for key in keys:
        bbc.keyboard.matrix_down(*matrix_position(key))
    step_ticks(bbc, labels, 20)
    for key in keys:
        bbc.keyboard.matrix_up(*matrix_position(key))

    mask = sum(1 << ("up", "down", "left", "right").index(k) for k in held)
    inputs = [NO_DIRECTION] * 4
    inputs[player] = input_of_keys(mask)
    for _ in range(20):
        model.tick(inputs)
    assert state(bbc, labels) == model_state(model)


def test_releasing_keys_stops_the_tank(game):
    bbc, labels, _ = game
    w = matrix_position(LAYOUTS["A"]["right"])
    bbc.keyboard.matrix_down(*w)
    step_ticks(bbc, labels, 10)
    bbc.keyboard.matrix_up(*w)
    step_ticks(bbc, labels, 1)       # the release is seen on this tick
    before = state(bbc, labels)[0]
    step_ticks(bbc, labels, 10)
    assert state(bbc, labels)[0] == before      # (AI players keep moving)


def test_game_ticks_at_25_hz(game):
    bbc, labels, _ = game
    peek = bbc.memory.address.peek
    start = peek.word(labels["tick_count"])
    bbc.run_for_emulated_seconds(2.0)
    ticks = (peek.word(labels["tick_count"]) - start) & 0xFFFF
    assert 49 <= ticks <= 51


def test_game_keeps_25_hz_with_all_tanks_moving_and_firing(game):
    bbc, labels, _ = game
    set_controls(bbc, labels, [CONTROL_SCRIPTED] * 4)
    for p, byte in enumerate([3 | 0x10, 5 | 0x10, 7 | 0x10, 1 | 0x10]):
        bbc.memory.address.bus[labels["player_input"] + p] = byte
    peek = bbc.memory.address.peek
    start = peek.word(labels["tick_count"])
    bbc.run_for_emulated_seconds(2.0)
    ticks = (peek.word(labels["tick_count"]) - start) & 0xFFFF
    assert 49 <= ticks <= 51


def test_a_tank_driven_into_a_wall_stops_short_of_it(game):
    bbc, labels, model = game
    set_controls(bbc, labels, [CONTROL_SCRIPTED] * 4, model)
    inputs = [2, NO_DIRECTION, NO_DIRECTION, NO_DIRECTION]     # player 0 heads east
    bbc.memory.address.bus[labels["player_input"]] = 2
    step_ticks(bbc, labels, 80)
    for _ in range(80):
        model.tick(inputs)
    sx = state(bbc, labels)[0][0]
    # Colour Clash's spur at wall column 15 (superpixels 60..63) blocks a tank
    # whose footprint (sx..sx+5) would reach superpixel 60.
    assert sx == 54
    assert state(bbc, labels) == model_state(model)


@pytest.mark.parametrize("level_number", range(len(load_levels())))
def test_random_driving_never_enters_a_wall(game, game_build, level_number):
    from conftest import enter_level
    from dontdither.game import footprint_wall_cells

    bbc, labels, _ = game
    level = load_levels()[level_number]
    enter_level(bbc, labels, level_number)
    model = Game.start(level)
    count = len(model.players)
    set_controls(bbc, labels, [CONTROL_SCRIPTED] * count, model)
    walls = level.wall_cells()
    rng = random.Random(level_number)
    inputs = [rng.randrange(8) for _ in range(count)]
    for tick in range(150):
        if tick % 10 == 0:                     # hold a direction for a while
            inputs = [rng.randrange(8) for _ in range(count)]
        for p, byte in enumerate(inputs):
            bbc.memory.address.bus[labels["player_input"] + p] = byte
        step_ticks(bbc, labels)
        model.tick(inputs)
        for x, y, _, _ in state(bbc, labels):
            assert not set(footprint_wall_cells(x, y)) & walls, f"tank in a wall at tick {tick}"
    assert state(bbc, labels) == model_state(model)
