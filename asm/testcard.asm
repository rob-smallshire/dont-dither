\ ============================================================================
\ testcard.asm -- texture and wall test card, saved on the disc as TCARD
\
\ Run with *RUN TCARD. Draws every one of the 35 ink states as a 20x20
\ superpixel swatch, in a 6x6 grid inside a walled border, with a wall
\ feature (pillar, bars, L, T, cross) inside each swatch, so that every
\ texture can be judged over a large area, against its neighbours and
\ against walls. The layout is defined in tools/dontdither/testcard.py and
\ generated into testcard_data.asm.
\
\ The ink is drawn one superpixel at a time with set_superpixel_state (the
\ same routine the game will use for painting), then the walls are drawn from
\ the wall bitmap with draw_walls. This exercises both routines over the
\ whole arena. The border walls are black with a yellow rim; the swatch
\ features cycle through all 12 (core, rim) wall colourings.
\
\ Memory use is as for main.asm: code and tables from &1900, zero page in
\ &70-&8F, MODE 1 screen at &3000.
\ ============================================================================

INCLUDE "asm/os.asm"
INCLUDE "asm/macros.asm"
INCLUDE "asm/zeropage.asm"

ORG &1900
GUARD MODE1_SCREEN_BASE

.start
    LDA #0                     \ Boot in progress (see main.asm).
    STA zp_boot_status

    JSR init_display           \ MODE 1, cursor off, CMYK palette.
    JSR draw_swatches          \ Ink first...

    LDA #LO(testcard_walls)    \ ...then walls over it: every wall in the
    STA zp_wall_map            \ border colouring first...
    LDA #HI(testcard_walls)
    STA zp_wall_map+1
    LDA #TESTCARD_BORDER_CORE
    STA zp_wall_core
    LDA #TESTCARD_BORDER_RIM
    STA zp_wall_rim
    JSR draw_walls
    JSR draw_swatch_walls      \ ...then each swatch's feature in its own.

    SEND_VDU title_vdu_bytes, title_vdu_bytes_end

    LDA #BOOT_READY            \ Tell the harness we are done.
    STA zp_boot_status
.idle
    JMP idle

\ ----------------------------------------------------------------------------
\ draw_swatches -- set every arena superpixel to its swatch's ink state
\
\ On exit:  A, X, Y corrupted
\
\ For superpixel (sx, sy) the swatch index is
\     testcard_swatch_row_base[sy] + testcard_swatch_column[sx]
\ (the row table already holds row * 6), and the ink state is
\ testcard_swatch_states[index]. Border superpixels are clamped to the
\ nearest swatch by the tables; the border walls cover them afterwards.
\ ----------------------------------------------------------------------------

.draw_swatches
    LDA #0
    STA zp_sy
.draw_swatches_row
    LDA #0
    STA zp_sx
.draw_swatches_cell
    LDX zp_sx
    LDY zp_sy
    LDA testcard_swatch_row_base,Y
    CLC
    ADC testcard_swatch_column,X
    TAY                        \ Y = swatch index, 0..35.
    LDA testcard_swatch_states,Y   \ A = ink state.
    LDY zp_sy                  \ Restore Y = sy (X is still sx).
    JSR set_superpixel_state
    INC zp_sx
    LDA zp_sx
    CMP #ARENA_CELLS
    BNE draw_swatches_cell
    INC zp_sy
    LDA zp_sy
    CMP #ARENA_CELLS
    BNE draw_swatches_row
    RTS

\ ----------------------------------------------------------------------------
\ draw_swatch_walls -- redraw each swatch's wall feature in its colouring
\
\ On exit:  A, X, Y corrupted
\
\ Each testcard_swatch_walls record gives a swatch's top-left cell and the
\ core and rim inks for its feature. The swatch's 5x5 cells are redrawn with
\ draw_walls_in_rect, which cycles through all 12 colourings over the grid.
\ ----------------------------------------------------------------------------

.draw_swatch_walls
    LDA #0
    STA zp_swatch              \ Offset of the current 4-byte record.
.draw_swatch_walls_loop
    LDX zp_swatch
    LDA testcard_swatch_walls,X    \ Rectangle: origin cell to origin + 5.
    STA zp_rect_x0
    CLC
    ADC #TESTCARD_SWATCH_CELLS
    STA zp_rect_x1
    LDA testcard_swatch_walls+1,X
    STA zp_rect_y0
    CLC
    ADC #TESTCARD_SWATCH_CELLS
    STA zp_rect_y1
    LDA testcard_swatch_walls+2,X  \ Colouring.
    STA zp_wall_core
    LDA testcard_swatch_walls+3,X
    STA zp_wall_rim
    JSR draw_walls_in_rect

    LDA zp_swatch              \ Next record, until all 36 are done.
    CLC
    ADC #TESTCARD_SWATCH_RECORD
    STA zp_swatch
    CMP #TESTCARD_SWATCH_RECORD * TESTCARD_SWATCH_COUNT
    BNE draw_swatch_walls_loop
    RTS

.title_vdu_bytes
    EQUB VDU_TEXT_COLOUR, 3    \ Yellow text in the HUD.
    EQUB VDU_TAB, HUD_TEXT_COLUMN + 2, 1
    EQUS "TEST"
    EQUB VDU_TAB, HUD_TEXT_COLUMN + 2, 2
    EQUS "CARD"
.title_vdu_bytes_end

\ ----------------------------------------------------------------------------
\ Shared modules and generated tables
\ ----------------------------------------------------------------------------

INCLUDE "asm/display.asm"
INCLUDE "asm/arena.asm"
INCLUDE "asm/walls.asm"
INCLUDE "build/generated/ink_tables.asm"
INCLUDE "build/generated/screen_tables.asm"
INCLUDE "build/generated/wall_tiles.asm"
INCLUDE "build/generated/testcard_data.asm"

.end

SAVE "TCARD", start, end, start
