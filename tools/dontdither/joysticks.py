"""Joysticks through SPItFIRE: detection, the channel map, and how a
joystick's switch byte becomes the game's input byte.

SPItFIRE (a Master Compact peripheral; see the SPItFIRE repository's
docs/joystick-programming.md) provides up to four joysticks through its
ROM's documented interface:

- **Detection:** OSWORD &3F with reason code 0 in byte 0 of the block.
  With the ROM present, byte 0 comes back &53 ("S"), byte 4 is the number
  of joysticks allocated (0-4) and byte 10 holds flags (non-zero: not
  ready, no joysticks). Without it, nothing claims the call and byte 0 is
  unchanged.
- **Reading:** every joystick has a *switch byte*, built by SPItFIRE's
  firmware: fire in bit 0, and left, down, up and right in bits 4-7 (a
  direction set when the stick is more than a quarter of full scale from
  the centre, the firmware's threshold; two adjacent ones are a
  diagonal). OSBYTE &80 (ADVAL) on channel 12 returns joysticks 1 and 2's
  in X (low byte) and Y (high byte), and on channel 28 joysticks 3 and 4's.
  An unallocated joystick's switch byte is 0. So two calls read four
  joysticks, and the game needs neither the sticks' analogue readings nor
  a threshold of its own.

Joystick j plays player slot j (C, M, Y, K). A player chooses it by joining
with the joystick's fire button.

A switch byte's four direction bits are turned into a direction through
a 16-entry table (switch_direction) made from the keys' own
(game.direction_of_keys), so a joystick steers exactly as a player's keys
would.

The title screen says what it found (spitfire_line): whether SPItFIRE is
there, and if so each port's hardware and the joysticks it gives, e.g.
"SPItFIRE: A 3BT J1 J2, B 3BT J3 J4". It marks each player's key line
"J1"-"J4" for the joystick the player may use instead.
"""

from __future__ import annotations

SPITFIRE_SIGNATURE = 0x53          # OSWORD &3F byte 0 when SPItFIRE answers
JOYSTICKS = 4

# ADVAL channels holding the switch bytes: channel 12 has joysticks 1 and
# 2 (low byte, high byte), channel 28 joysticks 3 and 4.
SWITCH_CHANNELS = (12, 28)

# A switch byte's bits.
SWITCH_FIRE = 0x01
SWITCH_LEFT, SWITCH_DOWN, SWITCH_UP, SWITCH_RIGHT = 0x10, 0x20, 0x40, 0x80
SWITCH_DIRECTION_SHIFT = 4         # the direction bits are bits 4-7


def switch_channel(slot: int) -> tuple[int, int]:
    """Joystick slot (0-3)'s switch byte: (its ADVAL channel, 0 for the low
    byte or 1 for the high)."""
    return SWITCH_CHANNELS[slot // 2], slot % 2


def switch_mask(switches: int) -> int:
    """The keys' direction mask (controls.LAYOUT_KEYS: up 1, down 2, left 4,
    right 8) for a switch byte."""
    mask = 0
    for bit, key in ((SWITCH_UP, 1), (SWITCH_DOWN, 2), (SWITCH_LEFT, 4), (SWITCH_RIGHT, 8)):
        if switches & bit:
            mask |= key
    return mask


def switch_direction() -> list[int]:
    """The direction for each value (0-15) of a switch byte's direction bits
    (shifted down to bits 0-3), as the keys would give it."""
    from dontdither.game import direction_of_keys

    return [direction_of_keys(switch_mask(nibble << SWITCH_DIRECTION_SHIFT)) for nibble in range(16)]


def input_of_switch_byte(switches: int) -> int:
    """The game's input byte for a joystick's switch byte."""
    from dontdither.game import FIRE_BIT, direction_of_keys

    return direction_of_keys(switch_mask(switches)) | (FIRE_BIT if switches & SWITCH_FIRE else 0)


# The OSWORD &3F block's bytes.
BLOCK_BYTES = 16                   # 11 used; the guide says to allow 16
COUNT_BYTE = 4                     # joysticks allocated (0-4)
JOYSTICK_BYTES = 6                 # 6-9: joysticks 1-4: bit 7 port, bits 0-2 type
FLAGS_BYTE = 10
NOT_ALLOCATED = 0xFF               # a joystick byte for a joystick not there
FLAG_NO_WORKSPACE = 1              # the user must press Ctrl-Break
FLAG_NOT_ANSWERING = 2             # the hardware did not answer

# The port types, by number, as SPItFIRE's *SPITFIRE JOYSTICK PORT names them.
PORT_TYPE_NAMES = ("NONE", "SINGLE", "DUAL", "3BS", "3BT", "14B", "BITSTIK", "QUINKEY")
PORT_NAMES = ("A", "B")

# What the title screen says.
SPITFIRE_LINE_LENGTH = 36          # characters, from column 4 to the last
NO_SPITFIRE_TEXT = "No SPItFIRE: keyboard only"
SPITFIRE_TEXT = "SPItFIRE: "
CTRL_BREAK_TEXT = "press Ctrl-Break to start"
NOT_ANSWERING_TEXT = "hardware not responding"
NO_JOYSTICKS_TEXT = "no joysticks"


def joysticks_available(block: bytes) -> int:
    """How many joysticks the game can use, from the OSWORD &3F block as it
    came back: 0 unless SPItFIRE answered, is ready, and allocated some."""
    if block[0] != SPITFIRE_SIGNATURE or block[FLAGS_BYTE] != 0:
        return 0
    return min(block[COUNT_BYTE], JOYSTICKS)


def spitfire_line(block: bytes) -> str:
    """What the title screen says SPItFIRE gave, from the OSWORD &3F block:
    whether it is there and ready, and if so its joysticks, grouped by port
    with the port's type (e.g. "SPItFIRE: A 3BT J1 J2, B SINGLE J3"); cut at
    SPITFIRE_LINE_LENGTH characters."""
    if block[0] != SPITFIRE_SIGNATURE:
        return NO_SPITFIRE_TEXT
    flags = block[FLAGS_BYTE]
    if flags & FLAG_NO_WORKSPACE:
        return SPITFIRE_TEXT + CTRL_BREAK_TEXT
    if flags & FLAG_NOT_ANSWERING:
        return SPITFIRE_TEXT + NOT_ANSWERING_TEXT
    groups: list[str] = []
    port = None
    for j in range(JOYSTICKS):
        joystick = block[JOYSTICK_BYTES + j]
        if joystick == NOT_ALLOCATED:
            continue
        if joystick >> 7 != port:
            port = joystick >> 7
            groups.append(f"{PORT_NAMES[port]} {PORT_TYPE_NAMES[joystick & 7]}")
        groups[-1] += f" J{j + 1}"
    return (SPITFIRE_TEXT + (", ".join(groups) or NO_JOYSTICKS_TEXT))[:SPITFIRE_LINE_LENGTH]


def joystick_marker(slot: int) -> str:
    """The mark beside player slot's keys on the title screen when it may
    use a joystick: the joystick's number."""
    return f"J{slot + 1}"
