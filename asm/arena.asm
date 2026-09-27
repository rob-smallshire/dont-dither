\ ============================================================================
\ arena.asm -- reading and writing ink superpixels in the arena
\
\ The arena is the left 256x256 pixels of the MODE 1 screen, a 128x128 grid
\ of 2x2-pixel superpixels. A superpixel's pattern IS its ink state; there is
\ no separate ownership array.
\
\ Where a superpixel lives: superpixel (sx, sy) occupies one half of each of
\ two vertically adjacent raster bytes:
\     top byte    = superpixel_row_lo/hi[sy] + (sx DIV 2) * 8
\     bottom byte = top byte + 1
\ The left half (mask &CC, pixels 0 and 1) belongs to even sx, the right half
\ (mask &33, pixels 2 and 3) to odd sx.
\
\ superpixel_row_lo/hi are built at start-up by build_superpixel_rows, into
\ 256 bytes of uninitialised memory each program declares (SUPERPIXEL_ROWS
\ bytes for each), rather than being loaded: that saves 256 bytes of the
\ file and of initialised memory.
\
\ Requires: os.asm, zeropage.asm, and the generated ink_tables.asm and
\ screen_tables.asm.
\ ============================================================================

ARENA_CELLS        = 128       \ Superpixels per arena side.
ARENA_BYTE_COLUMNS = 64        \ 256 pixels / 4 pixels per MODE 1 byte.
                               \ Byte columns 64..79 (64 pixels) are the HUD.
HUD_TEXT_COLUMN    = 32        \ First text column of the HUD (pixel 256 is
                               \ text column 256 / 8 = 32 in MODE 1).
SUPERPIXEL_ROWS    = 128       \ Entries in superpixel_row_lo and _hi.

\ ----------------------------------------------------------------------------
\ build_superpixel_rows -- fill superpixel_row_lo/hi
\
\ Entry sy is the address of the top raster byte of superpixel (0, sy):
\     &3000 + (sy DIV 4) * 640 + (sy AND 3) * 2
\ Superpixel (sx, sy) is at that address + (sx DIV 2) * 8; the bottom raster
\ byte is the next address. For a character row cy, entry 4*cy is the
\ address of the row's first character cell.
\
\ zp_screen_ptr holds the current character row's address. Rows are 640
\ (&280) bytes apart from &3000, so its low byte is always &00 or &80, and
\ adding (sy AND 3) * 2 (at most 6) is an ORA, with no carry.
\
\ On exit:  A, X corrupted; zp_screen_ptr corrupted
\ ----------------------------------------------------------------------------

.build_superpixel_rows
    LDA #LO(MODE1_SCREEN_BASE)
    STA zp_screen_ptr
    LDA #HI(MODE1_SCREEN_BASE)
    STA zp_screen_ptr+1
    LDX #0                     \ X = sy.
.build_superpixel_rows_loop
    TXA                        \ Low byte: row address + (sy AND 3) * 2.
    AND #3
    ASL A
    ORA zp_screen_ptr
    STA superpixel_row_lo,X
    LDA zp_screen_ptr+1        \ High byte: the row's.
    STA superpixel_row_hi,X
    TXA                        \ After the row's fourth superpixel row, on
    AND #3                     \ to the next character row.
    CMP #3
    BNE build_superpixel_rows_next
    LDA zp_screen_ptr
    CLC
    ADC #LO(MODE1_ROW_BYTES)
    STA zp_screen_ptr
    LDA zp_screen_ptr+1
    ADC #HI(MODE1_ROW_BYTES)
    STA zp_screen_ptr+1
.build_superpixel_rows_next
    INX
    BPL build_superpixel_rows_loop   \ Until sy = 128.
    RTS

\ ----------------------------------------------------------------------------
\ set_superpixel_state -- draw one superpixel in an ink state's pattern
\
\ On entry:  A = ink state (0..STATE_COUNT-1)
\            X = sx (0..127), Y = sy (0..127)
\ On exit:   A, X, Y corrupted
\
\ Only the superpixel's half of each raster byte is changed; the neighbouring
\ superpixel sharing the byte is preserved. The merge uses the identity
\     new = old EOR ((pattern EOR old) AND mask)
\ which takes pattern bits where mask is 1 and old bits elsewhere, without
\ needing the inverted mask.
\ ----------------------------------------------------------------------------

.set_superpixel_state
    STA zp_ink_state

    \ Form zp_screen_ptr = row address + (sx DIV 2) * 8. (sx AND &FE) * 4 is
    \ the same value; it reaches 504, so it needs a ninth bit, which the
    \ second ASL shifts into carry and ROL moves into the high byte.
    LDA #0
    STA zp_screen_ptr+1
    TXA
    AND #&FE                   \ Round sx down to even: pairs share a byte.
    ASL A                      \ *2: at most 252, so carry is clear.
    ASL A                      \ *4: carry holds bit 8.
    ROL zp_screen_ptr+1        \ High byte := 0 or 1. Clears carry.
    ADC superpixel_row_lo,Y    \ Add the row address (carry clear).
    STA zp_screen_ptr
    LDA zp_screen_ptr+1
    ADC superpixel_row_hi,Y
    STA zp_screen_ptr+1

    \ Choose the half of the byte: shifting sx right puts its parity in
    \ carry. Even sx uses the left half (&CC), odd the right (&33).
    TXA
    LSR A
    LDA #&CC
    BCC set_superpixel_even
    LDA #&33
.set_superpixel_even
    STA zp_half_mask

    \ Merge the state's top row into the top raster byte...
    LDX zp_ink_state
    LDY #0
    LDA state_top_bytes,X
    EOR (zp_screen_ptr),Y
    AND zp_half_mask
    EOR (zp_screen_ptr),Y
    STA (zp_screen_ptr),Y

    \ ...and its bottom row into the bottom raster byte, one address on.
    INY
    LDA state_bottom_bytes,X
    EOR (zp_screen_ptr),Y
    AND zp_half_mask
    EOR (zp_screen_ptr),Y
    STA (zp_screen_ptr),Y
    RTS

\ ----------------------------------------------------------------------------
\ fill_arena_with_state -- set every arena superpixel to one ink state
\
\ On entry:  X = ink state (0..STATE_COUNT-1)
\ On exit:   A, X, Y corrupted
\
\ A fast path for whole-arena fills. In MODE 1 each character row is 640
\ bytes: 80 byte columns, each holding 8 consecutive raster lines. A
\ superpixel row is two raster lines, so within a byte column the bytes
\ alternate top, bottom, top, bottom... (raster lines 0/1, 2/3, 4/5, 6/7).
\ Every screen byte holds two superpixels side by side, and since both get the
\ same state, the full-byte state_top_bytes / state_bottom_bytes entries are
\ stored directly without masking.
\
\ The arena is the first 512 bytes (64 byte columns) of each of the 32
\ character rows; the remaining 128 bytes of each row are the HUD.
\ ----------------------------------------------------------------------------

.fill_arena_with_state
    \ Fetch this state's top and bottom raster bytes into zero page, where
    \ the inner loop can load them quickly.
    LDA state_top_bytes,X
    STA zp_fill_top
    LDA state_bottom_bytes,X
    STA zp_fill_bottom

    \ Start at the top-left of the screen.
    LDA #LO(MODE1_SCREEN_BASE)
    STA zp_screen_ptr
    LDA #HI(MODE1_SCREEN_BASE)
    STA zp_screen_ptr+1

    LDX #MODE1_CHAR_ROWS       \ X = character rows remaining.

.fill_char_row
    \ The 512 arena bytes of this row are two 256-byte pages: fill the
    \ first page at zp_screen_ptr, then the second page 256 bytes on.
    \ Y steps by two, writing a top byte at each even offset and a bottom
    \ byte at the following odd offset, so after 128 pairs Y wraps to 0.
    LDY #0
.fill_first_page
    LDA zp_fill_top
    STA (zp_screen_ptr),Y      \ Even offset: top raster line of a
    INY                        \ superpixel row.
    LDA zp_fill_bottom
    STA (zp_screen_ptr),Y      \ Odd offset: bottom raster line.
    INY
    BNE fill_first_page        \ Until Y wraps to 0 (256 bytes done).

    INC zp_screen_ptr+1        \ Advance the pointer 256 bytes to the
                               \ second page of the row. Y is 0 again.
.fill_second_page
    LDA zp_fill_top
    STA (zp_screen_ptr),Y
    INY
    LDA zp_fill_bottom
    STA (zp_screen_ptr),Y
    INY
    BNE fill_second_page

    \ The pointer is now row start + 256. The next row starts at
    \ row start + 640, so add 384 (= &0180) to skip the rest of this row
    \ (the second arena page and the 128 HUD bytes).
    CLC
    LDA zp_screen_ptr
    ADC #LO(MODE1_ROW_BYTES - 256)
    STA zp_screen_ptr
    LDA zp_screen_ptr+1
    ADC #HI(MODE1_ROW_BYTES - 256)
    STA zp_screen_ptr+1

    DEX
    BNE fill_char_row
    RTS
