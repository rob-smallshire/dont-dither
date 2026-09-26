\ ============================================================================
\ zeropage.asm -- zero page variables shared by all Don't Dither! programs
\
\ Two blocks:
\
\   &70-&8F  reserved by the MOS for user programs, so nothing else writes it
\            even before our program starts. Holds zp_boot_status, which the
\            test harness polls from the moment the disc is booted.
\
\   &00-&6F  BASIC's workspace. Our programs are *RUN from BASIC and never
\            return to it, so once they start this is ours. (&90-&FF stays
\            with Econet, the filing system and the MOS.)
\
\ Variables are declared with ORG/SKIP rather than as `=` constants so that
\ beebasm exports them as labels, which the Python tests use to find them by
\ name.
\
\ INCLUDE this before the program's code ORG; it emits no bytes.
\ ============================================================================

\ ============================================================================
\ &70-&8F: user zero page
\ ============================================================================

ORG &70
GUARD &90                      \ Assembly fails if we outgrow &70-&8F.

.zp_boot_status   SKIP 1       \ 0 while setting up; BOOT_READY when the
                               \ program has finished and is idling. The test
                               \ harness polls this.

BOOT_READY = &FF               \ zp_boot_status value once set-up is done.

\ ============================================================================
\ &00-&6F: former BASIC workspace
\ ============================================================================

ORG &00
GUARD &70

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
.zp_wall_byte     SKIP 1       \ is_wall / plot_wall_cell: scratch byte.
.zp_saved_y       SKIP 1       \ is_wall: caller's Y, restored on exit.

\ ---- Levels ------------------------------------------------------------------

.zp_level         SKIP 1       \ Level number to enter (0..LEVEL_COUNT-1).
.zp_level_ptr     SKIP 2       \ Pointer to the current level's bytecode.
.zp_level_offset  SKIP 1       \ run_level_commands: offset of the next
                               \ bytecode byte, saved across calls.
.zp_symmetry_step SKIP 1       \ Quarter turns between symmetric copies:
                               \ 1 (ROT4) or 2 (ROT2).
.zp_copy_turns    SKIP 1       \ Quarter turns applied to the copy being
                               \ drawn: 0..3.
.zp_pen_x         SKIP 1       \ Level pen position, wall cells 0..31.
.zp_pen_y         SKIP 1
.zp_target_x      SKIP 1       \ End of the DRAW line being plotted.
.zp_target_y      SKIP 1
.zp_step_x        SKIP 1       \ Per-cell step along the line: -1 (&FF), 0
.zp_step_y        SKIP 1       \ or +1.
.zp_plot_x        SKIP 1       \ plot_wall_cell: the cell after rotation.
.zp_plot_y        SKIP 1

\ ---- Sprites -----------------------------------------------------------------

.zp_player          SKIP 1     \ Player being saved, restored or drawn.
.zp_sprite_row_sy   SKIP 1     \ Superpixel row of the sprite row being walked.
.zp_sprite_column   SKIP 2     \ (sx DIV 2) * 8: offset of the sprite's first
                               \ byte column from the start of a raster line.
.zp_sprite_contrast SKIP 1     \ Contrast ink byte of the sprite being drawn.
.zp_sprite_xor      SKIP 1     \ Contrast EOR player ink byte.
.zp_sprite_tmp      SKIP 1     \ Scratch.

\ ---- Rendering and movement ---------------------------------------------------

.zp_beam            SKIP 1     \ wait_for_beam: beam position, 4-line units.
.zp_region_top      SKIP 1     \ wait_for_beam: rows a redraw touches, in
.zp_region_bottom   SKIP 1     \ 4-line units.
.zp_render_index    SKIP 1     \ render_sprites: entry being redrawn.
.zp_player_mask     SKIP 1     \ update_players: player_count - 1.
.zp_update_index    SKIP 1     \ update_players: player moving now.
.zp_update_remaining SKIP 1    \ update_players: players still to move.
.zp_step_player     SKIP 1     \ try_step / position_clear: moving player.
.zp_step_dx         SKIP 1     \ try_step: step, two's complement.
.zp_step_dy         SKIP 1
.zp_step_clear      SKIP 1     \ try_step: which single-axis steps are clear.
.zp_try_x           SKIP 1     \ position_clear: candidate footprint.
.zp_try_y           SKIP 1
.zp_other_x         SKIP 1     \ footprints_overlap: the other footprint.
.zp_other_y         SKIP 1
.zp_wall_cx0        SKIP 1     \ position_clear: wall cells a footprint
.zp_wall_cx1        SKIP 1     \ covers, columns cx0..cx1 and rows up to
.zp_wall_cy1        SKIP 1     \ cy1.

\ ---- Painting -----------------------------------------------------------------

.zp_shooter         SKIP 1     \ fire_splat: the player shooting.
.zp_painter_ink     SKIP 1     \ The shooter's ink (0 = C .. 3 = K).
.zp_last_victim     SKIP 1     \ The shooter's round-robin position.
.zp_shot_x          SKIP 1     \ The shooter's footprint top-left.
.zp_shot_y          SKIP 1
.zp_shot_base       SKIP 1     \ 0: tree drawn for E; 1: for NE.
.zp_shot_turns      SKIP 1     \ Quarter turns from the stored tree.
.zp_tree_ptr        SKIP 2     \ The splat tree.
.zp_tree_nodes      SKIP 1     \ Its node count.
.zp_node_index      SKIP 1     \ Node being processed...
.zp_node_offset     SKIP 1     \ ...and its byte offset in the tree.
.zp_node_dx         SKIP 1     \ Its cell offset, rotated.
.zp_node_dy         SKIP 1
.zp_node_parent     SKIP 1     \ Its parent index | SPLAT_PAINTS.
.zp_cell_x          SKIP 1     \ paint_cell: the cell.
.zp_cell_y          SKIP 1
.zp_cell_ptr        SKIP 2     \ Where its bytes live (screen or buffer)...
.zp_cell_top_offset SKIP 1     \ ...with these offsets for the top and
.zp_cell_bottom_offset SKIP 1  \ bottom raster bytes.
.zp_cell_mask       SKIP 1     \ &CC (even x) or &33 (odd x).
.zp_cell_top        SKIP 1     \ The two raster bytes as read.
.zp_cell_bottom     SKIP 1
.zp_cell_index      SKIP 1     \ pattern_to_state index being built.
.zp_cell_row        SKIP 1     \ Row / byte column within a save buffer.
.zp_cell_column     SKIP 1
.zp_cell_state      SKIP 1     \ The cell's ink state before painting...
.zp_count_base      SKIP 1     \ ...and state * 4, its state_counts offset.

\ ---- Input --------------------------------------------------------------------

.zp_keys          SKIP 1       \ scan_layout: held keys, up = bit 0 .. fire = 4.
.zp_key_index     SKIP 1       \ scan_layout: offset of the key being scanned.
.zp_key_end       SKIP 1       \ scan_layout: offset just past the layout.

\ ---- Test card ---------------------------------------------------------------

.zp_swatch        SKIP 1       \ Offset of the current testcard_swatch_walls
                               \ record.
