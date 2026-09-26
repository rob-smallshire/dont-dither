\ ============================================================================
\ game.asm -- the tick-driven simulation: input and movement
\
\ The game advances in ticks at 25 Hz, two 50 Hz video fields each. Every
\ tick (see main_loop in main.asm):
\   wait_for_tick    wait for two vertical syncs, then start the beam clock
\   read_inputs      fill player_input for every player from its control
\                    source (keyboard, scripted, or none)
\   update_players   move and turn the players (the world update)
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
\ init_keyboard -- make the keys the game uses plain keys
\
\ By default the MOS uses the cursor keys and COPY for cursor editing, which
\ would move a text cursor on screen. *FX4,1 makes them return plain codes.
\ The keyboard is otherwise left to the MOS: the game reads keys directly
\ with OSBYTE &81 and flushes the keyboard buffer every tick.
\ ----------------------------------------------------------------------------

.init_keyboard
    LDA #4                     \ OSBYTE 4: cursor editing status.
    LDX #1                     \ 1 = cursor keys and COPY give ASCII codes.
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
    CMP #CONTROL_NONE
    BNE read_inputs_keys
    LDA #NO_DIRECTION          \ No control: stationary, not firing.
    STA player_input,X
    JMP read_inputs_next

.read_inputs_keys
    \ Keyboard layout A (1) or B (2): the layout's codes start at
    \ (control - 1) * KEY_LAYOUT_BYTES in key_layouts.
    STX zp_player
    SEC
    SBC #CONTROL_KEYS_A
    TAY                        \ Y = layout number 0 or 1.
    LDA #0
.read_inputs_layout_offset
    DEY                        \ A += KEY_LAYOUT_BYTES for each layout
    BMI read_inputs_scan       \ before this one.
    CLC
    ADC #KEY_LAYOUT_BYTES
    JMP read_inputs_layout_offset
.read_inputs_scan
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
\ update_players -- move and turn every player according to its input
\
\ On exit:  A, X, Y corrupted
\
\ Players move one after another; the first to move rotates with the tick
\ count (player_count is 2 or 4, so AND with player_count - 1 is MOD). For a
\ player with a direction: face that way; add the direction's speed to the
\ player's accumulator; if that carries, try to step (see try_step). With
\ no direction nothing changes.
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
    LDA player_input,X
    AND #DIRECTION_MASK
    CMP #NO_DIRECTION
    BEQ update_players_next
    STA player_facing,X
    TAY                        \ Y = direction.

    LDA player_accumulator,X   \ Add the speed; carry means a step is due.
    CLC
    ADC direction_speed,Y
    STA player_accumulator,X
    BCC update_players_next
    JSR try_step

.update_players_next
    LDA zp_update_index        \ Next player, wrapping round.
    CLC
    ADC #1
    AND zp_player_mask
    STA zp_update_index
    DEC zp_update_remaining
    BNE update_players_loop
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
\ also rejects) or overlap another tank's footprint where that tank is now
\ (player_sx/sy) or was drawn at the start of the tick (saved_sx/sy).
\ Footprints overlap when both coordinate differences are under
\ SPRITE_FOOTPRINT.
\ ----------------------------------------------------------------------------

.position_clear
    LDA zp_try_x
    CMP #MAX_POSITION + 1
    BCS position_clear_blocked
    LDA zp_try_y
    CMP #MAX_POSITION + 1
    BCS position_clear_blocked

    LDX #0
.position_clear_loop
    CPX player_count
    BEQ position_clear_yes
    CPX zp_step_player         \ A tank never blocks itself.
    BEQ position_clear_next
    LDA player_sx,X            \ Against where the other tank is now...
    STA zp_other_x
    LDA player_sy,X
    STA zp_other_y
    JSR footprints_overlap
    BCS position_clear_blocked
    LDA saved_sx,X             \ ...and where it was drawn.
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
