# Design decisions

Decisions taken during development that refine or depart from
`dont_dither_game_design.md`. Most recent last.

## Ink patterns

- The canonical 2×2 pattern table (`data/ink_patterns.json`) is solved
  exactly by `tools/dontdither/solve_patterns.py` under hard constraints:
  2+2 states are checkerboards; 2+1+1 states have the doubled ink on a
  diagonal; colour cycling C→M→Y→K equals a clockwise 90° tile rotation up to
  a one-pixel translation. Churn is then minimised (proved optimal:
  78/32/6/4 edges changing 1/2/3/4 pixels). Visual coherence was preferred
  over minimal churn, since the 6502 rewrites both half-bytes of a cell
  whatever the churn.

## Walls

- Walls occupy whole MODE 1 character cells (8×8 pixels = 4×4 superpixels),
  a 32×32 grid, recorded in a 128-byte bitmap. Collision and painting will
  consult the bitmap rather than decoding screen patterns, so wall art is
  unconstrained by the ink table.
- A wall colouring is a (core, rim) pair of different inks, chosen per level:
  12 possibilities. The engine supports all 12; levels will normally use a
  C/M/Y core with a black rim, or a black core with a C/M/Y rim.
- Cells outside the arena count as walls, so border walls have no outer rim.
  With a coloured core this reads as a solid frame, which is fine.

## Levels

- Levels are text files in `levels/`, storing one quadrant (ROT4) or half
  (ROT2) of their walls as horizontal/vertical MOVE/DRAW lines in wall-cell
  coordinates. The 6502 expands them under the symmetry, so fairness is
  structural.

## Players and modes

- Players keep consistent ink colours across levels.
- Every mode, including two-player, starts from the four-way grey
  (1,1,1,1). In a two-player game the two inks without a player are neutral
  territory: they are never painted, so their share only falls. Scores count
  only the players' inks. The round-robin victim rule is unchanged: neutral
  inks are victims like any other represented ink.
- Which two inks the two players use is to be decided with the game-setup
  screen. A natural default is player k = ink k, giving C against Y on a ROT2
  level.

## Player sprites

- Players are told apart by colour only, not by silhouette: this saves memory
  and lets the shape show direction as clearly as possible.
- The sprite is a top-down tank, 12x12 pixels (6x6 superpixels), with its
  barrel pointing in the facing direction, which is also the direction of
  travel and of the splat.
- Every sprite is two-tone: the player's ink plus a contrast ink (black for
  C, M and Y; yellow for K), so it stays visible over any texture, including
  its own colour. The barrel has a player-ink core with a contrast outline so
  that direction stays readable on any ground.
- Every facing is mirror-symmetric about its own axis. The axial tank is drawn
  within 11 rows of the 12x12 picture so its one-pixel barrel has a centre
  row; the diagonal tank is symmetric about the box diagonal. Game geometry
  (collision footprint, brush) is in superpixels and so is symmetric about
  the 6x6-superpixel footprint's centre instead; the half-pixel offset
  between picture and footprint axes is imperceptible.
- Only facings E and NE are drawn (`sprites/tank.spr`, editable ASCII); the
  other six are exact quarter turns. `uv run dd-preview-sprites` renders every
  player, facing and a range of backgrounds for review.

### Drawing tanks on the 6502

- Frames are stored as a mask plane and a select plane per facing and per
  horizontal alignment (even or odd superpixel column), 4 bytes x 12 lines
  each: 16 frames, about 1.5 KB. Colour is applied at draw time
  (contrast EOR ((contrast EOR ink) AND select)), so all players share the
  frames. Runtime shifting could halve the frame memory if space runs short.
- Tanks are solid: they cannot pass through each other, so their pictures
  never overlap. Each tank that moved or turned is redrawn on its own
  (restore, save, draw); the rest are untouched. Painting will write cells
  under a tank into that tank's save buffer.
- Flicker-free: render_sprites races the beam. The User VIA's timer 2 is
  restarted at each tick's vertical sync as a beam clock (4-line units), and
  each redraw waits until the beam will not reach the tank before the redraw
  is done. Redraws are ordered by how low the tank reaches. A test captures
  every field while tanks move and requires every tank to appear whole.
- Rendering four moving tanks, including beam waits, takes about 42,000 to
  47,000 cycles of the 80,000-cycle tick. The waits are idle time that
  painting could later use.
- The tick keeps a fixed rhythm: wait_for_tick waits for vertical syncs until
  1.5 fields have passed since the tick started, so ticks start on every
  second sync even when their work runs into the second field.
- (Superseded: global hide_sprites/show_sprites each tick. They remain for a
  level's first frame and for clearing the tanks.)
- In two-player levels the players take inks C and Y.

## Paint splats

- A shot paints a messy 16-superpixel splat rather than a neat ellipse. Each
  player cycles deterministically through a few variants (no random numbers)
  so successive shots do not stamp identical shapes.
- Splats are drawn for E and NE only (`sprites/splats.spr`, editable ASCII);
  the other six facings are exact quarter turns about the footprint centre,
  cell (x, y) -> (5 - y, x), which the 6502 can apply per cell at paint time.
- Splats are symmetric about the footprint's centre line, not the one-pixel
  barrel; the half-pixel offset is fine for splatting.
- Fairness: every splat paints exactly 16 cells, never touches the tank's
  footprint, lies within 6 degrees of its facing's axis, and all variants
  reach within 0.6 cells of the same distance (tests enforce all of these).
  The one-cell gap on a diagonal costs more distance, so the axial splats
  sit two cells out to match.
- Walls stop splats: a splat cell is painted only if the straight line from
  the centre of the tank's footprint to the cell crosses no wall, so a wall
  shadows everything behind it (including a wall in the gap, which blocks
  the whole shot). This is precomputed per variant as a ray tree whose
  nodes are the cells on those lines, each with its parent (the previous
  cell on its line). The 6502 walks the nodes in order with one wall test
  each (about 30 per shot); a node is blocked if it is a wall or its parent
  is blocked. Trees are built for E and NE and rotated, never re-traced, so
  shadowing is identical for every facing.
- Cells are painted in tree order, which the round-robin victim rule
  follows.
- `uv run dd-preview-splats` renders every variant and facing, cumulative
  shots, and shots against a wall, all with the true one-quantum effect.

## Game loop and movement

- The game ticks at 25 Hz (two vertical syncs per tick). Each tick: read
  inputs, hide sprites, update players on the bare arena, show sprites.
  tick_done marks the point between ticks where tests stop and step.
- Each player's per-tick input is a direction (0-7 or none) plus fire, from
  a control source: keyboard layout A, keyboard layout B, scripted (tests,
  later AI) or none. The simulation never sees where input came from.
- Movement is in whole superpixels. A direction input sets the facing at
  once. An 8-bit accumulator per player adds the speed each tick (axial 200,
  diagonal 141 = 200/sqrt 2, in 1/256 superpixel per tick) and a carry means
  one step, so diagonals are no faster and no multiplication is needed.
  About 19.5 superpixels per second axially; tunable in game.py.
- A step is blocked if the footprint would leave the arena or overlap another
  tank where that tank is now or was drawn at the start of the tick (so no
  tank's old or new picture ever touches another's), or cover any part of a
  wall cell. A footprint at superpixel (x, y) covers wall cells x DIV 4 ..
  (x + 5) DIV 4 across and likewise down, checked against the wall map.
- Sliding, the same under every rotation: an axial step is taken if clear; a
  diagonal step whole if clear, otherwise the one clear single-axis step if
  exactly one is clear, otherwise none.
- Fair order: players move one after another, and the first to move rotates
  each tick (tick t starts with player t mod player_count).

## Firing and painting

- Holding fire shoots every FIRE_PERIOD (6) ticks, about 4 shots a second.
  Shots happen after all movement in the tick, in the same rotating player
  order, from each tank's new position and facing.
- Players shoot only on ticks of their own parity ((tick + player) even), so
  at most half the players shoot in a tick. This keeps painting within the
  tick budget (each shot costs about 13,000 cycles); as FIRE_PERIOD is even,
  a held fire is never delayed, and a new press waits at most one tick.
- A cell under a tank is painted in that tank's save buffer (the arena
  beneath it), and the tank is flagged for a redraw so the change shows.
- Restores are masked to the tank's footprint, so tanks side by side that
  share a screen byte column never disturb each other.
- Measured worst tick with all four players driving and firing: about
  58,600 of 80,000 cycles.

## Level titles

- Levels have titles of up to 24 characters in mixed case (the NAME line).
  They do not fit the 8-column HUD, which shows "LEVEL n"; instead each
  session level opens with a title card: the arena goes black, and
  "LEVEL n" and the title appear centred across it for 3 seconds.
- Titles are drawn from three categories (the current three levels use
  "either" titles):

  | Two-player | Either | Four-player |
  |---|---|---|
  | Double Trouble | Dithering Fights | Four Colour Problem |
  | Two Tone | Colour Clash | Four Corners |
  | Opposites Attract | Paint the Town | Four Play |
  | Split Decision | A Brush with Danger | Four Warned |
  | Divided We Fall | No Grey Area | Four Gone Conclusion |
  | Head to Head | True Colours | Four the Win |
  | Face Off | Mixed Emotions | Quarter Past |
  | Either Or | Splitting Pixels | Quartered |
  | Tit for Tat | Colour Blind | Four Square |
  | Give and Take | Off Colour | CMYK.O. |
  | This or That | Wall to Wall | Fourmidable |
  | Binary Opposition | Paint by Numbers | Four Better or Worse |
  | Two's Company | Between the Lines | Four All |
  | Tug of War | Ink Different | All Four One |
  | Duelling Colours | Colouring In | Four Way Street |

## Computer players

- Player slots without a human are played by the AI; players 1 and 2 are on
  the keyboard. The AI produces the same input byte as a keyboard player,
  and the simulation cannot tell them apart.
- The AI is deterministic (no random numbers) and simple: every 4 ticks
  (AIs take turns) it scores each direction by sampling 4 cells ahead,
  valuing ground it does not own and shunning walls, keeps its direction
  unless another is better (a small persistence bonus), avoids blocked
  steps, and fires when the target is worth it. Samples are rotated like
  splats, so every direction and player is treated alike. Model:
  tools/dontdither/ai.py; the 6502 matches it decision for decision.
- With identical AIs in a symmetric arena, shares come out equal, a useful
  check on fairness.

## Two- or four-player games and level sets

- The game is two-player or four-player, chosen once on the title screen
  by pressing 2 or 4. The title screen (SPLASH, run by !BOOT at &0900)
  shows the logo -- art/splash.png, resampled to 300 pixels wide and
  quantised to CMYK by the build, saved as screen bytes in LOGO -- with the
  prompt beneath it. It then blacks out the palette, loads that level set,
  LEVELS2 or LEVELS4, to &6000 -- the last disc access, while DFS still has
  its workspace -- and runs DITHER, whose loader copies the set into the
  game's level area. To switch mode, press Break and reload.
- A level set holds only levels of its player count (ROT2 or ROT4); the
  build generates both from levels/*.lvl. A set has a fixed header
  (players, count, tables of bytecode and title addresses, up to 16 levels)
  then the levels. Only player 1's start is stored; the 6502 rotates it for
  the other players, as the model does.
- Joining works the same in both modes: play starts when every player who
  can join (both keyboard players) has, or when the 10 seconds run out.
  Everyone else is the computer; computer against computer is the demo.

## Player selection, sessions and demo

- At boot, and after every session, players join by pressing fire within a
  10-second window (SHIFT for player 1, COPY for player 2), shown over a
  backdrop of level 1. Every slot nobody joins is played by the computer.
- A session plays every level in turn. After each round, points by rank:
  3, 2, 1, 0 for first to last with four players; 3 and 0 with two. Ties
  are ties: tied players share the better rank (two tied for first both
  score 3; the next is third). Running totals show in the HUD after each
  reveal; after the last level they are shown as final, then it is back to
  player selection.
- If nobody joins, the computer plays a demo (attract mode) in 1-minute
  rounds, cycling the levels for ever; any player key (a direction or
  fire) returns to player selection.
- Player slot k always plays in ink k (C, M, Y, K), so colours are
  consistent across a session; two-player levels are played by slots 1 and
  2 (C and M). (Supersedes the earlier "C against Y" default.)

## Rounds and scoring

- No running scores. As in Splatoon's Turf War, the HUD shows only a
  countdown during the round, and the result is revealed at the end. This
  replaces the design document's running totals: the framebuffer is the
  only record of territory, so the tally can never drift from it.
- Rounds last five minutes (ROUND_SECONDS in game.py; tests shorten them by
  writing round_length_ticks before entering a level).
- At the end the tanks are removed, revealing the bare territory; every open
  cell is decoded into a histogram of ink states (about 0.4 s); each
  player's share is its ink's quanta * 100 DIV total quanta (4 per open
  cell). Neutral inks count towards the total.
- The reveal is a bar chart in the HUD: bars grow one at a time from the
  smallest share to the largest, each labelled with its percentage in a
  3x5 font drawn straight into screen memory, in the player's colour
  (yellow for black); the winner's label, or all tied winners', is
  underlined. HUD text near the bottom never goes through the MOS: printing
  in the bottom-right cell would scroll the screen.

## Input

- Keyboard only for now. Beebium does not yet emulate joysticks, and the
  SPItFIRE four-joystick interface comes later.
- Player 1: W A S D, fire SHIFT. Player 2: cursor keys, fire COPY
  (tools/dontdither/controls.py). Keys are read with OSBYTE &81; *FX4,1
  stops the cursor keys and COPY doing cursor editing, and the keyboard
  buffer is flushed every tick.

## Memory

- Target a stock 32K Model B with DFS: load from disc, then reclaim DFS
  workspace. Sideways RAM only if we hit the limit, and only after raising it
  with the user.
- The game runs at &0E00-&2FFF, over the DFS workspace. The file DITHER is a
  loader stub followed by the game image; DFS loads it at &3100 (screen
  memory, unused until MODE 1), and the stub closes the !BOOT *EXEC file,
  copies the image to &0E00 and jumps to it. The game never uses the disc
  again, and ESCAPE is made an ordinary key (*FX229,1) so no Escape
  handling reaches the filing system.
- Memory map: &0400-&07FF a low block of initialised tables (paint data),
  copied there by the loader; &0800-&08FF left to the MOS for sound;
  &0900-&0CFF uninitialised buffers, over MOS buffers the game does not use
  (RS423/cassette, soft keys, user-defined characters 224-255); &0E00-&2FFF
  the main block of code and tables. Zero page &00-&6F is nearly full.
- Zero page: `zp_boot_status` in the MOS user block &70–&8F; everything else
  in &00–&6F, BASIC's workspace, free because our programs never return to
  BASIC.
