"""Computer players.

The 6502 AI must make exactly the model's decisions (tools/dontdither/ai.py),
so a round with AI players replays identically in both. The model tests
check the AI plays sensibly: it keeps moving, avoids walls and paints.
"""

import pytest

from conftest import boot_game, enter_level, step_ticks
from dontdither.ai import AI_PERIOD, samples
from dontdither.game import FIRE_BIT, NO_DIRECTION, Game
from dontdither.levels import load_levels
from dontdither.render import arena_bytes, arena_screen, draw_players
from dontdither.screen import MODE1_SCREEN_BASE, MODE1_SCREEN_SIZE

CONTROL_AI = 4


# ---- Model --------------------------------------------------------------------

def all_ai(level):
    game = Game.start(level)
    for p in game.players:
        p.ai = True
    return game


def test_samples_rotate_with_the_direction():
    """Each direction's samples are a quarter turn of those two before it."""
    for direction in range(8):
        turned = tuple((5 - y, x) for x, y in samples(direction))
        assert samples((direction + 2) % 8) == turned


@pytest.mark.parametrize("level", load_levels(), ids=lambda lv: lv.name)
def test_ai_players_keep_moving_and_paint(level):
    game = all_ai(level)
    last = [(p.sx, p.sy) for p in game.players]
    steps = [0] * len(game.players)
    for _ in range(25 * 60):
        game.tick()
        for i, p in enumerate(game.players):
            steps[i] += (p.sx, p.sy) != last[i]
            last[i] = (p.sx, p.sy)
    grey = sum(1 for s in game.cells.values() if s == (1, 1, 1, 1)) / len(game.cells)
    assert min(steps) > 600, steps           # of about 1,170 possible in a minute
    assert grey < 0.7


def test_ai_think_in_turns():
    game = all_ai(load_levels()[0])
    for tick in range(8):
        before = [p.ai_input for p in game.players]
        game.tick()
        changed = [i for i, p in enumerate(game.players) if p.ai_input != before[i]]
        assert all((tick + i) % AI_PERIOD == 0 for i in changed)


# ---- The 6502 AI --------------------------------------------------------------

@pytest.fixture
def game(launch_bbc, game_build):
    bbc = launch_bbc()
    boot_game(bbc, game_build)
    return bbc, game_build.labels["DITHER"]


@pytest.mark.parametrize("level_number", [0, 1, 2])
def test_6502_ai_matches_the_model(game, level_number):
    bbc, labels = game
    enter_level(bbc, labels, level_number)
    level = load_levels()[level_number]
    model = all_ai(level)
    peek = bbc.memory.address.peek
    for p in range(len(model.players)):
        bbc.memory.address.bus[labels["player_control"] + p] = CONTROL_AI
    fields = ("player_sx", "player_sy", "player_facing", "player_input", "player_cooldown")
    for tick in range(200):
        step_ticks(bbc, labels)
        model.tick()
        actual = [tuple(peek[labels[f] + p] for f in fields) for p in range(len(model.players))]
        expected = [(p.sx, p.sy, p.facing, p.ai_input, p.cooldown) for p in model.players]
        assert actual == expected, f"tick {tick}"
    screen = bytes(peek[MODE1_SCREEN_BASE:MODE1_SCREEN_BASE + MODE1_SCREEN_SIZE])
    expected_screen = arena_screen(level, model.cells)
    draw_players(expected_screen, [(p.sx, p.sy, p.facing, p.ink) for p in model.players])
    assert arena_bytes(screen) == arena_bytes(expected_screen)
