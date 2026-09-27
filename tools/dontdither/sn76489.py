"""A model of the BBC Micro's SN76489 sound chip, for listening to music on
the host before it reaches the machine: bytes written to the chip in, audio
samples out.

The chip (on the BBC, the discrete TI part clocked at 4 MHz):
- Writes: a latch byte %1 cc t dddd selects channel cc (3 = noise) and its
  tone/noise (t = 0) or attenuation (t = 1) register, and sets its low 4
  bits; a data byte %0x DDDDDD sets the top 6 bits of the latched tone
  period. Writing the noise register restarts its shift register.
- Its counters tick at 250 kHz (4 MHz / 16). A tone channel's output flips
  every N ticks, so f = 125000 / N Hz (N = 0 acts as 1024).
- Noise: a 15-bit shift register, starting with only its top bit set,
  shifting right with the new bit 14 = bit 0 XOR bit 1 (white) or bit 0
  (periodic: a period of 15, so tone channel 2's pitch / 15 when clocked
  by it). It shifts at 250 kHz / 32, / 64 or / 128 (rates 0-2), or on each
  rising edge of tone channel 2 (rate 3). Its output is bit 0.
- Attenuation: 2 dB steps, 15 is off: amplitude 10^(-v/10).
- Outputs are unipolar -- each channel swings between 0 and its level --
  and they add. (A DC-blocking filter makes the result listenable.)

Sources: SMS Power's SN76489 notes, scarybeasts' write-ups on sampled sound
from the SN76489, and Stardot threads (see docs/music.md).
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

CHIP_HZ = 250_000                  # the counters' rate
LFSR_RESET = 0x4000
NOISE_SHIFT_TICKS = (32, 64, 128)  # counter ticks per shift for rates 0-2


def amplitude(attenuation: int) -> float:
    return 0.0 if attenuation >= 15 else 10 ** (-attenuation / 10)


class SN76489:
    def __init__(self):
        self.periods = [1024, 1024, 1024]
        self.attenuation = [15, 15, 15, 15]
        self.noise_control = 0
        self.latched = 0               # register number: channel * 2 + type
        self.lfsr = LFSR_RESET
        self.tone_countdown = [1024, 1024, 1024]   # ticks until the next flip
        self.tone_output = [0, 0, 0]
        self.noise_countdown = NOISE_SHIFT_TICKS[0]

    # ---- Writes --------------------------------------------------------------

    def write(self, byte: int) -> None:
        if byte & 0x80:
            self.latched = (byte >> 4) & 7
            channel, is_volume = self.latched >> 1, self.latched & 1
            if is_volume:
                self.attenuation[channel] = byte & 0x0F
            elif channel == 3:
                self.noise_control = byte & 7
                self.lfsr = LFSR_RESET
            else:
                self.periods[channel] = (self.periods[channel] & 0x3F0) | (byte & 0x0F)
        else:
            channel, is_volume = self.latched >> 1, self.latched & 1
            if is_volume:
                self.attenuation[channel] = byte & 0x0F
            elif channel == 3:
                self.noise_control = byte & 7
                self.lfsr = LFSR_RESET
            else:
                self.periods[channel] = (self.periods[channel] & 0x00F) | (byte & 0x3F) << 4

    # ---- Running ---------------------------------------------------------------

    def _period(self, channel: int) -> int:
        return self.periods[channel] or 1024

    def _tone(self, channel: int, ticks: int) -> tuple[np.ndarray, list[int]]:
        """The channel's output bit for the next `ticks` ticks, and the
        ticks at which it rises (for noise rate 3)."""
        period = self._period(channel)
        first = self.tone_countdown[channel]          # ticks until the first flip
        t = np.arange(ticks)
        flips = np.where(t >= first, (t - first) // period + 1, 0)
        out = (self.tone_output[channel] + flips) & 1
        flip_times = np.arange(first, ticks, period)
        rising = [int(x) for i, x in enumerate(flip_times)
                  if (self.tone_output[channel] + i + 1) & 1]
        total = len(flip_times)
        self.tone_output[channel] = (self.tone_output[channel] + total) & 1
        self.tone_countdown[channel] = (flip_times[-1] + period - ticks) if total else first - ticks
        return out.astype(np.float64), rising

    def _shift(self) -> None:
        white = self.noise_control & 4
        bit = (self.lfsr ^ (self.lfsr >> 1)) & 1 if white else self.lfsr & 1
        self.lfsr = (self.lfsr >> 1) | (bit << 14)

    def _noise(self, ticks: int, tone2_rising: list[int]) -> np.ndarray:
        rate = self.noise_control & 3
        if rate == 3:
            shifts = tone2_rising
        else:
            step = NOISE_SHIFT_TICKS[rate]
            shifts = list(range(self.noise_countdown, ticks, step))
            self.noise_countdown = (shifts[-1] + step - ticks) if shifts else self.noise_countdown - ticks
        out = np.empty(ticks)
        last = 0
        for s in shifts:
            out[last:s] = self.lfsr & 1
            self._shift()
            last = s
        out[last:] = self.lfsr & 1
        return out

    def run(self, ticks: int) -> np.ndarray:
        """The mixed output for `ticks` chip ticks (250 kHz), 0..4."""
        mix = np.zeros(ticks)
        tone2_rising: list[int] = []
        for channel in range(3):
            out, rising = self._tone(channel, ticks)
            mix += out * amplitude(self.attenuation[channel])
            if channel == 2:
                tone2_rising = rising
        mix += self._noise(ticks, tone2_rising) * amplitude(self.attenuation[3])
        return mix


# ---- Rendering ---------------------------------------------------------------

OUTPUT_HZ = 50_000                 # CHIP_HZ / 5


def render(ticks_of_writes: list[list[int]], tick_hz: int = 50) -> np.ndarray:
    """Audio at OUTPUT_HZ for a list of ticks, each a list of chip writes
    made at its start: averaged down from the chip's rate, DC removed,
    scaled to -1..1."""
    chip = SN76489()
    chip_ticks = CHIP_HZ // tick_hz
    pieces = []
    for writes in ticks_of_writes:
        for byte in writes:
            chip.write(byte)
        pieces.append(chip.run(chip_ticks))
    raw = np.concatenate(pieces) if pieces else np.zeros(0)
    audio = raw[: len(raw) // 5 * 5].reshape(-1, 5).mean(axis=1)
    # DC blocker: y[n] = x[n] - x[n-1] + r * y[n-1]
    out = np.empty_like(audio)
    r, prev_x, prev_y = 0.999, audio[0] if len(audio) else 0.0, 0.0
    for i, x in enumerate(audio):
        prev_y = x - prev_x + r * prev_y
        prev_x = x
        out[i] = prev_y
    peak = np.max(np.abs(out)) if len(out) else 0
    return out / peak * 0.9 if peak else out


def write_wav(filepath: Path, audio: np.ndarray, rate: int = OUTPUT_HZ) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(filepath), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((audio * 32767).astype("<i2").tobytes())
