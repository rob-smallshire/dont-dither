"""Tunnels (tools/dontdither/game.py, levels.py). No emulator needed.

A level with TUNNELS has mouths in its border, centred on the edges its
symmetry pairs; a tank leaving through one is out of play for TUNNEL_TICKS,
then comes out of the opposite mouth.
"""

from dontdither.game import (
    FIRE_BIT,
    MAX_POSITION,
    MOUTH_HIGH,
    MOUTH_LOW,
    NO_DIRECTION,
    TUNNEL_TICKS,
    Game,
)
from dontdither.levels import MOUTH_CELLS, border_cells, parse_level

N, E, S, W, NW = 0, 2, 4, 6, 7
STILL = NO_DIRECTION


def level(symmetry: str = "ROT2", tunnels: bool = True):
    return parse_level(f"""
NAME Test
SYMMETRY {symmetry}
WALLS K Y
START 60 20 S
{"TUNNELS" if tunnels else ""}
MOVE 8 8
DRAW 9 8
""")


def game(symmetry: str = "ROT2", tunnels: bool = True) -> Game:
    g = Game.start(level(symmetry, tunnels))
    for p in g.players:
        p.ai = False
    return g


def park(g: Game, index: int, sx: int, sy: int, facing: int = W) -> None:
    p = g.players[index]
    p.sx, p.sy, p.facing = sx, sy, facing


# ---- The border ------------------------------------------------------------------

def test_two_player_tunnels_open_the_left_and_right_edges():
    walls = level("ROT2").wall_cells()
    for m in MOUTH_CELLS:
        assert (0, m) not in walls and (31, m) not in walls
        assert (m, 0) in walls and (m, 31) in walls


def test_four_player_tunnels_open_all_four_edges():
    walls = level("ROT4").wall_cells()
    for m in MOUTH_CELLS:
        assert {(0, m), (31, m), (m, 0), (m, 31)}.isdisjoint(walls)


def test_without_tunnels_the_border_is_whole():
    assert border_cells() <= level(tunnels=False).wall_cells()


def test_the_mouth_fits_a_footprint():
    assert MOUTH_LOW == 4 * MOUTH_CELLS[0] and MOUTH_HIGH + 6 == 4 * (MOUTH_CELLS[-1] + 1)


# ---- Going through ---------------------------------------------------------------

def drive(g: Game, inputs, ticks: int) -> None:
    for _ in range(ticks):
        g.tick(inputs)


def into_tunnel(g: Game, inputs, limit: int = 10) -> None:
    """Drive until player 0 goes into a tunnel."""
    for _ in range(limit):
        g.tick(inputs)
        if g.players[0].in_tunnel:
            return
    raise AssertionError("never went into the tunnel")


def test_a_tank_goes_through_the_tunnel_and_out_the_other_side():
    g = game()
    park(g, 0, 0, 60)
    into_tunnel(g, [W, STILL])                  # steps out of the mouth
    p = g.players[0]
    for _ in range(TUNNEL_TICKS - 1):
        g.tick([W, STILL])
        assert p.in_tunnel
    g.tick([W, STILL])
    assert not p.in_tunnel
    assert (p.sx, p.sy, p.facing) == (MAX_POSITION, 60, W)


def test_outside_a_mouth_the_edge_is_a_wall():
    g = game()
    park(g, 0, 4, 30)                           # beside the border, off the mouth
    drive(g, [W, STILL], 20)
    assert not g.players[0].in_tunnel and g.players[0].sx == 4


def test_the_whole_footprint_must_be_within_the_mouth():
    g = game()
    park(g, 0, 0, MOUTH_HIGH)
    drive(g, [W, STILL], 5)
    assert g.players[0].in_tunnel
    g = game()
    park(g, 0, 0, MOUTH_HIGH + 1)               # overlaps the border below the mouth
    drive(g, [W, STILL], 5)
    assert not g.players[0].in_tunnel


def test_a_diagonal_step_does_not_enter_a_tunnel():
    g = game()
    park(g, 0, 0, 60, NW)
    drive(g, [NW, STILL], 5)
    assert not g.players[0].in_tunnel


def test_top_and_bottom_mouths_only_on_four_player_levels():
    g = game("ROT4")
    park(g, 0, 60, 0, N)
    into_tunnel(g, [N, STILL, STILL, STILL])
    drive(g, [STILL] * 4, TUNNEL_TICKS)
    p = g.players[0]
    assert not p.in_tunnel and (p.sx, p.sy) == (60, MAX_POSITION)
    g = game("ROT2")
    park(g, 0, 60, 4, N)
    drive(g, [N, STILL], 20)
    assert not g.players[0].in_tunnel


# ---- Out of play -----------------------------------------------------------------

def test_in_the_tunnel_a_tank_neither_fires_nor_refills():
    g = game()
    park(g, 0, 0, 60)
    g.players[0].reservoir = 50
    drive(g, [W, STILL], 3)
    before = dict(g.cells)
    drive(g, [W | FIRE_BIT, STILL], TUNNEL_TICKS - 2)
    assert g.cells == before and g.players[0].reservoir == 50
    drive(g, [STILL, STILL], 1)
    assert g.players[0].reservoir == 50


def test_a_tank_in_the_tunnel_is_in_nobody_s_way():
    g = game()
    park(g, 0, 0, 60)
    park(g, 1, 10, 60)                          # right behind it
    drive(g, [W, STILL], 3)
    assert g.players[0].in_tunnel
    drive(g, [STILL, W], 20)                    # player 1 drives up to the mouth...
    assert g.players[1].sx == 0 or g.players[1].in_tunnel   # ...and on in


def test_a_blocked_exit_waits_until_it_is_clear():
    g = game()
    park(g, 0, 0, 60)
    park(g, 1, MAX_POSITION, 60, E)              # sitting in the far mouth
    drive(g, [W, STILL], 3 + TUNNEL_TICKS + 10)
    assert g.players[0].in_tunnel                # still waiting
    drive(g, [STILL, W], 20)                     # player 1 moves off
    assert not g.players[0].in_tunnel
    assert (g.players[0].sx, g.players[0].sy) == (MAX_POSITION, 60)
