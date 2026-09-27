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

Firing: after every player has moved, the players fire in the same order.
A player whose fire cooldown is non-zero counts it down instead. Otherwise,
if fire is held and it is the player's turn to fire -- players shoot only
on ticks of their own parity, (tick + player) even, so at most half of them
shoot in any tick -- the player shoots: the next of its splat variants (cycling
0, 1, 2), from its new position and facing, is applied to the arena (see
paint.py and splats.py: each unshadowed splat cell moves one quantum
towards the player's ink, victims round-robin per player), and the cooldown
is set to FIRE_PERIOD - 1, so holding fire shoots every FIRE_PERIOD ticks
(FIRE_PERIOD is even, so the parity rule never delays a held fire).
Cells under tanks are painted like any other.

Sessions: a session plays every level in turn. After each round each
player scores points by rank -- 3, 2, 1, 0 for first to last with four
players; 3 and 0 with two -- and points accumulate across the session.
Tied players share the better rank (competition ranking): two players tied
for first both score 3 and the next is third.

Rounds: a round lasts round_ticks ticks (ROUND_SECONDS at 25 Hz by
default); after the last tick nothing moves or fires. Scoring happens only
at the end: each player's quanta are the counts of their ink summed over
every open (non-wall) cell, and their share is quanta * 100 DIV total, where
the total is 4 quanta per open cell. Neutral inks (in a two-player game)
count towards the total but belong to no one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dontdither.inks import INKS, State
from dontdither.levels import Level
from dontdither.paint import Painter, apply_splat
from dontdither.splats import load_trees
from dontdither.walls import WallCells

NO_DIRECTION = 0x08
DIRECTION_MASK = 0x0F
FIRE_BIT = 0x10

AXIAL_SPEED = 200          # normal speed, 1/256 superpixel per tick: 19.5 cells/s
DIAGONAL_SPEED = 141       # AXIAL_SPEED / sqrt(2), per axis

DIRECTION_DX = (0, 1, 1, 1, 0, -1, -1, -1)
DIRECTION_DY = (-1, -1, 0, 1, 1, 1, 0, -1)

FOOTPRINT = 6
MAX_POSITION = 128 - FOOTPRINT      # 122

HUMAN_PLAYERS = 2          # players 1 and 2 are on the keyboard; the rest are AI

TICKS_PER_SECOND = 25
DEMO_ROUND_SECONDS = 60    # demo (attract) rounds, with no human players
SELECT_SECONDS = 10        # time to press fire and join, before a session
ROUND_SECONDS = 300        # five minutes
ROUND_TICKS = ROUND_SECONDS * TICKS_PER_SECOND
DEMO_ROUND_TICKS = DEMO_ROUND_SECONDS * TICKS_PER_SECOND

POINTS_BY_RANK = {4: (3, 2, 1, 0), 2: (3, 0)}

# A one-byte pseudo-random generator, state -> 5 * state + 1 (mod 256), a
# full-period linear congruential generator. Its low bits cycle quickly, so
# only its top bits are used. On the machine it is seeded from a VIA timer
# and stirred every field while players join, so real games differ; tests
# write DEFAULT_RANDOM_STATE before entering a level, as Game.start assumes.
DEFAULT_RANDOM_STATE = 17     # gives the two AI slots of a four-player game different facings


def next_random(state: int) -> int:
    return (5 * state + 1) & 0xFF


def random_direction(state: int) -> tuple[int, int]:
    """(a direction 0..7 from the top three bits, the new state)."""
    state = next_random(state)
    return state >> 5, state


def round_points(percentages: list[int]) -> list[int]:
    """Points for each player from their shares: by rank, ties sharing the
    better rank."""
    table = POINTS_BY_RANK[len(percentages)]
    return [table[sum(1 for other in percentages if other > mine)] for mine in percentages]

FIRE_PERIOD = 6            # ticks between shots while fire is held (4 per second);
                           # must be even (see the firing parity rule)

# The ink reservoir (like Splatoon's ink tank and squid form). Each shot
# uses a splat of ink; with none left, holding fire does nothing. While fire
# is released, the ground under the tank sets its speed and refill rate:
# its GROUND level is the tank's own ink quanta summed over the four centre
# superpixels of its footprint, DIV 4, so 0 (hostile) to 4 (solid own ink).
# The centre four are the only cells every player's rotation treats alike.
# While fire is held the tank moves at normal speed and does not refill.
RESERVOIR_SPLATS = 128     # a full reservoir, in splats (about 30 s of fire)
GROUND_LEVELS = 5
FIRING_GROUND = 1          # the ground level whose speed applies while firing
# By ground level: speed in 1/256 superpixel per tick (axial, then diagonal
# = axial / sqrt 2; more than 256 takes two steps on some ticks) and refill
# in 1/256 splat per tick.
GROUND_AXIAL_SPEED = (100, 200, 200, 250, 300)
GROUND_DIAGONAL_SPEED = (71, 141, 141, 177, 212)
GROUND_REFILL = (0, 16, 64, 104, 192)


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
    cooldown: int = 0
    variant: int = 0
    last_victim: int = -1
    reservoir: int = RESERVOIR_SPLATS   # whole splats of ink
    reservoir_fraction: int = 0         # and 1/256ths of a splat
    ai: bool = False               # controlled by the AI (see ai.py)
    ai_refilling: bool = False     # the AI is seeking its own ink to refill
    ai_direction: int = -1         # the AI's current direction
    ai_input: int = NO_DIRECTION   # the AI's last decision

    def __post_init__(self) -> None:
        if self.last_victim < 0:
            self.last_victim = INKS.index(self.ink)   # first victim: the next ink round
        if self.ai_direction < 0:
            self.ai_direction = self.facing


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
    cells: dict[tuple[int, int], State] = field(default_factory=dict)   # open superpixels
    round_ticks_left: int = ROUND_TICKS
    random_state: int = DEFAULT_RANDOM_STATE

    def __post_init__(self) -> None:
        # A game made without an arena gets a grey one, (1, 1, 1, 1) in every
        # open cell as on a four-player level: ground level 1, normal speed.
        if not self.cells:
            self.cells = {(x, y): (1, 1, 1, 1) for y in range(128) for x in range(128)
                          if (x // 4, y // 4) not in self.walls}

    @classmethod
    def start(cls, level: Level, random_state: int = DEFAULT_RANDOM_STATE,
              humans: int = HUMAN_PLAYERS) -> Game:
        """The level's starting state: the first `humans` players human (by
        default the game's two keyboard players), the rest the AI (all of
        them in demo mode). Each AI player, in slot order, faces (and heads)
        a random direction, so identical AIs do not move in step like
        dancers; humans face the level's way."""
        walls = level.wall_cells()
        cells = {(x, y): level.fill for y in range(128) for x in range(128) if (x // 4, y // 4) not in walls}
        players = []
        for index, (s, ink) in enumerate(zip(level.starts(), level.player_inks())):
            ai = index >= humans
            facing = s.facing
            if ai:
                facing, random_state = random_direction(random_state)
            players.append(Player(s.sx, s.sy, facing, ink, ai=ai))
        return cls(players, walls=walls, cells=cells, random_state=random_state)

    @property
    def round_over(self) -> bool:
        return self.round_ticks_left == 0

    def ink_quanta(self) -> list[int]:
        """Quanta of each ink (C, M, Y, K) over the whole arena."""
        return [sum(state[i] for state in self.cells.values()) for i in range(len(INKS))]

    def percentages(self) -> list[int]:
        """Each player's share of the arena, in whole percent (rounded down)."""
        quanta = self.ink_quanta()
        total = 4 * len(self.cells)
        return [quanta[INKS.index(p.ink)] * 100 // total for p in self.players]

    def ground(self, index: int) -> int:
        """Player index's ground level: its own ink quanta in the four
        centre superpixels of its footprint, DIV 4 (0..4)."""
        player = self.players[index]
        own = INKS.index(player.ink)
        return sum(self.cells[(player.sx + dx, player.sy + dy)][own]
                   for dy in (2, 3) for dx in (2, 3)) // 4

    def tick(self, inputs: list[int] | None = None) -> None:
        """Advance one tick; inputs[p] is player p's input byte (ignored for
        AI players, which decide for themselves). Does nothing once the round
        is over."""
        from dontdither.ai import AI_PERIOD, decide

        if self.round_over:
            return
        self.round_ticks_left -= 1
        count = len(self.players)
        inputs = list(inputs) if inputs is not None else [NO_DIRECTION] * count
        for index, player in enumerate(self.players):
            if player.ai:
                if (self.ticks + index) % AI_PERIOD == 0:
                    player.ai_input = decide(self, index)
                inputs[index] = player.ai_input
        starts = [(p.sx, p.sy) for p in self.players]
        first = self.ticks % count
        order = [(first + i) % count for i in range(count)]
        for index in order:
            self._move(index, inputs[index], starts)
        for index in order:
            self._fire(index, inputs[index], self.ticks)
        self.ticks += 1

    def _fire(self, index: int, byte: int, tick: int) -> None:
        player = self.players[index]
        if player.cooldown:
            player.cooldown -= 1
            return
        if not byte & FIRE_BIT or (tick + index) % 2 or not player.reservoir:
            return
        player.reservoir -= 1
        trees = _trees()[FACINGS_[player.facing]]
        painter = Painter(INKS.index(player.ink), player.last_victim)
        apply_splat(self.cells, painter, trees[player.variant], origin=(player.sx, player.sy))
        player.last_victim = painter.last_victim
        player.variant = (player.variant + 1) % len(trees)
        player.cooldown = FIRE_PERIOD - 1

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
        if byte & FIRE_BIT:
            ground = FIRING_GROUND
        else:
            ground = self.ground(index)
            fraction = player.reservoir_fraction + GROUND_REFILL[ground]
            player.reservoir += fraction >> 8
            player.reservoir_fraction = fraction & 0xFF
            if player.reservoir >= RESERVOIR_SPLATS:
                player.reservoir, player.reservoir_fraction = RESERVOIR_SPLATS, 0
        direction = byte & DIRECTION_MASK
        if direction == NO_DIRECTION:
            return
        player.facing = direction
        speeds = GROUND_DIAGONAL_SPEED if direction % 2 else GROUND_AXIAL_SPEED
        player.accumulator += speeds[ground]
        steps, player.accumulator = player.accumulator >> 8, player.accumulator & 0xFF
        for _ in range(steps):
            self._step(index, direction, starts)

    def _step(self, index: int, direction: int, starts) -> None:
        """One superpixel step, sliding along an obstacle if diagonal."""
        player = self.players[index]
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


FACINGS_ = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
_TREES = None


def _trees():
    global _TREES
    if _TREES is None:
        _TREES = load_trees()
    return _TREES
