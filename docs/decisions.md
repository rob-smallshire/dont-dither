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
- Draw cycle: hide_sprites restores every saved background in reverse player
  order; show_sprites saves then draws each player in order. Overlaps unwind
  exactly. Measured: about 6,750 cycles to hide and 16,800 to show four
  tanks, roughly 30% of a 25 Hz tick.
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

## Input

- Keyboard only for now. Beebium does not yet emulate joysticks, and the
  SPItFIRE four-joystick interface comes later.

## Memory

- Target a stock 32K Model B with DFS: load from disc, then reclaim DFS
  workspace. Sideways RAM only if we hit the limit, and only after raising it
  with the user.
- Zero page: `zp_boot_status` in the MOS user block &70–&8F; everything else
  in &00–&6F, BASIC's workspace, free because our programs never return to
  BASIC.
