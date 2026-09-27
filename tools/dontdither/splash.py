"""The logo: art/splash.png converted to MODE 1 screen bytes, twice.

The image is scaled to a given width (its height set to keep its proportions
on MODE 1's slightly wide pixels) and quantised to the four inks C, M, Y, K.

- The splash logo (LOGO_WIDTH pixels) is placed in character rows
  LOGO_TOP_ROW onwards, centred across the screen. Only those rows are
  kept: the SPLASH program loads them straight into screen memory.
- The HUD logo (HUD_LOGO_WIDTH pixels) is centred in the top HUD_LOGO_ROWS
  character rows of the HUD (byte columns 64..79). The DITHER loader copies
  it into place, and the game never draws over it, so it costs no memory.
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

HUD_LOGO_WIDTH = 60
HUD_LOGO_ROWS = 4                   # character rows at the top of the HUD
HUD_FIRST_COLUMN = 64               # byte column
HUD_COLUMNS = 16                    # byte columns, 64 pixels
HUD_ROW_BYTES = HUD_COLUMNS * 8     # one character row of the HUD, contiguous


def quantised_logo(width: int = LOGO_WIDTH, cropped: bool = False) -> Image.Image:
    """The logo scaled to width pixels and quantised to the inks. Cropped,
    the black margin around the artwork is removed first."""
    source = Image.open(SPLASH_FILEPATH).convert("RGB")
    if cropped:
        source = source.crop(source.convert("L").point(lambda v: 255 if v > 40 else 0).getbbox())
    height = round(width * source.height / source.width * MODE1_PIXEL_ASPECT)
    scaled = source.resize((width, height), Image.BOX)
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


def hud_logo() -> bytes:
    """The HUD logo: HUD_LOGO_ROWS character rows of the HUD's screen bytes,
    each row's HUD_ROW_BYTES contiguous (as in screen memory), row after row.
    The logo is centred in them; the rest is black."""
    logo = quantised_logo(HUD_LOGO_WIDTH, cropped=True)
    lines = HUD_LOGO_ROWS * 8
    assert logo.height <= lines, f"HUD logo is {logo.height} lines, more than {lines}"
    ink_of_rgb = {rgb: ink for ink, rgb in INK_RGB.items()}
    left = (HUD_COLUMNS * 4 - logo.width) // 2
    top = (lines - logo.height) // 2
    pixels = logo.load()

    def colour(x: int, y: int) -> int:
        lx, ly = x - left, y - top
        if 0 <= lx < logo.width and 0 <= ly < logo.height:
            return LOGICAL_COLOUR[ink_of_rgb[pixels[lx, ly]]]
        return LOGICAL_COLOUR["K"]

    data = bytearray(HUD_LOGO_ROWS * HUD_ROW_BYTES)
    for row in range(HUD_LOGO_ROWS):
        for column in range(HUD_COLUMNS):
            for line in range(8):
                data[row * HUD_ROW_BYTES + column * 8 + line] = mode1_byte(
                    [colour(column * 4 + p, row * 8 + line) for p in range(4)])
    return bytes(data)
