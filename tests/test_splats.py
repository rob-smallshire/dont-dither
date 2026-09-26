"""Paint splat geometry: size, gap, rotation and fairness. No emulator needed."""

import math

import pytest

from dontdither.splats import (
    FOOTPRINT,
    SPLAT_CELLS,
    SplatError,
    load_splats,
    parse_splats,
    rotate_clockwise,
)
from dontdither.sprites import FACINGS

FACING_ANGLE = {f: 90 - 45 * i for i, f in enumerate(FACINGS)}   # N 90, NE 45, E 0, ...
CENTRE = (FOOTPRINT - 1) / 2


@pytest.fixture(scope="module")
def splats():
    return load_splats()


def centroid(splat):
    return (sum(x for x, _ in splat) / len(splat) - CENTRE, sum(y for _, y in splat) / len(splat) - CENTRE)


def test_every_facing_has_the_same_number_of_variants(splats):
    assert len({len(v) for v in splats.values()}) == 1


def test_every_splat_paints_sixteen_distinct_cells(splats):
    for variants in splats.values():
        for splat in variants:
            assert len(set(splat)) == SPLAT_CELLS


def test_no_splat_touches_the_footprint(splats):
    for variants in splats.values():
        for splat in variants:
            assert not any(-1 <= x <= FOOTPRINT and -1 <= y <= FOOTPRINT for x, y in splat)


def test_facings_are_quarter_turns_of_each_other(splats):
    for i, facing in enumerate(FACINGS):
        turned = [rotate_clockwise(v) for v in splats[facing]]
        assert splats[FACINGS[(i + 2) % 8]] == turned


@pytest.mark.parametrize("facing", FACINGS)
def test_splats_lie_along_their_facing(splats, facing):
    for splat in splats[facing]:
        dx, dy = centroid(splat)
        angle = math.degrees(math.atan2(-dy, dx))
        error = (angle - FACING_ANGLE[facing] + 180) % 360 - 180
        assert abs(error) <= 6, f"{facing} splat centroid at {angle:.1f} degrees"


def test_axial_and_diagonal_splats_reach_equally_far(splats):
    distances = [math.hypot(*centroid(s)) for f in ("E", "NE") for s in splats[f]]
    assert max(distances) - min(distances) <= 0.6


def test_miscounted_splat_is_rejected():
    grid = "E 1\nTTTTTT..*\n" + "TTTTTT...\n" * 5
    with pytest.raises(SplatError, match="exactly 16"):
        parse_splats(grid + "NE 1\n" + grid.split("\n", 1)[1])


def test_ray_trees_list_parents_before_children_and_cover_the_splat():
    from dontdither.splats import load_trees

    trees = load_trees()
    for facing in FACINGS:
        for tree, splat in zip(trees[facing], load_splats()[facing]):
            assert all(n.parent < i for i, n in enumerate(tree))
            assert sorted(n.cell for n in tree if n.paints) == list(splat)
            assert not any(0 <= x < FOOTPRINT and 0 <= y < FOOTPRINT for x, y in (n.cell for n in tree))


def test_ray_tree_parents_are_adjacent_cells():
    from dontdither.splats import load_trees

    for trees in load_trees().values():
        for tree in trees:
            for node in tree:
                if node.parent >= 0:
                    px, py = tree[node.parent].cell
                    assert max(abs(px - node.cell[0]), abs(py - node.cell[1])) == 1
