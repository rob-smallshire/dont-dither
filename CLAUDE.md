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
`DITHER` (`asm/main.asm`, run by `!BOOT`) and `TCARD` (`asm/testcard.asm`, the
texture and wall test card, started with `*RUN TCARD`). Each program INCLUDEs
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

**Data flow from one source of truth:**

```
data/ink_patterns.json            canonical pattern per state (written by solve_patterns.py)
  -> tools/dontdither/inks.py     model: states, patterns, colour mapping, MODE 1 encoding
  -> tools/dontdither/gen_tables.py  -> build/generated/*.asm
       ink_tables (patterns, palette, STATE_*), screen_tables (row addresses),
       wall_tiles (16 tiles, corner patches), testcard_data (from testcard.py),
       level_data (from levels/*.lvl)
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
- `enter_routine` jumps an idling program to a routine (e.g. `enter_level`
  after setting `zp_level`). It runs to the `idle` label first, because
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

- Stock 32K Model B with DFS. The code currently loads at &1900 (`GUARD
  &3000`), and the MODE 1 screen is &3000-&7FFF.
- The plan is to load from disc, then reclaim DFS workspace below &1900.
  Sideways RAM only if we hit the limit, and raise it with the user first.
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
