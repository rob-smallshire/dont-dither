"""Computer players.

The 6502 AI must make exactly the model's decisions (tools/dontdither/ai.py),
so a round with AI players replays identically in both. The model tests
check the AI plays sensibly: it keeps moving, avoids walls and paints.
"""

import pytest

from conftest import SAMPLE_SET_LEVELS, SAMPLE_SET_LEVEL_IDS, boot_game, enter_level, step_ticks
from dontdither.ai import AI_PERIOD, samples
from dontdither.game import (
    DEFAULT_RANDOM_STATE,
    FIRE_BIT,
    HUMAN_PLAYERS,

    NO_DIRECTION,
    Game,
    next_random,
    random_direction,
)
from dontdither.levels import level_set, load_levels
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
    refilling = [0] * len(game.players)
    for _ in range(25 * 60):
        game.tick()
        for i, p in enumerate(game.players):
            steps[i] += (p.sx, p.sy) != last[i]
            last[i] = (p.sx, p.sy)
            refilling[i] += p.ai_refilling
    grey = sum(1 for s in game.cells.values() if s == (1, 1, 1, 1)) / len(game.cells)
    assert min(steps) > 600, steps           # of about 1,170 possible in a minute
    # Ink is limited: every AI paints, runs dry and refills -- but it spends
    # most of its time painting.
    assert all(0 < r / (25 * 60) < 0.8 for r in refilling), refilling
    assert grey < 0.8


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


@pytest.mark.parametrize("players, level_number", SAMPLE_SET_LEVELS, ids=SAMPLE_SET_LEVEL_IDS)
def test_6502_ai_matches_the_model(launch_bbc, game_build, players, level_number):
    bbc = launch_bbc()
    boot_game(bbc, game_build, players)
    labels = game_build.labels["DITHER"]
    enter_level(bbc, labels, level_number)
    level = level_set(players)[level_number]
    model = all_ai(level)
    peek = bbc.memory.address.peek
    for p, player in enumerate(model.players):
        bbc.memory.address.bus[labels["player_control"] + p] = CONTROL_AI
        # Little ink, so the AIs run dry, refill and paint again.
        bbc.memory.address.bus[labels["player_reservoir"] + p] = player.reservoir = 2 + p
    fields = ("player_sx", "player_sy", "player_facing", "player_input", "player_cooldown",
              "player_reservoir", "player_reservoir_fraction", "ai_refilling")
    for tick in range(300):
        step_ticks(bbc, labels)
        model.tick()
        actual = [tuple(peek[labels[f] + p] for f in fields) for p in range(len(model.players))]
        expected = [(p.sx, p.sy, p.facing, p.ai_input, p.cooldown,
                     p.reservoir, p.reservoir_fraction, int(p.ai_refilling)) for p in model.players]
        assert actual == expected, f"tick {tick}"
    screen = bytes(peek[MODE1_SCREEN_BASE:MODE1_SCREEN_BASE + MODE1_SCREEN_SIZE])
    expected_screen = arena_screen(level, model.cells)
    draw_players(expected_screen, [(p.sx, p.sy, p.facing, p.ink) for p in model.players])
    assert arena_bytes(screen) == arena_bytes(expected_screen)


# ---- Random starting directions ----------------------------------------------

def test_the_random_generator_has_a_full_period():
    state, seen = 0, set()
    for _ in range(256):
        state = next_random(state)
        seen.add(state)
    assert len(seen) == 256


@pytest.mark.parametrize("level", load_levels(), ids=lambda lv: lv.name)
def test_ai_players_start_facing_random_directions(level):
    game = Game.start(level)
    state = DEFAULT_RANDOM_STATE
    for index, (player, start) in enumerate(zip(game.players, level.starts())):
        if index < HUMAN_PLAYERS:
            assert player.facing == start.facing            # humans face the level's way
        else:
            direction, state = random_direction(state)
            assert player.facing == player.ai_direction == direction
    assert game.random_state == state


def test_different_seeds_start_ais_differently():
    level = load_levels()[0]
    facings = {tuple(p.facing for p in Game.start(level, seed, humans=0).players) for seed in range(256)}
    assert len(facings) > 32


def rotated_positions(game, level):
    """Each player's position turned back to player 0's quarter of the
    arena, by (x, y) -> (y, 122 - x) per symmetry step."""
    turned = []
    for index, p in enumerate(game.players):
        x, y = p.sx, p.sy
        for _ in range(index * level.symmetry.value):
            x, y = y, 122 - x
        turned.append((x, y))
    return turned


def shared_path(game, level, ticks=150) -> float:
    """How much of the AIs' paths, each turned back to player 0's quarter,
    they all share: 1.0 if they dance in step (each a tick or so behind the
    last, as AIs think on staggered ticks), near 0 if each goes its own way."""
    paths = [set() for _ in game.players]
    for _ in range(ticks):
        game.tick()
        for path, position in zip(paths, rotated_positions(game, level)):
            path.add(position)
    return len(set.intersection(*paths)) / len(set.union(*paths))


@pytest.mark.parametrize("level", [lv for lv in load_levels() if lv.symmetry.copies == 4],
                         ids=lambda lv: lv.name)
def test_ai_players_no_longer_dance_in_step(level):
    """With the level's facings, four identical AIs trace the same path under
    rotation, like country dancers; with random facings they share far less
    of it (only as much as the walls funnel them along the same streets)."""
    dancers = Game.start(level, humans=4)          # the level's facings...
    for player in dancers.players:
        player.ai = True                                      # ...all played by the AI
    in_step = shared_path(dancers, level)
    assert in_step > 0.9
    assert shared_path(Game.start(level, humans=0), level) < in_step / 2


@pytest.mark.parametrize("players, level_number", SAMPLE_SET_LEVELS, ids=SAMPLE_SET_LEVEL_IDS)
def test_6502_ais_start_facing_as_the_model_says(launch_bbc, game_build, players, level_number):
    bbc = launch_bbc()
    boot_game(bbc, game_build, players)
    labels = game_build.labels["DITHER"]
    bbc.memory.address.bus[labels["session_humans"]] = 0     # demo mode: all AI
    enter_level(bbc, labels, level_number)
    model = Game.start(level_set(players)[level_number], humans=0)
    peek = bbc.memory.address.peek
    count = len(model.players)
    assert [peek[labels["player_facing"] + p] for p in range(count)] == [p.facing for p in model.players]
    assert [peek[labels["ai_direction"] + p] for p in range(count)] == [p.ai_direction for p in model.players]
    assert peek[labels["random_state"]] == model.random_state
