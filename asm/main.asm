\ ============================================================================
\ main.asm -- Don't Dither! for the BBC Micro Model B
\
\ Build with `uv run dd-build` (runs beebasm from the project root, which is
\ why INCLUDE paths are relative to the root). The disc's !BOOT runs this
\ program, saved as DITHER.
\
\ CURRENT STAGE: tanks driven by the keyboard. The program
\   1. selects MODE 1, hides the cursor, programs the CMYK palette and makes
\      the cursor keys plain keys,
\   2. enters level 0 (see enter_level): fills the arena with the level's
\      initial ink state, expands the level's walls into the wall map under
\      its symmetry, draws them in the level's colouring, shows the title
\      and level name in the HUD, and draws each player's tank at its start,
\   3. sets zp_boot_status to BOOT_READY and runs the 25 Hz main loop, in
\      which players move and turn under keyboard control (player 1: W A S
\      D, player 2: cursor keys; see tools/dontdither/controls.py).
\
\ Test hooks: the label tick_done is reached once per tick, between ticks,
\ with the tanks drawn; tests step the simulation by running to it. Stopped
\ there, a test may change player state (position, facing, control source,
\ scripted input) for the next tick, or jump (by setting PC) to
\   enter_level     after setting zp_level, to start any level;
\   hold_display    to scan out fields with no redraw in progress (return by
\                   running to hold_display and setting PC to tick_done).
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
    JSR init_keyboard          \ Cursor keys and COPY as plain keys.
    JSR init_beam_timer        \ User VIA timer 2 as a beam clock.

    LDA #0                     \ Start with the first level.
    STA zp_level
    \ Fall through into enter_level.

\ ----------------------------------------------------------------------------
\ enter_level -- draw level zp_level and start playing it
\
\ On entry:  zp_level = level number (0..LEVEL_COUNT-1); display initialised
\ Never returns: sets zp_boot_status to BOOT_READY and runs the main loop.
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

    \ Tell the harness we have finished setting up.
    LDA #BOOT_READY
    STA zp_boot_status
    \ Fall through into the main loop.

\ ----------------------------------------------------------------------------
\ main_loop -- one 25 Hz tick per iteration (see game.asm)
\ ----------------------------------------------------------------------------

.main_loop
    JSR wait_for_tick          \ Two vertical syncs...
    JSR start_beam_timer       \ ...then time the beam from here.
    JSR read_inputs            \ player_input from keyboard or script.
    JSR update_players         \ Move and turn the tanks.
    JSR render_sprites         \ Redraw those that changed, racing the beam.
    INC tick_count             \ Count ticks (16 bits).
    BNE tick_done
    INC tick_count+1
.tick_done
    JMP main_loop              \ Tests stop here, between ticks.

\ ----------------------------------------------------------------------------
\ hold_display -- test hook: spin without touching the screen
\
\ Tests jump here from tick_done to let whole video fields be scanned out
\ with no redraw in progress, then jump back to tick_done.
\ ----------------------------------------------------------------------------

.hold_display
    JMP hold_display

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
INCLUDE "asm/game.asm"
INCLUDE "build/generated/ink_tables.asm"
INCLUDE "build/generated/screen_tables.asm"
INCLUDE "build/generated/wall_tiles.asm"
INCLUDE "build/generated/level_data.asm"
INCLUDE "build/generated/sprite_data.asm"
INCLUDE "build/generated/game_data.asm"

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
.player_control   SKIP MAX_PLAYERS \ CONTROL_NONE, _KEYS_A, _KEYS_B, _SCRIPTED.
.player_input     SKIP MAX_PLAYERS \ This tick's input byte (see game.asm).
.player_accumulator SKIP MAX_PLAYERS \ Movement speed accumulator.
.drawn_facing     SKIP MAX_PLAYERS \ Facing each tank was last drawn with.
.render_count     SKIP 1       \ render_sprites: tanks to redraw this tick.
.render_list      SKIP MAX_PLAYERS \ render_sprites: their player numbers,
.render_key       SKIP MAX_PLAYERS \ and lowest rows, sorted.
.tick_count       SKIP 2       \ Ticks since the level started.

.sprite_save_buffers
    SKIP MAX_PLAYERS * SPRITE_FRAME_BYTES   \ The screen under each tank.

SAVE "DITHER", start, end, start
