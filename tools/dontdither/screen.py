"""Read the arena's superpixels out of a MODE 1 screen memory image."""

from __future__ import annotations

from dontdither.inks import decode_superpixel

MODE1_SCREEN_BASE = 0x3000
MODE1_SCREEN_SIZE = 0x5000
MODE1_ROW_BYTES = 640
ARENA_CELLS = 128


def superpixel_address(sx: int, sy: int, screen_base: int = MODE1_SCREEN_BASE) -> int:
    """Address of the top raster byte of superpixel (sx, sy); the bottom
    raster byte is the next address."""
    return screen_base + (sy // 4) * MODE1_ROW_BYTES + (sx // 2) * 8 + (sy % 4) * 2


def arena_patterns(screen: bytes, screen_base: int = MODE1_SCREEN_BASE) -> list[list[str]]:
    """Literal 2x2 patterns of all arena superpixels, indexed [sy][sx].

    `screen` is the MODE 1 screen memory starting at `screen_base`.
    """
    rows = []
    for sy in range(ARENA_CELLS):
        row = []
        for sx in range(ARENA_CELLS):
            offset = superpixel_address(sx, sy, screen_base) - screen_base
            row.append(decode_superpixel(screen[offset], screen[offset + 1], sx))
        rows.append(row)
    return rows
