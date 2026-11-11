"""Joysticks through SPItFIRE: detection, the channel map, and how a
joystick's switch byte becomes the game's input byte.

SPItFIRE (a Master Compact peripheral; see the SPItFIRE repository's
docs/joystick-programming.md) provides up to four joysticks through its
ROM's documented interface:

- **Detection:** OSWORD &3F, its reason code in byte 0 of the block.
  SPItFIRE answers by setting byte 0 to &53 ("S"); without it (or for a
  reason it does not know) nothing claims the call and byte 0 is
  unchanged. Reason 0 identifies it, with status flags (non-zero: not
  ready); reason 1 lists its joysticks, each with its port and port type;
  reason 2 describes joystick j (its kind -- 1 is a stick -- and
  capabilities); reason 3 names a port type. The game plays with the
  joysticks that are sticks with directions (stick_slots), and the title
  screen names the port types as SPItFIRE does, so the game carries no
  table of SPItFIRE's types.
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

The title screen says what it found (spitfire_line): nothing at all
without SPItFIRE; with it, why it is not ready, or each port's hardware
and the joysticks it gives, e.g. "SPItFIRE: A 3BT J1 J2, B 3BT J3 J4". It
marks each player's key line "J1"-"J4" for the joystick the player may
use instead.
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


# OSWORD &3F (the guide's "Detecting SPItFIRE"). Byte 0 is the reason
# code on entry and SPITFIRE_SIGNATURE on exit if SPItFIRE answered; a
# reason it does not know is not claimed, so byte 0 comes back unchanged.
BLOCK_BYTES = 16                   # the guide says to allow 16
REASON_IDENTIFY = 0                # whether it is there and ready
REASON_SUMMARY = 1                 # the joysticks: count, ports and types
REASON_DESCRIBE = 2                # joystick j: kind, capabilities, buttons
REASON_NAME = 3                    # a port type's name, into our buffer

IDENTIFY_FLAGS = 5                 # reason 0: status flags
SUMMARY_COUNT = 1                  # reason 1: n, the joysticks (1 to n)
SUMMARY_JOYSTICKS = 4              # reason 1: 4-7, joysticks 1-4: bit 7 port,
                                   # bit 6 handset, bits 0-5 type; &FF none
DESCRIBE_JOYSTICK = 1              # reason 2: j on entry
DESCRIBE_KIND = 3                  # reason 2: kind
DESCRIBE_CAPABILITIES = 4          # reason 2: capabilities
NAME_TYPE = 1                      # reason 3: the type number
NAME_WHICH = 2                     # reason 3: 0 = keyword, 1 = full name
NAME_BUFFER = 3                    # reason 3: 3-4, the buffer's address
NAME_SIZE = 5                      # reason 3: the buffer's size
NAME_COPIED = 6                    # reason 3: characters copied (no CR)
NAME_FLAGS = 7                     # reason 3: bit 0, no such type or name

NOT_ALLOCATED = 0xFF               # a summary joystick byte: not there
PORT_BIT = 0x80                    # a summary joystick byte: port B
TYPE_MASK = 0x3F                   # a summary joystick byte: the type
KIND_STICK = 1                     # reason 2: a self-centring joystick
CAPABILITY_DIRECTIONS = 2          # reason 2: its switch byte has directions
NAME_KEYWORD = 0
NAME_SIZE_USED = 8                 # our buffer: a keyword ("BITSTIK") and CR

# Status flags (reasons 0 and 1), in order of precedence, with what the
# title screen tells the user (the guide's advice).
FLAG_MESSAGES = (
    (0x01, "press Ctrl-Break to start"),         # no workspace
    (0x02, "hardware not responding"),           # the hardware did not answer
    (0x04, "type *SPITFIRE JOYSTICK ON"),        # joystick handling off
    (0x08, "stopped: type *FX16,4"),             # updates stopped by *FX16,0
)

PORT_NAMES = ("A", "B")

# What the title screen says.
SPITFIRE_LINE_LENGTH = 36          # characters, from column 4 to the last
SPITFIRE_TEXT = "SPItFIRE: "
NO_JOYSTICKS_TEXT = "no joysticks"
UNKNOWN_TYPE_TEXT = "?"            # a type SPItFIRE has no name for


def answered(block: bytes) -> bool:
    """Did SPItFIRE answer this call (rather than nothing claiming it)?"""
    return block[0] == SPITFIRE_SIGNATURE


def stick_slots(identify: bytes, summary: bytes, describe) -> int:
    """The player slots that can play on a joystick, as a bit mask (bit j-1
    for joystick j): SPItFIRE answered and is ready (no status flags), and
    joystick j is one of its n and, described, a stick (kind 1) whose
    switch byte carries directions. describe(j) is reason 2's block for
    joystick j."""
    if not answered(identify) or identify[IDENTIFY_FLAGS] != 0 or not answered(summary):
        return 0
    mask = 0
    for j in range(1, min(summary[SUMMARY_COUNT], JOYSTICKS) + 1):
        block = describe(j)
        if (answered(block) and block[DESCRIBE_KIND] == KIND_STICK
                and block[DESCRIBE_CAPABILITIES] & CAPABILITY_DIRECTIONS):
            mask |= 1 << (j - 1)
    return mask


def spitfire_line(identify: bytes, summary: bytes, keyword) -> str:
    """What the title screen says SPItFIRE gave: nothing if it is not there;
    if it is, why it is not ready, or its joysticks grouped by port with
    the port's type, named by SPItFIRE (e.g. "SPItFIRE: A 3BT J1 J2, B
    SINGLE J3"); cut at SPITFIRE_LINE_LENGTH characters. keyword(type) is
    the keyword reason 3 gives (cut to NAME_SIZE_USED - 1 characters), or
    None if SPItFIRE has none."""
    if not answered(identify):
        return ""                  # nothing: no mention of SPItFIRE at all
    flags = identify[IDENTIFY_FLAGS]
    for flag, message in FLAG_MESSAGES:
        if flags & flag:
            return SPITFIRE_TEXT + message
    groups: list[str] = []
    port = None
    count = min(summary[SUMMARY_COUNT], JOYSTICKS) if answered(summary) else 0
    for j in range(count):
        joystick = summary[SUMMARY_JOYSTICKS + j]
        if joystick == NOT_ALLOCATED:
            continue
        if joystick & PORT_BIT != port:
            port = joystick & PORT_BIT
            name = keyword(joystick & TYPE_MASK)
            name = UNKNOWN_TYPE_TEXT if not name else name[:NAME_SIZE_USED - 1]
            groups.append(f"{PORT_NAMES[port >> 7]} {name}")
        groups[-1] += f" J{j + 1}"
    return (SPITFIRE_TEXT + (", ".join(groups) or NO_JOYSTICKS_TEXT))[:SPITFIRE_LINE_LENGTH]


def joystick_marker(slot: int) -> str:
    """The mark beside player slot's keys on the title screen when it may
    use a joystick: the joystick's number."""
    return f"J{slot + 1}"
