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


def start_without_ai(level):
    """A game where every player follows the given inputs (no AI players)."""
    game = Game.start(level)
    for player in game.players:
        player.ai = False
    return game
STILL = NO_DIRECTION
STILL_FIRE = NO_DIRECTION | FIRE_BIT


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


def test_walls_stop_tanks():
    # A wall cell at (10, 10) covers superpixels 40..43; a tank moving east
    # at sy 40 stops with its footprint (sx..sx+5) just short of it.
    game = Game([Player(20, 40, 2, "C")], walls=frozenset({(10, 10)}))
    for _ in range(40):
        game.tick([2])
    assert game.players[0].sx == 34


def test_diagonal_slides_along_a_wall():
    # A wall along row 10 (superpixels 40..43) below a tank heading SE.
    wall = frozenset((cx, 10) for cx in range(32))
    game = Game([Player(20, 30, 3, "C")], walls=wall)
    for _ in range(40):
        game.tick([3])
    player = game.players[0]
    assert player.sy == 34 and player.sx > 30


def test_footprint_covers_two_or_three_wall_cells_each_way():
    from dontdither.game import footprint_wall_cells
    assert len(footprint_wall_cells(0, 0)) == 4        # 0..5: cells 0, 1
    assert len(footprint_wall_cells(3, 3)) == 9        # 3..8: cells 0, 1, 2


def test_players_fire_on_ticks_of_their_own_parity():
    """Player 1 holding fire from tick 0 first shoots on tick 1, when
    (tick + player) is even."""
    from dontdither.levels import load_levels

    game = start_without_ai(load_levels()[0])
    for p in game.players:
        p.facing = 2
    fired = []
    for _ in range(3):
        before = dict(game.cells)
        game.tick([STILL, STILL_FIRE, STILL, STILL])
        fired.append(game.cells != before)
    assert fired == [False, True, False]


def test_holding_fire_shoots_every_fire_period_ticks():
    from dontdither.game import FIRE_PERIOD
    from dontdither.levels import load_levels

    game = start_without_ai(load_levels()[0])
    shots = []
    for t in range(3 * FIRE_PERIOD):
        before = dict(game.cells)
        game.tick([NO_DIRECTION | FIRE_BIT, NO_DIRECTION, NO_DIRECTION, NO_DIRECTION])
        if game.cells != before:
            shots.append(t)
    assert shots == [0, FIRE_PERIOD, 2 * FIRE_PERIOD]


def test_a_shot_moves_its_cells_one_quantum_towards_the_shooter():
    from dontdither.levels import load_levels

    game = start_without_ai(load_levels()[0])
    game.players[0].facing = 2        # east, into open space (SE hits a wall)
    game.tick([NO_DIRECTION | FIRE_BIT, NO_DIRECTION, NO_DIRECTION, NO_DIRECTION])
    changed = [s for s in game.cells.values() if s != (1, 1, 1, 1)]
    assert len(changed) == 16
    assert all(s[0] == 2 and sum(s) == 4 for s in changed)


def test_a_shot_at_a_wall_is_shadowed():
    from dontdither.levels import load_levels

    game = start_without_ai(load_levels()[0])        # player 0 faces SE, at a wall
    game.tick([NO_DIRECTION | FIRE_BIT, NO_DIRECTION, NO_DIRECTION, NO_DIRECTION])
    changed = [s for s in game.cells.values() if s != (1, 1, 1, 1)]
    assert 0 < len(changed) < 16


def test_round_ends_after_its_ticks_and_nothing_moves_after():
    from dontdither.levels import load_levels

    game = start_without_ai(load_levels()[0])
    game.round_ticks_left = 5
    for _ in range(5):
        game.tick([2, STILL, STILL, STILL])
    assert game.round_over
    position = (game.players[0].sx, game.players[0].sy)
    game.tick([2, STILL, STILL, STILL])
    assert (game.players[0].sx, game.players[0].sy) == position


def test_the_grey_start_gives_every_player_a_quarter():
    from dontdither.levels import load_levels

    game = start_without_ai(load_levels()[0])
    assert game.percentages() == [25, 25, 25, 25]
    total = 4 * len(game.cells)
    assert game.ink_quanta() == [total // 4] * 4


def test_round_points_by_rank():
    from dontdither.game import round_points
    assert round_points([30, 20, 25, 25]) == [3, 0, 2, 2]      # joint second both score 2
    assert round_points([40, 20, 25, 15]) == [3, 1, 2, 0]
    assert round_points([25, 25, 25, 25]) == [3, 3, 3, 3]
    assert round_points([30, 30, 20, 20]) == [3, 3, 1, 1]
    assert round_points([60, 40]) == [3, 0]
    assert round_points([50, 50]) == [3, 3]
