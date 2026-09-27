"""Draw the graph of the 35 ink states, sliced by how much black they hold,
with each state's canonical pattern at its node and each edge within a slice
coloured by its churn (the pixels that change between the two patterns).

    uv run dd-preview-ink-graph   # -> docs/images/ink_state_graph.png

See docs/ink_patterns.md.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from dontdither.inks import INK_RGB, PROJECT_DIRPATH, InkTable, adjacent_state_pairs, all_states, hamming

IMAGE_FILEPATH = PROJECT_DIRPATH / "docs" / "images" / "ink_state_graph.png"
PIXEL = 9                      # one pattern pixel, drawn
SPACING = 64                   # between neighbouring states in a slice
MARGIN = 96
CHURN_COLOUR = {1: (150, 150, 150), 2: (60, 120, 255), 3: (255, 150, 0), 4: (230, 30, 30)}
CHURN_WIDTH = {1: 2, 2: 3, 3: 4, 4: 5}
SLICE_SIZES = [4, 3, 2, 1, 0]  # C + M + Y in each slice; K = 4 - size


def draw() -> Image.Image:
    table = InkTable.load()
    states = all_states()
    width = MARGIN + sum(n * SPACING + MARGIN for n in SLICE_SIZES)
    height = 4 * SPACING + 150
    image = Image.new("RGB", (width, height), (255, 255, 255))
    d = ImageDraw.Draw(image)

    # Each slice is a triangle: C at the top, M bottom left, Y bottom right.
    position = {}
    x0 = MARGIN // 2
    for n in SLICE_SIZES:
        k = 4 - n
        for s in states:
            c, m, y, black = s
            if black == k:
                position[s] = (x0 + n * SPACING / 2 + (y - m) * SPACING / 2,
                               60 + (m + y) * SPACING * 0.866 + k * SPACING * 0.433)
        d.text((x0 + n * SPACING / 2 - 30, 10), f"K = {k} (black {k}/4)", fill=(0, 0, 0))
        x0 += n * SPACING + MARGIN

    for s, t in adjacent_state_pairs(states):
        if s[3] == t[3]:       # within a slice
            churn = hamming(table.pattern(s), table.pattern(t))
            d.line([position[s], position[t]], fill=CHURN_COLOUR[churn], width=CHURN_WIDTH[churn])

    for s, (px, py) in position.items():
        x, y = px - PIXEL, py - PIXEL
        for i, ink in enumerate(table.pattern(s)):
            left, top = x + (i % 2) * PIXEL, y + (i // 2) * PIXEL
            d.rectangle([left, top, left + PIXEL - 1, top + PIXEL - 1], fill=INK_RGB[ink])
        d.rectangle([x - 1, y - 1, x + 2 * PIXEL, y + 2 * PIXEL], outline=(0, 0, 0))

    legend_y = height - 40
    for i, churn in enumerate((1, 2, 3, 4)):
        lx = 40 + i * 200
        d.line([(lx, legend_y), (lx + 50, legend_y)], fill=CHURN_COLOUR[churn], width=CHURN_WIDTH[churn])
        label = f"{churn} pixel changes" if churn == 1 else f"{churn} pixels change"
        d.text((lx + 60, legend_y - 6), label, fill=(0, 0, 0))
    return image.resize((image.width * 2, image.height * 2), Image.NEAREST)


def main() -> None:
    IMAGE_FILEPATH.parent.mkdir(parents=True, exist_ok=True)
    draw().save(IMAGE_FILEPATH, optimize=True)
    print(IMAGE_FILEPATH)


if __name__ == "__main__":
    main()
