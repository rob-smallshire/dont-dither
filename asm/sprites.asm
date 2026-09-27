\ ============================================================================
\ sprites.asm -- drawing player tanks over the arena with save-under
\
\ Each player's tank is a 6x6-superpixel (12x12-pixel) sprite at superpixel
\ (player_sx, player_sy), the top-left of its footprint. Sprites are drawn
\ directly into screen memory, so they must never be mistaken for territory:
\ before a sprite is drawn, the screen bytes beneath it are saved, and before
\ the world is next updated every sprite is removed by restoring those bytes.
\
\ Tanks are solid, so their pictures never overlap, and the movement rules
\ keep each tank's old and new footprints clear of every other tank's (see
\ position_clear in game.asm). So each tank can be redrawn on its own:
\ render_sprites redraws just the tanks that moved or turned, each by
\ restore (old background), save (new background), draw. The world (paint)
\ can then be updated without hiding the tanks: a cell under a tank lives in
\ that tank's save buffer until the tank moves off it.
\
\ Flicker: while a tank is being redrawn it is briefly missing from the
\ screen. render_sprites races the beam: each redraw waits until the video
\ beam is somewhere it will not reach the tank before the redraw is done,
\ so the gap is never scanned out. The beam position is timed from vertical
\ sync by the User VIA's timer 2 (see start_beam_timer).
\
\ show_sprites (save and draw everything) and hide_sprites (restore
\ everything, in reverse order) remain for drawing a level's first frame
\ and for clearing the tanks away.
\
\ Screen footprint: a sprite covers raster lines 2*sy .. 2*sy+11 and pixel
\ columns 2*sx .. 2*sx+11. For even sx it starts at the left of screen byte
\ column sx DIV 2; for odd sx, two pixels in. Either way four byte columns
\ are saved, restored and drawn (the unused column of an even-aligned frame
\ has an all-zero mask). Each 12-line block is walked as 6 superpixel rows of
\ 2 raster lines x 4 bytes = 8 bytes; sprite_line_offsets gives each byte's
\ offset from the row's top-line address, so one index register (X) walks
\ the frame, the save buffer and the offsets together, while Y holds the
\ screen offset for (zp_screen_ptr),Y.
\
\ Self-modifying code: the absolute addresses of the frame planes and of the
\ player's save buffer are patched into the loops' LDA/STA abs,X operands
\ before each loop runs (marked PATCHED). That keeps the inner loops to
\ abs,X and (zp),Y accesses with no extra pointer arithmetic.
\
\ Colour: frames hold a mask plane (ones where opaque) and a select plane
\ (ones where the player's ink shows, else the contrast ink). The colour of
\ a byte is  contrast EOR ((contrast EOR ink) AND select),  merged into the
\ screen with  screen EOR ((screen EOR colour) AND mask).
\
\ Requires: zeropage.asm, screen_tables.asm, sprite_data.asm, level_format.asm,
\ and the player state and sprite_save_buffers defined by the program.
\ ============================================================================

MAX_PLAYERS = 4

\ ----------------------------------------------------------------------------
\ place_players -- set up the players for the current level
\
\ On entry:  zp_level_ptr = the level's bytecode (select_level)
\ On exit:   player_count and each player's position, facing and ink set;
\            control sources set (for each human in the session, its
\            keyboard layout; the computer otherwise); inputs, accumulators
\            and the tick count cleared; no sprites shown
\            A, X, Y corrupted
\
\ The level stores player 1's start (its START command). Each further player
\ starts where the previous one would be after the level's symmetry step --
\ one quarter turn (ROT4) or two (ROT2) about the arena centre:
\     (sx, sy) -> (MAX_POSITION - sy, sx), facing + 2 (per quarter turn)
\ so the starts share the level's symmetry. Player k plays in ink k.
\ ----------------------------------------------------------------------------

.place_players
    LDY #LEVEL_HEADER_SYMMETRY
    LDA (zp_level_ptr),Y
    STA zp_symmetry_step       \ 1 (ROT4, four players) or 2 (ROT2, two).
    LDX #4
    CMP #1
    BEQ place_players_count
    LDX #2
.place_players_count
    STX player_count

    LDY #LEVEL_START_SX        \ Player 1's start.
    LDA (zp_level_ptr),Y
    STA zp_try_x               \ (borrowed: the start being placed)
    LDY #LEVEL_START_SY
    LDA (zp_level_ptr),Y
    STA zp_try_y
    LDY #LEVEL_START_FACING
    LDA (zp_level_ptr),Y
    STA zp_other_x

    LDX #0                     \ X = player slot.
.place_players_loop
    LDA zp_try_x
    STA player_sx,X
    LDA zp_try_y
    STA player_sy,X
    LDA zp_other_x
    STA player_facing,X
    STA ai_direction,X         \ An AI starts heading the way it faces.
    TXA
    STA player_ink,X           \ Player k plays in ink k...
    STA player_last_victim,X   \ ...and its round-robin starts after it.

    LDA player_bits,X          \ A human in this session, or the computer?
    AND session_humans
    BEQ place_players_ai
    LDA session_controls,X     \ The control the player joined with.
    JMP place_players_control
.place_players_ai
    CPX player_count           \ A playing AI (not an unused slot) faces and
    BCS place_players_ai_control   \ heads a random way, so identical AIs do
    JSR random_direction       \ not move in step. (X preserved.)
    STA player_facing,X
    STA ai_direction,X
.place_players_ai_control
    LDA #CONTROL_AI
.place_players_control
    STA player_control,X
    LDA #NO_DIRECTION
    STA player_input,X
    STA ai_last_input,X
    LDA #0
    STA player_accumulator,X
    STA player_cooldown,X
    STA player_variant,X
    STA player_repaint,X
    STA player_reservoir_fraction,X
    STA ai_refilling,X
    STA gauge_drawn,X          \ (clear_hud has erased the gauges)
    LDA #RESERVOIR_SPLATS      \ A full reservoir of ink.
    STA player_reservoir,X

    LDY zp_symmetry_step       \ The next player's start: rotate by the
.place_players_turn            \ symmetry step.
    LDA #MAX_POSITION
    SEC
    SBC zp_try_y               \ New sx = MAX_POSITION - sy...
    PHA
    LDA zp_try_x               \ ...new sy = sx.
    STA zp_try_y
    PLA
    STA zp_try_x
    LDA zp_other_x
    CLC
    ADC #2
    AND #7
    STA zp_other_x
    DEY
    BNE place_players_turn

    INX
    CPX #MAX_PLAYERS           \ (All four slots are set; only player_count
    BNE place_players_loop     \ of them play.)

    LDA #0                     \ Nothing is on screen to restore yet.
    STA sprites_shown
    STA tick_count
    STA tick_count+1
    RTS


\ ----------------------------------------------------------------------------
\ show_sprites -- save the background under, then draw, each player in order
\ hide_sprites -- restore every player's background in reverse order
\
\ On exit:  A, X, Y corrupted
\ ----------------------------------------------------------------------------

.show_sprites
    LDX #0
.show_sprites_loop
    CPX player_count
    BEQ show_sprites_done
    STX zp_player
    JSR save_under
    LDX zp_player
    JSR prepare_sprite
    JSR draw_sprite
    LDX zp_player
    INX
    JMP show_sprites_loop
.show_sprites_done
    LDA #1
    STA sprites_shown
    RTS

.hide_sprites
    LDA sprites_shown          \ Nothing to do if no sprites are on screen.
    BEQ hide_sprites_done
    LDX player_count           \ X counts down from player_count - 1 to 0.
.hide_sprites_loop
    DEX
    BMI hide_sprites_hidden    \ Stop once X wraps below 0.
    STX zp_player
    JSR restore_under
    LDX zp_player
    JMP hide_sprites_loop
.hide_sprites_hidden
    LDA #0
    STA sprites_shown
.hide_sprites_done
    RTS

\ ----------------------------------------------------------------------------
\ Beam timing
\
\ MODE 1 has 312 raster lines per field: visible lines 0..255, then vertical
\ sync starting at line 272 (CRTC R7 = 34 character rows). The User VIA's
\ timer 2 counts down at 1 MHz; started at &FFFF just after vertical sync,
\ its high byte falls by one every 256 us, which is 4 raster lines (64 us
\ per line). We work in these 4-line units: a field is 78 units, the
\ visible area units 0..63, and vertical sync is unit 68. So the beam is at
\ unit (68 + elapsed units) MOD 78.
\ ----------------------------------------------------------------------------

USER_VIA_T2_LOW  = &FE68
USER_VIA_T2_HIGH = &FE69
USER_VIA_ACR     = &FE6B
USER_VIA_IER     = &FE6E

BEAM_FIELD_UNITS = 78          \ 312 lines / 4.
BEAM_VSYNC_UNIT  = 68          \ Line 272 / 4.
BEAM_REDRAW_UNITS = 14         \ Time for one restore + save + draw (about
                               \ 6,000 cycles = 3,000 us = 12 units) with a
                               \ margin.

\ ----------------------------------------------------------------------------
\ init_beam_timer -- set up the User VIA's timer 2 as a free-running clock
\ start_beam_timer -- restart it; call just after vertical sync
\ ----------------------------------------------------------------------------

.init_beam_timer
    LDA USER_VIA_ACR           \ ACR bit 5 = 0: timer 2 counts clock
    AND #&DF                   \ cycles (one-shot mode).
    STA USER_VIA_ACR
    LDA #&20                   \ IER bit 7 = 0 with bit 5: disable timer 2
    STA USER_VIA_IER           \ interrupts; we only read the counter.
    \ Fall through to start it.
.start_beam_timer
    LDA #&FF
    STA USER_VIA_T2_LOW        \ Low byte of the count (latched)...
    STA USER_VIA_T2_HIGH       \ ...writing the high byte loads and starts.
    RTS

\ ----------------------------------------------------------------------------
\ beam_unit -- where is the beam now?
\
\ On exit:  A = beam position in 4-line units, 0..77 (0 = top visible line)
\ ----------------------------------------------------------------------------

.beam_unit
    LDA #&FF                   \ Elapsed units = &FF - count high byte.
    SEC
    SBC USER_VIA_T2_HIGH
    CLC
    ADC #BEAM_VSYNC_UNIT       \ Units since line 0 of the current field...
.beam_unit_wrap
    CMP #BEAM_FIELD_UNITS      \ ...reduced MOD 78 (a tick is at most two
    BCC beam_unit_done         \ fields, so this loops at most three times).
    SBC #BEAM_FIELD_UNITS      \ Carry is set here, as SBC needs.
    JMP beam_unit_wrap
.beam_unit_done
    RTS

\ ----------------------------------------------------------------------------
\ wait_for_beam -- wait until a redraw of rows zp_region_top..bottom is safe
\
\ On entry:  zp_region_top, zp_region_bottom = the rows the redraw touches,
\            in 4-line beam units
\ On exit:   A corrupted
\
\ Safe when the beam is not inside the region and will not reach its top
\ within BEAM_REDRAW_UNITS: distance to top = (top - beam) MOD 78.
\ ----------------------------------------------------------------------------

.wait_for_beam
    JSR beam_unit
    STA zp_beam
    CMP zp_region_top          \ Inside the region (top <= beam <= bottom)?
    BCC wait_for_beam_outside
    LDA zp_region_bottom
    CMP zp_beam
    BCS wait_for_beam          \ Yes: wait.
.wait_for_beam_outside
    LDA zp_region_top          \ Distance until the beam reaches the top.
    SEC
    SBC zp_beam
    BCS wait_for_beam_distance
    ADC #BEAM_FIELD_UNITS      \ (top - beam) was negative: wrap round.
.wait_for_beam_distance
    CMP #BEAM_REDRAW_UNITS + 1
    BCC wait_for_beam          \ Too close: wait.
    RTS

\ ----------------------------------------------------------------------------
\ render_sprites -- redraw every tank that moved or turned, racing the beam
\
\ On exit:  A, X, Y corrupted
\
\ Each such tank is restored from its save buffer, then saved and drawn at
\ its new position, once wait_for_beam says the rows covering both its old
\ and new footprints are safe. Tanks are redrawn in order of how low on
\ screen they reach, so the beam, travelling down, is passed as rarely as
\ possible.
\ ----------------------------------------------------------------------------

.render_sprites
    \ Collect the tanks needing a redraw, with each one's lowest row (the
    \ larger of old and new sy) as its sort key.
    LDY #0                     \ Y = number collected.
    LDX #0
.render_collect
    CPX player_count
    BEQ render_sort
    LDA player_sx,X
    CMP saved_sx,X
    BNE render_collect_add
    LDA player_sy,X
    CMP saved_sy,X
    BNE render_collect_add
    LDA player_facing,X
    CMP drawn_facing,X
    BNE render_collect_add
    LDA player_repaint,X       \ Or the arena under it was painted.
    BEQ render_collect_next
.render_collect_add
    LDA #0                     \ The redraw will show the paint.
    STA player_repaint,X
    TXA
    STA render_list,Y
    LDA player_sy,X
    CMP saved_sy,X
    BCS render_collect_key     \ A = max(player_sy, saved_sy).
    LDA saved_sy,X
.render_collect_key
    STA render_key,Y
    INY
.render_collect_next
    INX
    JMP render_collect

.render_sort
    STY render_count
    \ Sort the (at most four) entries by key: a simple exchange sort.
    LDX #0
.render_sort_outer
    TXA
    CLC
    ADC #1
    CMP render_count
    BCS render_draw            \ X reached the last entry.
    TAY
.render_sort_inner
    CPY render_count
    BEQ render_sort_next
    LDA render_key,Y
    CMP render_key,X
    BCS render_sort_no_swap
    PHA                        \ Swap entries X and Y.
    LDA render_key,X
    STA render_key,Y
    PLA
    STA render_key,X
    LDA render_list,Y
    PHA
    LDA render_list,X
    STA render_list,Y
    PLA
    STA render_list,X
.render_sort_no_swap
    INY
    JMP render_sort_inner
.render_sort_next
    INX
    JMP render_sort_outer

.render_draw
    LDA #0
    STA zp_render_index
.render_draw_loop
    LDX zp_render_index
    CPX render_count
    BEQ render_done
    LDA render_list,X
    TAX
    STX zp_player

    \ Region: from the higher of old and new top rows to the lower of the
    \ bottoms, in beam units. Superpixel row sy starts at raster line 2*sy,
    \ unit sy DIV 2; a footprint ends 12 lines lower. One unit of margin
    \ each side covers the timer's granularity.
    LDA player_sy,X
    CMP saved_sy,X
    BCC render_top
    LDA saved_sy,X             \ A = min(player_sy, saved_sy).
.render_top
    LSR A
    BEQ render_top_store
    SEC
    SBC #1
.render_top_store
    STA zp_region_top
    LDX zp_render_index
    LDA render_key,X           \ max(sy): bottom = (2*sy + 12) DIV 4 + 1
    CLC                        \ = (sy + 6) DIV 2 + 1, plus 1 margin.
    ADC #6
    LSR A
    CLC
    ADC #2
    STA zp_region_bottom

    LDX zp_player              \ The frame first (shifting it takes time),
    JSR prepare_sprite         \ then wait for the beam to pass.
    JSR wait_for_beam
    LDX zp_player
    JSR restore_under
    LDX zp_player
    JSR save_under
    LDX zp_player
    JSR draw_sprite

    INC zp_render_index
    JMP render_draw_loop
.render_done
    RTS

\ ----------------------------------------------------------------------------
\ locate_sprite -- prepare to walk a sprite's screen footprint
\
\ On entry:  A = sx, Y = sy of the footprint's top-left superpixel
\ On exit:   zp_sprite_column = (sx DIV 2) * 8, the offset of its first byte
\            column; zp_sprite_row_sy = sy
\            A corrupted
\ ----------------------------------------------------------------------------

.locate_sprite
    STY zp_sprite_row_sy
    AND #&FE                   \ (sx AND &FE) * 4 = (sx DIV 2) * 8, up to
    ASL A                      \ 488, so the second ASL may carry into a
    ASL A                      \ ninth bit, which ROL moves into the high
    STA zp_sprite_column       \ byte.
    LDA #0
    ROL A
    STA zp_sprite_column+1
    RTS

\ ----------------------------------------------------------------------------
\ sprite_row_pointer -- point zp_screen_ptr at the next superpixel row
\
\ On entry:  zp_sprite_row_sy = the superpixel row; zp_sprite_column set
\ On exit:   zp_screen_ptr = address of that row's top raster line in the
\            sprite's first byte column; zp_sprite_row_sy advanced by one
\            A, Y corrupted; X preserved
\ ----------------------------------------------------------------------------

.sprite_row_pointer
    LDY zp_sprite_row_sy
    CLC
    LDA superpixel_row_lo,Y
    ADC zp_sprite_column
    STA zp_screen_ptr
    LDA superpixel_row_hi,Y
    ADC zp_sprite_column+1
    STA zp_screen_ptr+1
    INC zp_sprite_row_sy
    RTS

\ ----------------------------------------------------------------------------
\ point_at_save_buffer -- patch a loop operand to player X's save buffer
\
\ On entry:  X = player
\ On exit:   A = low byte, zp_sprite_tmp = high byte of
\            sprite_save_buffers + X * SPRITE_FRAME_BYTES (48)
\ ----------------------------------------------------------------------------

.point_at_save_buffer
    TXA                        \ X * 48 = X * 32 + X * 16 (at most 144).
    ASL A
    ASL A
    ASL A
    ASL A
    STA zp_sprite_tmp          \ X * 16
    ASL A                      \ X * 32
    CLC
    ADC zp_sprite_tmp
    CLC
    ADC #LO(sprite_save_buffers)
    PHA
    LDA #HI(sprite_save_buffers)
    ADC #0                     \ Carry from the low byte.
    STA zp_sprite_tmp
    PLA
    RTS

\ ----------------------------------------------------------------------------
\ save_under -- save the screen bytes under player X's sprite
\
\ On entry:  X = player
\ On exit:   the 48 bytes saved in the player's buffer; saved_sx/saved_sy
\            record where they came from; A, X, Y corrupted
\ ----------------------------------------------------------------------------

.save_under
    JSR point_at_save_buffer
    STA save_under_store+1     \ PATCHED: STA buffer,X below.
    LDA zp_sprite_tmp
    STA save_under_store+2

    LDA player_sx,X            \ Remember where this background came from,
    STA saved_sx,X             \ for restore_under.
    LDY player_sy,X
    TYA
    STA saved_sy,X
    LDA player_sx,X
    JSR locate_sprite

    LDX #0                     \ X = frame byte 0..47.
.save_under_row
    JSR sprite_row_pointer
.save_under_byte
    LDY sprite_line_offsets,X
    LDA (zp_screen_ptr),Y
.save_under_store
    STA &FFFF,X                \ PATCHED to the player's save buffer.
    INX
    TXA
    AND #7                     \ Eight bytes per superpixel row.
    BNE save_under_byte
    CPX #SPRITE_FRAME_BYTES
    BNE save_under_row
    RTS

\ ----------------------------------------------------------------------------
\ restore_under -- put back the screen bytes saved under player X's sprite
\
\ On entry:  X = player (whose background was saved by save_under)
\ On exit:   A, X, Y corrupted
\
\ Only the bits inside the tank's footprint are restored, merged under the
\ footprint mask for the saved alignment:
\     screen EOR ((screen EOR saved) AND footprint_mask)
\ A tank's four saved byte columns can include half a byte column of a
\ neighbouring tank touching it side by side; masking leaves that alone.
\ ----------------------------------------------------------------------------

.restore_under
    JSR point_at_save_buffer
    STA restore_under_load+1   \ PATCHED: LDA buffer,X below.
    LDA zp_sprite_tmp
    STA restore_under_load+2

    LDA saved_sx,X             \ Footprint mask for the saved alignment.
    AND #1
    TAY
    LDA footprint_mask_lo,Y
    STA restore_under_mask+1   \ PATCHED: AND mask,X below.
    LDA footprint_mask_hi,Y
    STA restore_under_mask+2

    LDY saved_sy,X             \ Restore where the background was saved,
    LDA saved_sx,X             \ wherever the player has moved to since.
    JSR locate_sprite

    LDX #0
.restore_under_row
    JSR sprite_row_pointer
.restore_under_byte
    LDY sprite_line_offsets,X
.restore_under_load
    LDA &FFFF,X                \ PATCHED: the player's save buffer.
    EOR (zp_screen_ptr),Y
.restore_under_mask
    AND &FFFF,X                \ PATCHED: the footprint mask.
    EOR (zp_screen_ptr),Y
    STA (zp_screen_ptr),Y
    INX
    TXA
    AND #7
    BNE restore_under_byte
    CPX #SPRITE_FRAME_BYTES
    BNE restore_under_row
    RTS

.footprint_mask_lo
    EQUB LO(footprint_mask_0), LO(footprint_mask_1)
.footprint_mask_hi
    EQUB HI(footprint_mask_0), HI(footprint_mask_1)

\ ----------------------------------------------------------------------------
\ prepare_sprite -- make player X's frame ready for draw_sprite
\
\ On entry:  X = player
\ On exit:   draw_sprite's plane operands point at the frame; X preserved;
\            A, Y, zp_sprite_tmp/xor/contrast and zp_shift_* corrupted
\
\ Frames are stored for even sx only. For odd sx the sprite starts a
\ superpixel (2 pixels) into its first byte, so the frame is shifted right
\ by that into sprite_shifted_mask/_select: each byte's pixels 0-1 move to
\ 2-3, and the byte to its left gives its pixels 2-3 to this one's 0-1:
\     shifted = ((byte >> 2) AND &33) OR ((left << 2) AND &CC)
\ A stored frame's fourth byte column is empty, so each raster line's
\ shifted bytes come from its first three. That gives exactly the odd
\ frame (tests check), for about 2000 cycles -- done here, before
\ render_sprites waits for the beam, so the timed redraw is unchanged.
\ ----------------------------------------------------------------------------

.prepare_sprite
    LDY player_facing,X
    LDA player_sx,X
    LSR A
    BCS prepare_sprite_odd
    LDA sprite_select_lo,Y     \ Even: the stored frame as it is.
    STA draw_sprite_select+1   \ PATCHED: LDA select,X in draw_sprite.
    LDA sprite_select_hi,Y
    STA draw_sprite_select+2
    LDA sprite_mask_lo,Y
    STA draw_sprite_mask+1     \ PATCHED: AND mask,X in draw_sprite.
    LDA sprite_mask_hi,Y
    STA draw_sprite_mask+2
    RTS

.prepare_sprite_odd
    TXA
    PHA
    LDA sprite_select_lo,Y     \ Odd: shift the select plane...
    STA zp_shift_source
    LDA sprite_select_hi,Y
    STA zp_shift_source+1
    LDA #LO(sprite_shifted_select)
    STA zp_shift_dest
    LDA #HI(sprite_shifted_select)
    STA zp_shift_dest+1
    TYA
    PHA
    JSR shift_plane
    PLA
    TAY
    LDA sprite_mask_lo,Y       \ ...and the mask plane...
    STA zp_shift_source
    LDA sprite_mask_hi,Y
    STA zp_shift_source+1
    LDA #LO(sprite_shifted_mask)
    STA zp_shift_dest
    LDA #HI(sprite_shifted_mask)
    STA zp_shift_dest+1
    JSR shift_plane
    LDA #LO(sprite_shifted_select)   \ ...and draw those.
    STA draw_sprite_select+1
    LDA #HI(sprite_shifted_select)
    STA draw_sprite_select+2
    LDA #LO(sprite_shifted_mask)
    STA draw_sprite_mask+1
    LDA #HI(sprite_shifted_mask)
    STA draw_sprite_mask+2
    PLA
    TAX
    RTS

\ shift_plane: (zp_shift_dest) = (zp_shift_source) shifted a superpixel
\ right, raster line by raster line (4 bytes each; see prepare_sprite).
\ zp_sprite_tmp and zp_sprite_xor hold the line's source bytes as they
\ are passed; zp_sprite_contrast is a working byte.
.shift_plane
    LDY #0
.shift_plane_line
    LDA (zp_shift_source),Y    \ Byte 0: its own pixels 0-1, moved right.
    STA zp_sprite_tmp
    LSR A
    LSR A
    AND #&33
    STA (zp_shift_dest),Y
    INY
    LDA (zp_shift_source),Y    \ Byte 1: its own, moved right, and byte
    STA zp_sprite_xor          \ 0's pixels 2-3.
    LSR A
    LSR A
    AND #&33
    STA zp_sprite_contrast
    LDA zp_sprite_tmp
    ASL A
    ASL A
    AND #&CC
    ORA zp_sprite_contrast
    STA (zp_shift_dest),Y
    INY
    LDA (zp_shift_source),Y    \ Byte 2: likewise, with byte 1's.
    STA zp_sprite_tmp
    LSR A
    LSR A
    AND #&33
    STA zp_sprite_contrast
    LDA zp_sprite_xor
    ASL A
    ASL A
    AND #&CC
    ORA zp_sprite_contrast
    STA (zp_shift_dest),Y
    INY
    LDA zp_sprite_tmp          \ Byte 3: byte 2's pixels 2-3 only.
    ASL A
    ASL A
    AND #&CC
    STA (zp_shift_dest),Y
    INY
    CPY #SPRITE_FRAME_BYTES
    BNE shift_plane_line
    RTS

\ ----------------------------------------------------------------------------
\ draw_sprite -- draw player X's tank at its position and facing
\
\ On entry:  X = player; its frame made ready by prepare_sprite
\ On exit:   A, X, Y corrupted
\ ----------------------------------------------------------------------------

.draw_sprite
    LDA player_facing,X        \ Remember the facing drawn, so render_sprites
    STA drawn_facing,X         \ can tell when the tank turns.

    \ Colours: zp_sprite_contrast = contrast ink byte; zp_sprite_xor =
    \ contrast EOR player ink, so contrast EOR (xor AND select) picks the
    \ player's ink where select is set.
    LDY player_ink,X
    LDA contrast_ink_bytes,Y
    STA zp_sprite_contrast
    EOR ink_bytes,Y
    STA zp_sprite_xor

    LDY player_sy,X
    LDA player_sx,X
    JSR locate_sprite

    LDX #0
.draw_sprite_row
    JSR sprite_row_pointer
.draw_sprite_byte
    LDY sprite_line_offsets,X
.draw_sprite_select
    LDA &FFFF,X                \ PATCHED: select plane.
    AND zp_sprite_xor          \ Colour byte: player ink where selected,
    EOR zp_sprite_contrast     \ contrast ink elsewhere.
    EOR (zp_screen_ptr),Y      \ Merge under the mask:
.draw_sprite_mask
    AND &FFFF,X                \ PATCHED: mask plane.
    EOR (zp_screen_ptr),Y      \ screen EOR ((screen EOR colour) AND mask).
    STA (zp_screen_ptr),Y
    INX
    TXA
    AND #7
    BNE draw_sprite_byte
    CPX #SPRITE_FRAME_BYTES
    BNE draw_sprite_row
    RTS
