"""The movement model (tools/dontdither/game.py). No emulator needed."""

import math

from dontdither.game import (
    AXIAL_SPEED,
    DIAGONAL_SPEED,
    FIRE_BIT,
    MAX_POSITION,
    NO_DIRECTION,
    Game,
    Player,
    direction_of_keys,
    input_of_keys,
)

UP, DOWN, LEFT, RIGHT, FIRE = 1, 2, 4, 8, 16


def test_keys_map_to_eight_directions_and_cancel():
    assert direction_of_keys(UP) == 0
    assert direction_of_keys(UP | RIGHT) == 1
    assert direction_of_keys(RIGHT) == 2
    assert direction_of_keys(DOWN | LEFT) == 5
    assert direction_of_keys(UP | DOWN) == NO_DIRECTION
    assert direction_of_keys(UP | DOWN | LEFT) == 6
    assert input_of_keys(FIRE) == NO_DIRECTION | FIRE_BIT


def test_diagonal_speed_matches_axial_speed():
    assert abs(DIAGONAL_SPEED * math.sqrt(2) - AXIAL_SPEED) < 1


def test_diagonal_travel_is_no_faster_than_axial():
    ticks = 150                # both stay inside the arena
    axial, diagonal = Game([Player(0, 60, 2, "C")]), Game([Player(0, 0, 3, "C")])
    for _ in range(ticks):
        axial.tick([2])        # E
        diagonal.tick([3])     # SE
    east = axial.players[0].sx
    diag = math.hypot(diagonal.players[0].sx, diagonal.players[0].sy)
    assert abs(east - ticks * AXIAL_SPEED / 256) <= 1
    assert abs(diag - east) / east < 0.02


def test_turning_without_moving_keeps_position():
    game = Game([Player(50, 50, 0, "C")])
    game.tick([NO_DIRECTION])
    assert (game.players[0].sx, game.players[0].sy, game.players[0].facing) == (50, 50, 0)


def test_tank_slides_along_the_arena_edge():
    game = Game([Player(MAX_POSITION, 50, 2, "C")])
    for _ in range(20):
        game.tick([3])         # SE, pressing against the east edge
    player = game.players[0]
    assert player.sx == MAX_POSITION and player.sy > 50


def test_tank_stops_at_the_corner():
    game = Game([Player(0, 0, 0, "C")])
    for _ in range(20):
        game.tick([7])         # NW into the corner
    assert (game.players[0].sx, game.players[0].sy) == (0, 0)


def rotate_player(player, turns):
    sx, sy, facing = player.sx, player.sy, player.facing
    for _ in range(turns):
        sx, sy = MAX_POSITION - sy, sx
    return (sx, sy, (facing + 2 * turns) % 8)


def test_movement_rules_are_the_same_under_rotation():
    """A scene and its quarter-turned copy evolve as quarter turns of each other."""
    import random

    rng = random.Random(3)
    for trial in range(20):
        a = Player(rng.randrange(40, 70), rng.randrange(40, 70), 0, "C")
        b = Player(a.sx + rng.choice([-7, 6, 7]), a.sy + rng.choice([-6, 0, 6]), 0, "M")
        inputs = [[rng.randrange(8), rng.randrange(8)] for _ in range(30)]
        for turns in (1, 2, 3):
            base = Game([Player(a.sx, a.sy, 0, "C"), Player(b.sx, b.sy, 0, "M")])
            turned = Game([Player(*rotate_player(a, turns), "C"), Player(*rotate_player(b, turns), "M")])
            for step in inputs:
                base.tick(step)
                turned.tick([(d + 2 * turns) % 8 for d in step])
            for p, q in zip(base.players, turned.players):
                assert rotate_player(p, turns) == (q.sx, q.sy, q.facing), (trial, turns)


def test_tanks_are_solid():
    game = Game([Player(40, 40, 2, "C"), Player(46, 40, 6, "M")])   # touching, facing each other
    for _ in range(10):
        game.tick([2, 6])
    assert (game.players[0].sx, game.players[1].sx) == (40, 46)


def test_diagonal_slides_along_a_tank():
    # Player 1 sits east of player 0; player 0 heads SE and slides south.
    game = Game([Player(40, 40, 3, "C"), Player(46, 40, 0, "M")])
    for _ in range(10):
        game.tick([3, NO_DIRECTION])
    assert game.players[0].sx == 40 and game.players[0].sy > 40


def test_diagonal_into_a_corner_between_tanks_stops():
    # Both single-axis steps clear, diagonal blocked by a tank to the SE.
    game = Game([Player(40, 40, 3, "C"), Player(46, 46, 0, "M")])
    game.players[0].accumulator = 255
    game.tick([3, NO_DIRECTION])
    assert (game.players[0].sx, game.players[0].sy) == (40, 40)


def test_first_mover_rotates_each_tick():
    """Two tanks racing for the same cell: each tick a different one gets it."""
    winners = []
    for first_tick in range(2):
        game = Game([Player(40, 40, 2, "C"), Player(47, 40, 6, "M")], ticks=first_tick)
        game.players[0].accumulator = game.players[1].accumulator = 255
        game.tick([2, 6])        # both step into the one-cell gap
        winners.append((game.players[0].sx, game.players[1].sx))
    assert winners[0] != winners[1]
