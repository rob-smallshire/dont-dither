\ ============================================================================
\ main.asm -- Don't Dither! for the BBC Micro Model B
\
\ Build with `uv run dd-build` (runs beebasm from the project root, which is
\ why INCLUDE paths are relative to the root). The disc's !BOOT runs this
\ program, saved as DITHER.
\
\ CURRENT STAGE: boot smoke test. The program
\   1. selects MODE 1, hides the cursor and programs the CMYK palette,
\   2. fills the 256x256-pixel arena with the four-way ink state (1,1,1,1),
\   3. prints the title in the right-hand HUD column,
\   4. sets zp_boot_status to BOOT_READY so the test harness knows it is done,
\   5. idles forever.
\
\ Memory map (for now):
\   &0070-&008F  zero page reserved for user programs (see zeropage.asm)
\   &1900-       program code and tables (loaded and run by DFS via !BOOT)
\   &3000-&7FFF  MODE 1 screen memory (20 KB)
\ Later the program will reclaim DFS workspace below &1900 once loaded.
\ ============================================================================

INCLUDE "asm/os.asm"
INCLUDE "asm/macros.asm"
INCLUDE "asm/zeropage.asm"

ORG &1900
GUARD MODE1_SCREEN_BASE        \ Assembly fails if code/data reach the
                               \ screen.

.start
    \ Mark boot as in progress. RAM contents at power-on are not guaranteed,
    \ so the harness must never see a stale BOOT_READY.
    LDA #0
    STA zp_boot_status

    JSR init_display           \ MODE 1, cursor off, CMYK palette.

    \ Fill the arena with the four-player initial ink state.
    LDX #STATE_FOUR_WAY
    JSR fill_arena_with_state

    SEND_VDU title_vdu_bytes, title_vdu_bytes_end

    \ Tell the harness we have finished setting up.
    LDA #BOOT_READY
    STA zp_boot_status

.idle
    JMP idle                   \ Nothing else to do yet.

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
\ Shared modules and generated tables
\ ----------------------------------------------------------------------------

INCLUDE "asm/display.asm"
INCLUDE "asm/arena.asm"
INCLUDE "build/generated/ink_tables.asm"
INCLUDE "build/generated/screen_tables.asm"

.end

SAVE "DITHER", start, end, start
