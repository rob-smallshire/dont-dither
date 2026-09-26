"""The player sprite model. No emulator needed."""

import math

import pytest

from dontdither.sprites import (
    CONTRAST_INK,
    FACINGS,
    SPRITE_PIXELS,
    SpriteError,
    coloured,
    load_tank,
    parse_sprite,
    rotate_clockwise,
)

DIRECTION = {"N": (0, -1), "NE": (1, -1), "E": (1, 0), "SE": (1, 1),
             "S": (0, 1), "SW": (-1, 1), "W": (-1, 0), "NW": (-1, -1)}


@pytest.fixture(scope="module")
def tank():
    return load_tank()


def test_tank_has_all_eight_facings(tank):
    assert tuple(tank) == FACINGS
    for picture in tank.values():
        assert len(picture) == SPRITE_PIXELS
        assert all(len(row) == SPRITE_PIXELS for row in picture)


def test_facings_are_quarter_turns_of_each_other(tank):
    for i, facing in enumerate(FACINGS):
        assert tank[FACINGS[(i + 2) % 8]] == rotate_clockwise(tank[facing])


def test_facings_are_distinct(tank):
    assert len(set(tank.values())) == 8


@pytest.mark.parametrize("facing", FACINGS)
def test_barrel_points_the_way_the_tank_faces(tank, facing):
    """The opaque pixel reaching furthest from the centre lies in the facing direction."""
    dx, dy = DIRECTION[facing]
    norm = math.hypot(dx, dy)
    centre = (SPRITE_PIXELS - 1) / 2
    pixels = [(x, y) for y, row in enumerate(tank[facing]) for x, ch in enumerate(row) if ch != "."]
    furthest = max(pixels, key=lambda p: ((p[0] - centre) * dx + (p[1] - centre) * dy) / norm)
    assert ((furthest[0] - centre) * dx + (furthest[1] - centre) * dy) / norm > 4


@pytest.mark.parametrize("player", "CMYK")
def test_every_player_is_two_tone(tank, player):
    inks = set(coloured(tank["E"], player).values())
    assert inks == {player, CONTRAST_INK[player]}
    assert player != CONTRAST_INK[player]


def test_bad_rows_are_rejected():
    with pytest.raises(SpriteError, match="rows must be"):
        parse_sprite("E\n" + "x" * 12 + "\n")


def test_missing_facing_is_rejected():
    with pytest.raises(SpriteError, match="facing NE"):
        parse_sprite("E\n" + ("." * 12 + "\n") * 12)
