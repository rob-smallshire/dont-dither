"""Render a preview sheet of the player sprite for design review.

Rows are the four players. The first columns show each player facing SE over
a range of ink textures; the rest show all eight facings over the four-way
grey start state.

    uv run dd-preview-sprites
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from dontdither.build import BUILD_DIRPATH
from dontdither.inks import INK_RGB, InkTable
from dontdither.sprites import FACINGS, coloured, load_tank

PREVIEW_FILEPATH = BUILD_DIRPATH / "design" / "sprites.png"
BACKGROUNDS = (
    ("grey", (1, 1, 1, 1)), ("C", (4, 0, 0, 0)), ("M", (0, 4, 0, 0)), ("Y", (0, 0, 4, 0)),
    ("K", (0, 0, 0, 4)), ("3C+M", (3, 1, 0, 0)), ("2Y+C+K", (1, 0, 2, 1)), ("2M+2K", (0, 2, 0, 2)),
)
PLAYERS = "CMYK"
TILE = 20          # pixels per preview tile
SCALE = 4
HEADER = 30


def render() -> Image.Image:
    table = InkTable.load()
    facings = load_tank()
    columns = [(state, "SE") for _, state in BACKGROUNDS] + [((1, 1, 1, 1), f) for f in FACINGS]
    image = Image.new("RGB", (len(columns) * TILE, len(PLAYERS) * TILE))
    offset = (TILE - 12) // 2
    for row, player in enumerate(PLAYERS):
        for column, (state, facing) in enumerate(columns):
            x0, y0 = column * TILE, row * TILE
            pattern = table.pattern(state)
            for y in range(TILE):
                for x in range(TILE):
                    image.putpixel((x0 + x, y0 + y), INK_RGB[pattern[(y % 2) * 2 + x % 2]])
            for (x, y), ink in coloured(facings[facing], player).items():
                image.putpixel((x0 + offset + x, y0 + offset + y), INK_RGB[ink])
    image = image.resize((image.width * SCALE, image.height * SCALE), Image.NEAREST)
    sheet = Image.new("RGB", (image.width, image.height + HEADER), (40, 40, 40))
    sheet.paste(image, (0, HEADER))
    labels = [name for name, _ in BACKGROUNDS] + list(FACINGS)
    draw = ImageDraw.Draw(sheet)
    for column, label in enumerate(labels):
        draw.text((column * TILE * SCALE + 4, 8), label, fill=(255, 255, 255))
    return sheet


def main() -> None:
    PREVIEW_FILEPATH.parent.mkdir(parents=True, exist_ok=True)
    render().save(PREVIEW_FILEPATH)
    print(f"Wrote {PREVIEW_FILEPATH}")


if __name__ == "__main__":
    main()
