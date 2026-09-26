"""Boot smoke tests: the game disc boots in Beebium and sets up the display.

All tests share one booted machine (see `booted_game`) and only observe it.
"""

import pytest

from dontdither.build import BUILD_DIRPATH
from dontdither.gen_tables import NON_CANONICAL, superpixel_index
from dontdither.inks import INK_RGB, LOGICAL_COLOUR, PHYSICAL_COLOUR, InkTable, pattern_rows_as_mode1_bytes
from dontdither.screen import ARENA_CELLS, MODE1_SCREEN_BASE, MODE1_SCREEN_SIZE, arena_patterns

MOS_CURRENT_MODE = 0x0355
SCREENSHOT_DIRPATH = BUILD_DIRPATH / "screenshots"


@pytest.fixture(scope="module")
def table() -> InkTable:
    return InkTable.load()


@pytest.fixture(scope="module")
def screen(booted_game) -> bytes:
    return bytes(booted_game.memory.address.peek[MODE1_SCREEN_BASE:MODE1_SCREEN_BASE + MODE1_SCREEN_SIZE])


def test_screen_mode_is_1(booted_game):
    assert booted_game.memory.address.peek[MOS_CURRENT_MODE] == 1


def test_palette_maps_logical_colours_to_cmyk(booted_game):
    # In a four-colour mode the ULA palette index takes logical colour bit 1
    # from index bit 3 and bit 0 from index bit 1; bits 2 and 0 are don't-cares.
    palette = booted_game.video_ula.state.palette
    for ink, logical in LOGICAL_COLOUR.items():
        for index in range(16):
            if ((index >> 3) & 1) << 1 | ((index >> 1) & 1) == logical:
                assert palette[index] == PHYSICAL_COLOUR[ink], (ink, index)


def test_every_arena_cell_is_the_four_way_state(screen, table):
    expected = table.pattern((1, 1, 1, 1))
    patterns = arena_patterns(screen)
    wrong = [(sx, sy, p) for sy, row in enumerate(patterns) for sx, p in enumerate(row) if p != expected]
    assert not wrong, f"{len(wrong)} cells differ, first: {wrong[:5]}"


def test_hud_is_untouched_by_the_arena_fill(screen):
    # HUD byte columns 64..79 of every raster line, excluding the title rows
    # (character rows 1 and 2), are still background (logical colour 0).
    for char_row in range(32):
        if char_row in (1, 2):
            continue
        row = screen[char_row * 640 + 512:(char_row + 1) * 640]
        assert row == bytes(128), f"HUD not blank on character row {char_row}"


def test_title_is_shown_in_hud(booted_game):
    text = booted_game.video.screen_text().text
    assert "DON'T" in text
    assert "DITHER!" in text


def test_ink_tables_in_memory_match_the_model(booted_game, game_build, table):
    peek = booted_game.memory.address.peek
    labels = game_build.labels["DITHER"]
    tops, bottoms = zip(*(pattern_rows_as_mode1_bytes(p) for p in table.patterns))
    assert bytes(peek[labels["state_top_bytes"]:labels["state_top_bytes"] + 35]) == bytes(tops)
    assert bytes(peek[labels["state_bottom_bytes"]:labels["state_bottom_bytes"] + 35]) == bytes(bottoms)

    lookup = bytes(peek[labels["pattern_to_state"]:labels["pattern_to_state"] + 256])
    assert labels["pattern_to_state"] % 256 == 0, "pattern_to_state must be page aligned"
    for state_number, pattern in enumerate(table.patterns):
        assert lookup[superpixel_index(pattern)] == state_number
    assert sum(1 for v in lookup if v == NON_CANONICAL) == 256 - 35


def test_displayed_arena_shows_only_cmyk_in_equal_shares(booted_game):
    frame = booted_game.video.capture_frame()
    SCREENSHOT_DIRPATH.mkdir(parents=True, exist_ok=True)
    frame.save_png(SCREENSHOT_DIRPATH / "boot.png")

    arena_pixels = ARENA_CELLS * 2
    tally: dict[tuple[int, int, int], int] = {}
    for y in range(arena_pixels):
        for x in range(arena_pixels):
            offset = (y * frame.width + x) * 4
            b, g, r = frame.pixels[offset:offset + 3]
            tally[(r, g, b)] = tally.get((r, g, b), 0) + 1
    quarter = arena_pixels * arena_pixels // 4
    assert tally == {rgb: quarter for rgb in INK_RGB.values()}
