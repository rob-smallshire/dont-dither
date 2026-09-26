"""Boot smoke tests: the game disc boots in Beebium, sets up the display and
draws the first level. (test_level_render.py checks every level in detail.)

All tests share one booted machine (see `booted_game`) and only observe it.
"""

import pytest

from conftest import align_to_tick

from dontdither.build import BUILD_DIRPATH
from dontdither.gen_tables import NON_CANONICAL, superpixel_index
from dontdither.inks import (
    INK_RGB,
    LOGICAL_COLOUR,
    PHYSICAL_COLOUR,
    InkTable,
    mode1_pixels,
    pattern_rows_as_mode1_bytes,
)
from dontdither.levels import load_levels
from dontdither.screen import ARENA_CELLS, MODE1_ROW_BYTES, MODE1_SCREEN_BASE, MODE1_SCREEN_SIZE
from dontdither.walls import wall_bitmap

HUD_TEXT_ROWS = (1, 2, 4, 6)   # title, title, level name, clock

MOS_CURRENT_MODE = 0x0355
SCREENSHOT_DIRPATH = BUILD_DIRPATH / "screenshots"


@pytest.fixture(scope="module")
def table() -> InkTable:
    return InkTable.load()


@pytest.fixture(scope="module")
def screen(booted_game, game_build) -> bytes:
    align_to_tick(booted_game, game_build.labels["DITHER"])   # tanks drawn
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


def test_boots_into_the_first_level(booted_game, game_build):
    labels = game_build.labels["DITHER"]
    peek = booted_game.memory.address.peek
    assert peek[labels["zp_level"]] == 0
    wall_map = bytes(peek[labels["wall_map"]:labels["wall_map"] + 128])
    assert wall_map == wall_bitmap(load_levels()[0].wall_cells())


def test_hud_is_blank_apart_from_its_text(screen):
    # HUD byte columns 64..79 of every character row except those holding
    # text are still background (logical colour 0).
    for char_row in range(32):
        if char_row in HUD_TEXT_ROWS:
            continue
        row = screen[char_row * MODE1_ROW_BYTES + 512:(char_row + 1) * MODE1_ROW_BYTES]
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


def test_displayed_arena_matches_screen_memory(booted_game, game_build, screen):
    """The frame Beebium displays shows exactly the arena in screen memory.

    The game redraws its tanks every tick, so the display is compared while
    the CPU is held in hold_display, with no redraw in progress.
    """
    bbc, labels = booted_game, game_build.labels["DITHER"]
    align_to_tick(bbc, labels)
    bbc.cpu.pc = labels["hold_display"]
    bbc.run_for_emulated_seconds(0.06)            # three fields
    frame = bbc.video.capture_frame()
    bbc.debugger.run_to(labels["hold_display"])   # an instruction boundary
    bbc.cpu.pc = labels["tick_done"]
    SCREENSHOT_DIRPATH.mkdir(parents=True, exist_ok=True)
    frame.save_png(SCREENSHOT_DIRPATH / "boot.png")

    rgb_of_logical = {LOGICAL_COLOUR[ink]: rgb for ink, rgb in INK_RGB.items()}
    arena_pixels = ARENA_CELLS * 2
    mismatches = 0
    for y in range(arena_pixels):
        for byte_column in range(arena_pixels // 4):
            byte = screen[(y // 8) * MODE1_ROW_BYTES + byte_column * 8 + y % 8]
            for p, logical in enumerate(mode1_pixels(byte)):
                offset = (y * frame.width + byte_column * 4 + p) * 4
                b, g, r = frame.pixels[offset:offset + 3]
                mismatches += (r, g, b) != rgb_of_logical[logical]
    assert mismatches == 0
