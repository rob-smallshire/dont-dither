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


# ---- On the title screen -------------------------------------------------------

def test_the_title_screen_plays_the_music(launch_bbc, game_build):
    bbc = launch_bbc()
    splash = game_build.labels["SPLASH"]
    bbc.boot_disc(game_build.disc_filepath)
    bbc.debugger.run_to(splash["splash_key"], timeout=60)
    bbc.run_for_emulated_seconds(1.0)
    peek = bbc.memory.address.peek
    assert peek[0x0220] | peek[0x0221] << 8 == splash["music_event"]
    bbc.debugger.run_to(splash["music_tick_done"])      # it is ticking
    heard = False
    for _ in range(100):                                 # something sounds within 2 s
        bbc.debugger.step(1)
        bbc.debugger.run_to(splash["music_tick_done"])
        heard |= any(v != 15 for _, v in chip_registers(bbc))
    assert heard


def test_choosing_the_game_silences_the_music_first(launch_bbc, game_build):
    bbc = launch_bbc()
    splash = game_build.labels["SPLASH"]
    bbc.boot_disc(game_build.disc_filepath)
    bbc.debugger.run_to(splash["splash_key"], timeout=60)
    bbc.run_for_emulated_seconds(3.0)                    # into the song
    bbc.keyboard.type("4")
    bbc.debugger.run_to(game_build.labels["DITHER"]["select_players"], timeout=60)
    peek = bbc.memory.address.peek
    assert peek[0x0220] | peek[0x0221] << 8 != splash["music_event"]
    assert [v for _, v in chip_registers(bbc)] == [15, 15, 15, 15]


# ---- Recorded from the emulator ---------------------------------------------------

RECORD_SECONDS = 12.0


def test_record_the_tune_from_the_emulator(launch_bbc, game_build):
    """Record TUNE's sound as Beebium produces it (its SN76489 emulation, not
    ours) to build/music/beebium_theme.wav, to listen to beside the model's
    build/music/splash_theme.wav. Beebium streams 48 kHz frames of 8 signed
    16-bit values: the chip's four channels, then four reserved (silent)."""
    import threading

    import numpy as np

    from dontdither.build import BUILD_DIRPATH
    from dontdither.sn76489 import write_wav

    bbc = launch_bbc()
    fmt = bbc.audio.format
    chunks, stop = [], threading.Event()

    def collect():
        for chunk in bbc.audio.subscribe(chunk_size=4096):
            if stop.is_set():
                break
            chunks.append(chunk.samples)

    thread = threading.Thread(target=collect, daemon=True)
    run_program(bbc, game_build, "TUNE")
    thread.start()
    bbc.run_for_emulated_seconds(RECORD_SECONDS)
    stop.set()
    frames = np.frombuffer(b"".join(chunks), dtype="<i2").reshape(-1, 8).astype(float)
    mix = frames[:, :4].sum(axis=1)
    mix -= mix.mean()
    peak = np.abs(mix).max()
    assert peak > 0, "the emulator played nothing"
    write_wav(BUILD_DIRPATH / "music" / "beebium_theme.wav", mix / peak * 0.9, rate=fmt.sample_rate)
    assert len(mix) / fmt.sample_rate > RECORD_SECONDS / 2
