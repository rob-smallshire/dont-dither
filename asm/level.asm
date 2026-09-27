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
\ Every level also has a border, the outermost ring of wall cells, which
\ build_wall_map draws itself: levels do not store it.
\
\ Bytecode layout (generated from levels/*.lvl into the level-set files; see
\ level_format.asm), compact so that as many levels as possible fit:
\   header   LEVEL_HEADER_SIZE bytes: symmetry step (1 = ROT4, 2 = ROT2),
\            wall core ink byte, wall rim ink byte, fill ink state, and
\            player 0's start sx, sy, facing (placed by place_players)
\   commands two bytes each: cx (with LEVEL_DRAW_BIT set: draw wall cells
\            from the pen to here; clear: just move the pen), then cy
\   LEVEL_END
\ A level's bytecode is under 256 bytes, so Y can index all of it. In the
\ level set, each level's bytecode follows its title (a length byte and the
\ characters), level after level; select_level walks to the one wanted.
\
\ Requires: zeropage.asm, screen_tables.asm (bit_masks), level_format.asm, the
\ loaded level set (level_area), and a 128-byte wall_map buffer and a
\ 2-byte level_title defined by the program.
\ ============================================================================

\ ----------------------------------------------------------------------------
\ select_level -- find level zp_level: its title and its bytecode
\
\ On entry:  zp_level = level number (0..level_set_count-1)
\ On exit:   level_title = the address of its title (a length byte then the
\            characters); zp_level_ptr = its bytecode; A, X, Y corrupted
\
\ Levels lie one after another from level_area + LEVEL_SET_LEVELS, each a
\ title then bytecode ending with LEVEL_END, so the walk skips zp_level of
\ them. (Coordinates are 0..31 even with LEVEL_DRAW_BIT set, so no command
\ byte is LEVEL_END; commands come in pairs, so testing every other byte
\ from the header's end finds it.)
\ ----------------------------------------------------------------------------

.select_level
    LDA #LO(level_area + LEVEL_SET_LEVELS)
    STA zp_level_ptr
    LDA #HI(level_area + LEVEL_SET_LEVELS)
    STA zp_level_ptr+1
    LDX zp_level
.select_level_title
    LDA zp_level_ptr           \ Here is a level's title...
    STA level_title
    LDA zp_level_ptr+1
    STA level_title+1
    LDY #0                     \ ...and its bytecode follows: zp_level_ptr +=
    LDA (zp_level_ptr),Y       \ length + 1.
    SEC
    ADC zp_level_ptr
    STA zp_level_ptr
    BCC select_level_code
    INC zp_level_ptr+1
.select_level_code
    DEX                        \ The level wanted?
    BMI select_level_done
    LDY #LEVEL_HEADER_SIZE     \ No: past its commands to LEVEL_END...
.select_level_command
    LDA (zp_level_ptr),Y
    CMP #LEVEL_END
    BEQ select_level_end
    INY
    INY
    BNE select_level_command   \ (Always: bytecode is under 256 bytes.)
.select_level_end
    TYA                        \ ...and past that: zp_level_ptr += Y + 1.
    SEC
    ADC zp_level_ptr
    STA zp_level_ptr
    BCC select_level_title
    INC zp_level_ptr+1
    JMP select_level_title
.select_level_done
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

    \ The border. The map is 4 bytes a row, MSB leftmost: the top and bottom
    \ rows are all set, and every row has its first and last cells set.
    LDA #&FF
    LDY #3
.build_wall_map_edges
    STA wall_map,Y             \ Row 0...
    STA wall_map + 124,Y       \ ...and row 31.
    DEY
    BPL build_wall_map_edges
    LDY #124
.build_wall_map_sides
    LDA wall_map,Y             \ Column 0: bit 7 of the row's first byte.
    ORA #&80
    STA wall_map,Y
    LDA wall_map + 3,Y         \ Column 31: bit 0 of its last.
    ORA #&01
    STA wall_map + 3,Y
    DEY
    DEY
    DEY
    DEY
    BPL build_wall_map_sides

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
    LDA (zp_level_ptr),Y       \ The command's cx, or the end.
    CMP #LEVEL_END
    BEQ run_level_done
    INY
    ASSERT LEVEL_DRAW_BIT = &80
    ASL A                      \ Draw or move? (LEVEL_DRAW_BIT into carry.)
    BCS run_level_draw
    LSR A                      \ Move: cx back, and cy: just move the pen.
    STA zp_pen_x
    LDA (zp_level_ptr),Y
    STA zp_pen_y
    INY
    JMP run_level_next

.run_level_draw
    \ Draw: plot from the pen to (cx, cy), which becomes the new pen
    \ position.
    LSR A                      \ cx back, without the draw bit.
    STA zp_target_x
    LDA (zp_level_ptr),Y
    STA zp_target_y
    INY
    STY zp_level_offset        \ draw_line uses X and Y.
    JSR draw_line
    LDY zp_level_offset
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
