"""Tunnels on the machine: a tank drives out of one mouth, vanishes, and
comes out of the other, exactly as the model says -- screen and all.
"""

import pytest

from conftest import boot_game, enter_level, step_ticks
from dontdither.game import NO_DIRECTION, TUNNEL_TICKS, Game
from dontdither.levels import level_set
from dontdither.render import arena_bytes, arena_screen, draw_players
from dontdither.screen import MODE1_SCREEN_BASE, MODE1_SCREEN_SIZE

CONTROL_SCRIPTED = 3
N, E, S, W = 0, 2, 4, 6
LEVEL_NAME = "Tug of War"
FIELDS = ("player_sx", "player_sy", "player_facing", "player_in_tunnel", "player_drawn")


@pytest.fixture
def game(launch_bbc, game_build):
    bbc = launch_bbc()
    boot_game(bbc, game_build, players=2)
    labels = game_build.labels["DITHER"]
    levels = level_set(2)
    number = next(i for i, lv in enumerate(levels) if lv.name == LEVEL_NAME)
    enter_level(bbc, labels, number)
    model = Game.start(levels[number])
    for p in range(2):
        bbc.memory.address.bus[labels["player_control"] + p] = CONTROL_SCRIPTED
        model.players[p].ai = False
    return bbc, labels, model, levels[number]


def run(bbc, labels, model, inputs):
    for p, byte in enumerate(inputs):
        bbc.memory.address.bus[labels["player_input"] + p] = byte
    step_ticks(bbc, labels)
    model.tick(inputs)


def assert_state(bbc, labels, model, tick):
    peek = bbc.memory.address.peek
    actual = [tuple(peek[labels[f] + p] for f in FIELDS) for p in range(2)]
    expected = [(p.sx, p.sy, p.facing, int(p.in_tunnel), int(not p.in_tunnel)) for p in model.players]
    assert actual == expected, f"tick {tick}"


def assert_screen(bbc, model, level):
    peek = bbc.memory.address.peek
    screen = bytes(peek[MODE1_SCREEN_BASE:MODE1_SCREEN_BASE + MODE1_SCREEN_SIZE])
    expected = arena_screen(level, model.cells)
    draw_players(expected, [(p.sx, p.sy, p.facing, p.ink) for p in model.players if not p.in_tunnel])
    assert arena_bytes(screen) == arena_bytes(expected)


def towards_the_left_mouth(player) -> int:
    """West along the top to the border, down the left side into the
    mouth's rows, then west into the tunnel -- and on west out of the other
    side."""
    if player.in_tunnel or player.sy >= 58 or player.sx > 4:
        return W
    return S


def test_a_tank_drives_through_a_tunnel(game):
    bbc, labels, model, level = game
    assert level.tunnels
    went_in = came_out = None
    for tick in range(400):
        run(bbc, labels, model, [towards_the_left_mouth(model.players[0]), NO_DIRECTION])
        assert_state(bbc, labels, model, tick)
        player = model.players[0]
        if player.in_tunnel and went_in is None:
            went_in = tick
            assert_screen(bbc, model, level)          # gone from the screen
        if went_in is not None and not player.in_tunnel and came_out is None:
            came_out = tick
            assert_screen(bbc, model, level)          # back, on the far side
        if came_out is not None and tick > came_out + 20:
            break
    assert went_in is not None and came_out == went_in + TUNNEL_TICKS
    assert model.players[0].sx < 122                  # and drove on in from the right
    assert_screen(bbc, model, level)
