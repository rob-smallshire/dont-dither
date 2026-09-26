\ ============================================================================
\ main.asm -- Don't Dither! for the BBC Micro Model B
\
\ Build with `uv run dd-build` (runs beebasm from the project root, which is
\ why INCLUDE paths below are relative to the root).
\
\ CURRENT STAGE: boot smoke test. The program
\   1. selects MODE 1 and hides the text cursor,
\   2. programs the CMYK palette,
\   3. fills the 256x256-pixel arena (the left 64 byte columns of the
\      screen) with the four-way ink state (1,1,1,1),
\   4. prints the title in the right-hand HUD column,
\   5. sets zp_boot_status to BOOT_READY so the test harness knows it is done,
\   6. idles forever.
\
\ Memory map (for now):
\   &0070-&008F  zero page reserved for user programs; ours, see below
\   &1900-       program code and tables (loaded and run by DFS via !BOOT)
\   &3000-&7FFF  MODE 1 screen memory (20 KB)
\ Later the program will reclaim DFS workspace below &1900 once loaded.
\ ============================================================================

INCLUDE "asm/os.asm"

\ ----------------------------------------------------------------------------
\ Screen geometry of the arena and HUD
\ ----------------------------------------------------------------------------

ARENA_BYTE_COLUMNS = 64        \ 256 pixels / 4 pixels per MODE 1 byte.
                               \ Byte columns 64..79 (64 pixels) are the HUD.
ARENA_ROW_BYTES    = ARENA_BYTE_COLUMNS * 8
                               \ = 512: arena bytes at the start of each
                               \ 640-byte character row.
HUD_TEXT_COLUMN    = 32        \ First text column of the HUD (pixel 256 is
                               \ text column 256 / 8 = 32 in MODE 1).

BOOT_READY = &FF               \ Value of zp_boot_status once set-up is done.

\ ----------------------------------------------------------------------------
\ Zero page variables
\
\ Declared with ORG/SKIP rather than as constants so that beebasm exports
\ them as labels; the Python tests look addresses up by name.
\ ----------------------------------------------------------------------------

ORG &70
GUARD &90                      \ Stay inside the user zero page block.

.zp_boot_status   SKIP 1       \ Boot progress; BOOT_READY when set-up done.
.zp_screen_ptr    SKIP 2       \ Little-endian pointer into screen memory,
                               \ used with (zp),Y addressing.
.zp_fill_top      SKIP 1       \ Screen byte for the top raster line of a
                               \ superpixel row while filling the arena.
.zp_fill_bottom   SKIP 1       \ Screen byte for the bottom raster line.

\ ----------------------------------------------------------------------------
\ Program
\ ----------------------------------------------------------------------------

ORG &1900
GUARD MODE1_SCREEN_BASE        \ Assembly fails if code/data reach the
                               \ screen.

.start
    \ Mark boot as in progress. RAM contents at power-on are not guaranteed,
    \ so the harness must never see a stale BOOT_READY.
    LDA #0
    STA zp_boot_status

    \ Send the VDU set-up sequence: MODE 1 and cursor off.
    LDX #LO(setup_vdu_bytes)
    LDY #HI(setup_vdu_bytes)
    LDA #setup_vdu_bytes_end - setup_vdu_bytes
    JSR send_vdu_bytes

    \ Program the CMYK palette. The VDU 19 records are generated from the
    \ ink model (see ink_tables.asm) so that the palette and the pattern
    \ tables cannot disagree about which logical colour is which ink.
    LDX #LO(palette_vdu_bytes)
    LDY #HI(palette_vdu_bytes)
    LDA #palette_vdu_bytes_end - palette_vdu_bytes
    JSR send_vdu_bytes

    \ Fill the arena with the four-player initial ink state.
    LDX #STATE_FOUR_WAY
    JSR fill_arena_with_state

    \ Print the title into the HUD.
    LDX #LO(title_vdu_bytes)
    LDY #HI(title_vdu_bytes)
    LDA #title_vdu_bytes_end - title_vdu_bytes
    JSR send_vdu_bytes

    \ Tell the harness we have finished setting up.
    LDA #BOOT_READY
    STA zp_boot_status

.idle
    JMP idle                   \ Nothing else to do yet.

\ ----------------------------------------------------------------------------
\ send_vdu_bytes -- write a block of bytes to OSWRCH
\
\ On entry:  X = low byte, Y = high byte of the block address
\            A = number of bytes to send (1..255)
\ On exit:   A, X, Y corrupted; zp_screen_ptr corrupted (borrowed as a
\            pointer, as the arena fill has not started yet or has finished)
\
\ VDU sequences contain zero bytes (e.g. VDU 19,l,p,0,0,0), so a length
\ count is used rather than a terminator.
\ ----------------------------------------------------------------------------

.send_vdu_bytes
    STX zp_screen_ptr          \ Point zp_screen_ptr at the block.
    STY zp_screen_ptr+1
    TAX                        \ X = bytes remaining.
    LDY #0                     \ Y = offset of the next byte.
.send_vdu_loop
    LDA (zp_screen_ptr),Y      \ Fetch the next byte...
    JSR OSWRCH                 \ ...and send it (OSWRCH preserves X and Y).
    INY
    DEX
    BNE send_vdu_loop
    RTS

\ ----------------------------------------------------------------------------
\ fill_arena_with_state -- set every arena superpixel to one ink state
\
\ On entry:  X = ink state number (0..STATE_COUNT-1)
\ On exit:   A, X, Y corrupted
\
\ Layout recap: in MODE 1 each character row is 640 bytes: 80 byte columns,
\ each holding 8 consecutive raster lines. A superpixel row is two raster
\ lines, so within a byte column the bytes alternate top, bottom, top,
\ bottom... (raster lines 0/1, 2/3, 4/5, 6/7). Every screen byte holds two
\ superpixels side by side, and since we fill with a single state both
\ halves are the same, so the full-byte state_top_bytes / state_bottom_bytes
\ entries can be stored directly without masking.
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

\ ----------------------------------------------------------------------------
\ VDU byte sequences
\ ----------------------------------------------------------------------------

.setup_vdu_bytes
    EQUB VDU_MODE, 1           \ MODE 1: 320x256, four colours. Clears the
                               \ screen to logical colour 0.
    \ VDU 23,1,0;0;0;0; -- hide the text cursor (6845 cursor off).
    EQUB VDU_DEFINE, 1, 0, 0, 0, 0, 0, 0, 0, 0
.setup_vdu_bytes_end

.title_vdu_bytes
    \ Two lines of title text in the HUD, in text colour 3 (Y), centred in
    \ the eight HUD text columns.
    EQUB VDU_TEXT_COLOUR, 3
    EQUB VDU_TAB, HUD_TEXT_COLUMN + 1, 1
    EQUS "DON'T"
    EQUB VDU_TAB, HUD_TEXT_COLUMN, 2
    EQUS "DITHER!"
.title_vdu_bytes_end

\ ----------------------------------------------------------------------------
\ Generated lookup tables (ink patterns, palette)
\ ----------------------------------------------------------------------------

INCLUDE "build/generated/ink_tables.asm"

.end

SAVE "DITHER", start, end, start
