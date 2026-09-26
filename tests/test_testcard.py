"""The TCARD program draws the texture and wall test card exactly as modelled.

All tests share one machine showing the test card (see `testcard`) and only
observe it.
"""

import pytest

from dontdither.build import BUILD_DIRPATH
from dontdither.inks import InkTable
from dontdither.screen import MODE1_ROW_BYTES, MODE1_SCREEN_BASE, MODE1_SCREEN_SIZE, arena_patterns
from dontdither.testcard import cell_colouring, state_at, wall_cells
from dontdither.walls import render_wall_cell

SCREENSHOT_DIRPATH = BUILD_DIRPATH / "screenshots"


@pytest.fixture(scope="module")
def screen(testcard) -> bytes:
    return bytes(testcard.memory.address.peek[MODE1_SCREEN_BASE:MODE1_SCREEN_BASE + MODE1_SCREEN_SIZE])


def cell_bytes(screen: bytes, cx: int, cy: int) -> bytes:
    offset = cy * MODE1_ROW_BYTES + cx * 16
    return screen[offset:offset + 16]


def test_every_open_superpixel_shows_its_swatch_state(screen):
    table = InkTable.load()
    walls = wall_cells()
    patterns = arena_patterns(screen)
    wrong = [
        (sx, sy, patterns[sy][sx], table.pattern(state_at(sx, sy)))
        for sy in range(128)
        for sx in range(128)
        if (sx // 4, sy // 4) not in walls and patterns[sy][sx] != table.pattern(state_at(sx, sy))
    ]
    assert not wrong, f"{len(wrong)} superpixels differ, first: {wrong[:5]}"


def test_every_wall_cell_shows_its_tile(screen):
    walls = wall_cells()
    wrong = [
        (cx, cy)
        for cx, cy in sorted(walls)
        if cell_bytes(screen, cx, cy) != render_wall_cell(walls, cx, cy, cell_colouring(cx, cy))
    ]
    assert not wrong, f"{len(wrong)} wall cells differ, first: {wrong[:5]}"


def test_open_superpixels_are_all_canonical(screen):
    table = InkTable.load()
    walls = wall_cells()
    patterns = arena_patterns(screen)
    for sy in range(128):
        for sx in range(128):
            if (sx // 4, sy // 4) not in walls:
                assert table.state_of(patterns[sy][sx]) is not None, (sx, sy)


def test_title_is_shown_in_hud(testcard):
    text = testcard.video.screen_text().text
    assert "TEST" in text and "CARD" in text


def test_save_screenshots(testcard):
    frame = testcard.video.capture_frame()
    SCREENSHOT_DIRPATH.mkdir(parents=True, exist_ok=True)
    frame.save_png(SCREENSHOT_DIRPATH / "testcard.png")
    image = frame.to_pil_image().convert("RGB")
    image.resize((image.width * 3, image.height * 3), resample=0).save(SCREENSHOT_DIRPATH / "testcard_x3.png")
