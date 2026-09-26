\ ============================================================================
\ display.asm -- display set-up and VDU output helpers
\
\ Requires: os.asm, macros.asm, zeropage.asm, and the generated ink_tables.asm (for
\ palette_vdu_bytes) to be INCLUDEd by the program.
\ ============================================================================

\ ----------------------------------------------------------------------------
\ init_display -- MODE 1, cursor off, CMYK palette
\
\ Selecting MODE 1 clears the screen to logical colour 0 (K) and resets the
\ text and graphics windows. The palette records are generated from the ink
\ model (see ink_tables.asm) so that the palette and the pattern tables
\ cannot disagree about which logical colour is which ink.
\
\ Corrupts A, X, Y.
\ ----------------------------------------------------------------------------

.init_display
    SEND_VDU mode_and_cursor_vdu_bytes, mode_and_cursor_vdu_bytes_end
    SEND_VDU palette_vdu_bytes, palette_vdu_bytes_end
    RTS

.mode_and_cursor_vdu_bytes
    EQUB VDU_MODE, 1           \ MODE 1: 320x256 pixels, four colours.
    \ VDU 23,1,0;0;0;0; -- hide the text cursor.
    EQUB VDU_DEFINE, 1, 0, 0, 0, 0, 0, 0, 0, 0
.mode_and_cursor_vdu_bytes_end

\ ----------------------------------------------------------------------------
\ send_vdu_bytes -- write a block of bytes to OSWRCH
\
\ On entry:  X = low byte, Y = high byte of the block address
\            A = number of bytes to send (1..255)
\ On exit:   A, X, Y corrupted; zp_screen_ptr corrupted (borrowed as the
\            block pointer)
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
