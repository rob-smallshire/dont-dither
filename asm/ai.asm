\ ============================================================================
\ ai.asm -- computer players
\
\ An AI produces exactly the input byte a keyboard player does -- a direction
\ (or none) plus fire -- which the rest of the game treats identically. It is
\ fully deterministic, and must match tools/dontdither/ai.py decision for
\ decision.
\
\ Each AI re-decides every AI_PERIOD ticks, when (tick_count + player) MOD
\ AI_PERIOD = 0, so AIs take turns thinking; in between it repeats its last
\ input.
\
\ Deciding: for each of the 8 directions, sample AI_SAMPLES cells ahead of
\ the tank (stored for E and NE, rotated for other facings like splats). A
\ cell is worth 8 minus the AI's own ink count there, or AI_WALL_VALUE if it
\ is a wall or outside the arena; a direction scores the sum. Starting from
\ the current direction (which gets AI_PERSISTENCE extra) and going
\ clockwise, the strictly best score wins. If a step that way is blocked,
\ the direction is ruled out and the choice made again; if all are ruled
\ out the AI stays put. It fires if the chosen direction's own score is at
\ least AI_FIRE_SCORE.
\
\ Requires: zeropage.asm, game.asm (position_clear), paint.asm (read_cell),
\ walls.asm (is_wall), and the generated game_data.asm and paint_data.asm.
\ ============================================================================

\ ----------------------------------------------------------------------------
\ ai_input -- the input byte of AI player X for this tick
\
\ On entry:  X = player
\ On exit:   A = input byte (also kept in ai_last_input); X, Y corrupted
\ ----------------------------------------------------------------------------

.ai_input
    STX zp_ai_player
    TXA                        \ Time to think? (tick_count + player) MOD 4.
    CLC
    ADC tick_count
    AND #AI_PERIOD - 1
    BEQ ai_think
    LDA ai_last_input,X        \ No: repeat the last decision.
    RTS

.ai_think
    \ Score every direction.
    LDA player_ink,X
    STA zp_ai_ink
    LDA #7
    STA zp_ai_direction
.ai_score_direction
    JSR ai_score
    LDX zp_ai_direction
    STA ai_scores,X
    DEC zp_ai_direction
    BPL ai_score_direction

    LDA #0                     \ No direction ruled out yet (a bit each).
    STA zp_ai_ruled

.ai_choose
    \ Best: clockwise from the current direction, strictly greater wins.
    \ Scores are at least 4 (four samples of at least 1), so 0 means none.
    LDX zp_ai_player
    LDA ai_direction,X
    STA zp_ai_current
    LDA #0
    STA zp_ai_best_score
    LDA #&FF
    STA zp_ai_best
    LDY #0                     \ Y = steps clockwise from current.
.ai_choose_loop
    TYA
    CLC
    ADC zp_ai_current
    AND #7
    TAX                        \ X = direction.
    LDA bit_masks,X            \ Ruled out?
    AND zp_ai_ruled
    BNE ai_choose_next
    LDA ai_scores,X
    CPY #0                     \ The current direction's bonus.
    BNE ai_choose_compare
    CLC
    ADC #AI_PERSISTENCE
.ai_choose_compare
    CMP zp_ai_best_score
    BCC ai_choose_next
    BEQ ai_choose_next         \ Strictly greater only.
    STA zp_ai_best_score
    STX zp_ai_best
.ai_choose_next
    INY
    CPY #8
    BNE ai_choose_loop

    LDX zp_ai_best             \ Everything ruled out: stay put.
    BPL ai_try_best
    LDA #NO_DIRECTION
    JMP ai_decided

.ai_try_best
    \ Is a step that way clear?
    LDY zp_ai_player
    STY zp_step_player
    LDA player_sx,Y
    CLC
    ADC direction_dx,X
    STA zp_try_x
    LDA player_sy,Y
    CLC
    ADC direction_dy,X
    STA zp_try_y
    JSR position_clear         \ Carry set if clear.
    BCS ai_go
    LDX zp_ai_best             \ Blocked: rule it out and choose again.
    LDA bit_masks,X
    ORA zp_ai_ruled
    STA zp_ai_ruled
    JMP ai_choose

.ai_go
    LDX zp_ai_player
    LDA zp_ai_best
    STA ai_direction,X
    TAY
    LDA ai_scores,Y            \ Fire at a worthwhile target.
    CMP #AI_FIRE_SCORE
    TYA
    BCC ai_decided
    ORA #FIRE_BIT
.ai_decided
    LDX zp_ai_player
    STA ai_last_input,X
    RTS

\ ----------------------------------------------------------------------------
\ ai_score -- score direction zp_ai_direction for player zp_ai_player
\
\ On exit:  A = the score (sum over the samples); X, Y corrupted
\ ----------------------------------------------------------------------------

.ai_score
    \ Samples are stored for E (even directions) and NE (odd); rotate by
    \ ((direction - 2 + base) DIV 2) MOD 4 quarter turns (as fire_splat).
    LDA zp_ai_direction
    AND #1
    STA zp_ai_base
    LDA zp_ai_direction
    SEC
    SBC #2
    CLC
    ADC zp_ai_base
    LSR A
    AND #3
    STA zp_ai_turns
    LDA zp_ai_base             \ First sample's offset: base * AI_SAMPLES * 2.
    BEQ ai_score_first
    LDA #AI_SAMPLES * 2
.ai_score_first
    STA zp_ai_sample
    CLC
    ADC #AI_SAMPLES * 2
    STA zp_ai_sample_end
    LDA #0
    STA zp_ai_total

.ai_score_sample
    LDX zp_ai_sample
    LDA ai_samples,X
    STA zp_node_dx
    LDA ai_samples+1,X
    STA zp_node_dy

    LDX zp_ai_turns            \ Rotate: (x, y) -> (5 - y, x).
    BEQ ai_score_rotated
.ai_score_turn
    LDA #SPRITE_FOOTPRINT - 1
    SEC
    SBC zp_node_dy
    LDY zp_node_dx
    STA zp_node_dx
    STY zp_node_dy
    DEX
    BNE ai_score_turn
.ai_score_rotated

    LDX zp_ai_player           \ The sample's cell; outside the arena if
    LDA player_sx,X            \ 128 or more (including negative).
    CLC
    ADC zp_node_dx
    STA zp_cell_x
    BMI ai_score_wall
    LDA player_sy,X
    CLC
    ADC zp_node_dy
    STA zp_cell_y
    BMI ai_score_wall
    LSR A                      \ In a wall? (wall cell = x DIV 4, y DIV 4)
    LSR A
    TAY
    LDA zp_cell_x
    LSR A
    LSR A
    TAX
    JSR is_wall
    BNE ai_score_wall

    JSR read_cell              \ A = state.
    ASL A                      \ Own ink count = state_counts[state*4 + ink].
    ASL A
    CLC
    ADC zp_ai_ink
    TAX
    LDA #8
    SEC
    SBC state_counts,X         \ Worth 8 - own count.
    JMP ai_score_add
.ai_score_wall
    LDA #AI_WALL_VALUE
.ai_score_add
    CLC
    ADC zp_ai_total
    STA zp_ai_total
    LDA zp_ai_sample
    CLC
    ADC #2
    STA zp_ai_sample
    CMP zp_ai_sample_end
    BNE ai_score_sample
    LDA zp_ai_total
    RTS
