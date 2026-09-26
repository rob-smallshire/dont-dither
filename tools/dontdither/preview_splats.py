"""Render a preview sheet of the paint splats for design review.

Each column is one facing. Tiles show a tank on the four-way grey start
state with the true effect of its shots: each shot moves every target cell
one quantum towards the player's ink (see paint.py), so a cell only becomes
solid after several hits. Rows:

    one shot of each variant in turn
    the cumulative result of 3 shots and of 6 shots from the same spot,
    cycling through the variants as the game does
    the same 3 and 6 shots with a short wall (black) across part of the
    splat: walls stop splats, shadowing the cells behind them

    uv run dd-preview-splats
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from dontdither.build import BUILD_DIRPATH
from dontdither.inks import INK_RGB, INKS, InkTable
from dontdither.paint import Painter, apply_splat
from dontdither.splats import FOOTPRINT, load_trees
from dontdither.sprites import FACINGS, coloured, load_tank

PREVIEW_FILEPATH = BUILD_DIRPATH / "design" / "splats.png"
PLAYER = "C"
TILE_CELLS = 26            # superpixels per tile side
SCALE = 3
HEADER = 24
LABEL_WIDTH = 90
CUMULATIVE_SHOTS = (3, 6)
# A demonstration wall in the E frame (footprint-relative cells), rotated with
# the facing like the splats.
DEMO_WALL_E = [(10, y) for y in range(-1, 3)]


def demo_wall(facing: str) -> set[tuple[int, int]]:
    index = FACINGS.index(facing)
    cells = DEMO_WALL_E if index % 2 == 0 else [(x - 1, y - 4) for x, y in DEMO_WALL_E]
    turns = ((index - (2 if index % 2 == 0 else 1)) // 2) % 4
    for _ in range(turns):
        cells = [(FOOTPRINT - 1 - y, x) for x, y in cells]
    return set(cells)


def render() -> Image.Image:
    table = InkTable.load()
    tank = load_tank()
    trees = load_trees()
    variants = len(trees["E"])
    rows = [(f"variant {v + 1}", [v], False) for v in range(variants)]
    rows += [(f"{n} shots", [i % variants for i in range(n)], False) for n in CUMULATIVE_SHOTS]
    rows += [(f"{n} shots,\nwall", [i % variants for i in range(n)], True) for n in CUMULATIVE_SHOTS]

    tile = TILE_CELLS * 2
    image = Image.new("RGB", (len(FACINGS) * tile, len(rows) * tile))
    origin = (TILE_CELLS - FOOTPRINT) // 2          # footprint top-left, in cells
    for row, (_, shots, walled) in enumerate(rows):
        for column, facing in enumerate(FACINGS):
            grid = {(x, y): (1, 1, 1, 1) for x in range(-origin, TILE_CELLS - origin)
                    for y in range(-origin, TILE_CELLS - origin)}
            walls = demo_wall(facing) if walled else set()
            for cell in walls:
                grid.pop(cell, None)
            painter = Painter(INKS.index(PLAYER))
            for variant in shots:
                apply_splat(grid, painter, trees[facing][variant])
            x0, y0 = column * tile, row * tile
            for (cx, cy), state in grid.items():
                pattern = table.pattern(state)
                for dy in range(2):
                    for dx in range(2):
                        image.putpixel((x0 + (origin + cx) * 2 + dx, y0 + (origin + cy) * 2 + dy),
                                       INK_RGB[pattern[dy * 2 + dx]])
            for cx, cy in walls:
                for dy in range(2):
                    for dx in range(2):
                        image.putpixel((x0 + (origin + cx) * 2 + dx, y0 + (origin + cy) * 2 + dy), (0, 0, 0))
            for (px, py), ink in coloured(tank[facing], PLAYER).items():
                image.putpixel((x0 + origin * 2 + px, y0 + origin * 2 + py), INK_RGB[ink])
    image = image.resize((image.width * SCALE, image.height * SCALE), Image.NEAREST)
    sheet = Image.new("RGB", (image.width + LABEL_WIDTH, image.height + HEADER), (40, 40, 40))
    sheet.paste(image, (LABEL_WIDTH, HEADER))
    draw = ImageDraw.Draw(sheet)
    for column, facing in enumerate(FACINGS):
        draw.text((LABEL_WIDTH + column * tile * SCALE + 4, 6), facing, fill=(255, 255, 255))
    for row, (label, _, _) in enumerate(rows):
        draw.text((6, HEADER + row * tile * SCALE + 6), label, fill=(255, 255, 255))
    return sheet


def main() -> None:
    PREVIEW_FILEPATH.parent.mkdir(parents=True, exist_ok=True)
    render().save(PREVIEW_FILEPATH)
    print(f"Wrote {PREVIEW_FILEPATH}")


if __name__ == "__main__":
    main()
