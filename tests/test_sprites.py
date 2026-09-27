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


def test_axial_tank_is_mirror_symmetric_about_its_barrel_row(tank):
    """Drawn in 11 rows (row 11 empty) so the one-pixel barrel has a centre row."""
    east = tank["E"]
    assert east[11] == "." * SPRITE_PIXELS
    assert all(east[5 - d] == east[5 + d] for d in range(6))


def test_diagonal_tank_is_mirror_symmetric_about_the_box_diagonal(tank):
    north_east = tank["NE"]
    n = SPRITE_PIXELS - 1
    assert all(north_east[y][x] == north_east[n - x][n - y] for y in range(n + 1) for x in range(n + 1))


def shift_right_a_superpixel(plane: bytes) -> list[int]:
    """What prepare_sprite (asm/sprites.asm) does to a stored frame plane for
    odd sx: per raster line of 4 bytes, each byte's pixels 0-1 move to 2-3,
    and the byte to its left gives its pixels 2-3 to this one's 0-1."""
    return [((b >> 2) & 0x33) | (((plane[i - 1] if i % 4 else 0) << 2) & 0xCC)
            for i, b in enumerate(plane)]


def test_odd_frames_are_the_even_frames_shifted():
    """Only even-sx frames are stored; the game shifts them for odd sx."""
    from dontdither.sprites import FACINGS, frame_planes, load_tank

    tank = load_tank()
    for facing in FACINGS:
        for even, odd in zip(frame_planes(tank[facing], 0), frame_planes(tank[facing], 1)):
            assert all(even[i] == 0 for i in range(3, len(even), 4)), facing   # 4th column empty
            assert shift_right_a_superpixel(even) == list(odd), facing
