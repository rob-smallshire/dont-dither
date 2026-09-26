"""Keyboard layouts for human players.

Keys are identified by their MOS internal key number (IK, Advanced User
Guide, key values table). The 6502 scans a key with OSBYTE &81 (negative
INKEY) using IK EOR &FF; Beebium's keyboard matrix position is
(IK >> 4, IK & 15).
"""

from __future__ import annotations

INTERNAL_KEY = {
    "SHIFT": 0x00, "CTRL": 0x01, "Q": 0x10, "W": 0x21, "E": 0x22, "A": 0x41,
    "S": 0x51, "D": 0x32, "Z": 0x61, "X": 0x42, "RETURN": 0x49, "SPACE": 0x62,
    "COPY": 0x69, "UP": 0x39, "DOWN": 0x29, "LEFT": 0x19, "RIGHT": 0x79,
}

# Order of the keys within a layout, and of the bits of the scanned key mask:
# up = bit 0, down = bit 1, left = bit 2, right = bit 3, fire = bit 4.
LAYOUT_KEYS = ("up", "down", "left", "right", "fire")

LAYOUTS = {
    "A": {"up": "W", "down": "S", "left": "A", "right": "D", "fire": "SHIFT"},
    "B": {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT", "fire": "COPY"},
}


def inkey_code(key: str) -> int:
    """The negative-INKEY byte for OSBYTE &81."""
    return INTERNAL_KEY[key] ^ 0xFF


def matrix_position(key: str) -> tuple[int, int]:
    """The (row, column) of a key in Beebium's keyboard matrix."""
    ik = INTERNAL_KEY[key]
    return ik >> 4, ik & 0x0F
