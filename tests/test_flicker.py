"""Tanks never flicker: every video field shows every tank whole, while they
drive and fire (shots painting under tanks force extra redraws).

The game redraws a tank by restoring its background, then drawing it anew;
in between it is missing from screen memory. render_sprites races the beam
so that gap is never scanned out. Here all four tanks are driven while every
field is captured, including the first field of each tick, during which the
redraws happen. In every field each tank must appear complete, at either its
position before the tick or its position after it.
"""

import pytest

from conftest import align_to_tick, boot_game
from dontdither.inks import INK_RGB
from dontdither.sprites import FACINGS, coloured, load_tank

CONTROL_SCRIPTED = 3
FIELD_SECONDS = 0.02


@pytest.fixture
def game(launch_bbc, game_build):
    bbc = launch_bbc()
    boot_game(bbc, game_build)
    labels = game_build.labels["DITHER"]
    align_to_tick(bbc, labels)
    return bbc, labels


def tanks(bbc, labels):
    peek = bbc.memory.address.peek
    return [
        (peek[labels["player_sx"] + p], peek[labels["player_sy"] + p],
         peek[labels["player_facing"] + p], "CMYK"[peek[labels["player_ink"] + p]])
        for p in range(peek[labels["player_count"]])
    ]


def shown_fraction(frame, tank_picture, sx, sy, ink):
    pixels = coloured(tank_picture, ink)
    hits = 0
    for (x, y), pixel_ink in pixels.items():
        offset = ((2 * sy + y) * frame.width + 2 * sx + x) * 4
        b, g, r = frame.pixels[offset:offset + 3]
        hits += (r, g, b) == INK_RGB[pixel_ink]
    return hits / len(pixels)


def test_every_field_shows_every_tank_whole(game):
    bbc, labels = game
    picture = load_tank()
    for p in range(4):
        bbc.memory.address.bus[labels["player_control"] + p] = CONTROL_SCRIPTED
        bbc.memory.address.bus[labels["player_input"] + p] = [3, 5, 7, 1][p] | 0x10   # to the centre, firing

    # Capture a frame every field, and record the tanks' positions at every
    # tick boundary. A frame captured after state k was recorded may show any
    # tank at its position in state k-1, k or k+1.
    history = [tanks(bbc, labels)]
    frames = []
    for _ in range(30):
        bbc.run_for_emulated_seconds(FIELD_SECONDS)
        frames.append((len(history) - 1, bbc.video.capture_frame()))
        bbc.debugger.run_to(labels["tick_done"])
        history.append(tanks(bbc, labels))
        frames.append((len(history) - 1, bbc.video.capture_frame()))
    assert history[-1] != history[0], "the tanks should have moved"

    failures = []
    for index, frame in frames:
        candidates = history[max(index - 1, 0):index + 2]
        for p in range(4):
            best = max(
                shown_fraction(frame, picture[FACINGS[state[p][2]]], state[p][0], state[p][1], state[p][3])
                for state in candidates
            )
            if best < 0.95:
                failures.append((index, p, round(best, 2)))
    assert not failures, f"{len(failures)} tank-fields not shown whole, first: {failures[:5]}"
