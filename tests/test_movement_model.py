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
