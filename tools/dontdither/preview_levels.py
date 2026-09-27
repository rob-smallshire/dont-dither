"""Render every level to a contact sheet for design review, with the tanks at
their starts, and report what each level and level set costs in bytes.

    uv run dd-preview-levels      # -> build/design/levels_2p.png, levels_4p.png
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from dontdither.build import BUILD_DIRPATH
from dontdither.game import Game
from dontdither.inks import INK_RGB, LOGICAL_COLOUR, InkTable, mode1_pixels
from dontdither.levels import PLAYER_COUNTS, Level, level_set
from dontdither.render import arena_screen, draw_players
from dontdither.screen import MODE1_ROW_BYTES

ARENA_PIXELS = 256
COLUMNS = 4
LABEL_HEIGHT = 30
SET_HEADER_BYTES = 2
INK_OF_LOGICAL = {v: k for k, v in LOGICAL_COLOUR.items()}


def level_bytes(level: Level, table: InkTable) -> int:
    """What a level costs in its level set: its title and its bytecode."""
    return 1 + len(level.name) + len(level.bytecode(table))


def arena_image(level: Level) -> Image.Image:
    screen = arena_screen(level)
    game = Game.start(level, humans=0)
    draw_players(screen, [(p.sx, p.sy, p.facing, p.ink) for p in game.players])
    image = Image.new("RGB", (ARENA_PIXELS, ARENA_PIXELS))
    pixels = image.load()
    for row in range(ARENA_PIXELS // 8):
        for column in range(ARENA_PIXELS // 4):
            for line in range(8):
                byte = screen[row * MODE1_ROW_BYTES + column * 8 + line]
                for p, logical in enumerate(mode1_pixels(byte)):
                    pixels[column * 4 + p, row * 8 + line] = INK_RGB[INK_OF_LOGICAL[logical]]
    return image


def sheet(levels: list[Level], table: InkTable) -> Image.Image:
    rows = (len(levels) + COLUMNS - 1) // COLUMNS
    tile_height = ARENA_PIXELS + LABEL_HEIGHT
    out = Image.new("RGB", (COLUMNS * (ARENA_PIXELS + 8), rows * (tile_height + 8)), (40, 40, 40))
    draw = ImageDraw.Draw(out)
    for i, level in enumerate(levels):
        x, y = (i % COLUMNS) * (ARENA_PIXELS + 8), (i // COLUMNS) * (tile_height + 8)
        out.paste(arena_image(level), (x, y + LABEL_HEIGHT))
        draw.text((x + 2, y + 2), f"{i + 1}. {level.name}", fill=(255, 255, 255))
        draw.text((x + 2, y + 15), f"{level_bytes(level, table)} bytes", fill=(180, 180, 180))
    return out


def main() -> None:
    table = InkTable.load()
    for players in PLAYER_COUNTS:
        levels = level_set(players)
        total = SET_HEADER_BYTES + sum(level_bytes(lv, table) for lv in levels)
        filepath = BUILD_DIRPATH / "design" / f"levels_{players}p.png"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        sheet(levels, table).save(filepath)
        print(f"{players} players: {len(levels)} levels, {total} bytes -> {filepath}")


if __name__ == "__main__":
    main()
