"""Keyboard layouts for human players.

Keys are identified by their MOS internal key number (IK, Advanced User
Guide, key values table). The 6502 scans a key with OSBYTE &81 (negative
INKEY) using IK EOR &FF; Beebium's keyboard matrix position is
(IK >> 4, IK & 15).
"""

from __future__ import annotations

# Every key's internal key number (Advanced User Guide, appendix C).
INTERNAL_KEY = {
    "SHIFT": 0x00, "CTRL": 0x01,
    "Q": 0x10, "3": 0x11, "4": 0x12, "5": 0x13, "f4": 0x14, "8": 0x15, "f7": 0x16, "-": 0x17,
    "^": 0x18, "LEFT": 0x19,
    "f0": 0x20, "W": 0x21, "E": 0x22, "T": 0x23, "7": 0x24, "I": 0x25, "9": 0x26, "0": 0x27,
    "_": 0x28, "DOWN": 0x29,
    "1": 0x30, "2": 0x31, "D": 0x32, "R": 0x33, "6": 0x34, "U": 0x35, "O": 0x36, "P": 0x37,
    "[": 0x38, "UP": 0x39,
    "CAPS LOCK": 0x40, "A": 0x41, "X": 0x42, "F": 0x43, "Y": 0x44, "J": 0x45, "K": 0x46,
    "@": 0x47, ":": 0x48, "RETURN": 0x49,
    "SHIFT LOCK": 0x50, "S": 0x51, "C": 0x52, "G": 0x53, "H": 0x54, "N": 0x55, "L": 0x56,
    ";": 0x57, "]": 0x58, "DELETE": 0x59,
    "TAB": 0x60, "Z": 0x61, "SPACE": 0x62, "V": 0x63, "B": 0x64, "M": 0x65, ",": 0x66,
    ".": 0x67, "/": 0x68, "COPY": 0x69,
    "ESCAPE": 0x70, "f1": 0x71, "f2": 0x72, "f3": 0x73, "f5": 0x74, "f6": 0x75, "f8": 0x76,
    "f9": 0x77, "\\": 0x78, "RIGHT": 0x79,
}

# Order of the keys within a layout, and of the bits of the scanned key mask:
# up = bit 0, down = bit 1, left = bit 2, right = bit 3, fire = bit 4.
LAYOUT_KEYS = ("up", "down", "left", "right", "fire")

# The default keys of each player, by ink (player slot order C, M, Y, K).
# Each is an inverted T under the right hand or the left, plus a fire key,
# chosen to work on a real BBC Micro keyboard and on an emulator's host.
LAYOUTS = {
    "C": {"up": "W", "left": "A", "down": "S", "right": "D", "fire": "SHIFT"},
    "M": {"up": "I", "left": "J", "down": "K", "right": "L", "fire": "M"},
    "Y": {"up": "F", "left": "C", "down": "V", "right": "B", "fire": "SPACE"},
    "K": {"up": "UP", "left": "LEFT", "down": "DOWN", "right": "RIGHT", "fire": "\\"},
}


def inkey_code(key: str) -> int:
    """The negative-INKEY byte for OSBYTE &81."""
    return INTERNAL_KEY[key] ^ 0xFF


def matrix_position(key: str) -> tuple[int, int]:
    """The (row, column) of a key in Beebium's keyboard matrix."""
    ik = INTERNAL_KEY[key]
    return ik >> 4, ik & 0x0F
