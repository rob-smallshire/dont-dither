\ ============================================================================
\ hud.asm -- the round clock, and the end-of-round territory tally
\
\ During a round the HUD shows only a countdown (m:ss). There are no running
\ scores: as in Splatoon's Turf War, nobody knows who is winning until the
\ end. When the clock reaches zero, play stops and:
\
\   1. the tanks are removed (hide_sprites), revealing the bare territory;
\   2. count_territory scans every open (non-wall) character cell of the
\      arena and builds a histogram of the 35 ink states;
\   3. compute_scores turns the histogram into each ink's quanta (a state
\      with n quanta of an ink contributes n per cell), and each player's
\      share: quanta * 100 DIV total, total being 4 quanta per open cell;
\   4. reveal_scores draws a bar per player in the HUD, one at a time from
\      the smallest share to the largest to build tension, labels each with
\      its percentage in a tiny 3x5 font (hud_font.asm) drawn straight into
\      screen memory, and underlines the winner's label (all winners', if
\      tied). Nothing at the bottom of the HUD goes through the MOS text
\      cursor: printing in the bottom-right character cell would make the
\      MOS scroll the screen, moving it in memory under our feet.
\
\ This must match tools/dontdither/game.py (Game.percentages).
\
\ Requires: os.asm, zeropage.asm, walls.asm, sprites.asm, display.asm and
\ the generated tables.
\ ============================================================================

HUD_CLOCK_COLUMN = HUD_TEXT_COLUMN + 2   \ "m:ss" centred in the HUD...
HUD_CLOCK_ROW    = 6                     \ ...below the level name.

BAR_BASE_LINE    = 239         \ Bars grow up from this raster line...
BAR_LABEL_LINE   = 242         \ ...with their percentage below (top line)
BAR_WINNER_LINE  = 249         \ and the winner's label underlined.
BAR_FRAMES_PER_STEP = 1        \ Vertical syncs per two lines of growth.

\ ----------------------------------------------------------------------------
\ start_round -- set the round clock from round_length_ticks and show it
\
\ On exit:  A, X, Y corrupted
\ ----------------------------------------------------------------------------

.start_round
    LDA round_length_ticks
    STA round_ticks_left
    LDA round_length_ticks+1
    STA round_ticks_left+1
    LDA #TICKS_PER_SECOND
    STA clock_ticks

    \ Clock = round length in whole seconds, as minutes and seconds:
    \ divide by 25 then by 60, by repeated subtraction (at most a few
    \ hundred steps, once per round).
    LDA round_length_ticks
    STA tally_value
    LDA round_length_ticks+1
    STA tally_value+1
    LDX #0                     \ X:Y counts seconds (low, high).
    LDY #0
.start_round_seconds
    LDA tally_value
    SEC
    SBC #TICKS_PER_SECOND
    STA zp_sprite_tmp
    LDA tally_value+1
    SBC #0
    BCC start_round_minutes    \ Less than a second left: done.
    STA tally_value+1
    LDA zp_sprite_tmp
    STA tally_value
    INX
    BNE start_round_seconds
    INY
    JMP start_round_seconds
.start_round_minutes
    STX tally_value              \ Seconds, 16 bits.
    STY tally_value+1
    LDX #0                     \ X counts minutes.
.start_round_minute
    LDA tally_value
    SEC
    SBC #60
    STA zp_sprite_tmp
    LDA tally_value+1
    SBC #0
    BCC start_round_clock
    STA tally_value+1
    LDA zp_sprite_tmp
    STA tally_value
    INX
    JMP start_round_minute
.start_round_clock
    STX clock_minutes
    LDA tally_value
    STA clock_seconds
    JMP print_clock            \ Tail call.

\ ----------------------------------------------------------------------------
\ tick_clock -- count one tick off the round
\
\ On exit:  carry set if the round has just ended; A, X, Y corrupted
\
\ Every TICKS_PER_SECOND ticks the displayed clock goes down a second.
\ ----------------------------------------------------------------------------

.tick_clock
    DEC clock_ticks
    BNE tick_clock_round
    LDA #TICKS_PER_SECOND
    STA clock_ticks
    DEC clock_seconds          \ Down a second, borrowing from the minutes.
    BPL tick_clock_show
    LDA #59
    STA clock_seconds
    DEC clock_minutes
.tick_clock_show
    JSR print_clock
.tick_clock_round
    LDA round_ticks_left       \ 16-bit decrement...
    BNE tick_clock_low
    DEC round_ticks_left+1
.tick_clock_low
    DEC round_ticks_left
    LDA round_ticks_left       \ ...ended when both bytes are zero.
    ORA round_ticks_left+1
    BNE tick_clock_running
    SEC                        \ Over.
    RTS
.tick_clock_running
    CLC
    RTS

\ ----------------------------------------------------------------------------
\ print_clock -- show clock_minutes:clock_seconds as m:ss in the HUD
\ ----------------------------------------------------------------------------

.print_clock
    LDA #VDU_TAB
    JSR OSWRCH
    LDA #HUD_CLOCK_COLUMN
    JSR OSWRCH
    LDA #HUD_CLOCK_ROW
    JSR OSWRCH
    LDA clock_minutes
    CLC
    ADC #'0'
    JSR OSWRCH
    LDA #':'
    JSR OSWRCH
    LDA clock_seconds
    JSR two_digits             \ A = tens digit, X = units digit (ASCII).
    JSR OSWRCH
    TXA
    JMP OSWRCH

\ ----------------------------------------------------------------------------
\ two_digits -- split A (0..99) into ASCII digits
\
\ On exit:  A = tens digit, X = units digit, as characters; Y preserved
\ ----------------------------------------------------------------------------

.two_digits
    LDX #'0'
.two_digits_tens
    CMP #10
    BCC two_digits_done
    SBC #10                    \ Carry is set (A >= 10).
    INX
    JMP two_digits_tens
.two_digits_done
    CLC
    ADC #'0'
    STA zp_sprite_tmp          \ Units...
    TXA                        \ ...tens into A...
    LDX zp_sprite_tmp          \ ...units into X.
    RTS

\ ----------------------------------------------------------------------------
\ end_of_round -- stop play, tally the territory and reveal the result
\
\ Never returns: goes on to after_round (flow.asm) via round_over, where
\ tests stop once the reveal is complete.
\ ----------------------------------------------------------------------------

.end_of_round
    JSR hide_sprites           \ The bare, final territory.
    JSR clear_gauges           \ Room for the tally bars.
    JSR count_territory
    JSR compute_scores
    JSR reveal_scores
.round_over                    \ Tests stop here.
    JMP after_round            \ Points, totals, and on (flow.asm).

\ ----------------------------------------------------------------------------
\ count_territory -- histogram of the ink states of every open arena cell
\
\ On exit:  state_histogram_lo/hi[s] = number of superpixels in state s
\           A, X, Y corrupted
\
\ Walks the 32x32 wall-cell grid, skipping wall cells (their tiles are not
\ ink). Each open character cell holds 4x4 superpixels: per superpixel row,
\ a top and a bottom raster byte in each of its two byte columns (offsets
\ 2r, 2r+1 and 8+2r, 8+2r+1), each byte holding two superpixels.
\ ----------------------------------------------------------------------------

.count_territory
    LDX #STATE_COUNT - 1       \ Clear the histogram.
    LDA #0
.count_clear
    STA state_histogram_lo,X
    STA state_histogram_hi,X
    DEX
    BPL count_clear

    LDA #0
    STA zp_cy
.count_row
    LDA #0
    STA zp_cx
.count_cell
    LDX zp_cx
    LDY zp_cy
    JSR is_wall
    BNE count_next_cell

    \ zp_screen_ptr = the character cell: row 4 * cy's address + cx * 16.
    LDA zp_cy
    ASL A
    ASL A
    TAY
    LDA #0
    STA zp_screen_ptr+1
    LDA zp_cx
    ASL A
    ASL A
    ASL A
    ASL A                      \ cx * 16: bit 8 in carry.
    ROL zp_screen_ptr+1
    ADC superpixel_row_lo,Y    \ Carry clear after the ROL.
    STA zp_screen_ptr
    LDA zp_screen_ptr+1
    ADC superpixel_row_hi,Y
    STA zp_screen_ptr+1

    LDX #0                     \ X walks count_offsets: 8 byte pairs.
.count_pair
    STX zp_render_index
    LDY count_offsets,X
    LDA (zp_screen_ptr),Y
    STA zp_cell_top
    INY
    LDA (zp_screen_ptr),Y
    STA zp_cell_bottom

    LDA zp_cell_bottom         \ Left superpixel of the byte:
    AND #&CC                   \ (top AND &CC) OR ((bottom AND &CC) >> 2).
    LSR A
    LSR A
    STA zp_cell_index
    LDA zp_cell_top
    AND #&CC
    ORA zp_cell_index
    JSR count_pattern

    LDA zp_cell_top            \ Right superpixel:
    AND #&33                   \ ((top AND &33) << 2) OR (bottom AND &33).
    ASL A
    ASL A
    STA zp_cell_index
    LDA zp_cell_bottom
    AND #&33
    ORA zp_cell_index
    JSR count_pattern

    LDX zp_render_index
    INX
    CPX #8
    BNE count_pair

.count_next_cell
    INC zp_cx
    LDA zp_cx
    CMP #WALL_GRID_CELLS
    BNE count_cell
    INC zp_cy
    LDA zp_cy
    CMP #WALL_GRID_CELLS
    BNE count_row
    RTS

\ count_pattern: add one to the histogram entry of pattern index A.
.count_pattern
    TAX
    LDA pattern_to_state,X
    CMP #NON_CANONICAL
    BEQ count_pattern_done
    TAX
    INC state_histogram_lo,X
    BNE count_pattern_done
    INC state_histogram_hi,X
.count_pattern_done
    RTS

.count_offsets                 \ Top-byte offsets of the 8 byte pairs of a
    EQUB 0, 8, 2, 10, 4, 12, 6, 14   \ character cell (bottom = top + 1).

\ ----------------------------------------------------------------------------
\ compute_scores -- each player's quanta and share from the histogram
\
\ On exit:  player_quanta_lo/hi[p] and player_percent[p] set; total_quanta
\           = 4 per counted cell; A, X, Y corrupted
\ ----------------------------------------------------------------------------

.compute_scores
    \ Total quanta = 4 * cells counted.
    LDA #0
    STA total_quanta
    STA total_quanta+1
    LDX #STATE_COUNT - 1
.compute_total
    LDA total_quanta
    CLC
    ADC state_histogram_lo,X
    STA total_quanta
    LDA total_quanta+1
    ADC state_histogram_hi,X
    STA total_quanta+1
    DEX
    BPL compute_total
    ASL total_quanta           \ Times 4.
    ROL total_quanta+1
    ASL total_quanta
    ROL total_quanta+1

    LDX #0
.compute_player
    CPX player_count
    BEQ compute_done
    STX zp_player
    JSR ink_quanta             \ tally_value = quanta of player X's ink.
    LDX zp_player
    LDA tally_value
    STA player_quanta_lo,X
    LDA tally_value+1
    STA player_quanta_hi,X
    JSR percent_of_total       \ A = tally_value * 100 DIV total_quanta.
    LDX zp_player
    STA player_percent,X
    INX
    JMP compute_player
.compute_done
    RTS

\ ink_quanta: tally_value = sum over states s of histogram[s] * counts[s][ink],
\ ink being player X's. Each count is 0..4, so add histogram[s] that often.
.ink_quanta
    LDA #0
    STA tally_value
    STA tally_value+1
    LDA player_ink,X
    STA zp_count_base          \ state * 4 + ink walks state_counts.
    LDY #0                     \ Y = state.
.ink_quanta_state
    LDX zp_count_base
    LDA state_counts,X
    TAX                        \ X = this state's count of the ink.
.ink_quanta_add
    BEQ ink_quanta_next
    LDA tally_value
    CLC
    ADC state_histogram_lo,Y
    STA tally_value
    LDA tally_value+1
    ADC state_histogram_hi,Y
    STA tally_value+1
    DEX
    JMP ink_quanta_add
.ink_quanta_next
    LDA zp_count_base
    CLC
    ADC #4
    STA zp_count_base
    INY
    CPY #STATE_COUNT
    BNE ink_quanta_state
    RTS

\ percent_of_total: A = tally_value * 100 DIV total_quanta (0..100).
\ tally_product (24 bits) = quanta * 100 = quanta * 64 + quanta * 32 + quanta
\ * 4; then count how many times total_quanta can be subtracted.
.percent_of_total
    LDA #0
    STA tally_product
    STA tally_product+1
    STA tally_product+2
    LDA tally_value              \ tally_shift (24 bits) = quanta * 4.
    STA tally_shift
    LDA tally_value+1
    STA tally_shift+1
    LDA #0
    STA tally_shift+2
    JSR shift_left
    JSR shift_left
    JSR add_shift              \ + quanta * 4
    JSR shift_left
    JSR shift_left
    JSR shift_left
    JSR add_shift              \ + quanta * 32
    JSR shift_left
    JSR add_shift              \ + quanta * 64

    LDX #0                     \ X = percent.
.percent_loop
    LDA tally_product             \ Subtract total_quanta if it fits.
    SEC
    SBC total_quanta
    STA tally_shift
    LDA tally_product+1
    SBC total_quanta+1
    STA tally_shift+1
    LDA tally_product+2
    SBC #0
    BCC percent_done
    STA tally_product+2
    LDA tally_shift+1
    STA tally_product+1
    LDA tally_shift
    STA tally_product
    INX
    JMP percent_loop
.percent_done
    TXA
    RTS

.shift_left
    ASL tally_shift
    ROL tally_shift+1
    ROL tally_shift+2
    RTS

.add_shift
    LDA tally_product
    CLC
    ADC tally_shift
    STA tally_product
    LDA tally_product+1
    ADC tally_shift+1
    STA tally_product+1
    LDA tally_product+2
    ADC tally_shift+2
    STA tally_product+2
    RTS

\ ----------------------------------------------------------------------------
\ reveal_scores -- grow each player's bar, smallest share first
\
\ On exit:  A, X, Y corrupted
\
\ Bars stand in slots of 16 pixels (two text columns) across the HUD; with
\ two players the middle two slots are used. A bar is 8 pixels wide in the
\ player's ink, edged in its contrast ink (so a black bar shows on the black
\ HUD), and grows 1.5 pixels per percent from BAR_BASE_LINE.
\ ----------------------------------------------------------------------------

.reveal_scores
    LDA #0                     \ Nobody revealed yet.
    LDX #MAX_PLAYERS - 1
.reveal_clear
    STA player_revealed,X
    DEX
    BPL reveal_clear
    LDA player_count
    STA zp_update_remaining

.reveal_next
    \ Choose the unrevealed player with the smallest share (the lowest
    \ numbered, if tied).
    LDA #&FF
    STA bar_best
    LDX #0
.reveal_find
    CPX player_count
    BEQ reveal_found
    LDA player_revealed,X
    BNE reveal_find_next
    LDA player_percent,X
    CMP bar_best
    BCS reveal_find_next
    STA bar_best
    STX zp_player
.reveal_find_next
    INX
    JMP reveal_find
.reveal_found
    LDX zp_player
    LDA #1
    STA player_revealed,X
    JSR grow_bar
    DEC zp_update_remaining
    BNE reveal_next

    \ Underline the winner(s): every player with the largest share.
    LDA #0
    STA bar_best
    LDX #0
.reveal_max
    CPX player_count
    BEQ reveal_mark
    LDA player_percent,X
    CMP bar_best
    BCC reveal_max_next
    STA bar_best
.reveal_max_next
    INX
    JMP reveal_max
.reveal_mark
    LDX #0
.reveal_mark_loop
    CPX player_count
    BEQ reveal_done
    LDA player_percent,X
    CMP bar_best
    BNE reveal_mark_next
    STX zp_player
    JSR set_label_colour
    JSR bar_slot               \ Underline under the bar's two byte columns,
    ASL A                      \ two raster lines deep.
    ASL A
    CLC
    ADC #64 + 1
    JSR set_hud_column
    LDA #BAR_WINNER_LINE
    STA bar_line
    JSR draw_underline
    INC bar_line
    JSR draw_underline
    LDX zp_player
.reveal_mark_next
    INX
    JMP reveal_mark_loop
.reveal_done
    RTS

\ draw_underline: both of the bar's byte columns on line bar_line, in
\ the label colour.
.draw_underline
    LDA label_colour
    TAX
    JMP draw_bar_line

\ bar_slot: A = the bar slot (0..3) of player zp_player.
.bar_slot
    LDA player_count
    CMP #MAX_PLAYERS
    LDA zp_player
    BCS bar_slot_done          \ Four players: slot = player.
    CLC
    ADC #1                     \ Two players: the middle slots.
.bar_slot_done
    RTS

\ ----------------------------------------------------------------------------
\ grow_bar -- animate player zp_player's bar, then label it
\ ----------------------------------------------------------------------------

.grow_bar
    JSR bar_bytes
    JSR bar_column

    \ Height = percent * 1.5.
    LDX zp_player
    LDA player_percent,X
    LSR A
    CLC
    ADC player_percent,X
    STA bar_height

    LDA #BAR_BASE_LINE
    STA bar_line
    JMP grow_bar_loop

\ bar_bytes: bar_left and bar_right = the two bytes of a line of player
\ zp_player's bar: [contrast, ink, ink, ink] [ink, ink, ink, contrast];
\ pixel 0 of a byte is mask &88, pixel 3 mask &11.
.bar_bytes
    LDX zp_player
    LDY player_ink,X
    LDA ink_bytes,Y
    STA zp_sprite_xor          \ (borrowed) the ink byte
    LDA contrast_ink_bytes,Y
    STA zp_sprite_contrast
    AND #&88
    STA bar_left
    LDA zp_sprite_xor
    AND #&77
    ORA bar_left
    STA bar_left
    LDA zp_sprite_contrast
    AND #&11
    STA bar_right
    LDA zp_sprite_xor
    AND #&EE
    ORA bar_right
    STA bar_right
    RTS

\ bar_column: bar_offset = the byte column of player zp_player's bar: HUD
\ column 64 + 4 * slot + 1, as an offset from a raster line's start, times
\ 8 (at most 632: 16 bits).
.bar_column
    JSR bar_slot
    ASL A
    ASL A
    CLC
    ADC #64 + 1
    JMP set_hud_column         \ Tail call.

.grow_bar_loop
    LDA bar_height
    BEQ grow_bar_label
    LDA bar_left            \ Body line.
    LDX bar_right
    JSR draw_bar_line
    DEC bar_line
    LDA zp_sprite_contrast     \ Cap on the line above (overdrawn by the
    TAX                        \ next body line).
    JSR draw_bar_line
    DEC bar_height
    LDA bar_line            \ Pause for a field every two lines.
    AND #1
    BNE grow_bar_loop
    LDA #19
    JSR OSBYTE
    JMP grow_bar_loop

.grow_bar_label
    \ The percentage, in the player's colour, centred under the bar: tens
    \ in the bar's left byte column and units in its right one (a leading
    \ zero omitted); 100 takes one more column to the right.
    JSR set_label_colour
    JSR bar_slot
    ASL A
    ASL A
    CLC
    ADC #64 + 1                \ The bar's left byte column.
    STA label_column
    LDX zp_player
    LDA player_percent,X
    CMP #100
    BCC grow_bar_two_digits
    LDA #1                     \ 100: "1", "0", "0".
    JSR draw_digit
    INC label_column
    LDA #0
    JSR draw_digit
    INC label_column
    LDA #0
    JMP draw_digit
.grow_bar_two_digits
    JSR two_digits             \ ASCII tens in A, units in X.
    STX label_units
    SEC
    SBC #'0'
    BEQ grow_bar_units         \ No leading zero.
    JSR draw_digit
.grow_bar_units
    INC label_column
    LDA label_units
    SEC
    SBC #'0'
    JMP draw_digit

\ ----------------------------------------------------------------------------
\ set_label_colour -- label_colour = player zp_player's label colour
\
\ The player's ink, except black, which would not show on the black HUD:
\ that player's labels are in its contrast ink (yellow).
\ ----------------------------------------------------------------------------

.set_label_colour
    LDX zp_player
    LDY player_ink,X
    LDA ink_bytes,Y
    BNE set_label_colour_done
    LDA contrast_ink_bytes,Y
.set_label_colour_done
    STA label_colour
    RTS

\ ----------------------------------------------------------------------------
\ Ink gauges -- each player's reservoir, shown during play like an inkjet
\ printer's ink levels
\
\ A gauge is a bar in the player's ink, in the same byte columns as its
\ tally bar and rising from the same BAR_BASE_LINE, GAUGE_LINES_PER_SPLAT
\ raster lines per splat (64 lines when full). gauge_drawn holds how many
\ splats each gauge shows. Each tick update_gauges moves every gauge one
\ splat towards its reservoir -- a reservoir changes by at most a splat a
\ tick, so gauges keep up, and a new level's gauges fill from empty over
\ its first RESERVOIR_SPLATS ticks. clear_gauges empties them all at the
\ end of a round, before the tally bars grow in their place.
\ ----------------------------------------------------------------------------

GAUGE_LINES_PER_SPLAT = 2

.update_gauges
    LDX player_count
    DEX
.update_gauges_loop
    STX zp_player
    LDA player_reservoir,X
    JSR gauge_step
    LDX zp_player
    DEX
    BPL update_gauges_loop
    RTS

.clear_gauges
    LDX player_count
    DEX
.clear_gauges_loop
    STX zp_player
    LDA #0
    JSR gauge_step
    LDX zp_player
    LDA gauge_drawn,X
    BNE clear_gauges_loop      \ Until this gauge is empty.
    DEX
    BPL clear_gauges_loop
    RTS

\ gauge_step: move player zp_player's gauge one splat towards A splats.
\ Splat d of a gauge is drawn on lines BAR_BASE_LINE - 2d and the one above.
.gauge_step
    LDX zp_player
    CMP gauge_drawn,X
    BEQ gauge_step_done
    BCC gauge_step_lower
    JSR bar_bytes              \ Higher: draw the next splat in the ink.
    LDX zp_player
    LDA gauge_drawn,X
    INC gauge_drawn,X
    JMP gauge_step_draw
.gauge_step_lower
    DEC gauge_drawn,X          \ Lower: erase the top splat.
    LDA #0
    STA bar_left
    STA bar_right
    LDA gauge_drawn,X
.gauge_step_draw
    ASL A                      \ Its lines: BAR_BASE_LINE - 2d and above.
    ASSERT GAUGE_LINES_PER_SPLAT = 2
    STA bar_height             \ (borrowed)
    JSR bar_column
    LDA #BAR_BASE_LINE
    SEC
    SBC bar_height
    STA bar_line
    LDA bar_left
    LDX bar_right
    JSR draw_bar_line
    DEC bar_line
    LDA bar_left
    LDX bar_right
    JMP draw_bar_line          \ Tail call.
.gauge_step_done
    RTS

\ ----------------------------------------------------------------------------
\ set_hud_column -- bar_offset = byte column A * 8 (at most 632)
\ ----------------------------------------------------------------------------

.set_hud_column
    LDX #0
    STX bar_offset+1
    ASL A
    ROL bar_offset+1
    ASL A
    ROL bar_offset+1
    ASL A
    ROL bar_offset+1
    STA bar_offset
    RTS

\ ----------------------------------------------------------------------------
\ draw_digit -- draw digit A (0..9) of the HUD font at byte column
\ label_column, lines BAR_LABEL_LINE.., in label_colour
\ ----------------------------------------------------------------------------

.draw_digit
    STA label_digit         \ Glyph offset = digit * 5.
    ASL A
    ASL A
    CLC
    ADC label_digit
    STA label_digit
    LDA label_column
    JSR set_hud_column
    LDA #BAR_LABEL_LINE
    STA bar_line
    LDA #GLYPH_ROWS
    STA bar_height          \ (borrowed) rows still to draw
.draw_digit_row
    JSR hud_line_pointer
    LDX label_digit
    LDA hud_digits,X
    AND label_colour
    LDY #0
    STA (zp_screen_ptr),Y
    INC label_digit
    INC bar_line
    DEC bar_height
    BNE draw_digit_row
    RTS

\ draw_bar_line: write A (left byte) and X (right byte) of the bar on raster
\ line bar_line.
.draw_bar_line
    STA bar_byte
    JSR hud_line_pointer
    LDY #0
    LDA bar_byte
    STA (zp_screen_ptr),Y
    TXA
    LDY #8                     \ The next byte column.
    STA (zp_screen_ptr),Y
    RTS

\ hud_line_pointer: zp_screen_ptr = raster line bar_line in byte column
\ bar_offset / 8. Line y is at superpixel_row[y DIV 2] + (y AND 1).
\ Preserves X.
.hud_line_pointer
    LDA bar_line
    LSR A
    TAY
    LDA bar_line
    AND #1
    CLC
    ADC superpixel_row_lo,Y
    STA zp_screen_ptr
    LDA superpixel_row_hi,Y
    ADC #0
    STA zp_screen_ptr+1
    LDA zp_screen_ptr
    CLC
    ADC bar_offset
    STA zp_screen_ptr
    LDA zp_screen_ptr+1
    ADC bar_offset+1
    STA zp_screen_ptr+1
    RTS
