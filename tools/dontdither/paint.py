"""The painting rule: one paint application moves a cell one quantum towards
the painter.

A cell's ink state is the count tuple (C, M, Y, K) summing to 4. Applying the
painter's ink increments the painter's count and decrements one other ink
present in the cell, the victim. Victims are chosen round-robin per painter:
starting after the painter's last victim, take the first other ink with a
non-zero count. A cell already solidly the painter's is unchanged and does not
advance the round-robin. Inks without a player (neutral inks in a two-player
game) are victims like any other.

A splat applies paint once to each of its cells that walls do not shadow
(see splats.ray_tree), in the tree's order, so the round-robin advances
across the cells of a single shot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dontdither.inks import INKS, State


def paint_cell(state: State, painter: int, last_victim: int) -> tuple[State, int]:
    """Apply one quantum of the painter's ink (an index into INKS).

    Returns the new state and the painter's new last victim.
    """
    if state[painter] == len(INKS):
        return state, last_victim
    victim = (last_victim + 1) % len(INKS)
    while victim == painter or state[victim] == 0:
        victim = (victim + 1) % len(INKS)
    counts = list(state)
    counts[victim] -= 1
    counts[painter] += 1
    return tuple(counts), victim  # type: ignore[return-value]


@dataclass
class Painter:
    """One player's painting state: their ink and round-robin position."""

    ink: int
    last_victim: int = field(default=-1)

    def __post_init__(self) -> None:
        if self.last_victim < 0:
            self.last_victim = self.ink    # first victim is the next ink round


def apply_splat(
    grid: dict[tuple[int, int], State],
    painter: Painter,
    tree,
    origin: tuple[int, int] = (0, 0),
) -> None:
    """Fire one shot. `tree` is the splat's shadowing tree (splats.RayTree)
    in footprint-relative cells; `origin` is the footprint's top-left cell in
    the grid. Grid cells that are absent are walls (or outside the arena):
    they, and every cell they shadow, are not painted."""
    from dontdither.splats import unblocked_cells

    ox, oy = origin
    for cx, cy in unblocked_cells(tree, lambda c: (c[0] + ox, c[1] + oy) not in grid):
        cell = (cx + ox, cy + oy)
        grid[cell], painter.last_victim = paint_cell(grid[cell], painter.ink, painter.last_victim)
