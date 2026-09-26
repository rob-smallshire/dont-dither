\ ============================================================================
\ level.asm -- expanding a level's compact bytecode into the wall map
\
\ A level stores only one quadrant (ROT4) or half (ROT2) of its walls, as
\ MOVE/DRAW commands in wall-cell coordinates 0..31. build_wall_map runs the
\ commands once per symmetric copy, rotating every plotted cell by that
\ copy's number of clockwise quarter turns about the arena centre:
\     one quarter turn: (x, y) -> (31 - y, x)
\ so the arena's symmetry, and hence its fairness, is structural rather than
\ hand-copied.
\
\ Bytecode layout (generated from levels/*.lvl into level_data.asm):
\   header   LEVEL_HEADER_SIZE bytes: symmetry step (1 = ROT4, 2 = ROT2),
\            wall core ink byte, wall rim ink byte, fill ink state
\   commands LEVEL_START sx, sy, facing   (player 0's start; skipped here)
\            LEVEL_MOVE  cx, cy            (move the pen)
\            LEVEL_DRAW  cx, cy            (wall cells from pen to here)
\            LEVEL_END
\ A level's bytecode is under 256 bytes, so Y can index all of it.
\
\ Requires: zeropage.asm, screen_tables.asm (bit_masks), level_data.asm, and
\ a 128-byte wall_map buffer defined by the program.
\ ============================================================================

\ ----------------------------------------------------------------------------
\ select_level -- point zp_level_ptr at level zp_level's bytecode
\
\ On entry:  zp_level = level number
\ On exit:   A, X corrupted
\ ----------------------------------------------------------------------------

.select_level
    LDX zp_level
    LDA level_table_lo,X
    STA zp_level_ptr
    LDA level_table_hi,X
    STA zp_level_ptr+1
    RTS

\ ----------------------------------------------------------------------------
\ build_wall_map -- expand the current level's walls into wall_map
\
\ On entry:  zp_level_ptr points at the level's bytecode
\ On exit:   wall_map holds the level's complete 32x32 wall bitmap
\            A, X, Y corrupted
\ ----------------------------------------------------------------------------

.build_wall_map
    \ Clear the map: Y counts 127 down to 0, and BPL stops once it wraps to
    \ &FF.
    LDA #0
    LDY #127
.build_wall_map_clear
    STA wall_map,Y
    DEY
    BPL build_wall_map_clear

    LDY #LEVEL_HEADER_SYMMETRY
    LDA (zp_level_ptr),Y
    STA zp_symmetry_step       \ 1 for ROT4, 2 for ROT2.

    \ Draw the stored geometry once per copy, at 0, step, 2*step... quarter
    \ turns: 0, 1, 2, 3 for ROT4; 0, 2 for ROT2.
    LDA #0
    STA zp_copy_turns
.build_wall_map_copy
    JSR run_level_commands
    LDA zp_copy_turns
    CLC
    ADC zp_symmetry_step
    STA zp_copy_turns
    CMP #4
    BCC build_wall_map_copy
    RTS

\ ----------------------------------------------------------------------------
\ run_level_commands -- plot one symmetric copy of the level's walls
\
\ On entry:  zp_level_ptr = the level; zp_copy_turns = rotation of this copy
\ On exit:   A, X, Y corrupted
\ ----------------------------------------------------------------------------

.run_level_commands
    LDY #LEVEL_HEADER_SIZE     \ First command follows the header.
.run_level_next
    LDA (zp_level_ptr),Y       \ Fetch the opcode and step past it.
    INY
    CMP #LEVEL_END
    BEQ run_level_done
    CMP #LEVEL_MOVE
    BEQ run_level_move
    CMP #LEVEL_START
    BEQ run_level_skip_start

    \ LEVEL_DRAW cx, cy: plot from the pen to (cx, cy), which becomes the
    \ new pen position.
    LDA (zp_level_ptr),Y
    STA zp_target_x
    INY
    LDA (zp_level_ptr),Y
    STA zp_target_y
    INY
    STY zp_level_offset        \ draw_line uses X and Y.
    JSR draw_line
    LDY zp_level_offset
    JMP run_level_next

.run_level_move
    \ LEVEL_MOVE cx, cy: just move the pen.
    LDA (zp_level_ptr),Y
    STA zp_pen_x
    INY
    LDA (zp_level_ptr),Y
    STA zp_pen_y
    INY
    JMP run_level_next

.run_level_skip_start
    \ LEVEL_START sx, sy, facing: not needed to build walls.
    INY
    INY
    INY
    JMP run_level_next

.run_level_done
    RTS

\ ----------------------------------------------------------------------------
\ draw_line -- plot wall cells from the pen to the target, inclusive
\
\ On entry:  zp_pen_x/y = start cell; zp_target_x/y = end cell, on the same
\            row or column (the level compiler guarantees it)
\ On exit:   zp_pen_x/y = the target; A, X, Y corrupted
\ ----------------------------------------------------------------------------

.draw_line
    \ step_x := sign(target_x - pen_x) as 0, +1 or -1 (&FF). CMP sets carry
    \ when target >= pen; equality was handled first.
    LDA #0
    STA zp_step_x
    LDA zp_target_x
    CMP zp_pen_x
    BEQ draw_line_step_y
    LDA #1
    BCS draw_line_set_x
    LDA #&FF
.draw_line_set_x
    STA zp_step_x

.draw_line_step_y
    \ step_y likewise.
    LDA #0
    STA zp_step_y
    LDA zp_target_y
    CMP zp_pen_y
    BEQ draw_line_loop
    LDA #1
    BCS draw_line_set_y
    LDA #&FF
.draw_line_set_y
    STA zp_step_y

.draw_line_loop
    LDX zp_pen_x               \ Plot the pen's cell.
    LDY zp_pen_y
    JSR plot_wall_cell
    LDA zp_pen_x               \ Stop once the pen reaches the target.
    CMP zp_target_x
    BNE draw_line_advance
    LDA zp_pen_y
    CMP zp_target_y
    BEQ draw_line_done
.draw_line_advance
    LDA zp_pen_x               \ Step the pen one cell towards the target.
    CLC                        \ Adding &FF subtracts 1, modulo 256.
    ADC zp_step_x
    STA zp_pen_x
    LDA zp_pen_y
    CLC
    ADC zp_step_y
    STA zp_pen_y
    JMP draw_line_loop
.draw_line_done
    RTS

\ ----------------------------------------------------------------------------
\ plot_wall_cell -- set a wall cell in wall_map, rotated for this copy
\
\ On entry:  X = cx, Y = cy (0..31, unrotated); zp_copy_turns = quarter turns
\ On exit:   A, X, Y corrupted
\
\ Each clockwise quarter turn maps (x, y) to (31 - y, x). For 0..31,
\ 31 - y equals y EOR 31, since 31 is all ones in the low five bits.
\ ----------------------------------------------------------------------------

.plot_wall_cell
    STX zp_plot_x
    STY zp_plot_y
    LDX zp_copy_turns          \ X counts the quarter turns still to apply.
    BEQ plot_wall_cell_set
.plot_wall_cell_turn
    LDY zp_plot_x              \ Y = old x, the new y.
    LDA zp_plot_y
    EOR #31                    \ New x = 31 - old y.
    STA zp_plot_x
    STY zp_plot_y
    DEX
    BNE plot_wall_cell_turn

.plot_wall_cell_set
    \ Byte index = y * 4 + x DIV 8 (y * 4 has its low two bits clear, so
    \ OR adds); bit = bit_masks[x MOD 8], most significant bit leftmost.
    LDA zp_plot_y
    ASL A
    ASL A
    STA zp_wall_byte
    LDA zp_plot_x
    LSR A
    LSR A
    LSR A
    ORA zp_wall_byte
    TAY
    LDA zp_plot_x
    AND #7
    TAX
    LDA wall_map,Y
    ORA bit_masks,X
    STA wall_map,Y
    RTS
