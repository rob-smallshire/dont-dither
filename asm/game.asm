\ ============================================================================
\ game.asm -- the tick-driven simulation: input and movement
\
\ The game advances in ticks at 25 Hz, two 50 Hz video fields each. Every
\ tick (see main_loop in main.asm):
\   wait_for_tick    wait for two vertical syncs
\   read_inputs      fill player_input for every player from its control
\                    source (keyboard, scripted, or none)
\   hide_sprites     restore the bare arena
\   update_players   move and turn the players (the world update)
\   show_sprites     save backgrounds and draw the tanks
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
\ wait_for_tick -- wait for the start of the next tick (two vertical syncs)
\
\ On exit:  A, X, Y corrupted
\ ----------------------------------------------------------------------------

.wait_for_tick
    LDA #19                    \ OSBYTE 19 (*FX19): wait for vertical sync.
    JSR OSBYTE
    LDA #19                    \ Twice: 25 ticks per second.
    JMP OSBYTE

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
\ For a player with a direction: face that way; add the direction's speed
\ to the player's accumulator; if that carries, step one superpixel,
\ taking each axis only if it keeps the footprint in the arena (0 ..
\ MAX_POSITION), so a tank slides along the arena edge. With no direction
\ nothing changes.
\ ----------------------------------------------------------------------------

.update_players
    LDX #0
.update_players_loop
    CPX player_count
    BEQ update_players_done

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

    \ Step x: new = sx + dx, accepted if it is 0..MAX_POSITION. Moving left
    \ from 0 wraps to &FF, which the unsigned compare also rejects.
    LDA player_sx,X
    CLC
    ADC direction_dx,Y
    CMP #MAX_POSITION + 1
    BCS update_players_y
    STA player_sx,X
.update_players_y
    LDA player_sy,X            \ Step y likewise.
    CLC
    ADC direction_dy,Y
    CMP #MAX_POSITION + 1
    BCS update_players_next
    STA player_sy,X

.update_players_next
    INX
    JMP update_players_loop
.update_players_done
    RTS
