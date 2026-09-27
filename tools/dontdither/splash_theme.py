"""The title screen's music: an original loop in the spirit of Splatoon's
battle music (punk rock with chip-tune sparkle), for the SN76489.

D Mixolydian at 187.5 BPM (a 16th note is 4 ticks of 50 Hz). Channel 0 is
the lead (the "squid" vocal: short syllables, call and response, a flat
third against the major chord now and then), channel 1 the guitar (fast
arpeggiated power chords, chugs and stabs), channel 2 the bass (roots in
8ths, octave pops), and the noise channel the drums (a punk two-beat, fills
and a riser).

    Intro  4 bars   drum fill, then a rising run
    A      8 bars   I-bVII-IV-I (D C G D), call and response
    B      8 bars   double time, offbeat stabs: Bb C D D | Bb C F# A
    Break  4 bars   a stop, an arpeggio solo, a noise riser
    Chorus 8 bars   gang-shout unison: D C G D | D C Bb F#

The lowest tone the chip plays is B2, so the bass roots are D3, C3, G3,
Bb3, F#3 and A3.
"""

from __future__ import annotations

from dontdither.music import Instrument, Song, pattern

TICKS_PER_STEP = 4                 # a 16th note; 16 steps a bar
STEPS_PER_BAR = 16

# Noise control values: bit 2 white (1) or periodic (0); bits 0-1 the rate
# (0 fastest, 2 slowest, 3 following tone channel 2).
KICK_NOISE, SNARE_NOISE, HAT_NOISE = 2, 5, 4


def ramp(start: int, end: int, ticks: int) -> tuple[int, ...]:
    return tuple(round(start + (end - start) * t / (ticks - 1)) for t in range(ticks))


INSTRUMENTS = {
    # The lead: a sharp attack, settling to a sung level.
    "lead":   Instrument(envelope=(0, 0, 1, 2, 3, 3, 4, 4, 5)),
    # ...scooping up a tone into the note, then holding it.
    "scoop":  Instrument(envelope=(1, 0, 0, 1, 2, 3, 3, 4, 4, 5), arpeggio=(-2, -1, 0), arpeggio_loop=2),
    # The solo: a fast major arpeggio from each note.
    "solo":   Instrument(envelope=(0, 1, 1, 2, 3, 4, 5, 6), arpeggio=(0, 4, 7, 12)),
    # Guitar: a palm-muted power chord, and an open one.
    "chug":   Instrument(envelope=(1, 3, 6, 10, 15), arpeggio=(0, 7, 12)),
    "open":   Instrument(envelope=(0, 1, 2, 3, 4, 5, 6, 7, 8), arpeggio=(0, 7, 12)),
    # Stabs: a short major chord.
    "stab":   Instrument(envelope=(0, 2, 4, 7, 11, 15), arpeggio=(0, 4, 7)),
    # The gang shout, doubling the lead an octave up and down.
    "shout":  Instrument(envelope=(0, 0, 1, 2, 3, 4, 5, 6), arpeggio=(0, 12)),
    # Bass: punchy 8ths.
    "bass":   Instrument(envelope=(0, 1, 2, 4, 6, 8, 11, 15)),
    "boom":   Instrument(envelope=(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)),
    # Drums, on the noise channel.
    "kick":   Instrument(envelope=(0, 2, 5, 9, 15)),
    "snare":  Instrument(envelope=(0, 1, 3, 5, 7, 9, 11, 13, 15)),
    "hat":    Instrument(envelope=(7, 11, 15)),
    "crash":  Instrument(envelope=ramp(0, 15, 40)),
    "riser":  Instrument(envelope=ramp(15, 2, 64)),
}
NUMBERS = {name: i for i, name in enumerate(INSTRUMENTS)}


def p(text: str):
    return pattern(text, NUMBERS, TICKS_PER_STEP)


def bars(*texts: str) -> str:
    return " ".join(texts)


# ---- Lead -----------------------------------------------------------------------

LEAD = {
    "lead_intro": bars(
        "-.16",
        "-.16",
        "@lead D4.2 E4.2 F#4.2 G4.2 A4.2 B4.2 C5.2 D5.2",
        "E5.2 F#5.2 G5.2 A5.2 @scoop D6.6 -.2"),
    "lead_a": bars(
        "@lead D5.2 D5.2 -.2 F#5.2 A5.3 F#5.1 E5.2 D5.2",          # D: the call
        "C5.2 E5.2 @scoop G5.4 -.2 @lead E5.2 G5.2 C6.2",          # C
        "B5.3 A5.1 G5.2 E5.2 D5.2 B4.2 -.2 D5.2",                  # G
        "F5.1 F#5.3 E5.2 @scoop D5.6 -.4",                         # D: b3 into 3
        "@lead -.4 A4.2 A4.2 B4.2 A4.2 F#4.2 D4.2",                # D: the response
        "-.4 G4.2 G4.2 A4.2 G4.2 E4.2 C4.2",                       # C
        "D5.2 -.2 D5.2 -.2 B4.2 C5.2 D5.2 G5.2",                   # G
        "A5.4 F#5.2 A5.2 @scoop D6.6 -.2"),                        # D
    "lead_b": bars(
        "@lead D5.2 F5.2 D5.2 F5.2 Bb5.4 A5.2 F5.2",               # Bb
        "E5.2 G5.2 E5.2 G5.2 C6.4 B5.2 G5.2",                      # C
        "F#5.3 E5.1 D5.2 E5.2 F#5.2 A5.2 F#5.2 E5.2",              # D
        "@scoop D5.8 -.4 @lead D5.1 E5.1 F#5.1 G5.1",              # D
        "D5.2 F5.2 Bb5.2 F5.2 D6.4 C6.2 Bb5.2",                    # Bb
        "C6.2 G5.2 E5.2 G5.2 C6.4 D6.2 E6.2",                      # C
        "F#5.2 A#5.2 C#6.2 A#5.2 F#6.4 E6.2 C#6.2",                # F#: V/vi
        "E6.4 C#6.2 A5.2 E5.2 G5.2 A5.2 C#6.2"),                   # A: V
    "lead_break": bars(
        "@open D6.2 -.14",                                         # the stop
        "@solo D5.4 C5.4 G4.4 D5.4",
        "Bb4.4 C5.4 D5.8",
        "@lead A4.1 B4.1 C#5.1 D5.1 E5.1 F#5.1 G5.1 A5.1 B5.1 C#6.1 D6.1 E6.1 F#6.1 G6.1 A6.2"),
    "lead_chorus": bars(
        "@shout A5.2 A5.2 B5.2 A5.2 -.2 F#5.2 A5.2 D6.2",          # D
        "C6.4 B5.2 G5.2 -.2 E5.2 G5.2 C6.2",                       # C
        "B5.2 B5.2 C6.2 B5.2 -.2 G5.2 B5.2 D6.2",                  # G
        "D6.4 C6.2 A5.2 F5.1 F#5.3 D5.4",                          # D
        "A5.2 A5.2 B5.2 A5.2 -.2 F#5.2 A5.2 D6.2",                 # D
        "C6.4 B5.2 G5.2 -.2 E5.2 G5.2 C6.2",                       # C
        "Bb5.2 Bb5.2 C6.2 D6.2 -.2 F6.2 D6.2 Bb5.2",               # Bb
        "@scoop C#6.4 A#5.4 F#5.4 -.4"),                           # F#
}

# ---- Guitar ----------------------------------------------------------------------

def chugs(root: str, accent: bool = True) -> str:
    """A bar of 8th-note power-chord chugs, the first open."""
    return (f"@open {root}.2 @chug " if accent else f"@chug {root}.2 ") + " ".join([f"{root}.2"] * 7)


def offbeats(root: str) -> str:
    """A bar of offbeat stabs (ska-style)."""
    return "@stab " + " ".join([f"-.2 {root}.2"] * 4)


GUITAR = {
    "guitar_intro": bars("-.16", "-.16", chugs("D4"), "@open D4.8 C4.8"),
    "guitar_a": bars(*(chugs(r) for r in ["D4", "C4", "G4", "D4", "D4", "C4", "G4", "D4"])),
    "guitar_b": bars(*(offbeats(r) for r in ["Bb4", "C5", "D5", "D5", "Bb4", "C5", "F#4", "A4"])),
    "guitar_break": bars("@open D4.2 -.14", "-.16", "-.16", "@stab A4.4 A4.4 A4.4 A4.4"),
    "guitar_chorus": bars(*(chugs(r) for r in ["D4", "C4", "G4", "D4", "D4", "C4", "Bb4", "F#4"])),
}

# ---- Bass ------------------------------------------------------------------------

def bass_bar(root: str, octave_up: str) -> str:
    """Roots in 8ths, popping up an octave on the offbeats of beats 2 and 4."""
    return f"@bass {root}.2 {root}.2 {root}.2 {octave_up}.2 {root}.2 {root}.2 {root}.2 {octave_up}.2"


ROOTS = {"D": ("D3", "D4"), "C": ("C3", "C4"), "G": ("G3", "G4"), "Bb": ("Bb3", "Bb4"),
         "F#": ("F#3", "F#4"), "A": ("A3", "A4")}


def bass(*chords: str) -> str:
    return bars(*(bass_bar(*ROOTS[c]) for c in chords))


BASS = {
    "bass_intro": bars("-.16", "-.16", bass("D"), "@boom D3.8 C3.8"),
    "bass_a": bass("D", "C", "G", "D", "D", "C", "G", "D"),
    "bass_b": bass("Bb", "C", "D", "D", "Bb", "C", "F#", "A"),
    "bass_break": bars("@boom D3.2 -.14", "-.16", "-.16", "@bass A3.4 A3.4 A3.4 A3.4"),
    "bass_chorus": bass("D", "C", "G", "D", "D", "C", "Bb", "F#"),
}

# ---- Drums -----------------------------------------------------------------------

K, S, H = f"@kick {KICK_NOISE}.2", f"@snare {SNARE_NOISE}.2", f"@hat {HAT_NOISE}.2"
TWO_BEAT = " ".join([K, H, S, H, K, K, S, H])             # a punk two-beat
DOUBLE = " ".join([K, H, S, H, K, H, S, S])               # driving, with a pickup
CRASH_BAR = " ".join([f"@crash {SNARE_NOISE}.2", H, S, H, K, K, S, H])

DRUMS = {
    "drums_intro": bars(
        " ".join([f"@snare {SNARE_NOISE}.4"] * 4),
        " ".join([f"@snare {SNARE_NOISE}.2"] * 8),
        TWO_BEAT,
        " ".join([f"@snare {SNARE_NOISE}.1"] * 16)),
    "drums_a": bars(CRASH_BAR, TWO_BEAT, TWO_BEAT, TWO_BEAT, CRASH_BAR, TWO_BEAT, TWO_BEAT,
                    " ".join([K, H, S, H] + [f"@snare {SNARE_NOISE}.1"] * 8)),
    "drums_b": bars(*([DOUBLE] * 7), " ".join([f"@snare {SNARE_NOISE}.1"] * 16)),
    "drums_break": bars(
        f"@crash {SNARE_NOISE}.16",
        " ".join([K, H, H, H, K, H, H, H]),
        " ".join([K, H, H, H, K, H, S, S]),
        f"@riser {SNARE_NOISE}.16"),
    "drums_chorus": bars(CRASH_BAR, DOUBLE, DOUBLE, DOUBLE, CRASH_BAR, DOUBLE, DOUBLE,
                         " ".join([f"@snare {SNARE_NOISE}.1"] * 16)),
}

# ---- The song --------------------------------------------------------------------

SECTIONS = ["intro", "a", "b", "break", "chorus"]


def song() -> Song:
    texts = {**LEAD, **GUITAR, **BASS, **DRUMS}
    patterns = {name: p(text) for name, text in texts.items()}
    for name, pat in patterns.items():
        assert pat.ticks % (STEPS_PER_BAR * TICKS_PER_STEP) == 0, f"{name} is not whole bars"
    order = [(f"lead_{s}", f"guitar_{s}", f"bass_{s}", f"drums_{s}") for s in SECTIONS]
    return Song(list(INSTRUMENTS.values()), patterns, order)


def loop_ticks() -> int:
    s = song()
    return sum(s.section_ticks(section) for section in s.order)


def main() -> None:
    """Render one loop of the theme to build/music/splash_theme.wav."""
    from dontdither.build import BUILD_DIRPATH
    from dontdither.music import Player, compile_song
    from dontdither.sn76489 import render, write_wav

    s = song()
    compiled = compile_song(s, base=0x2000)
    player = Player(compiled, s.instruments)
    ticks = [player.tick() for _ in range(loop_ticks())]
    wav_filepath = BUILD_DIRPATH / "music" / "splash_theme.wav"
    write_wav(wav_filepath, render(ticks))
    seconds = len(ticks) / 50
    print(f"{wav_filepath}: {seconds:.1f} s, song data {len(compiled.data)} bytes")


if __name__ == "__main__":
    main()
