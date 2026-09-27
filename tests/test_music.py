"""The title music: the song, the player model, and the 6502 player
(asm/music.asm), which must drive the SN76489 exactly as the model does.

The emulator tests run TUNE (the player alone) and, tick by tick, compare
the chip's registers with those the model's writes leave.
"""

import pytest

from conftest import run_program
from dontdither import splash_theme
from dontdither.music import (
    NOTE_PERIODS,
    Player,
    compile_song,
    note_index,
    song_assembly,
    tone_period,
)
from dontdither.sn76489 import SN76489, render

SONG = splash_theme.song()


def model_player() -> Player:
    return Player(compile_song(SONG, base=0x2000), SONG.instruments)


# ---- The model -----------------------------------------------------------------

def test_a4_has_the_bbc_period():
    assert NOTE_PERIODS[note_index("A4")] == tone_period(440.0) == 284


def test_every_note_is_in_range_and_every_section_lines_up():
    song_assembly(SONG, "check")                      # checks note ranges
    for section in SONG.order:
        SONG.section_ticks(section)                   # asserts equal lengths


def test_the_loop_is_about_forty_seconds():
    assert 35 <= splash_theme.loop_ticks() / 50 <= 50


def test_the_song_is_small():
    assert len(compile_song(SONG, base=0x2000).data) < 2048


def test_the_player_loops_back_to_the_start():
    player = model_player()
    first = [player.tick() for _ in range(200)]
    for _ in range(splash_theme.loop_ticks() - 200):
        player.tick()
    again = [player.tick() for _ in range(200)]
    assert again == first


def test_the_music_is_audible():
    player = model_player()
    audio = render([player.tick() for _ in range(250)])
    assert abs(audio).max() > 0.5


# ---- The 6502 player -----------------------------------------------------------

@pytest.fixture
def tune(launch_bbc, game_build):
    bbc = launch_bbc()
    run_program(bbc, game_build, "TUNE")
    return bbc, game_build.labels["TUNE"]


def audible(registers: list[tuple]) -> list[tuple]:
    """Registers as heard: a silent channel's (attenuation 15) setting does
    not matter (and may be left over from before the song began)."""
    return [(setting if volume != 15 else None, volume) for setting, volume in registers]


def chip_registers(bbc) -> list[tuple]:
    state = bbc.sound.state()
    tones = [(state.tone(c).frequency_divider, state.tone(c).volume) for c in range(3)]
    noise = state.noise
    return audible(tones + [(noise.noise_rate | (4 if noise.white_noise else 0), noise.volume)])


def model_registers(chip: SN76489) -> list[tuple]:
    return audible([(chip.periods[c], chip.attenuation[c]) for c in range(3)]
                   + [(chip.noise_control, chip.attenuation[3])])


def test_the_6502_player_matches_the_model_tick_by_tick(tune):
    bbc, labels = tune
    player, chip = model_player(), SN76489()
    # From the start of the song: the player may already have run some ticks
    # by the time the harness sees it ready, so restart it from a boundary.
    bbc.debugger.run_to(labels["idle"])
    old = bytes(bbc.memory.address.peek[labels["music_old_eventv"]:labels["music_old_eventv"] + 2])
    bbc.memory.address.bus[0x0220:0x0222] = old       # unhook, to hook afresh
    bbc.cpu.pc = labels["start"]
    for tick in range(splash_theme.loop_ticks() + 100):   # the whole loop, and round again
        if bbc.cpu.pc == labels["music_tick_done"]:
            bbc.debugger.step(1)                      # (run_to would stop at once)
        bbc.debugger.run_to(labels["music_tick_done"])
        for byte in player.tick():
            chip.write(byte)
        assert chip_registers(bbc) == model_registers(chip), f"tick {tick}"
