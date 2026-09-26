"""A tiny 3x5-pixel digit font for HUD labels.

Each glyph row is one MODE 1 byte: four pixels, of which the left three
carry the glyph and the fourth is the gap before the next glyph. A glyph
byte has all-ones pixels where the glyph is set, so ANDing it with a byte
of four pixels of a colour draws the glyph in that colour.
"""

from __future__ import annotations

from dontdither.inks import mode1_byte

GLYPH_ROWS = 5

DIGITS = {
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("###", "..#", "###", "#..", "###"),
    "3": ("###", "..#", "###", "..#", "###"),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "###", "..#", "###"),
    "6": ("###", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", "..#", "..#", "..#"),
    "8": ("###", "#.#", "###", "#.#", "###"),
    "9": ("###", "#.#", "###", "..#", "###"),
}


def glyph_bytes(glyph: tuple[str, ...]) -> bytes:
    return bytes(mode1_byte([3 if ch == "#" else 0 for ch in row + "."]) for row in glyph)


def font_bytes() -> bytes:
    """GLYPH_ROWS bytes per digit, digits 0..9 in order."""
    return b"".join(glyph_bytes(DIGITS[d]) for d in "0123456789")
