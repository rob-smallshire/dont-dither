# Music

The title screen plays an original loop, about 41 seconds long, in the
spirit of Splatoon's battle music. It runs on the BBC Micro's SN76489 sound
chip, from a small player on the vertical-sync event, so the title screen
works as usual meanwhile. The game itself has no music: it has no memory for
it.

| Piece | Where |
|---|---|
| The song, as data | `tools/dontdither/splash_theme.py` |
| Song format, compiler, and a tick-by-tick model of the player | `tools/dontdither/music.py` |
| A model of the SN76489, for listening on the host | `tools/dontdither/sn76489.py` |
| The 6502 player | `asm/music.asm` |
| The song as assembly (generated) | `build/generated/splash_theme.asm` |
| The player on its own (`*RUN TUNE`) | `asm/tune.asm` |
| Tests | `tests/test_music.py` |

On the title screen, `SPLASH` draws everything with every colour black,
reveals it all at once with the CMYK palette, then starts the music. The
music stops before the disc is used. The tests also record `TUNE` from
Beebium's own SN76489 emulation (its audio stream: 48 kHz, the chip's
channels as separate sources) to `build/music/beebium_theme.wav`, to
compare with the model's rendering.

```bash
uv run dd-render-music      # -> build/music/splash_theme.wav, one loop
```

## The chip

These facts come from research: SMS Power's SN76489 notes, the MOS 1.20
disassembly, scarybeasts' write-ups and code, and Stardot threads. They
shape both the player and the model.

- **Writing.**
  - Put the byte on System VIA port A (`&FE4F`, no handshake), with port
    A set as all outputs (`&FE43` = `&FF`).
  - Pull the chip's write enable low: bit 0 of the addressable latch, via
    `&FE40` (`&00` low, `&08` high).
  - Hold it low for at least 8 µs, then release it.
  - The MOS keyboard scan uses port A too (it sets DDRA to `&7F`), so
    writes happen with interrupts off. The player writes from the vsync
    event, inside the MOS's interrupt handler. The MOS's OSBYTE entry
    also disables interrupts, so the title screen's key scans are never
    interrupted mid-scan.
- **Registers.**
  - A latch byte, `%1 cc t dddd`, selects channel `cc` (3 is noise) and
    either its tone or noise register (`t` = 0) or its attenuation
    (`t` = 1).
  - A data byte, `%0x DDDDDD`, sets the top 6 bits of a 10-bit tone
    period.
  - Tone frequency is f = 4 MHz / (32·N) = 125000/N Hz. A4 is N = 284, and
    the lowest note is N = 1023, about 122 Hz, just below B2.
  - Attenuation goes in 2 dB steps; 15 is silent.
- **Noise.**
  - The noise generator is a 15-bit shift register. White noise feeds back
    bit 0 XOR bit 1; periodic noise feeds back bit 0 alone, giving a
    period of 15.
  - It shifts at 4 MHz/512, /1024 or /2048, or at channel 2's pitch.
    Clocked by channel 2, periodic noise sounds at channel 2's pitch / 15:
    that's the tuned "periodic noise bass".
  - Writing the noise register restarts the noise, so the player writes it
    only when a drum note starts.
- **Outputs are unipolar.** Each channel swings between 0 and its level,
  and the channels add. The host model keeps this, then filters out the
  DC.

## The song format and player

The player ticks at 50 Hz, once per field. Each of the four channels
(tones 0–2 and noise) plays its own byte stream:

| Byte | Meaning |
|---|---|
| `&00–&5F` | a note: a semitone index from B2, or on the noise channel a noise control value 0–7 |
| `&60` | a rest |
| `&80–&BF` | set the duration: `(b AND &3F) + 1` ticks |
| `&C0–&DF` | set the instrument |
| `&F0 l h` | call a pattern (one level deep) |
| `&F1` | return from a pattern |
| `&FF` | back to the start of the stream |

**Instruments** have two parts:
- **An envelope:** an attenuation per tick, the last one held. Envelopes
  are what make square waves sound "played".
- **An arpeggio:** semitone offsets per tick, with a loop point. Examples:
  - `(0, 7, 12)` cycles at 50 Hz and sounds as a power chord on a single
    channel.
  - `(0, 4, 7)` gives major stabs.
  - `(-2, -1, 0)`, with its loop point at the end, scoops up into a note.

Drums are noise-channel notes with short envelopes:
- kick: periodic noise at the slowest rate;
- snare: white noise at the middle rate;
- hi-hat: white noise at the fastest rate, quiet and very short;
- crash and riser: long volume ramps.

**Each tick,** for each channel in turn:
1. Count the note down. When it runs out, read the stream to the next note
   or rest.
2. Write the tone period (the note, moved by the arpeggio).
3. Write the attenuation (from the envelope, or silent when resting).

**Starting and stopping:**
- `music_start` hooks EVENTV and enables the vsync event (`*FX14,4`).
- `music_stop` disables the event first, unhooks EVENTV, then silences
  all four channels.

**Testing:** `music.py`'s `Player` models this exactly. The tests run the
player alone (`TUNE`) and, on every tick of a whole loop and past its
wrap, compare the chip's registers with the model's. The comparison
ignores the setting of a silent channel, since it can't be heard.

## The composition

The Splatoon research drew on Hooktheory, Nintendo's band pages, Inkipedia
and published analyses. It found:
- **Tempo and key:** 172–190 BPM, in modal keys (Mixolydian ♭VII, Dorian).
- **Harmony:** loops such as I–♭VII–IV–I, with V/vi turnarounds and power
  chords.
- **The "squid" flavour:** a ♭3 against a major chord.
- **Drums:** punk two-beats, stops and breaks, rising runs.
- **Vocals:** short syllabic phrases in call and response, gang shouts.
- **Chip style:** the Chirpy Chips band makes chip-tune arpeggios part of
  the style.

The theme is original, at 187.5 BPM (a 16th note is 4 ticks), in D
Mixolydian. The chip can't go below B2, so D suits the bass.

| Section | Bars | Content |
|---|---|---|
| Intro | 4 | a drum fill, then a rising run |
| A | 8 | D–C–G–D; the lead calls and answers itself an octave down |
| B | 8 | double time, offbeat stabs; B♭–C–D–D, then B♭–C–F♯ (V/vi)–A |
| Break | 4 | a full-band stop, an arpeggio solo, a white-noise riser |
| Chorus | 8 | a gang shout (the lead doubled in octaves); D–C–G–D–D–C–B♭–F♯ |

**Channels:** 0 is the lead, 1 the guitar (chugs and stabs), 2 the bass
(roots in 8ths, popping up an octave), and 3 the drums. The song data is
about 1.4 KB.

## Sample playback: a possible next step

scarybeasts (Chris Evans) has written players that play samples through the
SN76489, in the style of MOD files. They play 3 voices at about 15.6 kHz,
or 4 at 12.5 kHz, and sound "like an Amiga". Sources: Stardot threads
[t=31654](https://stardot.org.uk/forums/viewtopic.php?t=31654) and
[t=33609](https://stardot.org.uk/forums/viewtopic.php?t=33609), and
[scarybeasts/misc/beebmod](https://github.com/scarybeasts/misc/tree/master/beebmod).

**How they work:**
- Each tone channel is set to period 1 (125 kHz, inaudible), and its
  volume register serves as a 4-bit DAC.
- The chip's write enable is held low, so each sample is a single store to
  port A.
- Everything runs from a loop timed to the cycle, with interrupts off.

**What that would mean here:**
- The loop takes the whole machine: no MOS while it plays. The title
  screen could only poll a few keys from inside the loop, so redefining
  keys (which uses the MOS) would have to stop the music.
- Samples take memory: `SPLASH` has a few KB spare.
- The emulator must model the chip's bus timing. b-em, beebjit and b2 do;
  Beebium would need checking (see its issues #82 and #89).

A cheaper middle way would be a short sampled "splat" or drum hit, played
while one channel of the tone music pauses.
