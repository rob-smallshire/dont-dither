\ ============================================================================
\ zeropage.asm -- zero page variables shared by all Don't Dither! programs
\
\ The MOS reserves &70-&8F for user programs and leaves it alone, so all our
\ zero page lives there. Variables are declared with ORG/SKIP rather than as
\ `=` constants so that beebasm exports them as labels, which the Python tests
\ use to find them by name.
\
\ INCLUDE this before the program's code ORG; it emits no bytes.
\ ============================================================================

ORG &70
GUARD &90                      \ Assembly fails if we outgrow &70-&8F.

\ ---- Harness handshake ------------------------------------------------------

.zp_boot_status   SKIP 1       \ 0 while setting up; BOOT_READY when the
                               \ program has finished and is idling. The test
                               \ harness polls this.

\ ---- Screen access -----------------------------------------------------------

.zp_screen_ptr    SKIP 2       \ Little-endian pointer into screen memory
                               \ for (zp),Y addressing. Also borrowed by
                               \ send_vdu_bytes to walk a VDU block.
.zp_fill_top      SKIP 1       \ fill_arena_with_state: top raster byte.
.zp_fill_bottom   SKIP 1       \ fill_arena_with_state: bottom raster byte.
.zp_half_mask     SKIP 1       \ set_superpixel_state: &CC (even sx) or &33
                               \ (odd sx), selecting the superpixel's half of
                               \ each raster byte.
.zp_ink_state     SKIP 1       \ set_superpixel_state: ink state being drawn.

\ ---- Arena iteration ---------------------------------------------------------

.zp_sx            SKIP 1       \ Superpixel column, 0..127.
.zp_sy            SKIP 1       \ Superpixel row, 0..127.

\ ---- Walls -------------------------------------------------------------------

.zp_wall_map      SKIP 2       \ Pointer to the 128-byte, 32x32 wall bitmap.
.zp_wall_core     SKIP 1       \ Wall colouring, set per level before
.zp_wall_rim      SKIP 1       \ draw_walls: screen bytes of four core-ink and
                               \ four rim-ink pixels (WALL_INK_K/_C/_M/_Y).
                               \ Core and rim must differ.
.zp_wall_core_xor_rim SKIP 1   \ zp_wall_core EOR zp_wall_rim, computed by
                               \ draw_walls_in_rect for the tile loop.
.zp_rect_x0       SKIP 1       \ draw_walls_in_rect: cell rectangle, columns
.zp_rect_y0       SKIP 1       \ x0 <= cx < x1 and rows y0 <= cy < y1.
.zp_rect_x1       SKIP 1
.zp_rect_y1       SKIP 1
.zp_cx            SKIP 1       \ Wall cell column, 0..31.
.zp_cy            SKIP 1       \ Wall cell row, 0..31.
.zp_neighbours    SKIP 1       \ Neighbour mask of the wall cell being drawn
                               \ (WALL_NORTH | WALL_EAST | ...).
.zp_corner        SKIP 1       \ Offset of the current wall_corners record.
.zp_wall_byte     SKIP 1       \ is_wall: the bitmap byte being tested.
.zp_saved_y       SKIP 1       \ is_wall: caller's Y, restored on exit.

\ ---- Test card -----------------------------------------------------------------

.zp_swatch        SKIP 1       \ Offset of the current testcard_swatch_walls
                               \ record.

\ ---- Constants for the above ---------------------------------------------------

BOOT_READY = &FF               \ zp_boot_status value once set-up is done.
