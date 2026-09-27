\ ============================================================================
\ main.asm -- Don't Dither! for the BBC Micro Model B
\
\ Build with `uv run dd-build` (runs beebasm from the project root, which is
\ why INCLUDE paths are relative to the root). The disc's !BOOT runs this
\ program, saved as DITHER.
\
\ CURRENT STAGE: a playable game. Players join by pressing fire (flow.asm);
\ a session plays every level, each a round in which tanks, driven by the
\ keyboard or the computer and blocked by walls and each other, fire splats
\ that paint the arena until the clock runs out; the territory is then
\ tallied, revealed as a bar chart, and points awarded by rank. With no
\ players the computer plays a demo until a key is pressed. The program
\   1. selects MODE 1, hides the cursor, programs the CMYK palette and makes
\      the cursor keys plain keys,
\   2. enters level 0 (see enter_level): fills the arena with the level's
\      initial ink state, expands the level's walls into the wall map under
\      its symmetry, draws them in the level's colouring, shows the title
\      and level name in the HUD, and draws each player's tank at its start,
\   3. sets zp_boot_status to BOOT_READY and runs the 25 Hz main loop, in
\      which players move, turn and fire under keyboard control (player 1:
\      W A S D and SHIFT, player 2: cursor keys and COPY; see
\      tools/dontdither/controls.py), painting the arena.
\
\ Test hooks: the label tick_done is reached once per tick, between ticks,
\ with the tanks drawn; tests step the simulation by running to it. Stopped
\ there, a test may change player state (position, facing, control source,
\ scripted input) for the next tick, or jump (by setting PC) to
\   enter_level     after setting zp_level, to start any level;
\   hold_display    to scan out fields with no redraw in progress (return by
\                   running to hold_display and setting PC to tick_done).
\
\ Memory map:
\   &0000-&006F  zero page, former BASIC workspace (see zeropage.asm)
\   &0070-&008F  zero page reserved for user programs
\   &0400-&07FF  low block: initialised tables (paint data), in BASIC's
\                language workspace
\   &0800-&08FF  left to the MOS (sound workspace)
\   &0900-&0CFF  uninitialised buffers (wall map, player state, sprite save
\                buffers, tally), over MOS buffers the game does not use
\   &0E00-&2FFF  main block: code and tables. This reclaims the DFS
\                workspace (&0E00-&18FF): the game never uses the disc once
\                loaded.
\   &3000-&7FFF  MODE 1 screen memory (20 KB)
\
\ Loading: DFS cannot load a file into its own workspace, so the file
\ DITHER is a loader stub followed by the main and low blocks. DFS loads it
\ at LOADER_ADDRESS (in the screen area, unused until MODE 1 is selected)
\ and runs the stub, which copies the blocks into place and jumps to start.
\ ============================================================================

INCLUDE "asm/os.asm"
INCLUDE "asm/macros.asm"
INCLUDE "asm/zeropage.asm"

GAME_ADDRESS   = &0E00         \ Where the game runs (main block).
LOW_BLOCK_ADDRESS = &0400      \ Where its low block of tables goes.
LOADER_ADDRESS = &3100         \ Where DFS loads the file (see the loader).

ORG GAME_ADDRESS
GUARD MODE1_SCREEN_BASE        \ Assembly fails if code, data or buffers
                               \ reach the screen.

.start
    \ Mark boot as in progress. RAM contents at power-on are not guaranteed,
    \ so the harness must never see a stale BOOT_READY.
    LDA #0
    STA zp_boot_status

    JSR init_display           \ MODE 1, cursor off, CMYK palette.
    JSR init_keyboard          \ Cursor keys and COPY as plain keys; no
                               \ Escape.
    JSR init_beam_timer        \ User VIA timer 2 as a beam clock.

    LDA #LO(ROUND_TICKS)       \ Default round length (tests may change it
    STA round_length_ticks     \ before entering a level).
    LDA #HI(ROUND_TICKS)
    STA round_length_ticks+1

    LDA #%11                   \ Default session: players 1 and 2 human
    STA session_humans         \ (tests enter levels directly with this).

    JMP select_players         \ Let players join; then play (flow.asm).

\ ----------------------------------------------------------------------------
\ enter_level -- draw level zp_level and start playing it
\
\ On entry:  zp_level = level number (0..LEVEL_COUNT-1); session_humans and
\            round_length_ticks set; display initialised
\ Never returns: sets zp_boot_status to BOOT_READY and runs the main loop.
\ ----------------------------------------------------------------------------

.enter_level
    LDA #0                     \ Not ready while drawing (matters when a test
    STA zp_boot_status         \ jumps here to draw another level).
    JSR draw_level
    JSR start_round            \ Set and show the round clock.
    LDA #BOOT_READY            \ Tell the harness we have finished setting
    STA zp_boot_status         \ up.
    JMP main_loop

\ ----------------------------------------------------------------------------
\ draw_level -- draw level zp_level with its tanks at their starts
\
\ Clears the HUD, fills the arena, builds and draws the walls, shows the
\ title and level name, and places and draws the players.
\ ----------------------------------------------------------------------------

.draw_level
    JSR clear_hud
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
    JMP show_sprites           \ Tail call.

\ ----------------------------------------------------------------------------
\ clear_hud -- blank the HUD (byte columns 64..79 of every character row)
\ ----------------------------------------------------------------------------

.clear_hud
    LDA #LO(MODE1_SCREEN_BASE + 64 * 8)
    STA zp_screen_ptr
    LDA #HI(MODE1_SCREEN_BASE + 64 * 8)
    STA zp_screen_ptr+1
    LDX #MODE1_CHAR_ROWS
.clear_hud_row
    LDA #0
    LDY #127                   \ 16 byte columns x 8 lines = 128 bytes.
.clear_hud_byte
    STA (zp_screen_ptr),Y
    DEY
    BPL clear_hud_byte
    LDA zp_screen_ptr          \ Next character row, 640 bytes on.
    CLC
    ADC #LO(MODE1_ROW_BYTES)
    STA zp_screen_ptr
    LDA zp_screen_ptr+1
    ADC #HI(MODE1_ROW_BYTES)
    STA zp_screen_ptr+1
    DEX
    BNE clear_hud_row
    RTS

\ ----------------------------------------------------------------------------
\ main_loop -- one 25 Hz tick per iteration (see game.asm)
\ ----------------------------------------------------------------------------

.main_loop
    JSR check_demo_exit        \ In demo mode, a player key returns to
                               \ player selection.
    JSR wait_for_tick          \ Two vertical syncs...
    JSR start_beam_timer       \ ...then time the beam from here.
    JSR read_inputs            \ player_input from keyboard or script.
    JSR update_players         \ Move and turn the tanks.
    JSR fire_players           \ Shoot: splats paint the arena.
    JSR render_sprites         \ Redraw tanks that changed, racing the beam.
    INC tick_count             \ Count ticks (16 bits).
    BNE main_loop_clock
    INC tick_count+1
.main_loop_clock
    JSR tick_clock             \ Count the tick off the round clock.
    BCC tick_done
    JMP end_of_round           \ Time up: tally and reveal. Never returns.
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
INCLUDE "asm/paint.asm"
INCLUDE "asm/hud.asm"
INCLUDE "asm/ai.asm"
INCLUDE "asm/flow.asm"
INCLUDE "build/generated/ink_tables.asm"
INCLUDE "build/generated/screen_tables.asm"
INCLUDE "build/generated/wall_tiles.asm"
INCLUDE "build/generated/level_data.asm"
INCLUDE "build/generated/sprite_data.asm"
INCLUDE "build/generated/game_data.asm"
INCLUDE "build/generated/hud_font.asm"

.end

\ ----------------------------------------------------------------------------
\ Low block: initialised tables in BASIC's language workspace (&0400-&07FF),
\ which is free once the game runs (it never returns to BASIC). The loader
\ copies them here along with the main block.
\ ----------------------------------------------------------------------------

ORG LOW_BLOCK_ADDRESS
GUARD &0800                    \ &0800-&08FF is the MOS sound workspace.

.low_start
INCLUDE "build/generated/paint_data.asm"
.low_end

\ ----------------------------------------------------------------------------
\ Uninitialised buffers at &0900-&0CFF: MOS pages normally holding the RS423
\ and cassette buffers, extended envelopes and speech (&0900-&0AFF), soft
\ key definitions (&0B00) and user-defined characters 224-255 (&0C00). The
\ game uses none of those. Nothing here is saved to disc or loaded; the game
\ initialises what it uses.
\ ----------------------------------------------------------------------------

ORG &0900
GUARD &0D00                    \ &0D00 holds the NMI routine and ROM tables.

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
.player_cooldown  SKIP MAX_PLAYERS \ Ticks until the player may fire again.
.player_variant   SKIP MAX_PLAYERS \ The player's next splat variant.
.player_last_victim SKIP MAX_PLAYERS \ Round-robin: last ink painted over.
.player_repaint   SKIP MAX_PLAYERS \ Non-zero: redraw the tank (the arena
                               \ under it was painted).
.splat_blocked    SKIP SPLAT_MAX_NODES \ fire_splat: which tree nodes are
                               \ shadowed by walls.
.round_length_ticks SKIP 2     \ Length of a round, in ticks.
.round_ticks_left SKIP 2       \ Ticks until the round ends.
.clock_ticks      SKIP 1       \ Ticks until the clock shows a second less.
.clock_seconds    SKIP 1       \ The clock's display, m:ss.
.clock_minutes    SKIP 1
.state_histogram_lo SKIP STATE_COUNT \ count_territory: superpixels in each
.state_histogram_hi SKIP STATE_COUNT \ ink state.
.total_quanta     SKIP 2       \ 4 per open cell.
.player_quanta_lo SKIP MAX_PLAYERS \ Each player's quanta at the end.
.player_quanta_hi SKIP MAX_PLAYERS
.player_percent   SKIP MAX_PLAYERS \ ...and share, in whole percent.
.player_revealed  SKIP MAX_PLAYERS \ reveal_scores: bar drawn yet?
.ai_direction     SKIP MAX_PLAYERS \ Each AI's current direction.
.ai_last_input    SKIP MAX_PLAYERS \ Each AI's last decision.
.ai_scores        SKIP 8       \ ai_input: score of each direction.
.session_humans   SKIP 1       \ Bit per player slot: played by a human.
.session_joined   SKIP 1       \ select_players: who has pressed fire.
.session_level    SKIP 1       \ The session's current level.
.session_points   SKIP MAX_PLAYERS \ Points so far this session.
.session_seconds  SKIP 1       \ Countdown / pause seconds left.
.session_fields   SKIP 1       \ Fields left in the current second.

\ Working variables of the round clock and tally (hud.asm). Used rarely, so
\ kept out of zero page.
.tally_value      SKIP 2       \ 16-bit working value (clock, quanta).
.tally_product    SKIP 3       \ percent_of_total: quanta * 100, 24 bits.
.tally_shift      SKIP 3       \ percent_of_total: shifted quanta, 24 bits.
.bar_best         SKIP 1       \ reveal_scores: smallest / largest share.
.bar_left         SKIP 1       \ grow_bar: the bar's two bytes per line.
.bar_right        SKIP 1
.bar_offset       SKIP 2       \ HUD byte column * 8.
.bar_height       SKIP 1       \ grow_bar: lines still to grow.
.bar_line         SKIP 1       \ Raster line being drawn.
.bar_byte         SKIP 1       \ draw_bar_line: left byte.
.label_colour     SKIP 1       \ Labels: colour byte.
.label_column     SKIP 1       \ Labels: byte column of the next digit.
.label_digit      SKIP 1       \ draw_digit: glyph byte offset.
.label_units      SKIP 1       \ grow_bar: units digit (ASCII).

.sprite_save_buffers
    SKIP MAX_PLAYERS * SPRITE_FRAME_BYTES   \ The screen under each tank.

\ ============================================================================
\ Loader
\
\ Assembled to run at LOADER_ADDRESS, where DFS loads the file, and
\ followed in the file by copies of the main block (start..end) and the low
\ block (low_start..low_end), placed there by COPYBLOCK. It:
\   1. closes any *EXEC file: the disc's !BOOT is still open as an *EXEC
\      file, and the filing system must not touch its buffers (in the DFS
\      workspace we are about to overwrite) ever again;
\   2. copies each block to where it was assembled, whole pages at a time.
\      Destinations are below the source, so a forward copy is safe even if
\      they overlapped. Copying a partial final page in full only writes
\      beyond a block into memory the game initialises before use (below
\      the screen for the main block, below &0800 for the low block);
\   3. jumps to start.
\ It uses zero page &00-&03 (BASIC's, free once we run) as copy pointers.
\ ============================================================================

CLEAR LOADER_ADDRESS, &7C00    \ Undo the game region's guard for this part.
ORG LOADER_ADDRESS
GUARD &7C00                    \ The file must not reach MODE 7 screen memory,
                               \ which is where the loading screen is.

LOADER_SOURCE = &00            \ Copy pointers in zero page.
LOADER_DEST   = &02
MAIN_BLOCK_PAGES = (end - start + 255) DIV 256
LOW_BLOCK_PAGES  = (low_end - low_start + 255) DIV 256

.loader
    LDA #&77                   \ OSBYTE &77: close any SPOOL and EXEC files.
    JSR OSBYTE

    LDA #LO(loader_main_image) \ The main block to GAME_ADDRESS...
    STA LOADER_SOURCE
    LDA #HI(loader_main_image)
    STA LOADER_SOURCE+1
    LDA #LO(start)
    STA LOADER_DEST
    LDA #HI(start)
    STA LOADER_DEST+1
    LDX #MAIN_BLOCK_PAGES
    JSR loader_copy

    LDA #LO(loader_low_image)  \ ...and the low block to &0400.
    STA LOADER_SOURCE
    LDA #HI(loader_low_image)
    STA LOADER_SOURCE+1
    LDA #LO(low_start)
    STA LOADER_DEST
    LDA #HI(low_start)
    STA LOADER_DEST+1
    LDX #LOW_BLOCK_PAGES
    JSR loader_copy

    JMP start

\ loader_copy: copy X pages from LOADER_SOURCE to LOADER_DEST.
.loader_copy
    LDY #0
.loader_copy_byte
    LDA (LOADER_SOURCE),Y
    STA (LOADER_DEST),Y
    INY
    BNE loader_copy_byte
    INC LOADER_SOURCE+1        \ Next page of both.
    INC LOADER_DEST+1
    DEX
    BNE loader_copy_byte
    RTS

.loader_main_image
COPYBLOCK start, end, loader_main_image
loader_low_image = loader_main_image + (end - start)
COPYBLOCK low_start, low_end, loader_low_image

SAVE "DITHER", loader, loader_low_image + (low_end - low_start), loader
