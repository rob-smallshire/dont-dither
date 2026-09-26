"""Model of the game simulation, tick by tick.

The 6502 game must match this exactly: given the same level and the same
per-tick inputs, positions, facings and accumulators are identical.

Input: each player's input byte per tick is a direction 0..7 (0 = N,
clockwise) or NO_DIRECTION in the low nibble, plus FIRE_BIT.

Movement: a direction input sets the facing at once. Each player has an
8-bit speed accumulator; each tick with a direction it adds the speed for
that direction (axial or diagonal), and when the addition carries past 255
the tank steps one superpixel in that direction. The diagonal speed is the
axial speed divided by sqrt 2, so diagonal travel is no faster.

A step is blocked if the tank's new footprint would leave the arena, cover
any part of a wall cell, or overlap another tank's footprint, either where
that tank is now or where it was at the start of the tick. (Checking both
keeps every tank's old and new pictures clear of every other tank's, which
lets the renderer redraw each tank on its own.) Tanks are solid: they never
overlap. A footprint at superpixel (x, y) covers wall cells x DIV 4 ..
(x + 5) DIV 4 across and likewise down.

Sliding: an axial step is taken if clear. A diagonal step is taken whole if
clear; otherwise, if exactly one of its two single-axis steps is clear, that
one is taken (the tank slides); if both or neither are clear, the tank does
not move. This rule is the same under every rotation, so no facing is
favoured.

Order: players move one after another, and each tick the first to move
rotates: tick t (counting from 0) starts with player t mod player_count.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dontdither.levels import Level
from dontdither.walls import WallCells

NO_DIRECTION = 0x08
DIRECTION_MASK = 0x0F
FIRE_BIT = 0x10

AXIAL_SPEED = 200          # 1/256 superpixel per tick: 200/256 at 25 Hz = 19.5 cells/s
DIAGONAL_SPEED = 141       # AXIAL_SPEED / sqrt(2), per axis

DIRECTION_DX = (0, 1, 1, 1, 0, -1, -1, -1)
DIRECTION_DY = (-1, -1, 0, 1, 1, 1, 0, -1)

FOOTPRINT = 6
MAX_POSITION = 128 - FOOTPRINT      # 122


def direction_of_keys(mask: int) -> int:
    """Direction from a 4-bit key mask (up, down, left, right); opposite keys
    cancel."""
    dy = ((mask >> 1) & 1) - (mask & 1)
    dx = ((mask >> 3) & 1) - ((mask >> 2) & 1)
    if dx == 0 and dy == 0:
        return NO_DIRECTION
    return next(d for d in range(8) if (DIRECTION_DX[d], DIRECTION_DY[d]) == (dx, dy))


def input_of_keys(mask: int) -> int:
    """Input byte from a 5-bit key mask (up, down, left, right, fire)."""
    return direction_of_keys(mask & 0x0F) | (FIRE_BIT if mask & 0x10 else 0)


@dataclass
class Player:
    sx: int
    sy: int
    facing: int
    ink: str
    accumulator: int = 0


def footprints_overlap(ax: int, ay: int, bx: int, by: int) -> bool:
    return abs(ax - bx) < FOOTPRINT and abs(ay - by) < FOOTPRINT


def footprint_wall_cells(x: int, y: int) -> list[tuple[int, int]]:
    """The wall cells a footprint at superpixel (x, y) covers."""
    return [(cx, cy) for cy in range(y // 4, (y + FOOTPRINT - 1) // 4 + 1)
            for cx in range(x // 4, (x + FOOTPRINT - 1) // 4 + 1)]


@dataclass
class Game:
    players: list[Player] = field(default_factory=list)
    ticks: int = 0
    walls: WallCells = frozenset()

    @classmethod
    def start(cls, level: Level) -> Game:
        return cls([Player(s.sx, s.sy, s.facing, ink) for s, ink in zip(level.starts(), level.player_inks())],
                   walls=level.wall_cells())

    def tick(self, inputs: list[int]) -> None:
        """Advance one tick; inputs[p] is player p's input byte."""
        count = len(self.players)
        starts = [(p.sx, p.sy) for p in self.players]
        first = self.ticks % count
        for i in range(count):
            index = (first + i) % count
            self._move(index, inputs[index], starts)
        self.ticks += 1

    def _clear(self, index: int, x: int, y: int, starts) -> bool:
        if not (0 <= x <= MAX_POSITION and 0 <= y <= MAX_POSITION):
            return False
        if any(cell in self.walls for cell in footprint_wall_cells(x, y)):
            return False
        for other, player in enumerate(self.players):
            if other == index:
                continue
            if footprints_overlap(x, y, player.sx, player.sy):
                return False
            if footprints_overlap(x, y, *starts[other]):
                return False
        return True

    def _move(self, index: int, byte: int, starts) -> None:
        player = self.players[index]
        direction = byte & DIRECTION_MASK
        if direction == NO_DIRECTION:
            return
        player.facing = direction
        player.accumulator += DIAGONAL_SPEED if direction % 2 else AXIAL_SPEED
        if player.accumulator < 256:
            return
        player.accumulator -= 256
        dx, dy = DIRECTION_DX[direction], DIRECTION_DY[direction]
        x, y = player.sx, player.sy
        if self._clear(index, x + dx, y + dy, starts):
            player.sx, player.sy = x + dx, y + dy
        elif dx and dy:
            x_clear = self._clear(index, x + dx, y, starts)
            y_clear = self._clear(index, x, y + dy, starts)
            if x_clear and not y_clear:
                player.sx = x + dx
            elif y_clear and not x_clear:
                player.sy = y + dy
