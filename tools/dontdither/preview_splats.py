"""Render a preview sheet of the paint splats for design review.

Each row is one splat variant; each column one facing. Every tile shows a
tank over the four-way grey with its splat cells painted solid in the
player's ink. The last row overlays all variants, to show the spread of
successive shots.

    uv run dd-preview-splats
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from dontdither.build import BUILD_DIRPATH
from dontdither.inks import INK_RGB, InkTable
from dontdither.splats import FOOTPRINT, load_splats
from dontdither.sprites import FACINGS, coloured, load_tank

PREVIEW_FILEPATH = BUILD_DIRPATH / "design" / "splats.png"
PLAYER = "C"
TILE_CELLS = 26            # superpixels per tile side
SCALE = 3
HEADER = 24


def render() -> Image.Image:
    table = InkTable.load()
    tank = load_tank()
    splats = load_splats()
    variants = len(splats["E"])
    grey = table.pattern((1, 1, 1, 1))
    tile = TILE_CELLS * 2
    image = Image.new("RGB", (len(FACINGS) * tile, (variants + 1) * tile))
    origin = (TILE_CELLS - FOOTPRINT) // 2          # footprint top-left, in cells
    for row in range(variants + 1):
        for column, facing in enumerate(FACINGS):
            x0, y0 = column * tile, row * tile
            for y in range(tile):
                for x in range(tile):
                    image.putpixel((x0 + x, y0 + y), INK_RGB[grey[(y % 2) * 2 + x % 2]])
            shown = splats[facing] if row == variants else [splats[facing][row]]
            for splat in shown:
                for cx, cy in splat:
                    for dy in range(2):
                        for dx in range(2):
                            image.putpixel((x0 + (origin + cx) * 2 + dx, y0 + (origin + cy) * 2 + dy),
                                           INK_RGB[PLAYER])
            for (px, py), ink in coloured(tank[facing], PLAYER).items():
                image.putpixel((x0 + origin * 2 + px, y0 + origin * 2 + py), INK_RGB[ink])
    image = image.resize((image.width * SCALE, image.height * SCALE), Image.NEAREST)
    sheet = Image.new("RGB", (image.width, image.height + HEADER), (40, 40, 40))
    sheet.paste(image, (0, HEADER))
    draw = ImageDraw.Draw(sheet)
    for column, facing in enumerate(FACINGS):
        draw.text((column * tile * SCALE + 4, 6), facing, fill=(255, 255, 255))
    return sheet


def main() -> None:
    PREVIEW_FILEPATH.parent.mkdir(parents=True, exist_ok=True)
    render().save(PREVIEW_FILEPATH)
    print(f"Wrote {PREVIEW_FILEPATH}")


if __name__ == "__main__":
    main()
