"""The painting rule (see tools/dontdither/paint.py). No emulator needed."""

from dontdither.inks import INKS, all_states
from dontdither.paint import Painter, apply_splat, paint_cell
from dontdither.splats import load_trees

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


def open_grid(size=30, offset=10):
    return {(x, y): (1, 1, 1, 1) for x in range(-offset, size - offset) for y in range(-offset, size - offset)}


def test_unobstructed_splat_paints_all_sixteen_cells():
    tree = load_trees()["E"][0]
    grid = open_grid()
    apply_splat(grid, Painter(C), tree)
    assert sum(1 for s in grid.values() if s != (1, 1, 1, 1)) == 16


def test_wall_in_the_gap_blocks_the_whole_splat():
    tree = load_trees()["E"][0]
    grid = open_grid()
    for y in range(-10, 20):
        grid.pop((6, y), None)          # a wall column just beyond the footprint
    apply_splat(grid, Painter(C), tree)
    assert all(s == (1, 1, 1, 1) for s in grid.values())


def test_wall_shadows_only_the_cells_behind_it():
    tree = load_trees()["E"][0]
    splat = [n.cell for n in tree if n.paints]
    grid = open_grid()
    wall = (11, 3)
    assert wall in splat
    grid.pop(wall)
    apply_splat(grid, Painter(C), tree)
    painted = {c for c, s in grid.items() if s != (1, 1, 1, 1)}
    shadowed = set(splat) - painted - {wall}
    assert 0 < len(painted) < 16
    assert all(x > wall[0] for x, _ in shadowed), "only cells beyond the wall are shadowed"
