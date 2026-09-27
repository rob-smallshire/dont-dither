"""Level source files, their compiled bytecode, and the model of their expansion.

A level is a text file in levels/, compiled in filename order. Blank lines and
text after '#' are ignored. Directives:

    NAME <text>                 title, mixed case, at most 24 characters (shown on
                                a title card before the level is played)
    SYMMETRY ROT4 | ROT2        fourfold (four players) or twofold symmetry
    WALLS <core> <rim>          wall colouring, two different inks of C M Y K
    FILL <c> <m> <y> <k>        initial ink state of open cells (default 1 1 1 1)
    START <sx> <sy> <facing>    player 0's start: top-left superpixel (0..127)
                                of its 6x6 footprint, and facing N NE E SE S
                                SW W NW; other players by symmetry
    TUNNELS                     mouths in the border, centred on the edges the
                                symmetry pairs (left and right; on four-player
                                levels top and bottom too), joined by tunnels
                                (see game.py)
    MOVE <cx> <cy>              move the pen to wall cell (0..31)
    DRAW <cx> <cy>              draw wall cells from the pen to here inclusive,
                                horizontally or vertically, and move the pen

Every level has a border: the outermost ring of wall cells, which the game
draws itself (it is not stored). Only the stored geometry is written; the
renderer repeats it under the symmetry: ROT4 applies 0, 1, 2 and 3 clockwise
quarter turns about the arena centre, ROT2 applies 0 and 2. A quarter turn
maps wall cell (x, y) to (31 - y, x).

Bytecode, made compact so that as many levels as possible fit the game's
level area:
    header   symmetry step (quarter turns between copies: 1 ROT4, 2 ROT2;
             TUNNELS_BIT set if the level has tunnels),
             core ink byte, rim ink byte, fill state, and player 0's start
             sx, sy and facing (HEADER_SIZE bytes)
    commands two bytes each: cx, with bit 7 set for DRAW (clear for MOVE),
             then cy
    END      a single byte
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from pathlib import Path

from dontdither.inks import INKS, PROJECT_DIRPATH, InkTable, State
from dontdither.walls import WALL_GRID_CELLS, Colouring, WallCells, check_colouring, full_byte

LEVELS_DIRPATH = PROJECT_DIRPATH / "levels"

ARENA_SUPERPIXELS = 128
PLAYER_FOOTPRINT = 6          # superpixels per side of a player's sprite
NAME_LENGTH = 24              # shown centred on a title card across the arena (32 columns)

FACINGS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")   # clockwise from north


class LevelOp(enum.IntEnum):
    MOVE = 0
    DRAW = 1


DRAW_BIT = 0x80                # in a command's first byte (cx)
TUNNELS_BIT = 0x80             # in the header's symmetry byte
MOUTH_CELLS = range(14, 18)    # a tunnel mouth: 4 cells in the middle of an edge
END = 0xFF                     # the byte ending a level's commands
HEADER_SIZE = 7


def border_cells(mouths: str = "") -> set[tuple[int, int]]:
    """The outermost ring of wall cells, which every level has, less any
    tunnel mouths: "LR" in the left and right edges, "LRTB" in all four."""
    last = WALL_GRID_CELLS - 1
    cells = {(x, y) for x in range(WALL_GRID_CELLS) for y in range(WALL_GRID_CELLS)
             if x in (0, last) or y in (0, last)}
    for m in MOUTH_CELLS:
        if "L" in mouths:
            cells -= {(0, m), (last, m)}
        if "T" in mouths:
            cells -= {(m, 0), (m, last)}
    return cells


class Symmetry(enum.IntEnum):
    """Value is the number of clockwise quarter turns between copies."""

    ROT4 = 1
    ROT2 = 2

    @property
    def copies(self) -> int:
        return 4 // self.value


class LevelError(ValueError):
    pass


@dataclass(frozen=True)
class Start:
    sx: int
    sy: int
    facing: int   # index into FACINGS


@dataclass(frozen=True)
class Level:
    name: str
    symmetry: Symmetry
    colouring: Colouring
    fill: State
    start: Start
    commands: tuple[tuple[LevelOp, int, int], ...] = field(default=())
    tunnels: bool = False

    @property
    def mouths(self) -> str:
        if not self.tunnels:
            return ""
        return "LRTB" if self.symmetry.copies == 4 else "LR"

    # ---- Model of the expansion -----------------------------------------------

    def stored_cells(self) -> list[tuple[int, int]]:
        """Wall cells drawn by the stored commands, before symmetry."""
        cells = []
        pen = None
        for op, x, y in self.commands:
            if op is LevelOp.MOVE:
                pen = (x, y)
            elif op is LevelOp.DRAW:
                assert pen is not None
                cells.extend(line_cells(pen, (x, y)))
                pen = (x, y)
        return cells

    def wall_cells(self) -> WallCells:
        """All wall cells after applying the symmetry, and the border."""
        cells = border_cells(self.mouths)
        for copy in range(self.symmetry.copies):
            turns = copy * self.symmetry.value
            cells.update(rotate_cell(c, turns) for c in self.stored_cells())
        return frozenset(cells)

    def starts(self) -> list[Start]:
        """Every player's start: player k gets k symmetry steps of rotation."""
        return [rotate_start(self.start, k * self.symmetry.value) for k in range(self.symmetry.copies)]

    def player_inks(self) -> list[str]:
        """Each player's ink: player slot k always takes ink k (C, M, Y, K),
        so players keep their colours across a session. A two-player level
        is played by slots 0 and 1 (C and M), leaving Y and K neutral."""
        return [INKS[k] for k in range(self.symmetry.copies)]

    # ---- Bytecode ----------------------------------------------------------------

    def bytecode(self, table: InkTable) -> bytes:
        data = [
            self.symmetry.value | (TUNNELS_BIT if self.tunnels else 0),
            full_byte(self.colouring.core),
            full_byte(self.colouring.rim),
            table.states.index(self.fill),
            self.start.sx, self.start.sy, self.start.facing,
        ]
        assert len(data) == HEADER_SIZE
        for op, x, y in self.commands:
            data += [x | (DRAW_BIT if op is LevelOp.DRAW else 0), y]
        data.append(END)
        return bytes(data)


def line_cells(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """Cells from a to b inclusive along a horizontal or vertical line."""
    (x0, y0), (x1, y1) = a, b
    dx = (x1 > x0) - (x1 < x0)
    dy = (y1 > y0) - (y1 < y0)
    cells = [(x0, y0)]
    while cells[-1] != (x1, y1):
        x, y = cells[-1]
        cells.append((x + dx, y + dy))
    return cells


def rotate_cell(cell: tuple[int, int], quarter_turns: int) -> tuple[int, int]:
    x, y = cell
    for _ in range(quarter_turns % 4):
        x, y = WALL_GRID_CELLS - 1 - y, x
    return x, y


def rotate_start(start: Start, quarter_turns: int) -> Start:
    """Rotate a footprint's top-left corner, keeping it the top-left corner."""
    sx, sy = start.sx, start.sy
    for _ in range(quarter_turns % 4):
        sx, sy = ARENA_SUPERPIXELS - PLAYER_FOOTPRINT - sy, sx
    return Start(sx, sy, (start.facing + 2 * quarter_turns) % 8)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _int(token: str, low: int, high: int, what: str) -> int:
    try:
        value = int(token)
    except ValueError:
        raise LevelError(f"{what} must be an integer, not {token!r}") from None
    if not low <= value <= high:
        raise LevelError(f"{what} must be in {low}..{high}, not {value}")
    return value


def parse_level(text: str, source: str = "<level>") -> Level:
    name = None
    symmetry = None
    colouring = None
    fill: State = (1, 1, 1, 1)
    start = None
    tunnels = False
    commands: list[tuple[LevelOp, int, int]] = []
    pen = None

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        keyword, *args = line.split()
        keyword = keyword.upper()
        where = f"{source}:{number}"
        try:
            if keyword == "NAME":
                name = line.split(None, 1)[1].strip() if args else ""
                if not 1 <= len(name) <= NAME_LENGTH or not re.fullmatch(r"[ !#-~]+", name):
                    raise LevelError(f"NAME must be 1..{NAME_LENGTH} printable characters, excluding \"")
            elif keyword == "SYMMETRY":
                (value,) = args
                symmetry = Symmetry[value.upper()]
            elif keyword == "WALLS":
                core, rim = (a.upper() for a in args)
                colouring = Colouring(core, rim)
                check_colouring(colouring)
            elif keyword == "FILL":
                counts = tuple(_int(a, 0, 4, "FILL count") for a in args)
                if len(counts) != len(INKS) or sum(counts) != 4:
                    raise LevelError("FILL needs four counts (C M Y K) summing to 4")
                fill = counts  # type: ignore[assignment]
            elif keyword == "START":
                sx, sy, facing = args
                limit = ARENA_SUPERPIXELS - PLAYER_FOOTPRINT
                start = Start(_int(sx, 0, limit, "START sx"), _int(sy, 0, limit, "START sy"),
                              FACINGS.index(facing.upper()))
            elif keyword == "TUNNELS":
                if args:
                    raise LevelError("TUNNELS takes no arguments")
                tunnels = True
            elif keyword in ("MOVE", "DRAW"):
                x, y = (_int(a, 0, WALL_GRID_CELLS - 1, f"{keyword} coordinate") for a in args)
                if keyword == "DRAW":
                    if pen is None:
                        raise LevelError("DRAW before any MOVE")
                    if pen[0] != x and pen[1] != y:
                        raise LevelError(f"DRAW from {pen} to {(x, y)} is not horizontal or vertical")
                pen = (x, y)
                commands.append((LevelOp[keyword], x, y))
            else:
                raise LevelError(f"Unknown directive {keyword!r}")
        except (LevelError, ValueError, KeyError) as e:
            raise LevelError(f"{where}: {e}") from None

    for value, directive in ((name, "NAME"), (symmetry, "SYMMETRY"), (colouring, "WALLS"), (start, "START")):
        if value is None:
            raise LevelError(f"{source}: missing {directive}")
    return Level(name, symmetry, colouring, fill, start, tuple(commands), tunnels)  # type: ignore[arg-type]


PLAYER_COUNTS = (2, 4)


def level_set(players: int, dirpath: Path = LEVELS_DIRPATH) -> list[Level]:
    """The levels for a two- or four-player game, in filename order."""
    return [lv for lv in load_levels(dirpath) if lv.symmetry.copies == players]


def level_filepaths(dirpath: Path = LEVELS_DIRPATH) -> list[Path]:
    return sorted(dirpath.glob("*.lvl"))


def load_levels(dirpath: Path = LEVELS_DIRPATH) -> list[Level]:
    return [parse_level(p.read_text(), p.name) for p in level_filepaths(dirpath)]
