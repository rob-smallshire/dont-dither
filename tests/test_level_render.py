"""The game draws every level exactly as the level model says.

One machine boots the game, then each level is entered through the
enter_level test hook and its screen and wall map are captured. Tests then
compare them with the model.
"""

from dataclasses import dataclass

import pytest

from conftest import enter_level, show_display
from dontdither.build import BUILD_DIRPATH
from dontdither.levels import Level, load_levels
from dontdither.render import arena_bytes, arena_screen, draw_players
from dontdither.screen import MODE1_ROW_BYTES, MODE1_SCREEN_BASE, MODE1_SCREEN_SIZE
from dontdither.walls import render_wall_cell, wall_bitmap

SCREENSHOT_DIRPATH = BUILD_DIRPATH / "screenshots"
LEVELS = load_levels()


@dataclass(frozen=True)
class Rendered:
    screen: bytes
    wall_map: bytes
    text: str


@pytest.fixture(scope="module")
def rendered(booted_game, game_build) -> dict[int, Rendered]:
    bbc = booted_game
    labels = game_build.labels["DITHER"]
    peek = bbc.memory.address.peek
    SCREENSHOT_DIRPATH.mkdir(parents=True, exist_ok=True)
    results = {}
    for number in range(len(LEVELS)):
        enter_level(bbc, labels, number)       # stopped before the first tick
        show_display(bbc, labels)
        results[number] = Rendered(
            screen=bytes(peek[MODE1_SCREEN_BASE:MODE1_SCREEN_BASE + MODE1_SCREEN_SIZE]),
            wall_map=bytes(peek[labels["wall_map"]:labels["wall_map"] + 128]),
            text=bbc.video.screen_text().text,
        )
        bbc.video.capture_frame().save_png(SCREENSHOT_DIRPATH / f"level_{number:02d}.png")
    return results


def level_params():
    return [pytest.param(n, lv, id=lv.name) for n, lv in enumerate(LEVELS)]


@pytest.mark.parametrize("number, level", level_params())
def test_wall_map_matches_model(rendered, number, level: Level):
    assert rendered[number].wall_map == wall_bitmap(level.wall_cells())


@pytest.mark.parametrize("number, level", level_params())
def test_every_wall_cell_shows_its_tile(rendered, number, level: Level):
    screen = rendered[number].screen
    walls = level.wall_cells()
    wrong = []
    for cx, cy in sorted(walls):
        offset = cy * MODE1_ROW_BYTES + cx * 16
        if screen[offset:offset + 16] != render_wall_cell(walls, cx, cy, level.colouring):
            wrong.append((cx, cy))
    assert not wrong, f"{len(wrong)} wall cells differ, first: {wrong[:5]}"


@pytest.mark.parametrize("number, level", level_params())
def test_arena_matches_the_model_with_tanks_at_their_starts(rendered, number, level: Level):
    """Every arena byte: fill, walls, and each player's tank at its start."""
    expected = arena_screen(level)
    draw_players(expected, [(s.sx, s.sy, s.facing, ink) for s, ink in zip(level.starts(), level.player_inks())])
    actual, wanted = arena_bytes(rendered[number].screen), arena_bytes(expected)
    wrong = [i for i, (a, e) in enumerate(zip(actual, wanted)) if a != e]
    assert not wrong, f"{len(wrong)} arena bytes differ, first offsets {wrong[:8]}"


@pytest.mark.parametrize("number, level", level_params())
def test_hud_shows_level_number(rendered, number, level: Level):
    assert f"LEVEL {number + 1}" in rendered[number].text
