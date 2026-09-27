\ ============================================================================
\ handoff.asm -- what SPLASH leaves resident for the game: the key layouts
\
\ SPLASH (the title screen) fills this block and the game (DITHER) reads it,
\ so players' keys can be shown, and one day changed, before the game loads.
\ Both programs INCLUDE this file, which declares the block's labels at its
\ fixed address with ORG/SKIP (emitting nothing), so each program's labels
\ name it.
\
\ Where: the top of page &0C, which the MOS keeps for user-defined characters
\ 224-255; nothing here defines them. It lies above SPLASH's code, above the
\ game's buffers (each program checks), and below the DFS NMI routine at
\ &0D00. The DITHER loader never writes it.
\
\ Kept across Break: a BREAK (soft reset) leaves RAM alone; CTRL-BREAK and
\ power-on clear it (MOS 1.20 reset). SPLASH keeps the block when it is
\ sealed -- handoff_magic is HANDOFF_MAGIC and handoff_checksum matches --
\ and otherwise fills it with the default layouts and seals it.
\
\ Layout:
\   key_layouts       MAX_PLAYERS layouts of KEY_LAYOUT_BYTES negative-INKEY
\                     codes, in the order fire, right, left, down, up (see
\                     scan_layout in game.asm), one per player slot C, M, Y, K
\   handoff_magic     HANDOFF_MAGIC when sealed
\   handoff_checksum  the sum (mod 256) of key_layouts' bytes and the magic
\ ============================================================================

HANDOFF_ADDRESS   = &0CE0
HANDOFF_KEY_BYTES = 20         \ 4 player slots x 5 keys.
HANDOFF_MAGIC     = &DD        \ Not 0, which power-on RAM (in Beebium) is.

ORG HANDOFF_ADDRESS
.key_layouts      SKIP HANDOFF_KEY_BYTES
.handoff_magic    SKIP 1
.handoff_checksum SKIP 1
.handoff_end
ASSERT handoff_end <= &0D00    \ The DFS NMI routine is at &0D00.
