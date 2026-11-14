"""Draw the figures for the article on choosing the dither patterns
(docs/articles/choosing_the_dither_patterns.md), from the real table and
painting rule, so they cannot drift from what the game draws.

    uv run dd-preview-dither-figures   # -> docs/images/dither_*.png

Figures:
- dither_table.png: the 35 canonical patterns, each tiled as a region.
- dither_coherence.png: one painted field drawn the game's way (one pattern
  per state) and by keeping the pixels, recolouring one per hit (churn
  always 1, but history decides the arrangement).
- dither_stripes.png: checkerboards against stripes, for 2+2 states and for
  2+1+1 states with and without the doubled-ink-on-a-diagonal rule.
- dither_grey.png: the six grey (1,1,1,1) textures, each beside the view
  from the next player's seat (turned a quarter and recoloured C->M->Y->K).
- dither_churn.png: one cell painted from grey to solid cyan, changed pixels
  marked, and the table's worst edge.
- dither_frustration.png: why two of the six checkerboards must be out of
  phase with their neighbours.
"""

from __future__ import annotations

import random

from PIL import Image, ImageDraw, ImageFont

from dontdither.inks import (
    INK_RGB,
    INKS,
    PROJECT_DIRPATH,
    InkTable,
    all_states,
    arrangements,
    cycle_inks,
    cycle_state,
    hamming,
    rotate_clockwise,
    translations,
)
from dontdither.paint import Painter, paint_cell

IMAGES_DIRPATH = PROJECT_DIRPATH / "docs" / "images"
WHITE = (255, 255, 255)
INK_TEXT = (0, 0, 0)
GREY_TEXT = (90, 90, 90)
HIGHLIGHT = (230, 30, 30)
GOOD = (20, 140, 60)


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def state_text(state) -> str:
    return "(" + ",".join(str(c) for c in state) + ")"


def draw_cells(d: ImageDraw.ImageDraw, x: int, y: int, grid: list[list[str]], pixel: int) -> None:
    """Draw a grid of 2x2 patterns (row-major TL TR BL BR) at (x, y)."""
    for row, patterns in enumerate(grid):
        for column, pattern in enumerate(patterns):
            for i, ink in enumerate(pattern):
                left = x + (2 * column + i % 2) * pixel
                top = y + (2 * row + i // 2) * pixel
                d.rectangle([left, top, left + pixel - 1, top + pixel - 1], fill=INK_RGB[ink])


def tiled(pattern: str, n: int) -> list[list[str]]:
    return [[pattern] * n for _ in range(n)]


def outline(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, colour=(0, 0, 0), width: int = 1) -> None:
    d.rectangle([x - width, y - width, x + w + width - 1, y + h + width - 1], outline=colour, width=width)


def centred(d: ImageDraw.ImageDraw, cx: float, y: float, text: str, size: int, fill=INK_TEXT) -> None:
    f = font(size)
    w = d.textlength(text, font=f)
    d.text((cx - w / 2, y), text, font=f, fill=fill)


# ---- 1. The table -----------------------------------------------------------

def figure_table(table: InkTable) -> Image.Image:
    groups = [
        ("one ink", sorted((s for s in all_states() if max(s) == 4), reverse=True)),
        ("3+1", sorted((s for s in all_states() if sorted(s) == [0, 0, 1, 3]), reverse=True)),
        ("2+2: checkerboards", sorted((s for s in all_states() if sorted(s) == [0, 0, 2, 2]), reverse=True)),
        ("2+1+1: doubled ink on a diagonal", sorted((s for s in all_states() if sorted(s) == [0, 1, 1, 2]), reverse=True)),
        ("1+1+1+1: the grey start", [(1, 1, 1, 1)]),
    ]
    tiles, pixel, gap = 6, 5, 22
    swatch = 2 * tiles * pixel
    width = 40 + 12 * (swatch + gap)
    row_height = swatch + 64
    image = Image.new("RGB", (width, 30 + row_height * len(groups)), WHITE)
    d = ImageDraw.Draw(image)
    y = 20
    for title, states in groups:
        d.text((20, y), title, font=font(18), fill=INK_TEXT)
        for i, s in enumerate(states):
            x = 20 + i * (swatch + gap)
            draw_cells(d, x, y + 28, tiled(table.pattern(s), tiles), pixel)
            outline(d, x, y + 28, swatch, swatch)
            centred(d, x + swatch / 2, y + 32 + swatch, state_text(s), 13, GREY_TEXT)
        y += row_height
    return image


# ---- 2. Spatial coherence ---------------------------------------------------

def painted_field(size: int, seed: int = 3):
    """A field of size x size cells, from grey, splatted by cyan around the
    left and magenta around the right. Returns the final states and, for
    each cell, the pixels you get by recolouring one victim pixel per hit
    (the first in reading order) instead of redrawing the canonical pattern."""
    rng = random.Random(seed)
    grey = InkTable.load().pattern((1, 1, 1, 1))
    states = [[(1, 1, 1, 1)] * size for _ in range(size)]
    pixels = [[grey] * size for _ in range(size)]
    painters = {0: Painter(0), 1: Painter(1)}
    centres = {0: (size * 0.3, size * 0.45), 1: (size * 0.72, size * 0.55)}
    for _ in range(110):
        ink = rng.choice((0, 1))
        cx, cy = centres[ink]
        sx, sy = int(rng.gauss(cx, size * 0.2)), int(rng.gauss(cy, size * 0.2))
        painter = painters[ink]
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                x, y = sx + dx, sy + dy
                if not (0 <= x < size and 0 <= y < size):
                    continue
                before = states[y][x]
                after, painter.last_victim = paint_cell(before, ink, painter.last_victim, painter.step)
                if after != before:
                    victim = next(i for i in range(4) if after[i] < before[i])
                    p = pixels[y][x]
                    k = p.index(INKS[victim])
                    pixels[y][x] = p[:k] + INKS[ink] + p[k + 1:]
                    states[y][x] = after
    return states, pixels


def uniform_by_history(state, size: int, seed: int = 5) -> list[list[str]]:
    """A size x size region in which every cell holds `state`, each reached
    from the grey start by its own random history of one-quantum moves,
    recolouring one pixel per move: what the cells would look like if they
    kept their pixels rather than taking the state's one pattern."""
    rng = random.Random(seed)
    grey = InkTable.load().pattern((1, 1, 1, 1))
    grid = []
    for _ in range(size):
        row = []
        while len(row) < size:
            counts, pixels = [1, 1, 1, 1], grey
            for _ in range(rng.randrange(1, 9)):
                painter = rng.randrange(4)
                victims = [i for i in range(4) if i != painter and counts[i]]
                if not victims:
                    continue
                victim = rng.choice(victims)
                spots = [k for k, ink in enumerate(pixels) if ink == INKS[victim]]
                k = rng.choice(spots)
                pixels = pixels[:k] + INKS[painter] + pixels[k + 1:]
                counts[victim] -= 1
                counts[painter] += 1
            if tuple(counts) == state:
                row.append(pixels)
        grid.append(row)
    return grid


def figure_coherence(table: InkTable) -> Image.Image:
    size, pixel, gap = 40, 4, 40
    panel = 2 * size * pixel
    uniform_state = (2, 1, 1, 0)
    states, pixels = painted_field(size)
    rows = [
        (f"A region where every cell is {state_text(uniform_state)}: cyan 2, magenta 1, yellow 1",
         [(tiled(table.pattern(uniform_state), size), "One pattern per state (the game)"),
          (uniform_by_history(uniform_state, size), "Each cell keeps its own history")]),
        ("Cyan and magenta splatted over the grey start",
         [([[table.pattern(s) for s in row] for row in states], "One pattern per state (the game)"),
          (pixels, "Keep the pixels, change one per hit")]),
    ]
    row_height = panel + 110
    image = Image.new("RGB", (2 * panel + 3 * gap, len(rows) * row_height + 40), WHITE)
    d = ImageDraw.Draw(image)
    for r, (heading, panels) in enumerate(rows):
        y = 16 + r * row_height
        centred(d, image.width / 2, y, heading, 17)
        for i, (grid, title) in enumerate(panels):
            x = gap + i * (panel + gap)
            centred(d, x + panel / 2, y + 30, title, 15, GOOD if i == 0 else HIGHLIGHT)
            draw_cells(d, x, y + 56, grid, pixel)
            outline(d, x, y + 56, panel, panel)
    centred(d, image.width / 2, image.height - 30,
            "In each row both panels hold exactly the same ink counts in every cell.", 14, GREY_TEXT)
    return image


# ---- 3. Stripes -------------------------------------------------------------

def cycle_chain(state, pattern: str) -> list[tuple[tuple, str]]:
    """The state and its three colour-cycle images, each pattern turned a
    quarter and recoloured from the last: the four players' versions."""
    chain = [(state, pattern)]
    for _ in range(3):
        s, p = chain[-1]
        chain.append((cycle_state(s), rotate_clockwise(cycle_inks(p))))
    return chain


def figure_stripes(table: InkTable) -> Image.Image:
    tiles, pixel, gap = 8, 5, 60
    swatch = 2 * tiles * pixel
    image = Image.new("RGB", (40 + 4 * (swatch + gap) + 60, 3 * (swatch + 90) + 30), WHITE)
    d = ImageDraw.Draw(image)

    def row(y, title, items, verdicts):
        d.text((20, y), title, font=font(17), fill=INK_TEXT)
        for i, ((label, pattern), verdict) in enumerate(zip(items, verdicts)):
            x = 20 + i * (swatch + gap)
            draw_cells(d, x, y + 28, tiled(pattern, tiles), pixel)
            colour = GOOD if verdict else HIGHLIGHT
            outline(d, x, y + 28, swatch, swatch, colour, 3)
            centred(d, x + swatch / 2, y + 36 + swatch, label, 13, GREY_TEXT)

    row(20, "Half cyan, half magenta (2,2,0,0): a checkerboard (the game) or stripes",
        [("checkerboard", table.pattern((2, 2, 0, 0))),
         ("horizontal stripes", "CCMM"), ("vertical stripes", "CMCM")],
        [True, False, False])

    ours = cycle_chain((2, 1, 1, 0), table.pattern((2, 1, 1, 0)))
    row(20 + swatch + 90, "2+1+1, each player's ink doubled: on a diagonal (the game)",
        [(state_text(s), p) for s, p in ours], [True] * 4)

    rows = cycle_chain((2, 1, 1, 0), "CCYM")
    row(20 + 2 * (swatch + 90), "...or doubled along a row: stripes, and they turn with the player",
        [(state_text(s), p) for s, p in rows], [False] * 4)
    return image


# ---- 4. The grey start ------------------------------------------------------

def figure_grey(table: InkTable) -> Image.Image:
    grey = (1, 1, 1, 1)
    classes: list[str] = []
    for p in sorted(arrangements(grey)):
        if not any(p in translations(q) for q in classes):
            classes.append(p)
    ours = table.pattern(grey)
    classes.sort(key=lambda p: ours not in translations(p))     # the game's first
    tiles, pixel, gap = 6, 5, 30
    swatch = 2 * tiles * pixel
    image = Image.new("RGB", (40 + len(classes) * (swatch + gap), 2 * swatch + 150), WHITE)
    d = ImageDraw.Draw(image)
    d.text((20, 12), "The six grey textures (top), and the next player's view of each:", font=font(16), fill=INK_TEXT)
    d.text((20, 32), "turned a quarter, colours cycled C->M->Y->K (bottom)", font=font(16), fill=INK_TEXT)
    for i, p in enumerate(classes):
        x = 20 + i * (swatch + gap)
        image_pattern = rotate_clockwise(cycle_inks(p))
        same = any(image_pattern in translations(q) for q in translations(p))
        colour = GOOD if same else HIGHLIGHT
        draw_cells(d, x, 64, tiled(p, tiles), pixel)
        outline(d, x, 64, swatch, swatch, colour, 3)
        draw_cells(d, x, 80 + swatch, tiled(image_pattern, tiles), pixel)
        outline(d, x, 80 + swatch, swatch, swatch, colour, 3)
        label = "the game's" if ours in translations(p) else ("same" if same else "different")
        centred(d, x + swatch / 2, 90 + 2 * swatch, label, 14, colour)
    return image


# ---- 5. Churn -----------------------------------------------------------------

def draw_magnified(d, x, y, pattern, pixel, changed=frozenset()):
    draw_cells(d, x, y, [[pattern]], pixel)
    outline(d, x, y, 2 * pixel, 2 * pixel)
    for i in changed:
        left, top = x + (i % 2) * pixel, y + (i // 2) * pixel
        d.rectangle([left + 3, top + 3, left + pixel - 4, top + pixel - 4], outline=HIGHLIGHT, width=4)


def figure_churn(table: InkTable) -> Image.Image:
    pixel, step = 40, 230
    painter = Painter(0)
    path = [(1, 1, 1, 1)]
    while path[-1] != (4, 0, 0, 0):
        nxt, painter.last_victim = paint_cell(path[-1], 0, painter.last_victim, painter.step)
        path.append(nxt)
    worst = [(2, 0, 2, 0), (2, 1, 1, 0)]
    image = Image.new("RGB", (60 + len(path) * step, 2 * (2 * pixel + 120) + 40), WHITE)
    d = ImageDraw.Draw(image)

    def draw_path(y, title, states):
        d.text((20, y), title, font=font(17), fill=INK_TEXT)
        for i, s in enumerate(states):
            x = 40 + i * step
            p = table.pattern(s)
            changed = frozenset()
            if i:
                q = table.pattern(states[i - 1])
                changed = frozenset(k for k in range(4) if p[k] != q[k])
                ax = x - step + 2 * pixel + 12
                d.line([ax, y + 30 + pixel, x - 12, y + 30 + pixel], fill=GREY_TEXT, width=3)
                d.polygon([(x - 12, y + 30 + pixel), (x - 24, y + 22 + pixel), (x - 24, y + 38 + pixel)], fill=GREY_TEXT)
                centred(d, (ax + x - 12) / 2, y + 6 + pixel, f"{len(changed)} changed", 14, HIGHLIGHT)
            draw_magnified(d, x, y + 30, p, pixel, changed)
            centred(d, x + pixel, y + 40 + 2 * pixel, state_text(s), 14, GREY_TEXT)

    draw_path(20, "Cyan paints a grey cell solid: three hits, victims magenta, yellow, black", path)
    draw_path(20 + 2 * pixel + 120, "The worst edge: magenta paints over a cyan/yellow checkerboard", worst)
    return image


# ---- 6. Frustration -----------------------------------------------------------

def figure_frustration(table: InkTable) -> Image.Image:
    """Each checkerboard puts one ink on the main diagonal (TL-BR) and the
    other on the anti-diagonal. Give each ink the diagonal it holds in most
    of its checkerboards: the checkerboards whose two inks then want the
    same diagonal are frustrated, out of phase with their 2+1+1 neighbours."""
    boards = {tuple(sorted(i for i in range(4) if s[i])): table.pattern(s)
              for s in all_states() if sorted(s) == [0, 0, 2, 2]}
    votes = {i: 0 for i in range(4)}
    for pair, p in boards.items():
        main = INKS.index(p[0])
        for i in pair:
            votes[i] += 1 if i == main else -1
    diagonal = {i: "main" if votes[i] > 0 else "anti" for i in range(4)}

    size = 560
    image = Image.new("RGB", (size + 360, size + 60), WHITE)
    d = ImageDraw.Draw(image)
    corner = {0: (110, 110), 1: (size - 110, 110), 2: (size - 110, size - 110), 3: (110, size - 110)}
    for (a, b), p in boards.items():
        frustrated = diagonal[a] == diagonal[b]
        (x0, y0), (x1, y1) = corner[a], corner[b]
        d.line([x0, y0, x1, y1], fill=HIGHLIGHT if frustrated else (160, 160, 160), width=6 if frustrated else 3)
        along = 0.3 if frustrated else 0.5     # the diagonals cross at the centre
        if frustrated and a != 0:
            (x0, y0), (x1, y1) = (x1, y1), (x0, y0)    # M-K: measure from M
        mx, my = x0 + along * (x1 - x0), y0 + along * (y1 - y0)
        draw_cells(d, int(mx - 24), int(my - 24), tiled(p, 2), 12)
        outline(d, int(mx - 24), int(my - 24), 48, 48, HIGHLIGHT if frustrated else (0, 0, 0), 3 if frustrated else 1)
    for i, (x, y) in corner.items():
        d.ellipse([x - 44, y - 44, x + 44, y + 44], fill=INK_RGB[INKS[i]], outline=(0, 0, 0), width=2)
        centred(d, x, y - 12, INKS[i], 22, WHITE if INKS[i] == "K" else INK_TEXT)
        centred(d, x, y + 50 if y > size / 2 else y - 72, f"{diagonal[i]} diagonal", 15, GREY_TEXT)
    notes = [
        "Each line is a checkerboard of its two inks.",
        "A checkerboard puts one ink on each diagonal.",
        "",
        "Inks next to each other in the cycle",
        "C->M->Y->K sit on opposite diagonals,",
        "and their checkerboards agree with the",
        "2+1+1 patterns around them.",
        "",
        "Opposite inks, C/Y and M/K, want the",
        "same diagonal, so their checkerboards",
        "(red) must put one ink on the wrong one.",
        "All four of the table's 4-pixel edges",
        "touch these two checkerboards.",
    ]
    for i, text in enumerate(notes):
        d.text((size + 10, 120 + i * 24), text, font=font(15), fill=INK_TEXT)
    return image


def main() -> None:
    table = InkTable.load()
    figures = {
        "dither_table.png": figure_table,
        "dither_coherence.png": figure_coherence,
        "dither_stripes.png": figure_stripes,
        "dither_grey.png": figure_grey,
        "dither_churn.png": figure_churn,
        "dither_frustration.png": figure_frustration,
    }
    IMAGES_DIRPATH.mkdir(parents=True, exist_ok=True)
    for filename, draw in figures.items():
        filepath = IMAGES_DIRPATH / filename
        draw(table).save(filepath)
        print(f"Wrote {filepath}")


if __name__ == "__main__":
    main()
