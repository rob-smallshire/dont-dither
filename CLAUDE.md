# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Don't Dither! is a BBC Micro Model B game in 6502 assembly (beebasm), tested in
the Beebium emulator through its Python client and pytest. The design is in
`docs/dont_dither_game_design.md` (a rendering of the `.docx`, which is the
source). Decisions that refine or depart from it are recorded in
`docs/decisions.md`; add to it when a design decision is made.

## Commands

```bash
uv run dd-build                                   # generate tables + assemble -> build/dont-dither.ssd
uv run pytest                                     # all tests (builds the disc first)
uv run pytest tests/test_inks.py                  # pure-Python tests, no emulator
uv run pytest tests/test_boot.py::test_palette_maps_logical_colours_to_cmyk
uv run --group solver dd-solve-patterns           # re-solve data/ink_patterns.json (OR-tools CP-SAT)
uv run dd-preview-sprites                         # render sprites/tank.spr to build/design/sprites.png
uv run dd-preview-splats                          # render sprites/splats.spr to build/design/splats.png
uv run dd-render-music                            # the title theme -> build/music/splash_theme.wav
```

Screenshots from emulator tests land in `build/screenshots/` (`boot.png`,
`testcard.png`, `testcard_x3.png`).

beebasm 1.10 must be on the `PATH`. The Beebium client and headless server
come from PyPI (`beebium`, `beebium-server`) via the `test` dependency group.

## Architecture

**The framebuffer is the game state.** The arena is the left 256x256 pixels
of MODE 1 (byte columns 0-63), treated as 128x128 superpixels of 2x2 pixels.
Each superpixel's literal pattern encodes its ink state, a count tuple
(C,M,Y,K) summing to 4; there are 35 states, each with exactly one canonical
pattern. There is no separate ownership array. The HUD is byte columns 64-79.

**Programs.** One DFS disc holds several programs, each a beebasm source
that SAVEs a file of the same name (`PROGRAMS` in `tools/dontdither/build.py`):
`SPLASH` (`asm/splash.asm`, run by `!BOOT`: the title screen, which loads a
level set and runs the game), `DITHER` (`asm/main.asm`, the game) and `TCARD`
(`asm/testcard.asm`, the texture and wall test card, started with
`*RUN TCARD`) and `TUNE` (`asm/tune.asm`, the title music alone, `*RUN
TUNE`). The title screen plays music: `asm/music.asm` is a 50 Hz SN76489
player on the vsync event, the theme is `tools/dontdither/splash_theme.py`,
and `tools/dontdither/music.py` models the player tick by tick (the tests
compare the chip's registers). See `docs/music.md`. `LOGO` (screen bytes from `art/splash.png`, via
`tools/dontdither/splash.py`) and the level sets `LEVELS2`/`LEVELS4` are data
files. The loader puts a small logo (from `art/splash.png`) in the top
four HUD character rows, which the game never clears or draws over. The
full picture is in `docs/architecture.md`. Each program INCLUDEs
the shared modules it needs:
- `os.asm`, then `macros.asm` first (beebasm needs macros defined before use),
  then `zeropage.asm`;
- after the program's code: `display.asm`, `arena.asm`, `walls.asm` and the
  generated tables.

Labels are per program:
`BuildResult.labels["DITHER"]["zp_boot_status"]`.

**Walls** are whole character cells (8x8 pixels = 4x4 superpixels, a 32x32
grid) recorded in a 128-byte bitmap, MSB leftmost; collision/painting use the
bitmap, not screen decoding. `draw_walls` picks one of 16 tiles by the 4-bit
neighbour mask (N=1,E=2,S=4,W=8) and patches inner-corner pixels. The wall
colouring is per level: a (core, rim) pair of different inks, 12 in all
(`zp_wall_core`/`zp_wall_rim` = `WALL_INK_*`). Tiles are stored as rim masks;
each byte is drawn as `core EOR ((core EOR rim) AND mask)`.
`draw_walls_in_rect` draws part of the map, still taking neighbours from
the whole map. Cells outside the arena count as walls.
`tools/dontdither/walls.py` models this exactly and the tests compare every
wall cell byte-for-byte.

**Levels** are text files in `levels/` (format in `tools/dontdither/levels.py`),
compiled in filename order. A level stores one quadrant (`ROT4`) or half
(`ROT2`) of its walls as MOVE/DRAW lines in wall-cell coordinates, plus its
colouring, fill state and player 0's START. `asm/level.asm` interprets the
bytecode once per symmetric copy, rotating each plotted cell ((x, y) ->
(31 - y, x) per quarter turn) into a 128-byte `wall_map` buffer. So symmetry,
and hence fairness, is structural. `enter_level` in `asm/main.asm` fills the
arena, builds and draws the walls, and prints the level name.

**Sprites** (`asm/sprites.asm`): tanks are drawn straight into screen memory
with save-under. `hide_sprites` restores backgrounds in reverse player order,
`show_sprites` saves then draws in order; the world must only be read or
updated between the two. Frames (mask + select planes, from
`sprites/tank.spr`) are generated into `sprite_data.asm`; the inner loops use
self-modifying abs,X operands. `tools/dontdither/render.py` models the whole
arena with tanks for byte-exact tests.

**Painting** (`asm/paint.asm`): after movement, players fire in the same
rotating order. A shot walks its splat's ray tree (rotated per facing),
blocking nodes in walls or behind blocked parents, and applies one quantum
(round-robin victim) to each unblocked splat cell. A cell inside a tank's
drawn footprint is painted in that tank's save buffer and the tank is
flagged for redraw. `tools/dontdither/game.py` models all of it; tests
compare every arena byte with `render.arena_screen(level, model.cells)`
plus tanks.

**Keys** (`controls.py`, `asm/handoff.asm`): each player slot (C, M, Y, K)
has its own keyboard layout; any slot joins with its fire key, recording
its control in `session_controls` (`CONTROL_JOYSTICK` is reserved for
joining with a joystick's fire). The layouts are not in the game: SPLASH
fills a sealed block at &0CE0 (defaults, or a block kept across BREAK),
shows them, lets f1-f4 redefine them, and the game reads `key_layouts`
there. `test_keys.py` covers it.

**Ink reservoir** (`game.py`, `game.asm`, `hud.asm`): each shot uses a
splat from a 128-splat reservoir. With fire released, the tank's ground level
(own quanta over its footprint's centre four superpixels, DIV 4) sets its
speed (up to two steps a tick) and refill rate; with fire held it moves at
normal speed and does not refill. HUD gauges show the reservoirs. An AI
that runs dry refills on its own ink until it has 64 splats.

**Data flow from one source of truth:**

```
data/ink_patterns.json            canonical pattern per state (written by solve_patterns.py)
  -> tools/dontdither/inks.py     model: states, patterns, colour mapping, MODE 1 encoding
  -> tools/dontdither/gen_tables.py  -> build/generated/*.asm
       ink_tables (patterns, palette, STATE_*), screen_tables (bit_masks),
       wall_tiles (16 tiles, corner patches), testcard_data (from testcard.py),
       level_data (from levels/*.lvl), sprite_data (from sprites/tank.spr),
       game_data (controls, speeds), paint_data (state arithmetic, splat trees)
  -> asm/*.asm INCLUDE them; tools/dontdither/build.py runs beebasm from the project root
  -> build/dont-dither.ssd + build/labels/<PROGRAM>.txt
```

Change inks, palette or table layout in the Python model or generator, never
in generated files. `inks.LOGICAL_COLOUR` (K=0, C=1, M=2, Y=3) drives both the
VDU 19 palette records and the pattern bytes, so they cannot disagree.

**MODE 1 superpixel encoding** (used by the generator, the 6502 code and the
tests; they must stay consistent):
- Pixel p of a byte (0 = leftmost) has colour bit 1 at bit 7-p and bit 0 at
  bit 3-p.
- Superpixel (sx, sy) has its top raster byte at
  `&3000 + (sy DIV 4)*640 + (sx DIV 2)*8 + (sy AND 3)*2`. The bottom raster
  byte is the next address. Even sx uses the byte half masked by `&CC`; odd
  sx uses `&33`.
- `pattern_to_state` (256 entries, page-aligned) is indexed by a byte whose
  four pixels are TL, TR, BL, BR. The 6502 forms the index as
  `(top&CC)|((bottom&CC)>>2)` for even sx, and `((top&33)<<2)|(bottom&33)`
  for odd sx. `tests/test_inks.py` checks this formula against the model.

**The canonical table** is solved exactly, not hand-picked:
- **Hard constraints:** 2+2 states are checkerboards, 2+1+1 states have the
  doubled ink on a diagonal (no stripes), and colour cycling C->M->Y->K
  equals a clockwise 90 degree tile rotation up to a one-pixel texture
  translation.
- **Objective:** the solver then minimises pixel churn per one-quantum transfer.
  The proved result is 78/32/6/4 edges changing 1/2/3/4 pixels.
- `tests/test_inks.py` asserts these properties, so any edit to the table
  must keep them or deliberately change the tests.
- The table supersedes the one in
  `docs/dont_dither_35_minimal_churn_patterns.md`.

**Tests link to the assembly by label.**
- beebasm's `-d -labels` output is parsed into `BuildResult.labels`.
- Zero-page variables are declared with `ORG`/`SKIP` (not as `=` constants)
  so that they appear in the labels. `zp_boot_status` lives in the MOS user
  block &70-&8F. Everything else is in &00-&6F, BASIC's workspace, which is
  free because our programs never return to BASIC.
- Tests look up addresses such as `zp_boot_status` and `pattern_to_state` by
  name, never hard-coded. Only labels are exported, not `=` constants.

**Beebium fixtures** (`tests/conftest.py`):
- `testcard` is like `booted_game` but `*RUN`s TCARD from the BASIC prompt.
- The title screen (SPLASH) asks "2 or 4" players and loads that level set
  (LEVELS2 or LEVELS4); DITHER's loader copies it into `level_area`.
  `load_game(bbc, build, players)` answers at the `splash_key` label. Levels are addressed within a set: tests covering every level
  parametrise over `SET_LEVELS` (players, index) and boot in that mode.
- The game boots into `select_players` (asm/flow.asm). `boot_game` stops
  there and enters level 0 directly (default session: players 1 and 2
  human), stopping just before its first tick, at `main_loop`, with the
  screen displayed (`show_display` parks the CPU in `hold_display`), so AI
  tanks have not moved. Set `round_length_ticks` *before* entering a level. `Game.start` gives players 3 and 4 to the AI, as
  the game does; tests scripting every player set `player.ai = False`.
- The game runs a 25 Hz main loop. `align_to_tick` stops it at `tick_done`
  (between ticks, tanks drawn) and `step_ticks` runs whole ticks; between
  ticks tests may change player state or set a player's control to
  scripted and write `player_input`. `tools/dontdither/game.py` is the
  model the 6502 simulation must match tick for tick.
- `enter_level` starts a level and stops at `main_loop` before its first
  tick, so a `Game.start(level)` model stays exactly in step. It (and
  `boot_game`) writes `DEFAULT_RANDOM_STATE` to `random_state` first: AI
  players face random directions, drawn in `place_players`. Tests shorten
  rounds by writing `round_length_ticks` first; the round ends at the
  `round_over` label.
- `enter_routine` jumps the game to a routine (e.g. `enter_level` after
  setting `zp_level`) from `tick_done`. `hold_display` parks the CPU so a
  field can be scanned out with no redraw in progress. It runs to the `idle` label first, because
  cycle-based stepping (`run_for_emulated_seconds`) can stop the CPU
  mid-instruction, and writing PC then corrupts the in-flight instruction
  (beebium #106). Always reach an instruction boundary (`run_to` or
  `debugger.step(1)`) before writing registers.
- After a program is ready the harness runs two more frames: screen text and
  captured frames reflect what has been *displayed*, not screen memory.
- `launch_bbc` is a factory, and `bbc` shadows the plugin fixture of the same
  name.
- `booted_game` is module-scoped. It boots the disc with Shift-Break, runs in
  emulated time until `zp_boot_status == BOOT_READY`, and leaves the machine
  stopped. Tests that share it must only observe.
- Machines use the `model-b-disc` preset (Acorn 1770 FDC, DFS 2.26 in
  slot 14). The default Model B has no disc controller.
- This works around beebium issues #104 (`--preset` needs a file path) and
  #105 (the plugin fixture is not configurable).
- Emulator tests save screenshots to `build/screenshots/`.

## Conventions

- Use `uv` for all Python work.
- Comment all assembly comprehensively:
  - file headers covering purpose and memory use;
  - block comments explaining the approach;
  - line comments explaining intent, register and zero-page usage, and
    hardware/OS details.
- Generated `.asm` files get explanatory headers from their generator.
- Test first. Model properties go in pure-Python tests. Behaviour on the
  machine goes in emulator tests that observe memory and screen.
- Use `_filepath`, `_dirpath`, `_filename`, `_dirname` suffixes.

## Target constraints

- The main block starts with the ink tables, so the page-aligned
  `pattern_to_state` needs no padding. `superpixel_row_lo/hi` are built at
  start-up (`build_superpixel_rows`) into the buffers, not loaded.
- Stock 32K Model B with DFS. A loader stub at the end of `asm/main.asm`
  (DFS loads the file at &3100) copies the main block to &0E00 up
  (`GUARD &3000`, over DFS workspace), the low block of tables (paint data,
  game data, HUD font) to &0400-&07FF, and the level set to `level_area`,
  which runs from the end of the main block (not page-aligned) to &2FFF:
  code growth shrinks it. Keep an eye on its size (about 14 levels today).
  Uninitialised buffers are at &0900-&0CDF. The key layouts are at &0CE0
  (`asm/handoff.asm`): SPLASH (at &1900) fills them, the game reads them,
  and they survive BREAK. &0800 is left to
  the MOS for sound. The MODE 1 screen is &3000-&7FFF. Zero page &00-&6F
  is nearly full: put rarely used variables in the buffer area.
  Sideways RAM only if we hit the limit, and raise it with the user first.
- Never print through the MOS in the bottom-right text cell (row 31,
  column 39): the MOS would scroll the screen and move it in memory.
- User zero page is &70-&8F.
- 25 Hz game tick.
- Keyboard input only for now: Beebium has no joystick/ADC emulation, and the
  SPItFIRE four-joystick interface comes later.

## Beebium help

A peer agent session named `beebium-architect` can answer questions about
Beebium and file Beebium issues. Ask it rather than silently working around
emulator problems. The Beebium source is at `~/Code/beebium`. BBC Micro
manuals are in markdown under `~/Code/beebium/docs/manuals_text`. The
annotated MOS 1.20 disassembly is at `~/Code/os120`.
