"""Model of the game's screen memory: arena, walls and sprites.

Used by the tests to predict screen memory exactly.
"""

from __future__ import annotations

from dontdither.inks import InkTable, State, pattern_rows_as_mode1_bytes
from dontdither.levels import Level
from dontdither.screen import MODE1_ROW_BYTES, MODE1_SCREEN_BASE, MODE1_SCREEN_SIZE, superpixel_address
from dontdither.sprites import FACINGS, draw_sprite_on_screen, load_tank
from dontdither.walls import render_wall_cell

ARENA_BYTE_COLUMNS = 64


def arena_screen(level: Level, cells: dict[tuple[int, int], State] | None = None) -> bytearray:
    """Screen memory with the level's arena drawn: every open superpixel in
    its ink state (the fill state unless `cells` says otherwise) and every
    wall cell's tile. The HUD is left zero."""
    table = InkTable.load()
    screen = bytearray(MODE1_SCREEN_SIZE)
    walls = level.wall_cells()
    for sy in range(128):
        for sx in range(128):
            if (sx // 4, sy // 4) in walls:
                continue
            state = cells.get((sx, sy), level.fill) if cells else level.fill
            top, bottom = pattern_rows_as_mode1_bytes(table.pattern(state))
            mask = 0xCC if sx % 2 == 0 else 0x33
            address = superpixel_address(sx, sy) - MODE1_SCREEN_BASE
            screen[address] = (screen[address] & ~mask & 0xFF) | (top & mask)
            screen[address + 1] = (screen[address + 1] & ~mask & 0xFF) | (bottom & mask)
    for cx, cy in walls:
        offset = cy * MODE1_ROW_BYTES + cx * 16
        screen[offset:offset + 16] = render_wall_cell(walls, cx, cy, level.colouring)
    return screen


def draw_players(screen: bytearray, players: list[tuple[int, int, int, str]]) -> None:
    """Draw tanks in player order; each is (sx, sy, facing index, ink)."""
    tank = load_tank()
    for sx, sy, facing, ink in players:
        draw_sprite_on_screen(screen, sx, sy, tank[FACINGS[facing]], ink)


def arena_bytes(screen: bytes) -> bytes:
    """Only the arena's bytes (the first 64 byte columns of each character
    row), for comparisons that ignore the HUD."""
    return b"".join(screen[row * MODE1_ROW_BYTES:row * MODE1_ROW_BYTES + ARENA_BYTE_COLUMNS * 8]
                    for row in range(32))
