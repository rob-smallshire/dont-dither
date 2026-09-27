# Don't Dither! — Architecture and Implementation

This document describes how *Don't Dither!* is built: the toolchain, the
6502 program and its memory layout, each subsystem, the Python models that
specify it, and how it is tested in the Beebium emulator. It complements:

- `dont_dither_game_design.md`, the original design (the `.docx` is the source);
- `decisions.md`, the design decisions taken since, which override the design
  where they differ;
- `README.md` and `CLAUDE.md` at the project root: quick start and working
  conventions.

---

## 1. The game in brief

A territory game for a stock 32 KB BBC Micro Model B with DFS. Two or four
tanks drive round a walled arena firing splats of ink. The arena is MODE 1
(320×256, four colours), with the palette set to cyan, magenta, yellow and
black. The left 256×256 pixels are the arena, a 128×128 grid of 2×2-pixel
*superpixels*; the right 64 pixels are the HUD.

**The screen is the game state.** Each superpixel's 2×2 pattern *is* its
ownership: one of the 35 ways of sharing four quanta between C, M, Y and K.
There is no separate territory array. A shot moves each target cell one
quantum towards the shooter's ink, so territory builds up gradually from the
grey (1,1,1,1) start.

A session plays each level of the chosen set as a timed round. At the end of
a round the territory is tallied and revealed as a bar chart, and points are
awarded by rank.

---

## 2. Toolchain and repository

| Tool | Role |
|---|---|
| beebasm 1.10 | assembles the 6502 source straight onto a DFS `.ssd` |
| Python 3.12+ with `uv` | build, data generation, models, tests |
| Beebium (PyPI `beebium` and `beebium-server`) | headless emulator driven from pytest |
| OR-tools CP-SAT (the `solver` dependency group) | solves the ink pattern table |
| Pillow | previews, splash conversion |

| Path | Contents |
|---|---|
| `asm/` | 6502 source. `main.asm` is the game; `splash.asm` the title screen; `testcard.asm` the test card; the rest are modules |
| `tools/dontdither/` | Python: build, generators, and the models that specify the game |
| `data/ink_patterns.json` | the canonical 2×2 pattern of each of the 35 ink states |
| `levels/*.lvl` | level sources |
| `sprites/tank.spr`, `sprites/splats.spr` | the tank and splat pictures, as editable ASCII art |
| `art/splash.png` | the title logo, converted by the build |
| `tests/` | pytest suite (pure-model tests and emulator tests) |
| `build/` | generated sources, the disc image, labels, screenshots, design previews |

### Commands

```bash
uv run dd-build                           # generate, assemble -> build/dont-dither.ssd
uv run pytest                             # everything (about 7 minutes)
uv run pytest tests/test_inks.py          # a pure-model file, no emulator
uv run --group solver dd-solve-patterns   # re-solve data/ink_patterns.json
uv run dd-preview-sprites                 # build/design/sprites.png
uv run dd-preview-splats                  # build/design/splats.png
```

---

## 3. The build

`tools/dontdither/build.py`:

1. **Generate** sources into `build/generated/` (`gen_tables.generate_all`).
   Everything derived from data is generated, never hand-written:

   | File | From | Contents |
   |---|---|---|
   | `ink_tables.asm` | `data/ink_patterns.json`, `inks.py` | palette VDU bytes, `state_top_bytes`/`state_bottom_bytes`, `pattern_to_state` (256, page-aligned), `STATE_*` constants |
   | `screen_tables.asm` | — | `bit_masks` (the superpixel row tables are built at start-up) |
   | `wall_tiles.asm` | `walls.py` | 16 rim-mask tiles, corner patches, `WALL_INK_*` |
   | `sprite_data.asm` | `sprites/tank.spr` | 16 frames (8 facings × 2 alignments) as mask and select planes, footprint masks, ink bytes |
   | `game_data.asm` | `game.py`, `controls.py`, `ai.py` | speeds, direction tables, key layouts, AI constants and samples, round lengths |
   | `paint_data.asm` | ink table, `sprites/splats.spr` | ink-state arithmetic tables and splat ray trees |
   | `hud_font.asm` | `hud_font.py` | 3×5 digit font |
   | `level_format.asm` | `gen_tables.py` | level-set layout, level opcodes and header offsets |
   | `wall_ink_bytes.asm` | `walls.py` | `WALL_INK_*` for the level-set files |
   | `testcard_data.asm` | `testcard.py` | test card layout |
   | `logo.bin`, `logo.asm`, `splash_data.asm` | `art/splash.png` via `splash.py` | the logo's screen bytes and the title-screen palette |
   | `hud_logo.bin`, `hud_logo.asm` | `art/splash.png` via `splash.py` | the small HUD logo, 4 character rows × 128 bytes, and its constants |
   | `levels2.asm`, `levels4.asm` | `levels/*.lvl` | the level sets (generated after the game is assembled; see below) |

2. **Assemble** each entry in `PROGRAMS` onto one disc, from the project root
   (beebasm resolves `INCLUDE` paths from its working directory). The first
   entry, `SPLASH`, gets the `!BOOT`; later files are added with `-di`/`-do`
   through a staging copy. Each file's labels go to
   `build/labels/<NAME>.txt`. They are parsed into `BuildResult.labels`, and
   tests find every address by label.

3. **Level sets.** Their load location is the game's `level_area`, known
   only once `DITHER` is assembled. The build reads it from `DITHER`'s
   labels, then generates and assembles `LEVELS2` and `LEVELS4` to run
   there, saved with a load address of `LEVEL_TEMP` (&6000).

Disc files: `SPLASH`, `DITHER`, `TCARD`, `LOGO`, `LEVELS2`, `LEVELS4`.

Zero-page variables are declared with `ORG`/`SKIP`, not `=`, so that they
appear in the labels. beebasm exports labels, not `=` constants.

---

## 4. Loading and start-up

```
!BOOT ──► SPLASH (&0900)
            MODE 1, CMYK palette, *LOAD LOGO into screen memory
            the aim, each keyboard player's keys, how ink works
            "Press 2 for two players / or 4 for four players"
            key 2|4 ──► palette to black
                        *LOAD LEVELS2|LEVELS4  (to LEVEL_TEMP = &6000)
                        *RUN DITHER            (loads at &3100)
          DITHER loader (&3100)
            close *EXEC; copy main block ─► &0E00
                          low block  ─► &0400
                          level set  ─► level_area
                          HUD logo   ─► top 4 HUD rows (stays for good)
            JMP start
          start: clear screen around the logo, palette, *FX4,1, *FX229,1,
                 beam timer ─► select_players
```

- **Why a loader stub.** DFS cannot load a file into its own workspace
  (&0E00–&18FF), and the game lives there. So `DITHER` is a stub followed
  by images of the main and low blocks, placed with `COPYBLOCK`. The stub
  copies them down whole pages at a time; destinations are below the
  sources, so forward copies are safe.
- **Why `SPLASH` is separate.** `DITHER` loads at &3100, which is MODE 1
  screen memory, so it could not show a picture. `SPLASH` runs at &0900
  (MOS buffer pages unused at boot) and draws the logo by loading
  ready-made screen bytes.
- **The HUD logo** is a 60-pixel-wide copy of the logo, cropped to the
  artwork, 512 bytes at the end of the `DITHER` file. The loader copies it
  into the top four character rows of the HUD, last, because that part of
  the screen lies over the main block's image. From then on only the
  screen holds it: `clear_hud` starts below it and nothing draws there,
  so it costs no memory. For the same reason `start` does not select
  MODE 1 again (that would clear it). `SPLASH` has already done so, and
  `start` clears the arena and the HUD below the logo instead. Run any
  other way, for example by `*RUN DITHER` from BASIC, `start` selects
  MODE 1 and goes without the logo.
- **Why the palette goes black.** The loads that follow go through screen
  memory, and blacking out the palette hides that.
- **After loading, no disc access.** The game overwrites the DFS
  workspace, so the disc can't be used again. `SPLASH` therefore makes the
  mode choice and loads the level set first. The game closes the `*EXEC`
  file and makes Escape an ordinary key (`*FX229,1`), so no filing-system
  code runs again. To change mode, press Break and reload.

---

## 5. Memory map

| Range | Use |
|---|---|
| &00–&6F | zero page: game variables (BASIC's area; the game never returns to BASIC). Nearly full: top used &6B |
| &70–&8F | MOS user zero page: `zp_boot_status` only (polled by tests from boot) |
| &0400–&07FF | **low block**: initialised tables (paint data, game data, HUD digit font; about 970 bytes), copied by the loader |
| &0800–&08FF | left to the MOS (sound workspace) |
| &0900–&0CFF | **buffers** (uninitialised): superpixel row address tables (built at start-up), wall map, player state, sprite save buffers, tally and session variables. `SPLASH` runs here before the game |
| &0D00–&0DFF | left alone (DFS NMI routine, ROM tables) |
| &0E00–&2D08 | **main block**: ink tables first (so the page-aligned `pattern_to_state` needs no padding), then code and tables |
| &2D09–&2FFF | **level area**: the loaded level set. It starts right after the main block (not page-aligned, so nothing is lost to padding) and shrinks as code grows. The loader's whole-page copy runs a few bytes on into screen memory, which `start` clears |
| &3000–&7FFF | MODE 1 screen (the loader and level set pass through here while loading) |

At the last build (with random AI facings): the level area is 759 bytes;
56 bytes free in the low block; about 190 in the buffers. Building the superpixel row tables at start-up
freed 256 bytes of the main block, which the reservoir then used. A level
costs about 40–55 bytes plus its title, and a set's header 66 bytes, so
759 bytes hold about 14 levels. Candidates for more room: store sprite
frames at one alignment and shift at draw time (saves about 768 bytes),
move code into the low block, or trim code.

---

## 6. Display, inks and the canonical patterns

- **Inks → logical colours:** K=0 (so screen clears are black), C=1, M=2,
  Y=3. Physical colours K=0, C=6, M=5, Y=3. `inks.py` is the single source;
  it generates both the palette and the patterns.
- **MODE 1 byte layout:** pixel *p* (0 = leftmost) has colour bit 1 at bit
  7−p and bit 0 at bit 3−p.
- **Superpixel addressing:** the top raster byte of superpixel (sx, sy) is
  at `&3000 + (sy DIV 4)*640 + (sx DIV 2)*8 + (sy AND 3)*2`, and the bottom
  byte is the next address. Even sx use the byte half masked by `&CC`, odd
  sx the half masked by `&33`. `superpixel_row_lo/hi[sy]` tables hold the
  row addresses.
- **Decoding:** `pattern_to_state` is indexed by a byte whose pixels are the
  superpixel's TL, TR, BL, BR. It's formed as `(top&CC)|((bottom&CC)>>2)`
  for even sx, or `((top&33)<<2)|(bottom&33)` for odd sx. Non-ink patterns
  map to `NON_CANONICAL` (&FF).
- **Writing:** `byte EOR ((pattern EOR byte) AND mask)` changes only the
  cell's half of each byte.
- **The pattern table** (`solve_patterns.py`, proved optimal by CP-SAT) has
  three hard constraints:
  - 2+2 states are checkerboards;
  - 2+1+1 states have their doubled ink on a diagonal;
  - cycling C→M→Y→K equals rotating the tile 90° clockwise, allowing a
    one-pixel shift of the texture.

  Subject to those it minimises pixel churn per one-quantum change:
  78/32/6/4 of the 120 adjacent-state pairs change 1/2/3/4 pixels. Fewer
  changed pixels costs nothing extra on the 6502; the aim is purely visual
  coherence. `tests/test_inks.py` enforces the properties.

---

## 7. Arena, walls and levels

### Walls

- **Grid:** walls are whole MODE 1 character cells (8×8 pixels, or 4×4
  superpixels), forming a 32×32 grid. They're recorded in a 128-byte bitmap
  (`wall_map`, 4 bytes per row, MSB leftmost). Collision and painting use
  the bitmap; nothing decodes walls from the screen.
- **Tiles:** there are 16 tiles, chosen by the 4-bit neighbour mask (N=1,
  E=2, S=4, W=8). A rim runs along each side with no neighbour, and
  inner-corner pixels are patched so outlines are continuous. Cells outside
  the arena count as walls.
- **Colouring:** a level chooses a (core, rim) pair of different inks, 12
  possibilities. Tiles are stored as rim masks and drawn as
  `core EOR ((core EOR rim) AND mask)`.
- **Routines:** `draw_walls` / `draw_walls_in_rect` (the latter takes
  neighbours from the whole map) and `is_wall` (X, Y cell; out of range
  counts as a wall).

### Levels

- **Source:** each level is a text file (`levels.py` defines the format)
  with `NAME` (a title of up to 24 characters, mixed case), `SYMMETRY ROT4`
  or `ROT2`, `WALLS core rim`, optionally `FILL`, `START sx sy facing` for
  player 1, then `MOVE`/`DRAW` lines. Lines are horizontal or vertical in
  wall-cell coordinates, and only one quadrant (ROT4) or half (ROT2) is
  written.
- **Expansion:** `asm/level.asm` runs the bytecode once per symmetric copy,
  rotating each plotted cell by (x, y) → (31−y, x) per quarter turn. So
  symmetry, and hence fairness, is structural.
- **Starts:** `place_players` rotates player 1's start for each further
  player, by (sx, sy) → (122−sy, sx) with facing + 2 per quarter turn.
  Player *k* plays ink *k*.
- **Level sets:** each set has a fixed header (players, count, then address
  tables for up to `MAX_LEVELS` = 16 bytecodes and titles), followed by the
  titles and the bytecode. The game reads levels through
  `level_code_lo/hi` and `level_title_lo/hi`, which are fixed offsets from
  `level_area`.
- **Reachability:** every open cell must be reachable by a tank with two
  superpixels' clearance on each side, so gaps are at least three wall
  cells wide. `test_levels.py` checks this with a flood fill over tank
  positions from the starts.
- **Current levels:** Colour Clash and Dithering Fights (four-player), and
  Mixed Emotions (two-player). The categorised list of 45 titles is in
  `decisions.md`.

---

## 8. Tanks (sprites)

- **Pictures:** tanks are 12×12 pixels (6×6 superpixels), drawn in
  `sprites/tank.spr` as E and NE only, with the other facings as exact
  quarter turns. Every facing is mirror-symmetric about its own axis; axial
  tanks are drawn within 11 rows so the one-pixel barrel has a centre row.
  Each tank is two-tone: the player's ink plus a contrast ink (black, or
  yellow for the K player). Players are identified by colour only.
- **Frames:** each facing and horizontal alignment has a mask plane and a
  select plane, 4 bytes × 12 lines each. The colour is applied at draw time
  as `contrast EOR ((contrast EOR ink) AND select)`, merged under the mask.
  The inner loops patch their own absolute addresses (self-modifying code)
  and index everything with X through `sprite_line_offsets`.
- **Save-under:** `save_under` / `restore_under` / `draw_sprite` keep the
  screen under each tank in a 48-byte buffer. Restores are **masked to the
  footprint**, because tanks side by side can share a byte column.
- **Solid tanks** never overlap, and movement keeps each tank's old and new
  footprints clear of every other tank's. So `render_sprites` redraws each
  tank that moved, turned or was painted under on its own: restore, save,
  draw.
- **Racing the beam:** the User VIA's timer 2 is restarted at each tick's
  vertical sync, and read in 4-line units (78 per field, vsync at unit 68).
  `wait_for_beam` delays each redraw until the beam will not reach the tank
  before the redraw ends. Tanks are redrawn in order of how low on screen
  they reach. The result is no flicker, and a test checks every field.
- `show_sprites` and `hide_sprites` remain for a level's first frame and for
  clearing the tanks at round end.

---

## 9. The tick: input, movement and collision

`main_loop` runs one tick per iteration at 25 Hz, two fields per tick:

```
check_demo_exit ─ wait_for_tick ─ start_beam_timer ─ read_inputs
  ─ update_players ─ fire_players ─ render_sprites ─ update_gauges
  ─ tick_count++ ─ tick_clock ─ (round over? end_of_round) ─ tick_done
```

- **Timing:** `wait_for_tick` waits for vertical syncs until 1.5 fields have
  passed since the tick began. That keeps ticks on every second sync even
  when a tick's work runs into its second field. The worst case measured is
  about 58,600 of 80,000 cycles with four tanks moving and firing.
- **Input byte:** a direction 0–7 (0 = N, clockwise) or `NO_DIRECTION`
  (&08), plus `FIRE_BIT` (&10). It comes from the player's control source:
  keyboard layout A (W, A, S, D; fire Shift), keyboard layout B (cursor
  keys; fire Copy), AI, scripted (tests) or none.
  - Keys are read with OSBYTE &81 (negative INKEY codes).
  - `*FX4,1` stops the cursor keys and Copy doing cursor editing.
  - The keyboard buffer is flushed every tick.
- **Ground and refill:** with fire released, `ground_level` sums the
  tank's own ink quanta over the four centre superpixels of its footprint
  (through `read_cell`, so from its save buffer) and divides by 4, giving
  0–4. The reservoir (whole splats plus 1/256ths) refills by
  `ground_refill` for that level, up to 128 splats. With fire held the
  ground counts as 1 and there is no refill. See §10a.
- **Movement:** a direction sets the facing at once. The speed for the
  ground and direction (`ground_speed_lo` and `ground_speed_whole`; normal
  is 200 axial, 141 diagonal = 200/√2, in 1/256 superpixel per tick) is
  added to an 8-bit accumulator. The carry plus the whole part is the
  number of superpixel steps this tick, 0–2, each tried with `try_step`.
- **Blocking:** a step is blocked if it would leave the arena, cover any
  part of a wall cell, or overlap another tank where it is now or was drawn
  at the start of the tick.
- **Sliding** follows the same rule under every rotation. A diagonal step
  is taken whole if clear. Otherwise the tank takes whichever single-axis
  step is clear, if exactly one is; if neither or both are, it stays put.
- **Fair order:** the first player to move rotates with the tick
  (`tick_count AND (player_count−1)`).

---

## 10. Painting

- **The rule** (`paint.py` / `paint.asm`): the painter's ink count goes up
  by one. One other ink present goes down by one: the next after the
  painter's last victim, skipping the painter and absent inks
  (round-robin, per player). An already solid cell doesn't change.
  - **Implementation:** the 6502 finds the new state through
    `state_index_of` (C·25 + M·5 + Y) plus `ink_weight[painter]` minus
    `ink_weight[victim]`, then looks up `state_of_counts`.
- **Splats** (`sprites/splats.spr`): there are 3 variants per facing, each
  of 16 cells. They're drawn for E and NE and rotated about the footprint
  centre by (x, y) → (5−y, x). Each player cycles through the variants.
  - **Fairness:** tests require 16 cells per splat, a gap from the
    footprint, centroids within 6° of the facing, and equal reach.
- **Walls stop splats:** each variant has a precomputed **ray tree**, the
  cells on the lines from the footprint centre to each splat cell, each
  with its parent. `fire_splat` walks it, and a node is blocked if it's a
  wall, outside the arena, or its parent is blocked. Unblocked splat cells
  are painted.
- **Firing:** holding fire shoots every 6 ticks, after all movement, in the
  same rotating order, while the reservoir holds a splat; each shot uses
  one. Players shoot only on ticks where tick + player is
  even, which caps each tick at two shots. A shot costs about 13,000
  cycles.
- **Painting under tanks:** `read_cell` finds a cell on screen, or in a
  tank's save buffer if the cell is inside that tank's drawn footprint.
  Painting there marks the tank for redraw.

---

## 10a. The ink reservoir

Splatoon's ink tank and squid form for tanks: paint, run dry, seek your
colour, dash and refill, emerge and paint again. The rules are in
`game.py` (`Game._move`, `Game._fire`, `Game.ground`) and `decisions.md`.

| Ground (own quanta, centre four DIV 4) | Speed, fire released (axial / diagonal) | Refill, 1/256 splat per tick |
|---|---|---|
| 0 | 100 / 71 | 0 |
| 1 | 200 / 141 | 16 |
| 2 | 200 / 141 | 64 |
| 3 | 250 / 177 | 104 |
| 4 | 300 / 212 | 192 |

- **Buffers:** `player_reservoir`, `player_reservoir_fraction`,
  `gauge_drawn`, `ai_refilling`, and the working bytes `move_ground`,
  `move_steps`, `ground_total` and `ground_index`.
- **Gauges** (`hud.asm`): `update_gauges` runs each tick after the tanks
  are drawn and moves every gauge one splat (a raster line) towards its
  reservoir. `draw_gauge_frames` (from `enter_level`, so not on the
  player-select backdrop) frames each gauge in the player's colour, a pixel
  clear all round, in the gap columns between tally bars. The gauges share the tally bars' columns and base line and
  their drawing (`bar_bytes`, `bar_column`, `draw_bar_line`).
  `clear_gauges` empties them and erases the frames at the end of a round.
- **Cost:** a tank with fire released reads four cells instead of
  shooting, far cheaper than a shot. A test checks the game keeps 25 Hz
  with two tanks firing and two refilling.

---

## 11. Computer players

`ai.py` is the specification, and `ai.asm` matches it decision for decision.

- **When it decides:** every 4 ticks, on ticks where tick + player ≡ 0
  (mod 4), so AIs take turns. In between it repeats its last input.
- **Scoring:** each of the 8 directions is scored from 4 sample cells,
  stored for E and NE and rotated like splats. A cell is worth 8 minus the
  AI's own ink count there, or 1 if it's a wall or outside the arena.
- **Choosing:** the current direction gets +2. The strictly best direction
  wins, scanning clockwise from the current one. A blocked step rules that
  direction out, and the AI chooses again; if every direction is ruled out,
  it stays put.
- **Firing:** it fires when the chosen direction's score is at least 22.
- **Starting direction:** each AI slot faces, and heads, a random
  direction (`random_direction`, from `place_players`), so identical AIs
  don't trace the same path under rotation. Humans face the level's way.
  The generator (`next_random`: state → 5·state + 1 mod 256, top three
  bits) is seeded from the System VIA timer at start-up and stepped every
  field of the join screen.
- **Refilling:** an AI that decides with an empty reservoir switches to
  refilling (`ai_refilling`) until it has 64 splats. While refilling it
  holds fire, and a sample cell is worth 4 plus its own ink count, so it
  heads for its own ink.
- **Properties:** it's deterministic and produces the ordinary input byte.
  Identical AIs on symmetric four-player levels end with equal shares.

---

## 12. Rounds, HUD and scoring

- **During play,** the HUD shows only the logo, "LEVEL n", an m:ss
  countdown (5-minute rounds, or 1 minute in the demo) and the ink gauges.
  There are no running scores.
- **At the end of a round:**
  - `hide_sprites` removes the tanks, and `clear_gauges` the ink gauges;
  - `count_territory` builds a histogram of the 35 ink states over every
    open character cell;
  - `compute_scores` works out each ink's quanta and each player's
    percentage (quanta × 100 DIV total, where the total is 4 per open cell);
  - `reveal_scores` grows a bar per player, from the smallest share to the
    largest.
- **The reveal:** labels use the 3×5 font drawn straight into screen
  memory, in the player's colour (yellow for K), and the winner is
  underlined. Nothing at the bottom of the HUD goes through the MOS,
  because printing in the bottom-right text cell would scroll the screen.

---

## 13. Session flow (`flow.asm`)

- **Player select** (`select_players`): level 1 is drawn as a backdrop.
  Players press fire within 10 seconds to join: Shift for player 1, Copy
  for player 2. Play starts early once both keyboard players have joined.
  Unjoined slots are AI.
- **Sessions** play each level of the set in turn, each opening with a
  **title card** (a black arena, "LEVEL n" and the title).
- **Points:** after each reveal, `after_round` awards 3, 2, 1 and 0 by rank
  (3 and 0 with two players). Tied players share the better rank. Totals
  show in the HUD. After the last level, the final totals, then back to
  player select.
- **Demo mode:** if nobody joins, the AIs play one-minute rounds and cycle
  the levels for ever. Any player key returns to player select.

---

## 14. Python models and tests

### Models

The Python modules model the game exactly, and emulator tests compare
screen memory and state against them:

- `inks.py`, `walls.py`, `levels.py`, `sprites.py` and `splats.py`;
- `paint.py`, `game.py` (the whole tick, including movement, firing, rounds
  and `round_points`) and `ai.py`;
- `render.py` (the expected screen: arena, walls and tanks).

### Harness (`tests/conftest.py`)

- **Launching:** `launch_bbc` is a factory fixture (the design proposed as
  Beebium #105), using the `model-b-disc` preset.
- **Loading:** `load_game(bbc, build, players)` boots the disc, answers the
  title screen and stops at `select_players`.
- **Booting into play:** `boot_game` then enters level 0 directly and stops
  at `main_loop`, before the first tick, with the screen displayed. The
  default session has players 1 and 2 human.
- **Stepping:** `enter_level` starts any level exactly before its first
  tick. `step_ticks` runs whole ticks and stops at `tick_done`.
- **Display:** `show_display` parks the CPU in `hold_display` so fields can
  be scanned out without the game running.
- **Routines:** `enter_routine` jumps to a routine from an instruction
  boundary.
- **Random state:** `enter_level` and `boot_game` write
  `DEFAULT_RANDOM_STATE` to `random_state` before entering a level, as
  `Game.start` assumes, so AI facings match the model.
- **Timing rules:** always reach an instruction boundary before writing PC
  (Beebium #106). Set `round_length_ticks` before entering a level.
- **Coverage:** `SET_LEVELS` lists (players, index) pairs, so tests can
  cover every level of both sets.

### Test practice

- The model is written first, and the 6502 must match it: tick-for-tick
  state, byte-for-byte arena, and AI decisions.
- Mutation checks, breaking the 6502 code on purpose, confirm the tests can
  fail.
- Commit only when pytest itself exits 0. Don't pipe its output through
  `tail` into the commit condition.

### Beebium issues raised

#104–#113 cover:
- presets by name;
- a configurable fixture;
- PC writes mid-instruction;
- snapshots;
- a beebasm module;
- named special keys;
- `run_to` for the next occurrence;
- frame and beam correlation;
- rendering from memory;
- a profiling helper.

---

## 15. Status and open items

- **Done:** everything described above, including the title screen and HUD
  logo, the ink reservoir with its framed gauges, and random AI starting
  directions. Playability is much improved by the last two.
- **Tuning:** the reservoir's size, refill rates and ground speeds, and the
  AI's refill threshold, are constants in `game.py` and `ai.py`.
- **Next:**
  - more levels, from the categorised titles. The 759-byte level area
    holds about 14 per set; 15 needs a little more memory (§5);
  - SPItFIRE four-joystick support, once Beebium can emulate it;
  - sound (&0800 is reserved for it);
  - a faster suite once Beebium snapshots (#107) exist.
