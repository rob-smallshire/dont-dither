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
