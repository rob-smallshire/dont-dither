\ ============================================================================
\ main.asm -- Don't Dither! for the BBC Micro Model B
\
\ Build with `uv run dd-build` (runs beebasm from the project root, which is
\ why INCLUDE paths are relative to the root). The disc's !BOOT runs this
\ program, saved as DITHER.
\
\ CURRENT STAGE: arena and player sprites. The program
\   1. selects MODE 1, hides the cursor and programs the CMYK palette,
\   2. enters level 0 (see enter_level): fills the arena with the level's
\      initial ink state, expands the level's walls into the wall map under
\      its symmetry, draws them in the level's colouring, shows the title
\      and level name in the HUD, and draws each player's tank at its start,
\   3. sets zp_boot_status to BOOT_READY and idles.
\
\ Test hooks: with the machine idling, a test may jump (by setting PC at an
\ instruction boundary) to
\   enter_level     after setting zp_level, to draw any level;
\   redraw_sprites  after changing player_sx/sy/facing, to move tanks.
\ Both set BOOT_READY and idle when done.
\
\ Memory map (for now):
\   &0000-&006F  zero page, former BASIC workspace (see zeropage.asm)
\   &0070-&008F  zero page reserved for user programs
\   &1900-       program code and tables (loaded and run by DFS via !BOOT),
\                then uninitialised buffers (wall_map)
\   &3000-&7FFF  MODE 1 screen memory (20 KB)
\ Later the program will reclaim DFS workspace below &1900 once loaded.
\ ============================================================================

INCLUDE "asm/os.asm"
INCLUDE "asm/macros.asm"
INCLUDE "asm/zeropage.asm"

ORG &1900
GUARD MODE1_SCREEN_BASE        \ Assembly fails if code, data or buffers
                               \ reach the screen.

.start
    \ Mark boot as in progress. RAM contents at power-on are not guaranteed,
    \ so the harness must never see a stale BOOT_READY.
    LDA #0
    STA zp_boot_status

    JSR init_display           \ MODE 1, cursor off, CMYK palette.

    LDA #0                     \ Start with the first level.
    STA zp_level
    \ Fall through into enter_level.

\ ----------------------------------------------------------------------------
\ enter_level -- draw level zp_level and idle
\
\ On entry:  zp_level = level number (0..LEVEL_COUNT-1); display initialised
\ Never returns: sets zp_boot_status to BOOT_READY and idles.
\ ----------------------------------------------------------------------------

.enter_level
    LDA #0                     \ Not ready while drawing (matters when a test
    STA zp_boot_status         \ jumps here to draw another level).

    JSR select_level           \ zp_level_ptr -> the level's bytecode.

    \ Fill every arena superpixel with the level's initial ink state.
    LDY #LEVEL_HEADER_FILL
    LDA (zp_level_ptr),Y
    TAX
    JSR fill_arena_with_state

    \ Expand the level's walls into wall_map and draw them over the ink in
    \ the level's colouring.
    JSR build_wall_map
    LDY #LEVEL_HEADER_CORE
    LDA (zp_level_ptr),Y
    STA zp_wall_core
    LDY #LEVEL_HEADER_RIM
    LDA (zp_level_ptr),Y
    STA zp_wall_rim
    LDA #LO(wall_map)
    STA zp_wall_map
    LDA #HI(wall_map)
    STA zp_wall_map+1
    JSR draw_walls

    \ HUD: the title, then the level name.
    SEND_VDU title_vdu_bytes, title_vdu_bytes_end
    JSR print_level_name

    \ Put each player's tank at its start and draw it, saving the arena
    \ beneath.
    JSR place_players
    JSR show_sprites

    \ Tell the harness we have finished.
    LDA #BOOT_READY
    STA zp_boot_status

.idle
    JMP idle                   \ Nothing else to do yet.

\ ----------------------------------------------------------------------------
\ redraw_sprites -- test hook: move the tanks to their current positions
\
\ Restores the arena under every tank (in reverse order), then saves and
\ draws every tank at its current player_sx/sy/facing. Never returns.
\ ----------------------------------------------------------------------------

.redraw_sprites
    LDA #0
    STA zp_boot_status
    JSR hide_sprites
    JSR show_sprites
    LDA #BOOT_READY
    STA zp_boot_status
    JMP idle

\ ----------------------------------------------------------------------------
\ print_level_name -- print level zp_level's name in the HUD
\
\ On exit:  A, X, Y corrupted
\
\ Names are LEVEL_NAME_LENGTH (8) characters, space padded, which exactly
\ fills the HUD's eight text columns.
\ ----------------------------------------------------------------------------

.print_level_name
    SEND_VDU level_name_tab_vdu_bytes, level_name_tab_vdu_bytes_end

    \ X = zp_level * 8, the offset of this level's name in level_names.
    LDA zp_level
    ASL A
    ASL A
    ASL A
    TAX
    LDY #LEVEL_NAME_LENGTH     \ Y counts characters remaining.
.print_level_name_loop
    LDA level_names,X
    JSR OSWRCH                 \ OSWRCH preserves X and Y.
    INX
    DEY
    BNE print_level_name_loop
    RTS

.title_vdu_bytes
    \ Two lines of title text in the HUD, in text colour 3 (Y), centred in
    \ the eight HUD text columns.
    EQUB VDU_TEXT_COLOUR, 3
    EQUB VDU_TAB, HUD_TEXT_COLUMN + 1, 1
    EQUS "DON'T"
    EQUB VDU_TAB, HUD_TEXT_COLUMN, 2
    EQUS "DITHER!"
.title_vdu_bytes_end

.level_name_tab_vdu_bytes
    EQUB VDU_TAB, HUD_TEXT_COLUMN, 4   \ Level name on HUD text row 4.
.level_name_tab_vdu_bytes_end

\ ----------------------------------------------------------------------------
\ Shared modules and generated tables
\ ----------------------------------------------------------------------------

INCLUDE "asm/display.asm"
INCLUDE "asm/arena.asm"
INCLUDE "asm/walls.asm"
INCLUDE "asm/level.asm"
INCLUDE "asm/sprites.asm"
INCLUDE "build/generated/ink_tables.asm"
INCLUDE "build/generated/screen_tables.asm"
INCLUDE "build/generated/wall_tiles.asm"
INCLUDE "build/generated/level_data.asm"
INCLUDE "build/generated/sprite_data.asm"

.end

\ ----------------------------------------------------------------------------
\ Uninitialised buffers: after .end, so not saved to disc or loaded.
\ ----------------------------------------------------------------------------

.wall_map
    SKIP 128                   \ The current level's 32x32 wall bitmap.

\ Player state, indexed by player slot 0..MAX_PLAYERS-1.
.player_count     SKIP 1       \ Players in this level (2 or 4).
.player_sx        SKIP MAX_PLAYERS \ Footprint top-left superpixel.
.player_sy        SKIP MAX_PLAYERS
.player_facing    SKIP MAX_PLAYERS \ 0 = N, clockwise to 7 = NW.
.player_ink       SKIP MAX_PLAYERS \ 0 = C, 1 = M, 2 = Y, 3 = K.
.saved_sx         SKIP MAX_PLAYERS \ Where each saved background came from.
.saved_sy         SKIP MAX_PLAYERS
.sprites_shown    SKIP 1       \ Non-zero while sprites are on screen.

.sprite_save_buffers
    SKIP MAX_PLAYERS * SPRITE_FRAME_BYTES   \ The screen under each tank.

SAVE "DITHER", start, end, start
