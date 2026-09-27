"""The ink reservoir model (tools/dontdither/game.py, ai.py). No emulator needed.

Each shot uses a splat of ink. While fire is released the ground under a
tank -- its own ink in the four centre superpixels of its footprint -- sets
its speed and how fast its reservoir refills.
"""

import pytest

from dontdither.ai import REFILLED, decide
from dontdither.game import (
    FIRE_BIT,
    FIRE_PERIOD,
    GROUND_AXIAL_SPEED,
    GROUND_DIAGONAL_SPEED,
    GROUND_REFILL,
    NO_DIRECTION,
    RESERVOIR_SPLATS,
    Game,
    Player,
)
from dontdither.levels import load_levels

EAST, SOUTH_EAST = 2, 3


def game_on_ground(own: int, ink: str = "C", **player) -> Game:
    """A one-player game whose whole arena holds `own` quanta of the
    player's ink (the rest K, or C for a K player)."""
    other = "K" if ink != "K" else "C"
    counts = dict.fromkeys("CMYK", 0)
    counts[ink] += own
    counts[other] += 4 - own
    state = tuple(counts[i] for i in "CMYK")
    game = Game([Player(0, 60, EAST, ink, **player)])
    game.cells = dict.fromkeys(game.cells, state)
    return game


@pytest.mark.parametrize("own", range(5))
def test_ground_level_is_own_quanta_over_the_centre_four_div_4(own):
    assert game_on_ground(own).ground(0) == own


def test_ground_counts_only_the_centre_four_superpixels():
    game = game_on_ground(0)
    player = game.players[0]
    for dx in range(6):
        for dy in range(6):
            if dx in (2, 3) and dy in (2, 3):
                game.cells[(player.sx + dx, player.sy + dy)] = (3, 0, 0, 1)
    assert game.ground(0) == 3                  # 4 cells x 3 quanta DIV 4


@pytest.mark.parametrize("own", range(5))
def test_released_speed_depends_on_the_ground(own):
    ticks = 100
    game = game_on_ground(own)
    for _ in range(ticks):
        game.tick([EAST])
    assert game.players[0].sx == ticks * GROUND_AXIAL_SPEED[own] // 256


@pytest.mark.parametrize("own", range(5))
def test_diagonal_speed_depends_on_the_ground_too(own):
    ticks = 100
    game = game_on_ground(own)
    game.players[0].sy = 0
    for _ in range(ticks):
        game.tick([SOUTH_EAST])
    assert game.players[0].sx == ticks * GROUND_DIAGONAL_SPEED[own] // 256


@pytest.mark.parametrize("own", range(5))
def test_firing_moves_at_normal_speed_anywhere(own):
    ticks = 100
    game = game_on_ground(own)
    for _ in range(ticks):
        game.tick([EAST | FIRE_BIT])
    assert game.players[0].sx == ticks * 200 // 256


def test_the_fastest_ground_takes_two_steps_on_some_ticks():
    game = game_on_ground(4)
    positions = []
    for _ in range(20):
        game.tick([EAST])
        positions.append(game.players[0].sx)
    steps = {b - a for a, b in zip([0] + positions, positions)}
    assert steps == {1, 2}


@pytest.mark.parametrize("own", range(5))
def test_released_fire_refills_by_the_ground(own):
    ticks = 25
    game = game_on_ground(own, reservoir=0)
    for _ in range(ticks):
        game.tick([NO_DIRECTION])
    player = game.players[0]
    assert player.reservoir * 256 + player.reservoir_fraction == ticks * GROUND_REFILL[own]


def test_hostile_ground_never_refills_and_grey_ground_trickles():
    assert GROUND_REFILL[0] == 0
    assert 0 < GROUND_REFILL[1] < GROUND_REFILL[2] < GROUND_REFILL[3] < GROUND_REFILL[4]


def test_the_reservoir_fills_no_further_than_full():
    game = game_on_ground(4, reservoir=RESERVOIR_SPLATS - 1, reservoir_fraction=250)
    game.tick([NO_DIRECTION])
    player = game.players[0]
    assert (player.reservoir, player.reservoir_fraction) == (RESERVOIR_SPLATS, 0)


def test_holding_fire_does_not_refill_even_when_empty():
    game = game_on_ground(4, reservoir=0)
    for _ in range(25):
        game.tick([NO_DIRECTION | FIRE_BIT])
    assert (game.players[0].reservoir, game.players[0].reservoir_fraction) == (0, 0)


def test_each_shot_uses_a_splat():
    game = game_on_ground(1)
    shots = 5
    for _ in range(shots * FIRE_PERIOD):
        game.tick([NO_DIRECTION | FIRE_BIT])
    assert game.players[0].reservoir == RESERVOIR_SPLATS - shots


def test_an_empty_reservoir_cannot_fire():
    game = game_on_ground(1, reservoir=0)
    before = dict(game.cells)
    for _ in range(3 * FIRE_PERIOD):
        game.tick([NO_DIRECTION | FIRE_BIT])
    assert game.cells == before


def test_a_full_reservoir_lasts_32_shots():
    game = game_on_ground(1)
    for _ in range(RESERVOIR_SPLATS * FIRE_PERIOD):
        game.tick([NO_DIRECTION | FIRE_BIT])
    assert game.players[0].reservoir == 0
    before = dict(game.cells)
    for _ in range(3 * FIRE_PERIOD):
        game.tick([NO_DIRECTION | FIRE_BIT])
    assert game.cells == before


# ---- The AI -------------------------------------------------------------------

def ai_game(level, reservoir):
    game = Game.start(level)
    player = game.players[0]
    player.ai, player.reservoir = True, reservoir
    return game, player


@pytest.mark.parametrize("level", load_levels()[:1], ids=lambda lv: lv.name)
def test_an_empty_ai_refills_without_firing_until_nearly_full(level):
    game, player = ai_game(level, reservoir=0)
    assert not decide(game, 0) & FIRE_BIT
    assert player.ai_refilling
    player.reservoir = REFILLED - 1
    decide(game, 0)
    assert player.ai_refilling
    player.reservoir = REFILLED
    decide(game, 0)
    assert not player.ai_refilling


@pytest.mark.parametrize("level", load_levels()[:1], ids=lambda lv: lv.name)
def test_an_ai_with_ink_left_keeps_painting(level):
    game, player = ai_game(level, reservoir=1)
    decide(game, 0)
    assert not player.ai_refilling


def test_a_refilling_ai_heads_for_its_own_ink():
    game = game_on_ground(0, reservoir=0, ai=True)
    player = game.players[0]
    player.sx, player.sy, player.ai_direction = 60, 60, 6     # heading W
    for x in range(70, 128):                 # solid C to the east
        for y in range(128):
            game.cells[(x, y)] = (4, 0, 0, 0)
    assert decide(game, 0) == EAST
    player.reservoir, player.ai_refilling, player.ai_direction = RESERVOIR_SPLATS, False, 6
    assert decide(game, 0) & 7 == 6       # painting, it prefers the unowned ground


def test_each_diagonal_speed_is_its_axial_speed_over_root_2():
    import math
    for axial, diagonal in zip(GROUND_AXIAL_SPEED, GROUND_DIAGONAL_SPEED):
        assert abs(diagonal * math.sqrt(2) - axial) < 1.5


def test_no_speed_takes_more_than_two_steps_a_tick():
    assert max(GROUND_AXIAL_SPEED + GROUND_DIAGONAL_SPEED) < 512
