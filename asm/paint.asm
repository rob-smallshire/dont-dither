\ ============================================================================
\ paint.asm -- firing: splats that move arena cells towards the shooter's ink
\
\ After every player has moved, the players fire in the same rotating order
\ (fire_players). A shot applies the shooter's next splat variant from its
\ position and facing. A splat is a tree of cells (see paint_data.asm): the
\ cells on the lines from the tank to each splat cell, parents first. A node
\ is blocked if its cell is outside the arena or in a wall, or its parent is
\ blocked -- so walls shadow the cells behind them. Every unblocked splat
\ cell gets one paint application (paint_cell):
\
\   the shooter's ink count in the cell goes up by one, and one other ink
\   present goes down by one: the victim, chosen round-robin per player
\   (the first ink with a non-zero count after the player's last victim,
\   skipping the player's own). A cell already solidly the shooter's ink is
\   left alone and does not advance the round-robin.
\
\ The arena is the screen, except under the tanks: a cell inside a tank's
\ drawn footprint is read and painted in that tank's save buffer, which
\ holds the arena beneath it, and the tank is flagged for a redraw so the
\ change shows. This must match tools/dontdither/game.py exactly.
\
\ Requires: zeropage.asm, walls.asm (is_wall), sprites.asm, and the generated
\ ink_tables.asm, screen_tables.asm and paint_data.asm.
\ ============================================================================

\ ----------------------------------------------------------------------------
\ fire_players -- let each player fire, in this tick's rotating order
\
\ On exit:  A, X, Y corrupted
\
\ A player whose cooldown is non-zero counts it down. Otherwise, if fire is
\ held and it is the player's turn, it shoots and its cooldown becomes
\ FIRE_PERIOD - 1, so holding fire shoots every FIRE_PERIOD ticks. A player's
\ turn is a tick where tick_count + player is even: at most half the players
\ shoot in any one tick, which keeps a tick's painting within budget, and as
\ FIRE_PERIOD is even the rule never delays a held fire.
\ ----------------------------------------------------------------------------

.fire_players
    LDA player_count
    SEC
    SBC #1
    STA zp_player_mask         \ player_count - 1: 1 or 3.
    LDA tick_count             \ The same first player as update_players.
    AND zp_player_mask
    STA zp_update_index
    LDA player_count
    STA zp_update_remaining

.fire_players_loop
    LDX zp_update_index
    LDA player_cooldown,X
    BEQ fire_players_ready
    DEC player_cooldown,X      \ Still reloading.
    JMP fire_players_next
.fire_players_ready
    LDA player_input,X
    AND #FIRE_BIT
    BEQ fire_players_next
    TXA                        \ This player's turn: tick_count + player
    CLC                        \ even?
    ADC tick_count
    AND #1
    BNE fire_players_next
    JSR fire_splat
    LDX zp_update_index
    LDA #FIRE_PERIOD - 1
    STA player_cooldown,X

.fire_players_next
    LDA zp_update_index        \ Next player, wrapping round.
    CLC
    ADC #1
    AND zp_player_mask
    STA zp_update_index
    DEC zp_update_remaining
    BNE fire_players_loop
    RTS

\ ----------------------------------------------------------------------------
\ fire_splat -- player X shoots its next splat variant
\
\ On entry:  X = player
\ On exit:   A, X, Y corrupted
\ ----------------------------------------------------------------------------

.fire_splat
    STX zp_shooter
    LDA player_ink,X
    STA zp_painter_ink
    LDA player_last_victim,X
    STA zp_last_victim
    LDA player_sx,X
    STA zp_shot_x
    LDA player_sy,X
    STA zp_shot_y

    \ Trees are stored for E (even facings) and NE (odd facings); other
    \ facings are quarter turns of them. Base = facing AND 1; turns =
    \ ((facing - 2 + base) DIV 2) MOD 4, e.g. N (0): (0 - 2) = &FE -> 3
    \ turns of E; NW (7): 6 -> 3 turns of NE.
    LDA player_facing,X
    AND #1
    STA zp_shot_base
    LDA player_facing,X
    SEC
    SBC #2
    CLC
    ADC zp_shot_base
    LSR A
    AND #3
    STA zp_shot_turns

    \ Tree number = base * SPLAT_VARIANTS + variant; then advance the
    \ player's variant, cycling.
    LDA zp_shot_base
    BEQ fire_splat_tree
    LDA #SPLAT_VARIANTS
.fire_splat_tree
    CLC
    ADC player_variant,X
    TAY
    LDA splat_tree_lo,Y
    STA zp_tree_ptr
    LDA splat_tree_hi,Y
    STA zp_tree_ptr+1
    LDA splat_tree_nodes,Y
    STA zp_tree_nodes
    LDA player_variant,X
    CLC
    ADC #1
    CMP #SPLAT_VARIANTS
    BCC fire_splat_variant
    LDA #0
.fire_splat_variant
    STA player_variant,X

    \ Walk the tree.
    LDA #0
    STA zp_node_index
    STA zp_node_offset
.fire_splat_node
    LDY zp_node_offset
    LDA (zp_tree_ptr),Y        \ dx, dy, parent|paints.
    STA zp_node_dx
    INY
    LDA (zp_tree_ptr),Y
    STA zp_node_dy
    INY
    LDA (zp_tree_ptr),Y
    STA zp_node_parent
    INY
    STY zp_node_offset

    \ Rotate (dx, dy) by the shot's quarter turns: (x, y) -> (5 - y, x).
    LDX zp_shot_turns
    BEQ fire_splat_rotated
.fire_splat_turn
    LDA #SPRITE_FOOTPRINT - 1
    SEC
    SBC zp_node_dy
    LDY zp_node_dx             \ Y = old x, the new y.
    STA zp_node_dx
    STY zp_node_dy
    DEX
    BNE fire_splat_turn
.fire_splat_rotated

    \ The node's cell. Outside the arena if either coordinate is 128 or
    \ more, which includes negative results (&80 and up).
    LDA zp_shot_x
    CLC
    ADC zp_node_dx
    STA zp_cell_x
    BMI fire_splat_blocked
    LDA zp_shot_y
    CLC
    ADC zp_node_dy
    STA zp_cell_y
    BMI fire_splat_blocked

    \ In a wall? The wall cell is (x DIV 4, y DIV 4).
    LDA zp_cell_x
    LSR A
    LSR A
    TAX
    LDA zp_cell_y
    LSR A
    LSR A
    TAY
    JSR is_wall
    BNE fire_splat_blocked

    \ Is the parent blocked?
    LDA zp_node_parent
    AND #&7F
    CMP #SPLAT_NO_PARENT
    BEQ fire_splat_open
    TAX
    LDA splat_blocked,X
    BNE fire_splat_blocked

.fire_splat_open
    LDX zp_node_index
    LDA #0
    STA splat_blocked,X
    BIT zp_node_parent         \ Bit 7 (N): a splat cell to paint?
    BPL fire_splat_next
    JSR paint_cell
    JMP fire_splat_next

.fire_splat_blocked
    LDX zp_node_index
    LDA #1
    STA splat_blocked,X

.fire_splat_next
    INC zp_node_index
    LDA zp_node_index
    CMP zp_tree_nodes
    BNE fire_splat_node

    LDX zp_shooter             \ Keep the round-robin position.
    LDA zp_last_victim
    STA player_last_victim,X
    RTS

\ ----------------------------------------------------------------------------
\ paint_cell -- apply one quantum of the shooter's ink to cell (zp_cell_x,
\ zp_cell_y)
\
\ On entry:  zp_painter_ink, zp_last_victim = the shooter's ink and
\            round-robin position
\ On exit:   the cell (on screen or in a tank's save buffer) moved one
\            quantum towards the painter; zp_last_victim updated if a quantum
\            moved; A, X, Y corrupted
\ ----------------------------------------------------------------------------

.paint_cell
    \ Where does the cell live? Normally on screen: the top raster byte at
    \ superpixel_row[y] + (x DIV 2) * 8, the bottom one the next address.
    LDY zp_cell_y
    LDA #0
    STA zp_cell_ptr+1
    LDA zp_cell_x
    AND #&FE
    ASL A
    ASL A                      \ (x DIV 2) * 8, up to 504: bit 8 in carry.
    ROL zp_cell_ptr+1
    ADC superpixel_row_lo,Y    \ Carry is clear after the ROL.
    STA zp_cell_ptr
    LDA zp_cell_ptr+1
    ADC superpixel_row_hi,Y
    STA zp_cell_ptr+1
    LDA #0
    STA zp_cell_top_offset
    LDA #1
    STA zp_cell_bottom_offset

    \ Unless it is under a tank: inside some tank's drawn footprint
    \ (saved_sx..saved_sx+5, saved_sy..saved_sy+5; unsigned differences
    \ under 6). Then it lives in that tank's save buffer.
    LDA sprites_shown
    BEQ paint_cell_located
    LDX #0
.paint_cell_tank
    CPX player_count
    BEQ paint_cell_located
    LDA zp_cell_x
    SEC
    SBC saved_sx,X
    CMP #SPRITE_FOOTPRINT
    BCS paint_cell_next_tank
    LDA zp_cell_y
    SEC
    SBC saved_sy,X
    CMP #SPRITE_FOOTPRINT
    BCC paint_cell_under_tank
.paint_cell_next_tank
    INX
    JMP paint_cell_tank

.paint_cell_under_tank
    \ Buffer layout: 8 bytes per superpixel row r (4 top-line bytes, then 4
    \ bottom-line bytes); byte column b = x DIV 2 - saved_sx DIV 2. So the
    \ top byte is at r * 8 + b and the bottom byte 4 further on.
    STA zp_cell_row            \ A = r = y - saved_sy.
    LDA #1                     \ The tank must be redrawn to show the change.
    STA player_repaint,X
    LDA saved_sx,X
    LSR A
    STA zp_cell_column
    LDA zp_cell_x
    LSR A
    SEC
    SBC zp_cell_column         \ A = b.
    STA zp_cell_column
    LDA zp_cell_row
    ASL A
    ASL A
    ASL A
    CLC
    ADC zp_cell_column
    STA zp_cell_top_offset
    CLC
    ADC #4
    STA zp_cell_bottom_offset
    JSR point_at_save_buffer   \ A = low byte, zp_sprite_tmp = high byte.
    STA zp_cell_ptr
    LDA zp_sprite_tmp
    STA zp_cell_ptr+1

.paint_cell_located
    \ Which half of each byte: even x the left (&CC), odd x the right (&33).
    LDA zp_cell_x
    LSR A
    LDA #&CC
    BCC paint_cell_mask
    LDA #&33
.paint_cell_mask
    STA zp_cell_mask

    \ Read the two raster bytes and form the pattern_to_state index, a byte
    \ whose pixels are TL, TR, BL, BR:
    \   even x: (top AND &CC) OR ((bottom AND &CC) >> 2)
    \   odd x:  ((top AND &33) << 2) OR (bottom AND &33)
    LDY zp_cell_top_offset
    LDA (zp_cell_ptr),Y
    STA zp_cell_top
    LDY zp_cell_bottom_offset
    LDA (zp_cell_ptr),Y
    STA zp_cell_bottom
    LDA zp_cell_mask
    CMP #&CC
    BNE paint_cell_odd
    LDA zp_cell_bottom
    AND #&CC
    LSR A
    LSR A
    STA zp_cell_index
    LDA zp_cell_top
    AND #&CC
    ORA zp_cell_index
    JMP paint_cell_state
.paint_cell_odd
    LDA zp_cell_top
    AND #&33
    ASL A
    ASL A
    STA zp_cell_index
    LDA zp_cell_bottom
    AND #&33
    ORA zp_cell_index
.paint_cell_state
    TAX
    LDA pattern_to_state,X
    CMP #NON_CANONICAL         \ Not an ink pattern: leave it alone.
    BEQ paint_cell_done

    \ The state's ink counts are state_counts[state * 4 + ink].
    STA zp_cell_state
    ASL A
    ASL A                      \ state * 4 (at most 136).
    STA zp_count_base

    \ Already solidly the painter's ink: nothing to do.
    CLC
    ADC zp_painter_ink
    TAX
    LDA state_counts,X
    CMP #4
    BEQ paint_cell_done

    \ Victim: the next ink after the last victim that is not the painter's
    \ and has a non-zero count. (One exists: the painter's count is not 4.)
    LDY zp_last_victim
.paint_cell_victim
    INY
    TYA
    AND #3
    TAY
    CPY zp_painter_ink
    BEQ paint_cell_victim
    CLC
    ADC zp_count_base
    TAX
    LDA state_counts,X
    BEQ paint_cell_victim
    STY zp_last_victim

    \ New state: moving a quantum from victim (Y) to painter changes the
    \ state's counts index by ink_weight[painter] - ink_weight[victim].
    LDX zp_cell_state
    LDA state_index_of,X
    LDX zp_painter_ink
    CLC
    ADC ink_weight,X
    SEC
    SBC ink_weight,Y
    TAX
    LDA state_of_counts,X
    TAX                        \ X = new state.

    \ Write its pattern into this cell's half of each byte:
    \   byte EOR ((pattern EOR byte) AND mask)
    LDA state_top_bytes,X
    EOR zp_cell_top
    AND zp_cell_mask
    EOR zp_cell_top
    LDY zp_cell_top_offset
    STA (zp_cell_ptr),Y
    LDA state_bottom_bytes,X
    EOR zp_cell_bottom
    AND zp_cell_mask
    EOR zp_cell_bottom
    LDY zp_cell_bottom_offset
    STA (zp_cell_ptr),Y
.paint_cell_done
    RTS
