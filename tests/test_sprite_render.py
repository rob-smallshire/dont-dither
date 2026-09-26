"""Tanks are drawn, moved and removed exactly, including where they overlap.

One machine boots the game (level 0, four tanks at their starts). All players
are put under scripted control with no input, so nothing moves by itself.
Tests move tanks by writing player_sx/sy/facing between ticks and running one
tick (which restores the old backgrounds and draws the tanks anew), then
compare the whole arena in screen memory with the model: the bare arena with
the tanks composited in player order.
"""

import random

import pytest

from conftest import align_to_tick, step_ticks
from dontdither.levels import load_levels
from dontdither.render import arena_bytes, arena_screen, draw_players
from dontdither.screen import MODE1_SCREEN_BASE, MODE1_SCREEN_SIZE

LEVEL = load_levels()[0]
MAX_POSITION = 128 - 6


CONTROL_SCRIPTED = 3
NO_DIRECTION = 0x08


@pytest.fixture(scope="module")
def game(booted_game, game_build):
    bbc, labels = booted_game, game_build.labels["DITHER"]
    align_to_tick(bbc, labels)
    for p in range(4):
        bbc.memory.address.bus[labels["player_control"] + p] = CONTROL_SCRIPTED
        bbc.memory.address.bus[labels["player_input"] + p] = NO_DIRECTION
    return bbc, labels


def player_table(bbc, labels):
    peek = bbc.memory.address.peek
    count = peek[labels["player_count"]]
    return [
        (peek[labels["player_sx"] + p], peek[labels["player_sy"] + p],
         peek[labels["player_facing"] + p], "CMYK"[peek[labels["player_ink"] + p]])
        for p in range(count)
    ]


def move(bbc, labels, player, sx, sy, facing):
    bus = bbc.memory.address.bus
    bus[labels["player_sx"] + player] = sx
    bus[labels["player_sy"] + player] = sy
    bus[labels["player_facing"] + player] = facing
    step_ticks(bbc, labels)


def expected_arena(players):
    screen = arena_screen(LEVEL)
    draw_players(screen, players)
    return arena_bytes(screen)


def actual_arena(bbc):
    return arena_bytes(bytes(bbc.memory.address.peek[MODE1_SCREEN_BASE:MODE1_SCREEN_BASE + MODE1_SCREEN_SIZE]))


def assert_screen_matches(bbc, players):
    actual, expected = actual_arena(bbc), expected_arena(players)
    wrong = [i for i, (a, e) in enumerate(zip(actual, expected)) if a != e]
    assert not wrong, f"{len(wrong)} arena bytes differ, first offsets {wrong[:8]}"


def test_players_start_at_the_level_starts(game):
    bbc, labels = game
    starts = [(s.sx, s.sy, s.facing, ink) for s, ink in zip(LEVEL.starts(), LEVEL.player_inks())]
    assert player_table(bbc, labels) == starts


def test_tanks_are_drawn_at_their_starts(game):
    bbc, _ = game
    assert_screen_matches(bbc, [(s.sx, s.sy, s.facing, ink) for s, ink in zip(LEVEL.starts(), LEVEL.player_inks())])


@pytest.mark.parametrize("sx", [40, 41])        # even and odd alignment
@pytest.mark.parametrize("facing", range(8))
def test_tank_moves_in_every_facing_and_alignment(game, sx, facing):
    bbc, labels = game
    move(bbc, labels, 0, sx, 44, facing)
    assert_screen_matches(bbc, player_table(bbc, labels))


def test_overlapping_tanks_draw_in_player_order(game):
    bbc, labels = game
    move(bbc, labels, 0, 60, 60, 2)
    move(bbc, labels, 1, 63, 62, 6)          # overlaps player 0
    assert_screen_matches(bbc, player_table(bbc, labels))


def test_separating_overlapped_tanks_leaves_no_residue(game):
    bbc, labels = game
    move(bbc, labels, 0, 60, 60, 2)
    move(bbc, labels, 1, 63, 62, 6)
    move(bbc, labels, 0, 20, 70, 0)
    move(bbc, labels, 1, 90, 70, 4)
    assert_screen_matches(bbc, player_table(bbc, labels))


def test_random_moves_soak(game):
    """Many moves, often overlapping; the arena must stay exact throughout."""
    bbc, labels = game
    rng = random.Random(1234)
    for _ in range(25):
        player = rng.randrange(4)
        sx = rng.randrange(30, 60)            # a crowded region, so tanks overlap
        sy = rng.randrange(40, 70)
        move(bbc, labels, player, sx, sy, rng.randrange(8))
        assert_screen_matches(bbc, player_table(bbc, labels))
