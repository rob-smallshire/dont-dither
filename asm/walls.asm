\ ============================================================================
\ walls.asm -- the wall map and wall tile rendering
\
\ Walls occupy whole MODE 1 character cells: 8x8 pixels, i.e. 4x4
\ superpixels, so the arena is a 32x32 grid of wall cells. Which cells are
\ walls is held in a 128-byte bitmap: 4 bytes per cell row, the most
\ significant bit of each byte being the leftmost of its 8 cells. Collision
\ and painting consult this map rather than decoding screen patterns, which
\ leaves the wall art free to use any pixels, including solid black.
\
\ A character cell is 16 bytes of screen memory: its left byte column (8
\ raster lines, one byte each) followed by its right byte column. Cell
\ (cx, cy) starts at superpixel_row_lo/hi[4 * cy] + cx * 16.
\
\ Tile art (see the generated wall_tiles.asm): a black core with a one-pixel
\ rim on each side that does not join another wall. Cells outside the arena
\ count as walls, so the arena's border walls have no rim on their outer
\ side.
\
\ The colouring -- a core ink and a different rim ink -- is chosen per level
\ (12 possibilities). Tiles are stored as rim masks (rim pixels all ones, core
\ pixels zero), and each screen byte is
\     core EOR ((core EOR rim) AND mask)
\ which gives rim pixels where the mask is set and core pixels elsewhere.
\
\ Requires: os.asm, zeropage.asm, and the generated screen_tables.asm and
\ wall_tiles.asm.
\ ============================================================================

WALL_GRID_CELLS = 32

\ ----------------------------------------------------------------------------
\ is_wall -- test a cell of the wall map
\
\ On entry:  X = cx, Y = cy. Values of 32 or more, including -1 (&FF) from
\            decrementing 0, are outside the arena and count as walls.
\            zp_wall_map points at the wall bitmap.
\ On exit:   Z clear (A non-zero) if the cell is a wall or outside;
\            Z set (A = 0) if it is open.
\            X and Y preserved.
\ ----------------------------------------------------------------------------

.is_wall
    CPX #WALL_GRID_CELLS       \ An unsigned compare catches both 32 and
    BCS is_wall_outside        \ -1 (&FF) as out of range.
    CPY #WALL_GRID_CELLS
    BCS is_wall_outside

    STY zp_saved_y             \ Y is needed as an index; restore it later.

    \ Byte index = cy * 4 + cx DIV 8. cy * 4 has its low two bits clear
    \ and cx DIV 8 is 0..3, so OR does the addition.
    TYA
    ASL A
    ASL A
    STA zp_wall_byte           \ Temporarily hold cy * 4.
    TXA
    LSR A
    LSR A
    LSR A
    ORA zp_wall_byte
    TAY
    LDA (zp_wall_map),Y        \ Fetch the byte holding this cell's bit.
    STA zp_wall_byte

    \ Select bit (7 - cx MOD 8).
    TXA
    AND #7
    TAY
    LDA bit_masks,Y
    LDY zp_saved_y             \ Restore Y before the AND, so that the AND
    AND zp_wall_byte           \ sets the Z flag we return.
    RTS

.is_wall_outside
    LDA #&FF                   \ Non-zero: Z clear, "wall".
    RTS

\ ----------------------------------------------------------------------------
\ draw_walls -- draw every wall cell of the wall map
\ draw_walls_in_rect -- draw the wall cells within a rectangle of cells
\
\ On entry:  zp_wall_map points at the wall bitmap
\            zp_wall_core, zp_wall_rim = the colouring (WALL_INK_* bytes)
\            draw_walls_in_rect only: zp_rect_x0/y0 (inclusive) and
\            zp_rect_x1/y1 (exclusive) bound the cells to draw
\ On exit:   A, X, Y corrupted
\
\ Walls are drawn over whatever the cells held, so draw ink first. Neighbour
\ masks always come from the whole wall map, so a rectangle's walls join up
\ correctly with walls outside it.
\ ----------------------------------------------------------------------------

.draw_walls
    LDA #0                     \ The whole 32x32 grid.
    STA zp_rect_x0
    STA zp_rect_y0
    LDA #WALL_GRID_CELLS
    STA zp_rect_x1
    STA zp_rect_y1
    \ Fall through.

.draw_walls_in_rect
    LDA zp_wall_core           \ Precompute core EOR rim for the tile loop.
    EOR zp_wall_rim
    STA zp_wall_core_xor_rim

    LDA zp_rect_y0
    STA zp_cy
.draw_walls_row
    LDA zp_rect_x0
    STA zp_cx
.draw_walls_cell
    LDX zp_cx
    LDY zp_cy
    JSR is_wall
    BEQ draw_walls_next        \ Open cell: leave it alone.
    JSR draw_wall_cell
.draw_walls_next
    INC zp_cx
    LDA zp_cx
    CMP zp_rect_x1
    BNE draw_walls_cell
    INC zp_cy
    LDA zp_cy
    CMP zp_rect_y1
    BNE draw_walls_row
    RTS

\ ----------------------------------------------------------------------------
\ draw_wall_cell -- draw the wall tile for cell (zp_cx, zp_cy)
\
\ On entry:  zp_cx, zp_cy = a wall cell; zp_wall_map = the wall bitmap;
\            zp_wall_core, zp_wall_rim, zp_wall_core_xor_rim = the colouring
\ On exit:   A, X, Y corrupted
\
\ 1. Build the neighbour mask from the four orthogonal neighbours.
\ 2. Draw the matching 16-byte tile into the character cell, colouring its
\    rim mask with the level's core and rim inks.
\ 3. Patch inner corners: where two joined arms meet and the diagonal cell
\    between them is open, set that corner pixel to the rim ink so the
\    outline turns the corner without a gap.
\ ----------------------------------------------------------------------------

.draw_wall_cell
    \ ---- 1. Neighbour mask ----
    LDA #0
    STA zp_neighbours

    LDX zp_cx                  \ North: (cx, cy - 1).
    LDY zp_cy
    DEY
    JSR is_wall
    BEQ draw_wall_no_north
    LDA #WALL_NORTH
    ORA zp_neighbours
    STA zp_neighbours
.draw_wall_no_north

    LDX zp_cx                  \ East: (cx + 1, cy).
    INX
    LDY zp_cy
    JSR is_wall
    BEQ draw_wall_no_east
    LDA #WALL_EAST
    ORA zp_neighbours
    STA zp_neighbours
.draw_wall_no_east

    LDX zp_cx                  \ South: (cx, cy + 1).
    LDY zp_cy
    INY
    JSR is_wall
    BEQ draw_wall_no_south
    LDA #WALL_SOUTH
    ORA zp_neighbours
    STA zp_neighbours
.draw_wall_no_south

    LDX zp_cx                  \ West: (cx - 1, cy).
    DEX
    LDY zp_cy
    JSR is_wall
    BEQ draw_wall_no_west
    LDA #WALL_WEST
    ORA zp_neighbours
    STA zp_neighbours
.draw_wall_no_west

    \ ---- 2. Copy the tile ----
    \ zp_screen_ptr = start of character row cy + cx * 16. The row start is
    \ the superpixel row table entry for sy = 4 * cy. cx * 16 reaches 496, so
    \ the fourth ASL shifts bit 8 into carry and ROL moves it into the high
    \ byte.
    LDA zp_cy
    ASL A
    ASL A
    TAY                        \ Y = 4 * cy, a superpixel row.
    LDA #0
    STA zp_screen_ptr+1
    LDA zp_cx
    ASL A
    ASL A
    ASL A
    ASL A                      \ A = low byte of cx * 16, carry = bit 8.
    ROL zp_screen_ptr+1        \ High byte := 0 or 1. Clears carry.
    ADC superpixel_row_lo,Y
    STA zp_screen_ptr
    LDA zp_screen_ptr+1
    ADC superpixel_row_hi,Y
    STA zp_screen_ptr+1

    LDA zp_neighbours          \ Tile offset = mask * 16 (at most 240).
    ASL A
    ASL A
    ASL A
    ASL A
    TAX
    LDY #0
.draw_wall_copy
    LDA wall_tiles,X           \ X walks the tile, Y the character cell;
                               \ both run over 16 consecutive bytes.
    AND zp_wall_core_xor_rim   \ core EOR ((core EOR rim) AND mask): rim
    EOR zp_wall_core           \ pixels where the mask is set, core pixels
    STA (zp_screen_ptr),Y      \ elsewhere.
    INX
    INY
    CPY #16
    BNE draw_wall_copy

    \ ---- 3. Inner-corner patches ----
    LDA #0
    STA zp_corner              \ Offset of the current wall_corners record.
.draw_wall_corner
    LDX zp_corner
    LDA wall_corners,X         \ Do both of this corner's arms join?
    AND zp_neighbours
    CMP wall_corners,X
    BNE draw_wall_next_corner

    \ Test the diagonal cell (cx + dx, cy + dy). dx and dy are stored as
    \ two's complement bytes, so -1 is &FF and the sums wrap as needed; an
    \ out-of-range result counts as a wall and suppresses the patch.
    LDA zp_cy
    CLC
    ADC wall_corners+2,X       \ + dy
    TAY
    LDA zp_cx
    CLC
    ADC wall_corners+1,X       \ + dx
    TAX
    JSR is_wall
    BNE draw_wall_next_corner  \ Diagonal is a wall: no inner corner here.

    \ Set the corner pixel to the rim ink, keeping the byte's other pixels.
    LDX zp_corner
    LDY wall_corners+3,X       \ Byte offset of the corner within the cell.
    LDA zp_wall_rim
    EOR (zp_screen_ptr),Y
    AND wall_corners+4,X       \ The corner pixel's mask.
    EOR (zp_screen_ptr),Y
    STA (zp_screen_ptr),Y

.draw_wall_next_corner
    LDA zp_corner
    CLC
    ADC #WALL_CORNER_RECORD
    STA zp_corner
    CMP #WALL_CORNER_RECORD * WALL_CORNER_COUNT
    BNE draw_wall_corner
    RTS
