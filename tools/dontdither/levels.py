"""Level source files, their compiled bytecode, and the model of their expansion.

A level is a text file in levels/, compiled in filename order. Blank lines and
text after '#' are ignored. Directives:

    NAME <text>                 display name (at most 8 characters, for the HUD)
    SYMMETRY ROT4 | ROT2        fourfold (four players) or twofold symmetry
    WALLS <core> <rim>          wall colouring, two different inks of C M Y K
    FILL <c> <m> <y> <k>        initial ink state of open cells (default 1 1 1 1)
    START <sx> <sy> <facing>    player 0's start: top-left superpixel (0..127)
                                of its 6x6 footprint, and facing N NE E SE S
                                SW W NW; other players by symmetry
    MOVE <cx> <cy>              move the pen to wall cell (0..31)
    DRAW <cx> <cy>              draw wall cells from the pen to here inclusive,
                                horizontally or vertically, and move the pen

Only the stored geometry is written; the renderer repeats it under the
symmetry: ROT4 applies 0, 1, 2 and 3 clockwise quarter turns about the arena
centre, ROT2 applies 0 and 2. A quarter turn maps wall cell (x, y) to
(31 - y, x).

Bytecode (see LevelOp): a header of symmetry step (quarter turns between
copies: 1 for ROT4, 2 for ROT2), core ink byte, rim ink byte and fill state,
then commands, each an opcode byte followed by its operands, ending with END.
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
NAME_LENGTH = 8               # HUD width in characters

FACINGS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")   # clockwise from north


class LevelOp(enum.IntEnum):
    END = 0
    MOVE = 1
    DRAW = 2
    START = 3


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
        """All wall cells after applying the symmetry."""
        cells = set()
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
            self.symmetry.value,
            full_byte(self.colouring.core),
            full_byte(self.colouring.rim),
            table.states.index(self.fill),
            LevelOp.START, self.start.sx, self.start.sy, self.start.facing,
        ]
        for op, x, y in self.commands:
            data += [op, x, y]
        data.append(LevelOp.END)
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
    return Level(name, symmetry, colouring, fill, start, tuple(commands))  # type: ignore[arg-type]


def level_filepaths(dirpath: Path = LEVELS_DIRPATH) -> list[Path]:
    return sorted(dirpath.glob("*.lvl"))


def load_levels(dirpath: Path = LEVELS_DIRPATH) -> list[Level]:
    return [parse_level(p.read_text(), p.name) for p in level_filepaths(dirpath)]
