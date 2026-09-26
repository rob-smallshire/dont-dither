"""The 35 CMYK ink states, their canonical 2x2 patterns, and MODE 1 encodings.

A superpixel is a 2x2 block of MODE 1 pixels. Its ink state is the count
tuple (C, M, Y, K) summing to four. Each state has exactly one canonical
2x2 pattern, written row-major as a four-letter string "TL TR BL BR"
(e.g. "MKCY").

The canonical table lives in data/ink_patterns.json and is the single source
of truth for the 6502 lookup tables and for the tests.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

INKS = "CMYK"

# Logical MODE 1 colour number for each ink. K is logical colour 0 so that
# an OS screen clear, and the HUD background, are black.
LOGICAL_COLOUR = {"K": 0, "C": 1, "M": 2, "Y": 3}

# BBC physical colour number for each ink (VDU 19 actual colour).
PHYSICAL_COLOUR = {"K": 0, "C": 6, "M": 5, "Y": 3}

# RGB for each ink, as displayed.
INK_RGB = {"C": (0, 255, 255), "M": (255, 0, 255), "Y": (255, 255, 0), "K": (0, 0, 0)}

PROJECT_DIRPATH = Path(__file__).resolve().parents[2]
PATTERNS_FILEPATH = PROJECT_DIRPATH / "data" / "ink_patterns.json"

State = tuple[int, int, int, int]


def all_states() -> list[State]:
    """The 35 count tuples (C, M, Y, K) with C+M+Y+K == 4, in lexicographic order."""
    return [s for s in itertools.product(range(5), repeat=4) if sum(s) == 4]


def counts(pattern: str) -> State:
    """The ink state (count tuple) of a literal 2x2 pattern."""
    return tuple(pattern.count(ink) for ink in INKS)  # type: ignore[return-value]


def arrangements(state: State) -> list[str]:
    """All distinct literal 2x2 patterns having the given ink counts."""
    multiset = "".join(ink * n for ink, n in zip(INKS, state))
    return sorted({"".join(p) for p in itertools.permutations(multiset)})


def hamming(a: str, b: str) -> int:
    """Number of physical pixels that differ between two 2x2 patterns."""
    return sum(x != y for x, y in zip(a, b))


def adjacent_state_pairs(states: list[State]) -> list[tuple[State, State]]:
    """Undirected pairs of states differing by one transferred ownership quantum."""
    return [
        (s, t)
        for s, t in itertools.combinations(states, 2)
        if sum(abs(a - b) for a, b in zip(s, t)) == 2
    ]


# ---------------------------------------------------------------------------
# Symmetries of the 2x2 tile and of the colour labels
# ---------------------------------------------------------------------------

def rotate_clockwise(pattern: str) -> str:
    """Rotate a 2x2 pattern 90 degrees clockwise."""
    tl, tr, bl, br = pattern
    return bl + tl + br + tr


def cycle_inks(pattern: str) -> str:
    """Relabel inks C->M->Y->K->C."""
    return "".join(INKS[(INKS.index(c) + 1) % 4] for c in pattern)


def cycle_state(state: State) -> State:
    """The ink state after relabelling C->M->Y->K->C."""
    c, m, y, k = state
    return (k, c, m, y)


def translations(pattern: str) -> set[str]:
    """The pattern and its one-pixel translations as a repeating tile.

    When a 2x2 tile is repeated over a region, shifting it by one pixel
    horizontally and/or vertically produces the same texture, offset.
    """
    tl, tr, bl, br = pattern
    return {pattern, tr + tl + br + bl, bl + br + tl + tr, br + bl + tr + tl}


def is_checkerboard(pattern: str) -> bool:
    tl, tr, bl, br = pattern
    return tl == br and tr == bl and tl != tr


def is_two_two(state: State) -> bool:
    return sorted(state) == [0, 0, 2, 2]


def is_two_one_one(state: State) -> bool:
    return sorted(state) == [0, 1, 1, 2]


def has_doubled_ink_on_diagonal(pattern: str) -> bool:
    """True if some ink fills a diagonal (TL and BR, or TR and BL)."""
    tl, tr, bl, br = pattern
    return tl == br or tr == bl


# ---------------------------------------------------------------------------
# MODE 1 encoding
# ---------------------------------------------------------------------------

def mode1_byte(logical_colours: list[int]) -> int:
    """Encode four logical colours (left to right) as a MODE 1 screen byte.

    Pixel p (0 = leftmost) keeps its high colour bit in bit 7-p and its low
    colour bit in bit 3-p.
    """
    assert len(logical_colours) == 4
    value = 0
    for p, colour in enumerate(logical_colours):
        value |= ((colour >> 1) & 1) << (7 - p)
        value |= (colour & 1) << (3 - p)
    return value


def mode1_pixels(byte: int) -> list[int]:
    """Decode a MODE 1 screen byte into four logical colours, left to right."""
    return [((byte >> (7 - p)) & 1) << 1 | ((byte >> (3 - p)) & 1) for p in range(4)]


def pattern_rows_as_mode1_bytes(pattern: str) -> tuple[int, int]:
    """Screen bytes (top raster, bottom raster) filling a byte with two
    horizontally adjacent superpixels of the same pattern."""
    tl, tr, bl, br = (LOGICAL_COLOUR[c] for c in pattern)
    return mode1_byte([tl, tr, tl, tr]), mode1_byte([bl, br, bl, br])


def decode_superpixel(top: int, bottom: int, sx: int) -> str:
    """Recover the literal 2x2 pattern of superpixel column parity sx&1 from
    its top and bottom raster bytes."""
    inks = {v: k for k, v in LOGICAL_COLOUR.items()}
    half = (sx & 1) * 2
    t = mode1_pixels(top)[half:half + 2]
    b = mode1_pixels(bottom)[half:half + 2]
    return "".join(inks[c] for c in t + b)


# ---------------------------------------------------------------------------
# The canonical table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InkTable:
    """The canonical pattern for each of the 35 ink states, in state order."""

    patterns: tuple[str, ...]

    @classmethod
    def load(cls, filepath: Path = PATTERNS_FILEPATH) -> InkTable:
        data = json.loads(filepath.read_text())
        by_state = {tuple(entry["state"]): entry["pattern"] for entry in data["states"]}
        return cls(tuple(by_state[s] for s in all_states()))

    @cached_property
    def states(self) -> list[State]:
        return all_states()

    def pattern(self, state: State) -> str:
        return self.patterns[self.states.index(state)]

    def state_of(self, pattern: str) -> State | None:
        """The state whose canonical pattern this is, or None if non-canonical."""
        try:
            return self.states[self.patterns.index(pattern)]
        except ValueError:
            return None

    def churn_histogram(self) -> dict[int, int]:
        """Count of adjacent state pairs by physical pixels changed."""
        histogram = {1: 0, 2: 0, 3: 0, 4: 0}
        for s, t in adjacent_state_pairs(self.states):
            histogram[hamming(self.pattern(s), self.pattern(t))] += 1
        return histogram
