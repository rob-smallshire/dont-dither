"""The AI player: turns the arena into an input byte, like a human would.

An AI produces exactly the input a keyboard player does -- a direction (or
none) plus fire -- and the simulation treats it identically. It is fully
deterministic (no random numbers), so rounds replay exactly, and the 6502
version must match this model decision for decision.

Thinking: each AI re-decides every AI_PERIOD ticks, on ticks where
(tick + player) MOD AI_PERIOD = 0, so AIs take turns; in between it repeats
its last input.

Deciding: for each of the 8 directions, the AI samples AI_SAMPLE cells ahead
of its footprint (defined for E and NE, rotated like splats for the other
facings, so every direction and every player is treated alike). A cell is
worth 8 minus the AI's own ink count there -- so ground the AI does not own
is worth more -- or 1 if it is a wall or outside the arena. A direction's
score is the sum. The current direction gets a PERSISTENCE bonus. Starting
from the current direction and going clockwise, the direction with the
strictly highest (bonused) score is chosen. If a step that way is blocked
(by a wall, the arena edge or a tank), that direction is ruled out and the
choice is made again; if every direction is ruled out the AI stays put. The
AI fires if the chosen direction's unbonused score is at least FIRE_SCORE.

Refilling: an AI whose reservoir is empty when it decides switches to
refilling, until it has at least REFILLED splats again. While refilling it
never fires, and a sample cell is worth 4 plus its own ink count, so it
heads for its own ink, where it moves fastest and refills soonest.
"""

from __future__ import annotations

from dontdither.inks import INKS

AI_PERIOD = 4
PERSISTENCE = 2
FIRE_SCORE = 22            # 4 samples: more than 4 * 5.5, i.e. mostly unowned ground
WALL_VALUE = 1
REFILL_BASE = 4            # while refilling, a cell is worth this + own count
REFILLED = 64              # splats at which a refilling AI paints again
FOOTPRINT = 6

# Sample cells relative to the footprint's top-left superpixel, for facing E
# and NE. Other facings rotate them: (x, y) -> (5 - y, x) per quarter turn.
SAMPLES_E = ((8, 2), (8, 3), (11, 2), (11, 3))
SAMPLES_NE = ((6, -2), (7, -3), (8, -4), (9, -5))

FACINGS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _rotate(cell: tuple[int, int], turns: int) -> tuple[int, int]:
    x, y = cell
    for _ in range(turns % 4):
        x, y = FOOTPRINT - 1 - y, x
    return x, y


def samples(direction: int) -> tuple[tuple[int, int], ...]:
    """Sample cells for a direction (0 = N, clockwise)."""
    base = direction & 1                       # 0: E-based, 1: NE-based
    turns = ((direction - 2 + base) // 2) % 4
    stored = SAMPLES_NE if base else SAMPLES_E
    return tuple(_rotate(c, turns) for c in stored)


def direction_scores(game, index: int) -> list[int]:
    player = game.players[index]
    own = INKS.index(player.ink)
    scores = []
    for direction in range(8):
        total = 0
        for dx, dy in samples(direction):
            state = game.cells.get((player.sx + dx, player.sy + dy))
            if state is None:
                total += WALL_VALUE
            elif player.ai_refilling:
                total += REFILL_BASE + state[own]
            else:
                total += 8 - state[own]
        scores.append(total)
    return scores


def decide(game, index: int) -> int:
    """The AI's input byte for player `index` (see the module docstring)."""
    from dontdither.game import DIRECTION_DX, DIRECTION_DY, FIRE_BIT, NO_DIRECTION

    player = game.players[index]
    if player.ai_refilling:
        player.ai_refilling = player.reservoir < REFILLED
    else:
        player.ai_refilling = player.reservoir == 0
    scores = direction_scores(game, index)
    current = player.ai_direction
    starts = [None if p.in_tunnel else (p.sx, p.sy) for p in game.players]
    ruled_out = set()
    while len(ruled_out) < 8:
        best, best_score = None, -1
        for i in range(8):
            direction = (current + i) % 8
            if direction in ruled_out:
                continue
            score = scores[direction] + (PERSISTENCE if direction == current else 0)
            if score > best_score:
                best, best_score = direction, score
        x = player.sx + DIRECTION_DX[best]
        y = player.sy + DIRECTION_DY[best]
        if game._clear(index, x, y, starts):
            player.ai_direction = best
            fire = not player.ai_refilling and scores[best] >= FIRE_SCORE
            return best | (FIRE_BIT if fire else 0)
        ruled_out.add(best)
    return NO_DIRECTION
