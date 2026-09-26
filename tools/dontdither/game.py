"""Model of the game simulation, tick by tick.

The 6502 game must match this exactly: given the same level and the same
per-tick inputs, positions, facings and accumulators are identical.

Input: each player's input byte per tick is a direction 0..7 (0 = N,
clockwise) or NO_DIRECTION in the low nibble, plus FIRE_BIT.

Movement: a direction input sets the facing at once. Each player has an
8-bit speed accumulator; each tick with a direction it adds the speed for
that direction (axial or diagonal), and when the addition carries past 255
the tank steps one superpixel in that direction. The diagonal speed is the
axial speed divided by sqrt 2, so diagonal travel is no faster. Each axis of
a step is taken only if it keeps the footprint inside the arena, so a tank
slides along the arena edge. (Wall collision comes later.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dontdither.levels import Level

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


@dataclass
class Game:
    players: list[Player] = field(default_factory=list)

    @classmethod
    def start(cls, level: Level) -> Game:
        return cls([Player(s.sx, s.sy, s.facing, ink) for s, ink in zip(level.starts(), level.player_inks())])

    def tick(self, inputs: list[int]) -> None:
        """Advance one tick; inputs[p] is player p's input byte."""
        for player, byte in zip(self.players, inputs):
            direction = byte & DIRECTION_MASK
            if direction == NO_DIRECTION:
                continue
            player.facing = direction
            player.accumulator += DIAGONAL_SPEED if direction % 2 else AXIAL_SPEED
            if player.accumulator < 256:
                continue
            player.accumulator -= 256
            x = player.sx + DIRECTION_DX[direction]
            y = player.sy + DIRECTION_DY[direction]
            if 0 <= x <= MAX_POSITION:
                player.sx = x
            if 0 <= y <= MAX_POSITION:
                player.sy = y
