"""Music for the SN76489: the song format, its compiler, and a model of the
6502 player (asm/music.asm) that says exactly which sound chip writes it
makes on every tick.

The player runs at 50 Hz (the vertical sync) and drives the chip directly.
It has four channels: tone channels 0-2 and the noise channel 3. Each plays
its own byte stream:

    &00-&5F  note n (a semitone index into NOTE_PERIODS; on the noise
             channel, the noise control value 0-7), for the current duration
    &60      rest (silence) for the current duration
    &80-&BF  set the duration to (b AND &3F) + 1 ticks
    &C0-&DF  set the instrument to b AND &1F
    &F0 l h  call the pattern at address h*256+l (one level: patterns do not
             call patterns)
    &F1      return from a pattern
    &FF      end: go back to the stream's start (every stream lasts the same
             number of ticks, so the channels stay together)

An instrument has a volume envelope (an attenuation per tick, 0 loudest to
15 silent, the last marked with bit 7 and held), an arpeggio (semitone
offsets per tick, the last marked with bit 7, then back to its loop point:
(0, 7, 12) loops for a fast power chord; (-2, -1, 0) with its loop point at
the end scoops up into the note and holds it). Notes plus arpeggio offsets
must stay within NOTE_PERIODS (compile_song checks).

Every tick, for each channel in order 0-3, the player advances the stream
if the current note or rest has run out, then writes the channel's tone
period (tone channels) and attenuation. The noise channel's control
register is written only when a note starts, as writing it restarts the
noise generator.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CLOCK_HZ = 4_000_000               # the BBC Micro's SN76489 clock
TICK_HZ = 50                       # the player's rate: one tick per field
CHANNELS = 4                       # tone 0, 1, 2 and noise
NOISE = 3

LOWEST_MIDI = 47                   # B2: the lowest note a 10-bit period reaches
NOTE_COUNT = 0x60                  # B2 .. A#10, though the top is useless
SILENT = 15                        # attenuation: off

REST = 0x60
DURATION = 0x80
INSTRUMENT = 0xC0
CALL = 0xF0
RETURN = 0xF1
END = 0xFF
MAX_DURATION = 64
MAX_INSTRUMENTS = 32


# ---- Pitch -------------------------------------------------------------------------

def midi_frequency(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def tone_period(frequency: float) -> int:
    """The 10-bit period for a frequency: f = CLOCK / (32 * N)."""
    return max(1, min(1023, round(CLOCK_HZ / (32 * frequency))))


NOTE_PERIODS = [tone_period(midi_frequency(LOWEST_MIDI + n)) for n in range(NOTE_COUNT)]

NOTE_NAMES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note_index(name: str) -> int:
    """A note name such as "E4", "F#3" or "Bb5" as a semitone index into
    NOTE_PERIODS (0 = B2)."""
    letter, rest = name[0].upper(), name[1:]
    semitone = NOTE_NAMES[letter]
    while rest and rest[0] in "#b":
        semitone += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    midi = 12 * (int(rest) + 1) + semitone
    index = midi - LOWEST_MIDI
    if not 0 <= index < NOTE_COUNT:
        raise ValueError(f"note {name} is out of range")
    return index


# ---- Instruments ---------------------------------------------------------------

@dataclass(frozen=True)
class Instrument:
    envelope: tuple[int, ...]            # attenuation per tick; the last is held
    arpeggio: tuple[int, ...] = (0,)     # semitone offsets per tick...
    arpeggio_loop: int = 0               # ...looping back to this one

    def __post_init__(self):
        assert self.envelope and all(0 <= v <= SILENT for v in self.envelope)
        assert self.arpeggio and all(-64 <= v < 64 for v in self.arpeggio)
        assert 0 <= self.arpeggio_loop < len(self.arpeggio)


# ---- Patterns and songs ------------------------------------------------------------

@dataclass
class Pattern:
    """A channel's events: ("note", index, ticks), ("rest", ticks) or
    ("instrument", number). Build them with the helpers below."""
    events: list[tuple] = field(default_factory=list)

    @property
    def ticks(self) -> int:
        return sum(e[-1] for e in self.events if e[0] in ("note", "rest"))


@dataclass
class Song:
    instruments: list[Instrument]
    patterns: dict[str, Pattern]
    order: list[tuple[str | None, str | None, str | None, str | None]]   # per section

    def section_ticks(self, section) -> int:
        lengths = {self.patterns[name].ticks for name in section if name is not None}
        assert len(lengths) == 1, f"section {section} has patterns of different lengths"
        return lengths.pop()


def pattern(text: str, instruments: dict[str, int], ticks_per_step: int) -> Pattern:
    """A pattern from text: "@name" switches instrument; "D5.2" is a note
    (on the noise channel, a number 0-7: its noise control) for 2 steps;
    "-.4" rests for 4 steps. A step is ticks_per_step ticks."""
    events = []
    for token in text.split():
        if token.startswith("@"):
            events.append(("instrument", instruments[token[1:]]))
            continue
        name, steps = token.rsplit(".", 1)
        ticks = int(steps) * ticks_per_step
        if name == "-":
            events.append(("rest", ticks))
        elif name.isdigit():
            events.append(("note", int(name), ticks))
        else:
            events.append(("note", note_index(name), ticks))
    return Pattern(events)


# ---- Compiling -------------------------------------------------------------------

@dataclass
class CompiledSong:
    """The bytes of a song, laid out for the player at `base`: the streams'
    start addresses (one per channel), the instrument tables and the
    patterns."""
    base: int
    data: bytes
    stream_starts: list[int]
    labels: dict[str, int]


def pattern_bytes(pattern: Pattern) -> bytes:
    out = bytearray()
    duration = None
    for event in pattern.events:
        kind = event[0]
        if kind == "instrument":
            assert 0 <= event[1] < MAX_INSTRUMENTS
            out.append(INSTRUMENT | event[1])
            continue
        ticks = event[-1]
        if kind == "rest":
            while ticks:                   # long rests: several in a row
                step = min(ticks, MAX_DURATION)
                if step != duration:
                    out.append(DURATION | (step - 1))
                    duration = step
                out.append(REST)
                ticks -= step
            continue
        assert 1 <= ticks <= MAX_DURATION, f"a note of {ticks} ticks is too long"
        if ticks != duration:
            out.append(DURATION | (ticks - 1))
            duration = ticks
        out.append(event[1])
    out.append(RETURN)
    return bytes(out)


def check_ranges(song: Song) -> None:
    """Every tone note, with every offset of its instrument's arpeggio,
    must have a period (so the player need not clamp); noise notes must be
    noise control values."""
    for section in song.order:
        for channel, name in enumerate(section):
            if name is None:
                continue
            instrument = 0
            for event in song.patterns[name].events:
                if event[0] == "instrument":
                    instrument = event[1]
                elif event[0] == "note":
                    if channel == NOISE:
                        assert 0 <= event[1] <= 7, f"{name}: noise control {event[1]}"
                        continue
                    for offset in song.instruments[instrument].arpeggio:
                        assert 0 <= event[1] + offset < NOTE_COUNT, f"{name}: note out of range"


def compile_song(song: Song, base: int) -> CompiledSong:
    """Lay the song out from `base`: patterns first, then each channel's
    stream of calls. Patterns reset the duration, so each sets its own."""
    check_ranges(song)
    data = bytearray()
    labels: dict[str, int] = {}
    for name, pattern in song.patterns.items():
        labels[name] = base + len(data)
        data += pattern_bytes(pattern)
    silent_patterns: dict[int, str] = {}
    for section in song.order:
        ticks = song.section_ticks(section)
        if any(name is None for name in section) and ticks not in silent_patterns:
            name = f"__rest_{ticks}"
            labels[name] = base + len(data)
            data += pattern_bytes(Pattern([("rest", ticks)]))
            silent_patterns[ticks] = name
    starts = []
    for channel in range(CHANNELS):
        starts.append(base + len(data))
        for section in song.order:
            name = section[channel] or silent_patterns[song.section_ticks(section)]
            address = labels[name]
            data += bytes([CALL, address & 0xFF, address >> 8])
        data.append(END)
    return CompiledSong(base, bytes(data), starts, labels)


def instrument_tables(instruments: list[Instrument]) -> dict[str, list[int]]:
    """The instruments as byte lists for the player: envelopes and arpeggios
    with bit 7 marking their last value."""
    def marked(values):
        return [v & 0x7F for v in values[:-1]] + [(values[-1] & 0x7F) | 0x80]
    return {
        "envelopes": [marked(list(i.envelope)) for i in instruments],
        "arpeggios": [marked(list(i.arpeggio)) for i in instruments],
        "arpeggio_loops": [i.arpeggio_loop for i in instruments],
    }


# ---- The player model ----------------------------------------------------------

@dataclass
class ChannelState:
    pointer: int
    start: int
    return_to: int = 0
    wait: int = 1                  # ticks until the next event; 1: read at once
    duration: int = 1
    instrument: int = 0
    note: int | None = None        # None: resting
    envelope_step: int = 0
    arpeggio_step: int = 0


class Player:
    """The 6502 player's behaviour, tick by tick: tick() returns the chip
    writes (bytes, in order) the player makes on that tick."""

    def __init__(self, song: CompiledSong, instruments: list[Instrument]):
        self.memory = song.data
        self.base = song.base
        self.instruments = instruments
        self.channels = [ChannelState(pointer=s, start=s) for s in song.stream_starts]

    def _byte(self, address: int) -> int:
        return self.memory[address - self.base]

    def _advance(self, c: ChannelState, channel: int, writes: list[int]) -> None:
        while True:
            b = self._byte(c.pointer)
            c.pointer += 1
            if b == END:
                c.pointer = c.start
            elif b == CALL:
                target = self._byte(c.pointer) | self._byte(c.pointer + 1) << 8
                c.return_to = c.pointer + 2
                c.pointer = target
            elif b == RETURN:
                c.pointer = c.return_to
            elif b & 0xE0 == INSTRUMENT:
                c.instrument = b & 0x1F
            elif b & 0xC0 == DURATION:
                c.duration = (b & 0x3F) + 1
            elif b == REST:
                c.note = None
                c.wait = c.duration
                return
            else:
                c.note = b
                c.envelope_step = c.arpeggio_step = 0
                c.wait = c.duration
                if channel == NOISE:
                    writes.append(0xE0 | (b & 7))
                return

    def tick(self) -> list[int]:
        writes: list[int] = []
        for channel, c in enumerate(self.channels):
            c.wait -= 1
            if c.wait == 0:
                self._advance(c, channel, writes)
            if c.note is None:
                attenuation = SILENT
            else:
                instrument = self.instruments[c.instrument]
                attenuation = instrument.envelope[min(c.envelope_step, len(instrument.envelope) - 1)]
                c.envelope_step = min(c.envelope_step + 1, len(instrument.envelope) - 1)
                if channel != NOISE:
                    offset = instrument.arpeggio[c.arpeggio_step]
                    c.arpeggio_step += 1
                    if c.arpeggio_step == len(instrument.arpeggio):
                        c.arpeggio_step = instrument.arpeggio_loop
                    period = NOTE_PERIODS[c.note + offset]
                    writes += [0x80 | channel << 5 | period & 0x0F, period >> 4 & 0x3F]
            writes.append(0x90 | channel << 5 | attenuation)
        return writes


# ---- Assembly ----------------------------------------------------------------------

def _equb(values) -> str:
    return "    EQUB " + ", ".join(f"&{v & 0xFF:02X}" for v in values)


def song_assembly(song: Song, name: str) -> str:
    """The song as beebasm source for asm/music.asm: the note periods, the
    instrument tables, the patterns and the four channel streams, all
    labelled (so the song can go anywhere)."""
    check_ranges(song)
    tables = instrument_tables(song.instruments)
    lines = [
        "\\ " + "=" * 74,
        f"\\ {name}.asm -- GENERATED by tools/dontdither/music.py. Do not edit.",
        "\\ The song for asm/music.asm: its format is described there and in music.py.",
        "\\ " + "=" * 74,
        "",
        f"MUSIC_NOTE_COUNT = {NOTE_COUNT}",
        "\\ Tone periods by note (0 = B2), low bytes then high.",
        ".music_period_lo",
        *(_equb(NOTE_PERIODS[i:i + 16]) for i in range(0, NOTE_COUNT, 16)),
        ".music_period_hi",
        *(_equb([v >> 8 for v in NOTE_PERIODS[i:i + 16]]) for i in range(0, NOTE_COUNT, 16)),
        "",
        "\\ Instruments: envelope and arpeggio addresses, and arpeggio loop points.",
        ".music_envelope_lo",
        "    EQUB " + ", ".join(f"LO(music_envelope_{i})" for i in range(len(song.instruments))),
        ".music_envelope_hi",
        "    EQUB " + ", ".join(f"HI(music_envelope_{i})" for i in range(len(song.instruments))),
        ".music_arpeggio_lo",
        "    EQUB " + ", ".join(f"LO(music_arpeggio_{i})" for i in range(len(song.instruments))),
        ".music_arpeggio_hi",
        "    EQUB " + ", ".join(f"HI(music_arpeggio_{i})" for i in range(len(song.instruments))),
        ".music_arpeggio_loop",
        _equb(tables["arpeggio_loops"]),
    ]
    for i, (envelope, arpeggio) in enumerate(zip(tables["envelopes"], tables["arpeggios"])):
        lines += [f".music_envelope_{i}", _equb(envelope), f".music_arpeggio_{i}", _equb(arpeggio)]
    lines += ["", "\\ Patterns."]
    for pattern_name, pat in song.patterns.items():
        lines += [f".music_pattern_{pattern_name}"]
        data = pattern_bytes(pat)
        lines += [_equb(data[i:i + 16]) for i in range(0, len(data), 16)]
    rests = sorted({song.section_ticks(sec) for sec in song.order if None in sec})
    for ticks in rests:
        lines += [f".music_pattern___rest_{ticks}", _equb(pattern_bytes(Pattern([("rest", ticks)])))]
    lines += ["", "\\ The channels' streams: a call per section, then the end."]
    for channel in range(CHANNELS):
        lines.append(f".music_stream_{channel}")
        for section in song.order:
            target = section[channel] or f"__rest_{song.section_ticks(section)}"
            lines.append(f"    EQUB &{CALL:02X} : EQUW music_pattern_{target}")
        lines.append(f"    EQUB &{END:02X}")
    lines += [
        ".music_stream_lo",
        "    EQUB " + ", ".join(f"LO(music_stream_{c})" for c in range(CHANNELS)),
        ".music_stream_hi",
        "    EQUB " + ", ".join(f"HI(music_stream_{c})" for c in range(CHANNELS)),
    ]
    return "\n".join(lines) + "\n"
