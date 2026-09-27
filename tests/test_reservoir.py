"""The ink reservoir on the machine: ground speed, refilling, running dry and
the HUD ink gauges, all exactly as the model says.

A freshly booted game (level 1, Colour Clash) is driven by scripted input.
"""

import random

import pytest

from conftest import boot_game, enter_level, step_ticks
from dontdither.game import FIRE_BIT, NO_DIRECTION, RESERVOIR_SPLATS, Game
from dontdither.levels import load_levels
from dontdither.render import arena_bytes, arena_screen, draw_players
from dontdither.screen import MODE1_SCREEN_BASE, MODE1_SCREEN_SIZE, superpixel_address
from dontdither.walls import full_byte

LEVEL = load_levels()[0]
CONTROL_SCRIPTED = 3
EAST, SOUTH = 2, 4
BAR_BASE_LINE = 239
GAUGE_LINES_PER_SPLAT = 2
FIELDS = ("player_sx", "player_sy", "player_facing", "player_accumulator", "player_cooldown",
          "player_reservoir", "player_reservoir_fraction")


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


def run(bbc, labels, model, inputs):
    for p, byte in enumerate(inputs):
        bbc.memory.address.bus[labels["player_input"] + p] = byte
    step_ticks(bbc, labels)
    model.tick(inputs)


def assert_state_matches(bbc, labels, model, tick):
    peek = bbc.memory.address.peek
    actual = [tuple(peek[labels[f] + p] for f in FIELDS) for p in range(4)]
    expected = [(p.sx, p.sy, p.facing, p.accumulator, p.cooldown, p.reservoir, p.reservoir_fraction)
                for p in model.players]
    assert actual == expected, f"tick {tick}"


def assert_arena_matches(bbc, model):
    peek = bbc.memory.address.peek
    screen = bytes(peek[MODE1_SCREEN_BASE:MODE1_SCREEN_BASE + MODE1_SCREEN_SIZE])
    expected = arena_screen(LEVEL, model.cells)
    draw_players(expected, [(p.sx, p.sy, p.facing, p.ink) for p in model.players])
    assert arena_bytes(screen) == arena_bytes(expected)


def set_reservoirs(bbc, labels, model, splats):
    for p, player in enumerate(model.players):
        bbc.memory.address.bus[labels["player_reservoir"] + p] = player.reservoir = splats[p]


def test_a_full_reservoir_at_the_start(game):
    bbc, labels, model = game
    peek = bbc.memory.address.peek
    assert [peek[labels["player_reservoir"] + p] for p in range(4)] == [RESERVOIR_SPLATS] * 4


def test_running_dry_and_refilling_match_the_model(game):
    bbc, labels, model = game
    set_reservoirs(bbc, labels, model, [3, 0, 5, 1])
    rng = random.Random(7)
    inputs = [NO_DIRECTION] * 4
    for tick in range(300):
        if tick % 12 == 0:
            inputs = [rng.choice(list(range(8)) + [NO_DIRECTION]) | (FIRE_BIT if rng.random() < 0.5 else 0)
                      for _ in range(4)]
        run(bbc, labels, model, inputs)
        assert_state_matches(bbc, labels, model, tick)
        if tick % 60 == 59:
            assert_arena_matches(bbc, model)


def test_own_ink_is_a_fast_road_and_filling_station(game):
    """Paint the middle of the arena solid C, in the model and on screen,
    and drive player 1 (C) into it with fire released."""
    bbc, labels, model = game
    for cell in model.cells:
        if all(30 <= v < 90 for v in cell):
            model.cells[cell] = (4, 0, 0, 0)
    screen = arena_screen(LEVEL, model.cells)
    for char_row in range(30 // 4, 92 // 4):          # arena bytes only; no tanks there
        start = char_row * 640
        bbc.memory.address.bus[MODE1_SCREEN_BASE + start:MODE1_SCREEN_BASE + start + 512] = \
            bytes(screen[start:start + 512])
    set_reservoirs(bbc, labels, model, [0, 32, 32, 32])
    grounds = set()
    for tick in range(120):
        grounds.add(model.ground(0))
        # Out of the corner bracket eastwards, then south into the ink.
        direction = EAST if model.players[0].sx < 44 else SOUTH
        run(bbc, labels, model, [direction, NO_DIRECTION, NO_DIRECTION, NO_DIRECTION])
        assert_state_matches(bbc, labels, model, tick)
    assert 4 in grounds                               # it reached its own ink...
    assert model.players[0].reservoir > 10            # ...and filled up there
    assert_arena_matches(bbc, model)


# ---- The HUD gauges ------------------------------------------------------------

def gauge_line_bytes(player: int) -> tuple[int, int]:
    ink = "CMYK"[player]
    body, contrast = full_byte(ink), full_byte("Y" if ink == "K" else "K")
    return (contrast & 0x88) | (body & 0x77), (contrast & 0x11) | (body & 0xEE)


def gauge_on_screen(bbc, player: int, players: int = 4) -> list[tuple[int, int]]:
    """The gauge's two bytes on each line from BAR_BASE_LINE upwards."""
    slot = player if players == 4 else player + 1
    column = 64 + 4 * slot + 1
    peek = bbc.memory.address.peek
    lines = []
    for n in range(RESERVOIR_SPLATS * GAUGE_LINES_PER_SPLAT + 2):
        y = BAR_BASE_LINE - n
        address = superpixel_address(0, y // 2) + (y & 1) + column * 8
        lines.append((peek[address], peek[address + 8]))
    return lines


def expected_gauge(player: int, splats: int) -> list[tuple[int, int]]:
    height = splats * GAUGE_LINES_PER_SPLAT
    return [gauge_line_bytes(player) if n < height else (0, 0)
            for n in range(RESERVOIR_SPLATS * GAUGE_LINES_PER_SPLAT + 2)]


def test_gauges_fill_as_the_level_starts(game):
    bbc, labels, model = game
    for p in range(4):
        assert gauge_on_screen(bbc, p) == expected_gauge(p, 0)
    for tick in range(RESERVOIR_SPLATS):
        run(bbc, labels, model, [NO_DIRECTION] * 4)
    for p in range(4):
        assert gauge_on_screen(bbc, p) == expected_gauge(p, RESERVOIR_SPLATS)


def test_gauges_follow_the_reservoirs(game):
    bbc, labels, model = game
    for tick in range(RESERVOIR_SPLATS):
        run(bbc, labels, model, [NO_DIRECTION] * 4)
    rng = random.Random(3)
    inputs = [NO_DIRECTION] * 4
    for tick in range(200):
        if tick % 10 == 0:
            inputs = [rng.choice(list(range(8)) + [NO_DIRECTION]) | (FIRE_BIT if rng.random() < 0.7 else 0)
                      for _ in range(4)]
        run(bbc, labels, model, inputs)
        peek = bbc.memory.address.peek
        drawn = [peek[labels["gauge_drawn"] + p] for p in range(4)]
        # A reservoir moves by at most a splat a tick, and its gauge follows
        # a splat a tick.
        assert all(abs(d - p.reservoir) <= 1 for d, p in zip(drawn, model.players)), f"tick {tick}"
        if tick % 25 == 24:
            for p in range(4):
                assert gauge_on_screen(bbc, p) == expected_gauge(p, drawn[p]), f"tick {tick}"


def test_the_game_keeps_25_hz_with_two_tanks_firing_and_two_refilling(game):
    bbc, labels, model = game
    for p, byte in enumerate([3 | FIRE_BIT, 5, 7 | FIRE_BIT, 1]):
        bbc.memory.address.bus[labels["player_input"] + p] = byte
    peek = bbc.memory.address.peek
    start = peek.word(labels["tick_count"])
    bbc.run_for_emulated_seconds(2.0)
    ticks = (peek.word(labels["tick_count"]) - start) & 0xFFFF
    assert 49 <= ticks <= 51
