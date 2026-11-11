"""Joysticks through SPItFIRE: detection, the channel map, and how a stick's
readings become the game's input byte.

SPItFIRE (a Master Compact peripheral; see the SPItFIRE repository's
docs/joystick-programming.md) provides up to four analogue joysticks
through its ROM's documented interface:

- **Detection:** OSWORD &3F with reason code 0 in byte 0 of the block.
  With the ROM present, byte 0 comes back &53 ("S"), byte 4 is the number
  of joysticks allocated (0-4) and byte 10 holds flags (non-zero: not
  ready, no joysticks). Without it, nothing claims the call and byte 0 is
  unchanged.
- **Reading:** OSBYTE &80 (ADVAL) with X = a channel returns a 16-bit value
  in X (low) and Y (high). Joystick j's X and Y are channels 1, 3, 17, 19
  and 2, 4, 18, 20 for j = 1-4; fire buttons are bits 0 and 1 of the low
  byte of channel 0 (joysticks 1, 2) and channel 16 (3, 4).
- **Directions** follow the Acorn convention: X high is left, Y high is up.

Joystick j plays player slot j (C, M, Y, K). A player chooses it by joining
with the joystick's fire button.

A stick counts as pointing in a direction when it is more than a quarter of
full scale from the centre on that axis (the threshold SPItFIRE itself uses
for its direction bits): only the high byte of each reading is needed.
Both axes past the threshold give a diagonal. The resulting four-bit mask
(up, down, left, right) is turned into a direction exactly as the keys'
are (game.direction_of_keys).
"""

from __future__ import annotations

SPITFIRE_SIGNATURE = 0x53          # OSWORD &3F byte 0 when SPItFIRE answers
JOYSTICKS = 4

X_CHANNELS = (1, 3, 17, 19)
Y_CHANNELS = (2, 4, 18, 20)
FIRE_CHANNELS = (0, 0, 16, 16)
FIRE_MASKS = (1, 2, 1, 2)

# Thresholds on a reading's high byte: a quarter of full scale either side
# of the centre (&8000).
HIGH_THRESHOLD = 0xC0              # high byte >= this: left (X) or up (Y)
LOW_THRESHOLD = 0x40               # high byte < this: right (X) or down (Y)

UP, DOWN, LEFT, RIGHT = 1, 2, 4, 8  # the key mask's bits (controls.LAYOUT_KEYS)


def joystick_mask(x: int, y: int) -> int:
    """The direction mask (up, down, left, right) for 16-bit readings."""
    mask = 0
    if y >> 8 >= HIGH_THRESHOLD:
        mask |= UP
    elif y >> 8 < LOW_THRESHOLD:
        mask |= DOWN
    if x >> 8 >= HIGH_THRESHOLD:
        mask |= LEFT
    elif x >> 8 < LOW_THRESHOLD:
        mask |= RIGHT
    return mask


def input_of_joystick(x: int, y: int, fire: bool) -> int:
    """The game's input byte for a joystick's readings."""
    from dontdither.game import FIRE_BIT, direction_of_keys

    return direction_of_keys(joystick_mask(x, y)) | (FIRE_BIT if fire else 0)


def joysticks_available(block: bytes) -> int:
    """How many joysticks the game can use, from the OSWORD &3F block as it
    came back: 0 unless SPItFIRE answered, is ready, and allocated some."""
    if block[0] != SPITFIRE_SIGNATURE or block[10] != 0:
        return 0
    return min(block[4], JOYSTICKS)
