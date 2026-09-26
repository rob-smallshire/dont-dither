"""Paint splats: the superpixel cells one shot paints, relative to the tank.

A splat file (sprites/splats.spr) holds numbered variants for facings E and
NE, each drawn next to the tank's 6x6-superpixel footprint. The other six
facings are exact clockwise quarter turns about the footprint's centre, which
map footprint-relative cell (x, y) to (5 - y, x). Successive shots cycle
through the variants.
"""

from __future__ import annotations

from pathlib import Path

from dontdither.inks import PROJECT_DIRPATH
from dontdither.sprites import FACINGS

SPLATS_FILEPATH = PROJECT_DIRPATH / "sprites" / "splats.spr"

FOOTPRINT = 6          # superpixels per side of the tank's footprint
SPLAT_CELLS = 16       # cells painted by every splat

Cell = tuple[int, int]
Splat = tuple[Cell, ...]   # footprint-relative cells, sorted


class SplatError(ValueError):
    pass


def _parse_grid(rows: list[str], where: str) -> Splat:
    footprint = [(x, y) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "T"]
    paint = [(x, y) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "*"]
    stray = {ch for row in rows for ch in row} - set("T*.")
    if stray:
        raise SplatError(f"{where}: unexpected characters {sorted(stray)}")
    if len(footprint) != FOOTPRINT * FOOTPRINT:
        raise SplatError(f"{where}: the footprint must be a {FOOTPRINT}x{FOOTPRINT} block of 'T'")
    ox = min(x for x, _ in footprint)
    oy = min(y for _, y in footprint)
    if set(footprint) != {(ox + i, oy + j) for i in range(FOOTPRINT) for j in range(FOOTPRINT)}:
        raise SplatError(f"{where}: the footprint must be a {FOOTPRINT}x{FOOTPRINT} block of 'T'")
    if len(paint) != SPLAT_CELLS:
        raise SplatError(f"{where}: a splat must paint exactly {SPLAT_CELLS} cells, not {len(paint)}")
    cells = tuple(sorted((x - ox, y - oy) for x, y in paint))
    for x, y in cells:
        if -1 <= x <= FOOTPRINT and -1 <= y <= FOOTPRINT:
            raise SplatError(f"{where}: cell {(x, y)} touches the footprint; leave a one-cell gap")
    return cells


def parse_splats(text: str, source: str = "<splats>") -> dict[str, list[Splat]]:
    """Parse the E and NE variants, in file order."""
    grids: dict[str, list[tuple[int, list[str]]]] = {"E": [], "NE": []}
    current: list[str] | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        heading = line.split()
        if heading[0] in grids and len(heading) == 2 and heading[1].isdigit():
            current = []
            grids[heading[0]].append((number, current))
            continue
        if current is None:
            raise SplatError(f"{source}:{number}: grid row before a heading such as 'E 1'")
        current.append(line)
    splats = {}
    for facing, entries in grids.items():
        if not entries:
            raise SplatError(f"{source}: no {facing} splats")
        splats[facing] = [_parse_grid(rows, f"{source}:{number}") for number, rows in entries]
    if len(splats["E"]) != len(splats["NE"]):
        raise SplatError(f"{source}: E and NE must have the same number of variants")
    return splats


def rotate_clockwise(splat: Splat) -> Splat:
    return tuple(sorted((FOOTPRINT - 1 - y, x) for x, y in splat))


def all_facings(splats: dict[str, list[Splat]]) -> dict[str, list[Splat]]:
    """Every facing's variants: E and NE as drawn, the rest by quarter turns."""
    result = {}
    for base in ("E", "NE"):
        variants = splats[base]
        index = FACINGS.index(base)
        for turn in range(4):
            result[FACINGS[(index + 2 * turn) % 8]] = variants
            variants = [rotate_clockwise(v) for v in variants]
    return {facing: result[facing] for facing in FACINGS}


def load_splats(filepath: Path = SPLATS_FILEPATH) -> dict[str, list[Splat]]:
    return all_facings(parse_splats(filepath.read_text(), filepath.name))


# ---------------------------------------------------------------------------
# Wall shadowing
# ---------------------------------------------------------------------------
#
# Walls stop splats: a splat cell is painted only if the straight line from
# the centre of the tank's footprint to the cell crosses no wall. This is
# precomputed as a tree. Every cell on the line to a splat cell (outside the
# footprint) is a node whose parent is the previous cell on that line; the
# 6502 walks the nodes in order, marking a node blocked if it is a wall or
# its parent is blocked, and paints unblocked splat nodes.

from dataclasses import dataclass


@dataclass(frozen=True)
class RayNode:
    cell: Cell
    parent: int        # index of the parent node, or -1 if next to the footprint
    paints: bool       # True for splat cells, False for cells merely passed over


RayTree = tuple[RayNode, ...]

_ORIGIN = FOOTPRINT / 2    # centre of the footprint, in cell-corner coordinates
_STEPS = 200


def _line_cells(target: Cell) -> list[Cell]:
    """Cells crossed by the line from the footprint centre to a cell's centre,
    in order, excluding footprint cells."""
    tx, ty = target[0] + 0.5, target[1] + 0.5
    cells: list[Cell] = []
    for i in range(_STEPS + 1):
        f = i / _STEPS
        x = _ORIGIN + (tx - _ORIGIN) * f
        y = _ORIGIN + (ty - _ORIGIN) * f
        cell = (int(x // 1), int(y // 1))
        inside = 0 <= cell[0] < FOOTPRINT and 0 <= cell[1] < FOOTPRINT
        if not inside and (not cells or cells[-1] != cell):
            cells.append(cell)
    return cells


def ray_tree(splat: Splat) -> RayTree:
    """The shadowing tree for one splat, parents before children."""
    parent_of: dict[Cell, Cell | None] = {}
    for target in splat:
        previous = None
        for cell in _line_cells(target):
            parent_of.setdefault(cell, previous)
            previous = cell
    # Order nodes by distance from the footprint centre; a parent is always
    # nearer than its child, so it comes first.
    order = sorted(parent_of, key=lambda c: ((c[0] + 0.5 - _ORIGIN) ** 2 + (c[1] + 0.5 - _ORIGIN) ** 2, c))
    index = {cell: i for i, cell in enumerate(order)}
    painted = set(splat)
    return tuple(
        RayNode(cell, -1 if parent_of[cell] is None else index[parent_of[cell]], cell in painted)
        for cell in order
    )


def rotate_tree(tree: RayTree) -> RayTree:
    return tuple(RayNode((FOOTPRINT - 1 - y, x), n.parent, n.paints) for n in tree for (x, y) in [n.cell])


def all_facing_trees(splats: dict[str, list[Splat]]) -> dict[str, list[RayTree]]:
    """Trees for every facing: built for E and NE, rotated for the rest."""
    result = {}
    for base in ("E", "NE"):
        trees = [ray_tree(s) for s in splats[base]]
        index = FACINGS.index(base)
        for turn in range(4):
            result[FACINGS[(index + 2 * turn) % 8]] = trees
            trees = [rotate_tree(t) for t in trees]
    return {facing: result[facing] for facing in FACINGS}


def load_trees(filepath: Path = SPLATS_FILEPATH) -> dict[str, list[RayTree]]:
    return all_facing_trees(parse_splats(filepath.read_text(), filepath.name))


def unblocked_cells(tree: RayTree, is_wall) -> list[Cell]:
    """The splat cells a shot paints, in order, given is_wall(cell) for
    footprint-relative cells."""
    blocked = []
    painted = []
    for node in tree:
        b = is_wall(node.cell) or (node.parent >= 0 and blocked[node.parent])
        blocked.append(b)
        if node.paints and not b:
            painted.append(node.cell)
    return painted
