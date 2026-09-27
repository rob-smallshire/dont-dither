\ ============================================================================
\ game.asm -- the tick-driven simulation: input and movement
\
\ The game advances in ticks at 25 Hz, two 50 Hz video fields each. Every
\ tick (see main_loop in main.asm):
\   wait_for_tick    wait for two vertical syncs, then start the beam clock
\   read_inputs      fill player_input for every player from its control
\                    source (keyboard, scripted, or none)
\   update_players   refill, move and turn the players (the world update)
\   render_sprites   redraw the tanks that changed, racing the beam
\
\ The simulation depends only on the level and the ordered per-tick inputs,
\ never on timing, so it is deterministic and replayable. The Python model
\ in tools/dontdither/game.py must agree with it exactly.
\
\ Input byte (player_input): direction 0..7 (0 = N, clockwise) or
\ NO_DIRECTION in the low nibble, plus FIRE_BIT.
\
\ Requires: os.asm, zeropage.asm, game_data.asm, and the player state
\ defined by the program.
\ ============================================================================

\ ----------------------------------------------------------------------------
\ next_random -- step the pseudo-random generator
\
\ On exit:  A = random_state = 5 * random_state + 1 (mod 256); X, Y
\           preserved
\
\ A full-period linear congruential generator (every byte value comes up
\ once in 256 steps). Its low bits cycle quickly, so callers use its top
\ bits (random_direction). start seeds it from a VIA timer, and the
\ player-select screen steps it every field, so each game differs; tests
\ write a known state. Must match next_random in tools/dontdither/game.py.
\ ----------------------------------------------------------------------------

.next_random
    LDA random_state           \ 4 * state...
    ASL A
    ASL A
    CLC
    ADC random_state           \ ...+ state...
    CLC
    ADC #1                     \ ...+ 1, all mod 256.
    STA random_state
    RTS

\ random_direction: A = a random direction 0..7, the generator's top three
\ bits. X, Y preserved.
.random_direction
    JSR next_random
    LSR A
    LSR A
    LSR A
    LSR A
    LSR A
    RTS

\ ----------------------------------------------------------------------------
\ init_keyboard -- make the keys the game uses plain keys
\
\ By default the MOS uses the cursor keys and COPY for cursor editing, which
\ would move a text cursor on screen. *FX4,1 makes them return plain codes.
\ *FX229,1 makes ESCAPE an ordinary key rather than raising an Escape
\ condition, whose handling could call into the filing system (whose
\ workspace the game now occupies). The keyboard is otherwise left to the
\ MOS: the game reads keys directly with OSBYTE &81 and flushes the keyboard
\ buffer every tick.
\ ----------------------------------------------------------------------------

.init_keyboard
    LDA #4                     \ OSBYTE 4: cursor editing status.
    LDX #1                     \ 1 = cursor keys and COPY give ASCII codes.
    LDY #0
    JSR OSBYTE
    LDA #229                   \ OSBYTE 229: ESCAPE key status.
    LDX #1                     \ 1 = ESCAPE is an ordinary key.
    LDY #0
    JMP OSBYTE                 \ Tail call; OSBYTE returns to our caller.

\ ----------------------------------------------------------------------------
\ wait_for_tick -- wait for the vertical sync that starts the next tick
\
\ On exit:  A, X, Y corrupted
\
\ A tick is two fields. Rather than wait for two vertical syncs after the
\ tick's work (which would make a tick three fields whenever the work runs
\ into its second field), wait for vertical syncs until at least one and a
\ half fields have passed since this tick started, measured by the beam
\ timer that start_beam_timer restarted then. Ticks therefore start on
\ every second vertical sync as long as their work fits in two fields.
\ ----------------------------------------------------------------------------

TICK_MIN_UNITS = BEAM_FIELD_UNITS * 3 DIV 2   \ 1.5 fields, in beam units.

.wait_for_tick
    LDA #19                    \ OSBYTE 19 (*FX19): wait for vertical sync.
    JSR OSBYTE
    LDA #&FF                   \ Elapsed beam units since the tick started
    SEC                        \ = &FF - timer 2's high byte.
    SBC USER_VIA_T2_HIGH
    CMP #TICK_MIN_UNITS
    BCC wait_for_tick          \ Too soon: this is the tick's middle sync.
    RTS

\ ----------------------------------------------------------------------------
\ read_inputs -- set player_input for every player from its control source
\
\ On exit:  A, X, Y corrupted
\ ----------------------------------------------------------------------------

.read_inputs
    LDX #0
.read_inputs_loop
    CPX player_count
    BEQ read_inputs_flush
    LDA player_control,X
    CMP #CONTROL_SCRIPTED      \ Scripted input is written by someone else:
    BEQ read_inputs_next       \ leave it untouched.
    CMP #CONTROL_AI
    BNE read_inputs_not_ai
    STX zp_player              \ The computer decides.
    JSR ai_input
    LDX zp_player
    STA player_input,X
    JMP read_inputs_next
.read_inputs_not_ai
    CMP #CONTROL_NONE
    BNE read_inputs_keys
    LDA #NO_DIRECTION          \ No control: stationary, not firing.
    STA player_input,X
    JMP read_inputs_next

.read_inputs_keys
    \ The keyboard (CONTROL_KEYS): the slot's own layout. (CONTROL_JOYSTICK
    \ is reserved for when a joystick can be read.)
    STX zp_player
    JSR layout_offset          \ A = X * KEY_LAYOUT_BYTES.
    JSR scan_layout            \ A = input byte for this layout's keys.
    LDX zp_player
    STA player_input,X

.read_inputs_next
    INX
    JMP read_inputs_loop

.read_inputs_flush
    \ Throw away the characters the MOS has buffered from the keys we read,
    \ so nothing accumulates. OSBYTE 21 (*FX21,0): flush keyboard buffer.
    LDA #21
    LDX #0
    JMP OSBYTE

\ ----------------------------------------------------------------------------
\ layout_offset -- A = the offset of player slot X's layout in key_layouts
\
\ On exit:  A = X * KEY_LAYOUT_BYTES; X, Y preserved; zp_key_index corrupted
\ ----------------------------------------------------------------------------

.layout_offset
    STX zp_key_index           \ (borrowed: scan_layout sets it afresh)
    TXA
    ASL A                      \ 4X...
    ASL A
    CLC
    ADC zp_key_index           \ ...+ X.
    ASSERT KEY_LAYOUT_BYTES = 5
    RTS

\ ----------------------------------------------------------------------------
\ scan_layout -- read one keyboard layout's keys into an input byte
\
\ On entry:  A = offset of the layout in key_layouts
\ On exit:   A = input byte (direction | FIRE_BIT); X, Y corrupted
\
\ The five keys are scanned in the stored order fire, right, left, down, up.
\ OSBYTE &81 with a negative INKEY code returns X = &FF if the key is held,
\ else 0; ASL of that sets carry for a held key, and ROL shifts it into
\ zp_keys, so after five keys up is in bit 0 and fire in bit 4.
\ ----------------------------------------------------------------------------

.scan_layout
    STA zp_key_index
    CLC
    ADC #KEY_LAYOUT_BYTES
    STA zp_key_end
    LDA #0
    STA zp_keys
.scan_layout_loop
    LDY zp_key_index
    LDX key_layouts,Y          \ X = negative-INKEY code.
    LDY #&FF                   \ Y = &FF: scan a single key.
    LDA #&81                   \ OSBYTE &81: read key.
    JSR OSBYTE
    TXA                        \ &FF if held, 0 if not:
    ASL A                      \ carry = held.
    ROL zp_keys
    INC zp_key_index
    LDA zp_key_index
    CMP zp_key_end
    BNE scan_layout_loop

    LDA zp_keys                \ Direction from the four direction keys...
    AND #&0F
    TAX
    LDA key_direction,X
    STA zp_key_index           \ (borrowed to hold the direction)
    LDA zp_keys                \ ...plus fire from bit 4.
    AND #FIRE_BIT
    ORA zp_key_index
    RTS

\ ----------------------------------------------------------------------------
\ update_players -- refill, move and turn every player according to its input
\
\ On exit:  A, X, Y corrupted
\
\ Players move one after another; the first to move rotates with the tick
\ count (player_count is 2 or 4, so AND with player_count - 1 is MOD). For
\ each player:
\   1. The ground. With fire held it is FIRING_GROUND (normal speed, no
\      refill). With fire released it is the player's ground level (see
\      ground_level), and the reservoir refills by ground_refill for it, up
\      to RESERVOIR_SPLATS. A player's centre cells are under its own tank,
\      which has not moved yet, so reading them now is the same as reading
\      them before anyone moves.
\   2. With a direction: face that way, and add the speed for the ground and
\      direction (ground_speed_lo/whole) to the player's accumulator. The
\      carry plus the whole part is the number of steps, 0..2, each tried
\      with try_step. With no direction nothing moves.
\ ----------------------------------------------------------------------------

.update_players
    LDA player_count
    SEC
    SBC #1
    STA zp_player_mask         \ player_count - 1: 1 or 3.
    LDA tick_count
    AND zp_player_mask
    STA zp_update_index        \ First player to move this tick.
    LDA player_count
    STA zp_update_remaining

.update_players_loop
    LDX zp_update_index
    LDA player_in_tunnel,X     \ In a tunnel: only the tunnel's tick.
    BEQ update_players_in_play
    JSR tunnel_tick
    JMP update_players_next
.update_players_in_play
    LDA player_input,X         \ Fire held: move normally, no refill.
    AND #FIRE_BIT
    BEQ update_players_ground
    LDA #FIRING_GROUND
    STA move_ground
    ASSERT FIRING_GROUND <> 0
    BNE update_players_move    \ (Always.)

.update_players_ground
    JSR ground_level           \ A = ground level 0..4.
    STA move_ground
    TAY
    LDX zp_update_index
    LDA player_reservoir_fraction,X   \ Refill by the ground: a 16-bit add
    CLC                               \ of 1/256ths of a splat.
    ADC ground_refill,Y
    STA player_reservoir_fraction,X
    LDA player_reservoir,X
    ADC #0
    CMP #RESERVOIR_SPLATS      \ Full: exactly full.
    BCC update_players_refilled
    LDA #0
    STA player_reservoir_fraction,X
    LDA #RESERVOIR_SPLATS
.update_players_refilled
    STA player_reservoir,X

.update_players_move
    LDX zp_update_index
    LDA player_input,X
    AND #DIRECTION_MASK
    CMP #NO_DIRECTION
    BEQ update_players_next
    STA player_facing,X
    AND #1                     \ Speed index: ground * 2 + (direction AND 1).
    STA move_steps             \ (borrowed)
    LDA move_ground
    ASL A
    ORA move_steps
    TAY

    LDA player_accumulator,X   \ Add the speed: steps = carry + whole part.
    CLC
    ADC ground_speed_lo,Y
    STA player_accumulator,X
    LDA ground_speed_whole,Y
    ADC #0
    BEQ update_players_next
    STA move_steps
.update_players_step
    LDX zp_update_index
    JSR into_tunnel            \ Out through a mouth: into the tunnel, and
    BCC update_players_stepping    \ that is this tick's movement.
    LDA #1
    STA player_in_tunnel,X
    LDA #TUNNEL_TICKS
    STA player_tunnel_ticks,X
    JMP update_players_next
.update_players_stepping
    LDY player_facing,X        \ Y = direction.
    JSR try_step
    DEC move_steps
    BNE update_players_step

.update_players_next
    LDA zp_update_index        \ Next player, wrapping round.
    CLC
    ADC #1
    AND zp_player_mask
    STA zp_update_index
    DEC zp_update_remaining
    BEQ update_players_done
    JMP update_players_loop
.update_players_done
    RTS

\ ----------------------------------------------------------------------------
\ into_tunnel -- does player X's next step take it out through a mouth?
\
\ On entry:  X = player
\ On exit:   carry set if so; A, Y corrupted; X preserved
\
\ Only on a level with tunnels, and only an axial step: west from sx = 0
\ or east from sx = MAX_POSITION with sy within a mouth, or on four-player
\ levels north from sy = 0 or south from sy = MAX_POSITION with sx within
\ one (MOUTH_LOW..MOUTH_HIGH). Must match game.py's _into_tunnel.
\ ----------------------------------------------------------------------------

.into_tunnel
    LDA level_tunnels
    BEQ into_tunnel_no
    LDA player_facing,X
    LSR A                      \ Diagonal (odd): no. A = 0 N, 1 E, 2 S, 3 W.
    BCS into_tunnel_no
    CMP #1
    BEQ into_tunnel_east
    CMP #3
    BEQ into_tunnel_west
    LDY player_count           \ North and south: four-player levels only.
    CPY #4
    BNE into_tunnel_no
    CMP #0
    BEQ into_tunnel_north
    LDA player_sy,X            \ South: at the bottom edge?
    CMP #MAX_POSITION
    BNE into_tunnel_no
    BEQ into_tunnel_across_x   \ (Always.)
.into_tunnel_north
    LDA player_sy,X
    BNE into_tunnel_no
.into_tunnel_across_x
    LDA player_sx,X            \ Within the mouth across?
    JMP into_tunnel_across
.into_tunnel_east
    LDA player_sx,X
    CMP #MAX_POSITION
    BNE into_tunnel_no
    BEQ into_tunnel_across_y   \ (Always.)
.into_tunnel_west
    LDA player_sx,X
    BNE into_tunnel_no
.into_tunnel_across_y
    LDA player_sy,X
.into_tunnel_across
    CMP #MOUTH_LOW
    BCC into_tunnel_no
    CMP #MOUTH_HIGH + 1        \ Carry clear if within: flip it.
    BCS into_tunnel_no
    SEC
    RTS
.into_tunnel_no
    CLC
    RTS

\ ----------------------------------------------------------------------------
\ tunnel_tick -- a tick in a tunnel for player X
\
\ On entry:  X = player (also zp_update_index)
\ On exit:   A, X, Y corrupted
\
\ Count the ticks down; then come out of the opposite mouth -- sx = 0 for
\ a tank going east, MAX_POSITION going west; sy likewise going south or
\ north -- facing the same way, if the way is clear (position_clear);
\ otherwise try again next tick. Must match game.py's _tunnel.
\ ----------------------------------------------------------------------------

.tunnel_tick
    LDA player_tunnel_ticks,X
    BEQ tunnel_tick_out
    DEC player_tunnel_ticks,X
    BNE tunnel_tick_done
.tunnel_tick_out
    STX zp_step_player
    LDA player_sx,X
    STA zp_try_x
    LDA player_sy,X
    STA zp_try_y
    LDA player_facing,X        \ 0 N, 2 E, 4 S, 6 W.
    CMP #2
    BEQ tunnel_tick_east
    CMP #6
    BEQ tunnel_tick_west
    CMP #0
    BEQ tunnel_tick_north
    LDA #0                     \ Going south: out at the top.
    BEQ tunnel_tick_y          \ (Always.)
.tunnel_tick_north
    LDA #MAX_POSITION          \ Going north: out at the bottom.
.tunnel_tick_y
    STA zp_try_y
    JMP tunnel_tick_try
.tunnel_tick_east
    LDA #0                     \ Going east: out at the left.
    BEQ tunnel_tick_x          \ (Always.)
.tunnel_tick_west
    LDA #MAX_POSITION          \ Going west: out at the right.
.tunnel_tick_x
    STA zp_try_x
.tunnel_tick_try
    JSR position_clear
    BCC tunnel_tick_done       \ Blocked: wait.
    LDX zp_step_player
    LDA zp_try_x
    STA player_sx,X
    LDA zp_try_y
    STA player_sy,X
    LDA #0
    STA player_in_tunnel,X
.tunnel_tick_done
    RTS

\ ----------------------------------------------------------------------------
\ ground_level -- player zp_update_index's ground level
\
\ On exit:  A = the player's own ink quanta over the four centre superpixels
\           of its footprint, (sx + 2..3, sy + 2..3), DIV 4: 0..4; X, Y and
\           read_cell's zero page corrupted
\
\ Cells under the tank are read from its save buffer by read_cell. The four
\ centre cells are the only ones every player's rotation treats alike.
\ ground_index counts 3..0: bit 0 selects dx = 2 or 3, bit 1 dy = 2 or 3.
\ ----------------------------------------------------------------------------

.ground_level
    LDA #0
    STA ground_total
    LDA #3
    STA ground_index
.ground_level_cell
    LDX zp_update_index
    LDA ground_index           \ sx + 2 + (index AND 1).
    AND #1
    CLC
    ADC #2
    ADC player_sx,X
    STA zp_cell_x
    LDA ground_index           \ sy + 2 + (index DIV 2).
    LSR A
    CLC
    ADC #2
    ADC player_sy,X
    STA zp_cell_y
    JSR read_cell              \ A = the cell's state.
    ASL A                      \ Own quanta = state_counts[state * 4 + ink]
    ASL A                      \ (state * 4 < 256, low bits clear: ORA adds).
    LDX zp_update_index
    ORA player_ink,X
    TAX
    LDA state_counts,X
    CLC
    ADC ground_total
    STA ground_total
    DEC ground_index
    BPL ground_level_cell
    LDA ground_total           \ 0..16 DIV 4.
    LSR A
    LSR A
    RTS

\ ----------------------------------------------------------------------------
\ try_step -- step player X one superpixel in direction Y if the way is clear
\
\ On entry:  X = player, Y = direction
\ On exit:   player_sx/sy updated; A, X, Y corrupted
\
\ An axial step is taken if clear. A diagonal step is taken whole if clear;
\ otherwise, if exactly one of its single-axis steps is clear, that one is
\ taken; if both or neither are, the tank stays put. The rule is the same
\ under every rotation, so no facing is favoured.
\ ----------------------------------------------------------------------------

.try_step
    STX zp_step_player
    LDA direction_dx,Y
    STA zp_step_dx
    LDA direction_dy,Y
    STA zp_step_dy

    \ The whole step.
    LDA player_sx,X
    CLC
    ADC zp_step_dx
    STA zp_try_x
    LDA player_sy,X
    CLC
    ADC zp_step_dy
    STA zp_try_y
    JSR position_clear
    BCC try_step_diagonal
    LDX zp_step_player         \ Clear: take it.
    LDA zp_try_x
    STA player_sx,X
    LDA zp_try_y
    STA player_sy,X
    RTS

.try_step_diagonal
    \ Blocked. Only a diagonal step (both dx and dy non-zero) may slide.
    LDA zp_step_dx
    BEQ try_step_done
    LDA zp_step_dy
    BEQ try_step_done

    LDX zp_step_player         \ The x-only step.
    LDA player_sx,X
    CLC
    ADC zp_step_dx
    STA zp_try_x
    LDA player_sy,X
    STA zp_try_y
    JSR position_clear
    ROL zp_step_clear          \ Bit 0 := x-only step clear.

    LDX zp_step_player         \ The y-only step.
    LDA player_sx,X
    STA zp_try_x
    LDA player_sy,X
    CLC
    ADC zp_step_dy
    STA zp_try_y
    JSR position_clear
    ROL zp_step_clear          \ Bit 0 := y-only, bit 1 := x-only.

    LDX zp_step_player
    LDA zp_step_clear
    AND #3
    CMP #2                     \ x-only clear, y-only blocked: slide in x.
    BNE try_step_not_x
    LDA player_sx,X
    CLC
    ADC zp_step_dx
    STA player_sx,X
    RTS
.try_step_not_x
    CMP #1                     \ y-only clear, x-only blocked: slide in y.
    BNE try_step_done
    LDA player_sy,X
    CLC
    ADC zp_step_dy
    STA player_sy,X
.try_step_done
    RTS

\ ----------------------------------------------------------------------------
\ position_clear -- may player zp_step_player's footprint be at (zp_try_x,
\ zp_try_y)?
\
\ On exit:  carry set if clear, clear if blocked; A, X corrupted
\
\ Blocked if the footprint would leave the arena (either coordinate beyond
\ MAX_POSITION; a step left from 0 gives &FF, which the unsigned compare
\ also rejects), cover any part of a wall cell, or overlap another tank's
\ footprint where that tank is now (player_sx/sy) or was drawn at the start
\ of the tick (saved_sx/sy). Footprints overlap when both coordinate
\ differences are under SPRITE_FOOTPRINT.
\
\ Walls: a footprint at superpixel (x, y) covers wall cells x DIV 4 ..
\ (x + 5) DIV 4 across and y DIV 4 .. (y + 5) DIV 4 down: two or three each
\ way. Each is tested against the wall map with is_wall.
\ ----------------------------------------------------------------------------

.position_clear
    LDA zp_try_x
    CMP #MAX_POSITION + 1
    BCS position_clear_blocked
    LDA zp_try_y
    CMP #MAX_POSITION + 1
    BCS position_clear_blocked

    \ Wall cells covered: columns zp_wall_cx0..zp_wall_cx1, rows from
    \ zp_wall_cy (counting up) to zp_wall_cy1.
    LDA zp_try_x
    LSR A
    LSR A
    STA zp_wall_cx0
    LDA zp_try_x
    CLC
    ADC #SPRITE_FOOTPRINT - 1
    LSR A
    LSR A
    STA zp_wall_cx1
    LDA zp_try_y
    CLC
    ADC #SPRITE_FOOTPRINT - 1
    LSR A
    LSR A
    STA zp_wall_cy1
    LDA zp_try_y
    LSR A
    LSR A
    TAY                        \ Y = wall row.
.position_clear_wall_row
    LDX zp_wall_cx0            \ X = wall column.
.position_clear_wall_cell
    JSR is_wall                \ Preserves X and Y; Z clear for a wall.
    BNE position_clear_blocked
    CPX zp_wall_cx1
    INX
    BCC position_clear_wall_cell   \ Carry from CPX: X was below cx1.
    CPY zp_wall_cy1
    INY
    BCC position_clear_wall_row

    LDX #0
.position_clear_loop
    CPX player_count
    BEQ position_clear_yes
    CPX zp_step_player         \ A tank never blocks itself.
    BEQ position_clear_next
    LDA player_in_tunnel,X     \ (A tank in a tunnel is nowhere.)
    BNE position_clear_drawn
    LDA player_sx,X            \ Against where the other tank is now...
    STA zp_other_x
    LDA player_sy,X
    STA zp_other_y
    JSR footprints_overlap
    BCS position_clear_blocked
.position_clear_drawn
    LDA player_drawn,X         \ ...and where it was drawn, if it is.
    BEQ position_clear_next
    LDA saved_sx,X
    STA zp_other_x
    LDA saved_sy,X
    STA zp_other_y
    JSR footprints_overlap
    BCS position_clear_blocked
.position_clear_next
    INX
    JMP position_clear_loop
.position_clear_yes
    SEC
    RTS
.position_clear_blocked
    CLC
    RTS

\ ----------------------------------------------------------------------------
\ footprints_overlap -- do footprints at (zp_try_x, zp_try_y) and
\ (zp_other_x, zp_other_y) overlap?
\
\ On exit:  carry set if they overlap; A corrupted; X, Y preserved
\ Coordinates are 0..MAX_POSITION, so differences fit in a signed byte.
\ ----------------------------------------------------------------------------

.footprints_overlap
    LDA zp_try_x
    SEC
    SBC zp_other_x
    BPL footprints_overlap_x   \ |dx|: negate if negative.
    EOR #&FF
    CLC
    ADC #1
.footprints_overlap_x
    CMP #SPRITE_FOOTPRINT      \ Carry set if |dx| >= 6: apart.
    BCS footprints_apart
    LDA zp_try_y
    SEC
    SBC zp_other_y
    BPL footprints_overlap_y
    EOR #&FF
    CLC
    ADC #1
.footprints_overlap_y
    CMP #SPRITE_FOOTPRINT
    BCS footprints_apart
    SEC                        \ Both differences under 6: overlap.
    RTS
.footprints_apart
    CLC
    RTS
