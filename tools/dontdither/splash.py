"""The splash logo: art/splash.png converted to a band of MODE 1 screen bytes.

The image is scaled to LOGO_WIDTH pixels wide (its height set to keep its
proportions on MODE 1's slightly wide pixels), quantised to the four inks
C, M, Y, K, and placed in character rows LOGO_TOP_ROW onwards, centred
across the screen. Only those rows are kept: the SPLASH program loads them
straight into screen memory.
"""

from __future__ import annotations

from PIL import Image

from dontdither.inks import INK_RGB, LOGICAL_COLOUR, PROJECT_DIRPATH, mode1_byte

SPLASH_FILEPATH = PROJECT_DIRPATH / "art" / "splash.png"

SCREEN_WIDTH = 320
LOGO_WIDTH = 300
LOGO_TOP_ROW = 4                    # character row (8 raster lines each)
MODE1_PIXEL_ASPECT = 1.0667         # a MODE 1 pixel is this much wider than tall
ROW_BYTES = 640


def quantised_logo() -> Image.Image:
    source = Image.open(SPLASH_FILEPATH).convert("RGB")
    height = round(LOGO_WIDTH * source.height / source.width * MODE1_PIXEL_ASPECT)
    scaled = source.resize((LOGO_WIDTH, height), Image.BOX)
    out = Image.new("RGB", scaled.size)
    src, dst = scaled.load(), out.load()
    inks = list(INK_RGB.values())
    for y in range(scaled.height):
        for x in range(scaled.width):
            r, g, b = src[x, y]
            dst[x, y] = min(inks, key=lambda c: (c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2)
    return out


def logo_band() -> tuple[int, bytes]:
    """(number of character rows, their screen bytes) for the logo."""
    logo = quantised_logo()
    rows = (logo.height + 7) // 8
    ink_of_rgb = {rgb: ink for ink, rgb in INK_RGB.items()}
    left = (SCREEN_WIDTH - LOGO_WIDTH) // 2
    pixels = logo.load()

    def colour(x: int, y: int) -> int:
        lx = x - left
        if 0 <= lx < logo.width and y < logo.height:
            return LOGICAL_COLOUR[ink_of_rgb[pixels[lx, y]]]
        return LOGICAL_COLOUR["K"]

    band = bytearray(rows * ROW_BYTES)
    for row in range(rows):
        for column in range(SCREEN_WIDTH // 4):
            for line in range(8):
                y = row * 8 + line
                band[row * ROW_BYTES + column * 8 + line] = mode1_byte(
                    [colour(column * 4 + p, y) for p in range(4)])
    return rows, bytes(band)
