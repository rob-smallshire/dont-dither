"""A SPItFIRE configuration for tests: what its OSWORD &3F reasons 0-3
answer, for the model (tools/dontdither/joysticks.py) and for the fake
SPItFIRE (tests/fake_spitfire.asm) alike.

The port type keywords are SPItFIRE's (its guide, "Ports and port types");
the game never holds them -- it asks SPItFIRE -- so only the tests and the
fake do.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dontdither.joysticks import (
    BLOCK_BYTES,
    DESCRIBE_CAPABILITIES,
    DESCRIBE_KIND,
    IDENTIFY_FLAGS,
    KIND_STICK,
    NOT_ALLOCATED,
    PORT_BIT,
    SPITFIRE_SIGNATURE,
    SUMMARY_COUNT,
    SUMMARY_JOYSTICKS,
)

PORT_TYPE_KEYWORDS = ("NONE", "SINGLE", "DUAL", "3BS", "3BT", "14B", "BITSTIK", "QUINKEY")
NONE, SINGLE, DUAL, SINGLE_3B, TWIN, KEYPAD_14B, BITSTIK, QUINKEY = range(8)
NAME_BYTES = 8                     # each keyword in the fake's table, with its CR

XY_READINGS, DIRECTIONS, KEYPAD = 1, 2, 4      # reason 2 capabilities
KIND_POSITION = 2


@dataclass
class Joystick:
    port: int                      # 0 = A, 1 = B
    handset: int                   # 0 = the port's first joystick, 1 = its second
    type: int
    kind: int = KIND_STICK
    capabilities: int = XY_READINGS | DIRECTIONS
    buttons: int = 1

    def summary_byte(self) -> int:
        return (PORT_BIT if self.port else 0) | (self.handset << 6) | self.type


@dataclass
class SpitfireConfig:
    present: bool = True
    flags: int = 0
    port_types: tuple[int, int] = (TWIN, TWIN)
    joysticks: list[Joystick] = field(default_factory=lambda: twins(4))

    def identify(self) -> bytes:
        """Reason 0's answer (the block as it comes back)."""
        block = bytearray(BLOCK_BYTES)
        if self.present:
            block[0:IDENTIFY_FLAGS + 1] = bytes([SPITFIRE_SIGNATURE, 1, 0x00, 0x03, 0x01, self.flags])
        return bytes(block)

    def summary(self) -> bytes:
        """Reason 1's answer."""
        block = bytearray([1] + [0] * (BLOCK_BYTES - 1))
        if self.present:
            joysticks = [] if self.flags & 3 else self.joysticks      # none if not ready
            block[0] = SPITFIRE_SIGNATURE
            block[SUMMARY_COUNT] = len(joysticks)
            block[2:4] = bytes(self.port_types)
            for j in range(4):
                block[SUMMARY_JOYSTICKS + j] = joysticks[j].summary_byte() if j < len(joysticks) else NOT_ALLOCATED
            block[8] = self.flags
        return bytes(block)

    def describe(self, j: int) -> bytes:
        """Reason 2's answer for joystick j (1-4)."""
        block = bytearray([2, j] + [0] * (BLOCK_BYTES - 2))
        if self.present:
            block[0] = SPITFIRE_SIGNATURE
            joysticks = [] if self.flags & 3 else self.joysticks
            if 1 <= j <= len(joysticks):
                stick = joysticks[j - 1]
                block[2:6] = bytes([stick.summary_byte(), stick.kind, stick.capabilities, stick.buttons])
            else:
                block[2] = NOT_ALLOCATED
        return bytes(block)

    @staticmethod
    def keyword(type_number: int) -> str | None:
        """Reason 3's keyword for a port type, or None."""
        return PORT_TYPE_KEYWORDS[type_number] if type_number < len(PORT_TYPE_KEYWORDS) else None

    def ram(self) -> bytes:
        """The fake's configuration (cfg_present to cfg_describe)."""
        identify, summary = self.identify(), self.summary()
        describe = b"".join(self.describe(j)[2:6] for j in range(1, 5))
        return bytes([1 if self.present else 0]) + identify[1:6] + summary[1:9] + describe


def twins(count: int) -> list[Joystick]:
    """count joysticks from two Delta 3B Twins, port A's then port B's."""
    return [Joystick(port=j // 2, handset=j % 2, type=TWIN) for j in range(count)]


def names_source() -> str:
    """fake_names for the fake ROM: the keywords, NAME_BYTES each."""
    lines = [f"FAKE_TYPES = {len(PORT_TYPE_KEYWORDS)}", ".fake_names"]
    for keyword in PORT_TYPE_KEYWORDS:
        padded = keyword.encode() + b"\r" + bytes(NAME_BYTES - len(keyword) - 1)
        lines.append("    EQUB " + ", ".join(f"&{b:02X}" for b in padded) + f"    \\ {keyword}")
    return "\n".join(lines) + "\n"
