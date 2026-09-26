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
