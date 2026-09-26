"""The painting rule (see tools/dontdither/paint.py). No emulator needed."""

from dontdither.inks import INKS, all_states
from dontdither.paint import Painter, apply_splat, paint_cell

C, M, Y, K = range(4)


def test_one_application_transfers_exactly_one_quantum():
    for state in all_states():
        for painter in range(4):
            if state[painter] == 4:
                continue
            new, victim = paint_cell(state, painter, painter)
            assert sum(new) == 4
            assert new[painter] == state[painter] + 1
            assert new[victim] == state[victim] - 1
            assert victim != painter


def test_own_solid_cell_is_unchanged_and_keeps_the_round_robin():
    assert paint_cell((4, 0, 0, 0), C, Y) == ((4, 0, 0, 0), Y)


def test_three_hits_turn_the_grey_start_solid():
    state, last = (1, 1, 1, 1), C
    for _ in range(3):
        state, last = paint_cell(state, C, last)
    assert state == (4, 0, 0, 0)


def test_capturing_an_opponents_solid_cell_takes_four_hits():
    state, last = (0, 4, 0, 0), C
    for hits in range(1, 5):
        state, last = paint_cell(state, C, last)
        assert state[C] == hits


def test_victims_rotate_round_the_other_inks():
    victims = []
    last = C
    for _ in range(3):
        _, last = paint_cell((1, 1, 1, 1), C, last)
        victims.append(last)
    assert victims == [M, Y, K]


def test_absent_inks_are_skipped_without_using_a_turn():
    # Painter Y, last victim K: the search starts at C, which is present.
    new, victim = paint_cell((1, 0, 1, 2), Y, K)
    assert victim == C and new == (0, 0, 2, 2)
    # Now C and M are absent and Y is the painter, so the search wraps round
    # to K again.
    new, victim = paint_cell((0, 0, 2, 2), Y, K)
    assert victim == K and new == (0, 0, 3, 1)


def test_the_rule_is_the_same_for_every_player_under_relabelling():
    """Cycling ink labels commutes with painting."""
    def cycle(state):
        return (state[3], state[0], state[1], state[2])

    for state in all_states():
        for painter in range(4):
            if state[painter] == 4:
                continue
            for last in range(4):
                new, victim = paint_cell(state, painter, last)
                new2, victim2 = paint_cell(cycle(state), (painter + 1) % 4, (last + 1) % 4)
                assert new2 == cycle(new) and victim2 == (victim + 1) % 4


def test_splat_skips_cells_outside_the_grid_without_advancing():
    grid = {(0, 0): (1, 1, 1, 1), (2, 0): (1, 1, 1, 1)}
    painter = Painter(INKS.index("C"))
    apply_splat(grid, painter, [(0, 0), (1, 0), (2, 0)])   # (1, 0) is a wall
    assert grid == {(0, 0): (2, 0, 1, 1), (2, 0): (2, 1, 0, 1)}
