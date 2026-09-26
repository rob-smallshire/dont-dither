\ ============================================================================
\ os.asm -- Acorn MOS 1.20 entry points and addresses used by Don't Dither!
\
\ Only constants live here: no code or data is emitted, so this file can be
\ INCLUDEd anywhere. References are to the Advanced User Guide (AUG) and to
\ Toby Nelson's annotated MOS 1.20 disassembly.
\ ============================================================================

\ ----------------------------------------------------------------------------
\ MOS entry points (AUG chapter 7, "Operating System calls")
\ ----------------------------------------------------------------------------

OSWRCH = &FFEE          \ Write the character in A to the VDU stream.
                        \ Preserves A, X and Y.
OSBYTE = &FFF4          \ Miscellaneous OS call selected by A, arguments
                        \ in X and Y.

\ ----------------------------------------------------------------------------
\ VDU control codes (AUG appendix D)
\ ----------------------------------------------------------------------------

VDU_TEXT_COLOUR = 17    \ VDU 17,c          -- set text colour
VDU_PALETTE     = 19    \ VDU 19,l,p,0,0,0  -- logical colour l := physical p
VDU_MODE        = 22    \ VDU 22,m          -- select screen mode m
VDU_DEFINE      = 23    \ VDU 23,...        -- 6845 register writes etc.
VDU_TAB         = 31    \ VDU 31,x,y        -- move text cursor to column x,
                        \                     row y

\ ----------------------------------------------------------------------------
\ Screen layout in MODE 1 (AUG appendix F)
\ ----------------------------------------------------------------------------

MODE1_SCREEN_BASE   = &3000   \ First byte of screen memory in MODE 1.
MODE1_ROW_BYTES     = 640     \ Bytes per character row: 80 byte columns,
                              \ each 8 raster lines (one byte per line) deep.
MODE1_CHAR_ROWS     = 32      \ 32 character rows of 8 raster lines = 256
                              \ lines.

\ ----------------------------------------------------------------------------
\ MOS workspace we read or rely on
\ ----------------------------------------------------------------------------

VDU_CURRENT_MODE = &0355      \ MOS variable holding the current screen mode.
