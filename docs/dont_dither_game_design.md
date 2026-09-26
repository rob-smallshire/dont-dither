<!-- Markdown rendering of dont_dither_game_design.docx. The .docx is the source; regenerate this file if it changes. -->

# DON'T DITHER!

**BBC Micro Game Design & Implementation Specification**

*Two- and four-player local play, with an architecture suitable for later Econet play*

## 1. Game concept

Don't Dither! is a fast top-down territory game for the BBC Micro. Two or four players move around a shared arena and project coloured ink in the direction of travel. The arena begins as a deliberately dithered field. Painting changes the ownership mixture of small logical cells until contested dithered regions become solidly owned by one player or team. A timed round ends with the player or team owning the greatest share of paintable territory.

The defining implementation idea is that the dithered display is also the territory state. There is no separate full arena ownership map: MODE 1 screen memory is authoritative except where temporarily obscured by sprites.

## 2. Target machine and display

Target a disc-equipped BBC Micro-class machine using MODE 1. The standard MODE 1 display is 320×256 with four physical colours and a 20 KB screen.

Use the leftmost 256×256 pixels as the square arena and the remaining 64×256 pixels as a HUD for timer, scores/percentages, player status and round information.

The arena is interpreted as a 128×128 logical grid of 2×2 physical-pixel superpixels. All gameplay coordinates, walls, paint cells, player positions, AI and collision logic operate on this superpixel grid.

## 3. CMYK palette and the 35 ink states

Use four fixed physical colours identified as C, M, Y and K. A 2×2 superpixel contains four physical pixels, each one of these four colours. Ignore spatial permutation when defining ownership: an ink state is the count tuple (C,M,Y,K), with non-negative components summing to four.

```
C + M + Y + K = 4
number of states = C(4+4-1,4) = C(7,4) = 35
```

For any one player, a cell therefore has five possible ownership levels: 0, 1, 2, 3 or 4 physical pixels, corresponding to 0%, 25%, 50%, 75% or 100% ownership. The complete state retains which opponents own the remaining fractions.

| Partition | Meaning               | Examples  |
|-----------|-----------------------|-----------|
| 4         | solid ownership       | (4,0,0,0) |
| 3+1       | strongly dominated    | (3,1,0,0) |
| 2+2       | two-way contest       | (2,2,0,0) |
| 2+1+1     | three-colour contest  | (2,1,1,0) |
| 1+1+1+1   | maximally contested   | (1,1,1,1) |

## 4. Canonical dither patterns

Choose exactly one canonical 2×2 physical arrangement for each of the 35 count tuples. Every occurrence of the same ownership tuple must render with the same pattern. This is essential: large regions with equal ownership ratios should form coherent, repeated halftone textures rather than history-dependent coloured noise.

Curate the 35 patterns as a set. Favour visually equivalent motifs for colour permutations: solid fills for 4; a consistent corner/minority structure for 3+1; checker-like patterns for 2+2; consistent motifs for 2+1+1; and a clean four-colour pattern for 1+1+1+1. Optimise adjacent ownership states to minimise physical-pixel changes, but never sacrifice colour fairness or canonical uniformity merely to obtain a one-pixel graphical transition.

At design time, construct tables mapping canonical pattern ↔ state 0..34 and state → C/M/Y/K counts. Non-canonical 2×2 patterns should never normally appear in bare arena memory and may be treated as invalid/debug states.

## 5. Initial territory and painting semantics

In four-player free-for-all, initialise every paintable cell to (1,1,1,1). Every player therefore begins with exactly 25% of every paintable cell and 25% of the arena globally. This is the maximally dithered neutral-looking starting field without requiring a fifth 'neutral' colour.

A successful paint application transfers exactly one ownership quantum: increment the painter's component by one and decrement one represented opponent component by one. Thus a player needs three uninterrupted applications to turn the initial (1,1,1,1) cell solidly into their colour. Capturing a cell already solidly owned by another player requires four applications.

Victim selection is deterministic round-robin. Each player maintains a small 'last victim' state. On a successful paint application, search cyclically through the other colours after the last victim and select the first opponent that has a non-zero component in the target cell. Absent opponents are skipped and do not consume a turn. Set last victim to the opponent actually displaced. Painting an already-solid own cell changes nothing and does not advance the victim state.

This rule avoids pseudorandom generation, distributes displacement fairly over time, and is identical for all players under cyclic relabelling. Ownership mechanics are independent of the spatial arrangement chosen by the canonical renderer.

## 6. Two-player and team modes

Support two-player and four-player configurations only. Four-player free-for-all uses all four CMYK identities. A two-player game uses two active ink identities and should use a 180°-symmetric arena. A four-player 2v2 mode may also use only two team colours: both members of a team paint the same ownership component and contribute to the same team score. Keep team/player input identity separate from ink/team identity.

## 7. Screen memory as world state

Do not allocate a 128×128 ownership array. It would duplicate information already present in the 20 KB MODE 1 framebuffer and cost 16 KB at one byte per cell. Read and update territory directly from screen memory.

In MODE 1 one byte represents four horizontal pixels, with interleaved colour bits. A horizontally aligned 2×2 superpixel occupies one half of each of two consecutive raster bytes. Because BBC screen memory stores the eight raster lines of a character row consecutively, the two rows of a 2×2 cell are adjacent addresses when y is even. Align all gameplay cells to this grid.

```
superpixel (sx,sy): x=2*sx, y=2*sy
address ≈ screen_base + (sy DIV 4)*640 + (sx DIV 2)*8 + (sy AND 3)*2
sx even: cell bits use mask &CC
sx odd : cell bits use mask &33
```

Use a 128-entry row-address table (low/high bytes: 256 bytes total) so hot code does not repeatedly calculate the full screen address. Precompute rendering/decoding tables where ROM space saves CPU cycles. A 256-entry decoder is feasible because four 2-bit pixels have only 4^4 = 256 literal arrangements.

## 8. Walls and arena graphics

Walls are static, unpaintable screen patterns deliberately outside the 35 canonical ink patterns. Define a compact tile vocabulary at superpixel resolution sufficient to draw clean connected walls: horizontal, vertical, four end caps, four corners as needed, T-junctions and crosses. The exact wall pattern set should be curated alongside the ink patterns so walls remain unmistakable against every dither mixture.

Collision detection may therefore classify cells directly from their framebuffer pattern: canonical ink state = traversable/paintable; recognised wall pattern = solid/unpaintable. Keep any decorative patterns from colliding with the territory encoding.

## 9. Level representation

Use handcrafted (canned) arenas, not procedural generation. Storage is cheap, while handcrafted maps allow deliberate difficulty progression, choke points, defensible regions and tested fairness.

Represent levels compactly as vector-like wall primitives plus player start positions and symmetry metadata. A minimal language should include MOVE and DRAW, with an optional RECT/BLOCK primitive only if it materially simplifies level data. Coordinates are 0..127 logical cells.

```
ROT2 / ROT4
START x,y,facing
MOVE  x,y
DRAW  x,y
[RECT x1,y1,x2,y2]
END
```

For four-player free-for-all, store one quadrant and generate the other three by exact 90° rotations. For two-player and 2v2 maps, use 180° symmetry and store half the geometry. Generate start positions and initial facing directions using the same symmetry transform. This makes geometric fairness structural rather than dependent on manual duplication.

Start with a small set of strong maps (for example ~16) and progress from open arenas through central obstacles, corridors, choke points and defensible pockets.

## 10. Player representation and sprites

Use a logical player position on the 128×128 superpixel grid. Render each avatar as approximately 6×6 superpixels = 12×12 physical pixels. Give players strongly distinct silhouettes as well as colour identity so they remain recognisable over every ink mixture.

Use conventional save-under sprites: before drawing a player, save the framebuffer bytes beneath it; before the next world update, restore all player backgrounds in reverse drawing order. Then update movement/paint/world state on the bare arena, save fresh backgrounds, and redraw sprites in a stable order. This prevents sprite pixels from becoming territory state and handles overlapping sprites deterministically.

A 12×12 MODE 1 sprite covers only a few dozen screen bytes; four background buffers are inexpensive. The visual sprite may be 6×6 cells while collision uses a smaller footprint such as 4×4 cells, leaving a one-cell visual margin.

## 11. Movement and collision

Support eight movement directions plus stationary. Movement occurs in whole superpixel cells; one logical step therefore moves two physical pixels. Direction/facing is part of player state and determines the paint direction.

Correct or cadence-limit diagonal movement so it does not receive an unintended √2 speed advantage. Prefer integer/tick-based scheduling rather than runtime multiplication or division.

Wall collision is evaluated against the logical collision footprint using framebuffer wall classification. Decide player-player collision explicitly and implement it deterministically; if players are allowed to overlap/pass through each other, sprite overlap handling still remains necessary.

## 12. Paint brush geometry

Firing paints a compact elliptical region slightly elongated along the direction of travel, separated from the 6×6 player sprite by one superpixel to convey ballistic projection rather than an aura.

Use a provisional brush area of exactly 16 logical cells for every direction. Maintain equal area and approximately equal centroid, length and width for axial and diagonal brushes. Design one axial and one 45° mask, then derive/store all eight orientations. Runtime should use precomputed offset lists; no geometry or trigonometry is required.

Each target cell in the brush receives one paint application, i.e. one 25% ownership transfer where possible. The 16-cell brush is a gameplay and CPU budget parameter and can later be tuned without changing the ownership model.

## 13. Scoring and HUD

Maintain running ownership totals rather than rescanning the framebuffer. Whenever painter P steals one quantum from victim V: score[P]++, score[V]--. The denominator is the total number of paintable ownership quanta (four per paintable superpixel); wall cells do not count.

The right-hand 64-pixel HUD should show at minimum the countdown timer and live player/team territory shares. It may also show health/damage if that mechanic is retained. At time expiry, stop gameplay, display final shares and resolve ties explicitly.

## 14. Damage, hostile ink and respawn

Treat damage rules as a gameplay subsystem rather than part of the ownership representation. A suitable baseline is that travelling through hostile ink is disadvantageous and enemy attacks can damage/splat a player. Exact damage/slow/recharge values should be tuned experimentally. If respawning is used, define spawn protection and ensure starts remain symmetric.

## 15. AI

AI is both a game feature and a development tool. It must produce exactly the same input structure as a joystick player: direction (0..7 or stationary) plus fire. It must not call privileged movement or painting functions.

A useful first AI needs no expensive global pathfinding. Sample nearby cells, favour neutral/enemy-dominated territory, avoid walls and strongly hostile regions, follow ownership boundaries, fire when the forward brush contains valuable targets, and use short persistence/random-free tie-breaking to avoid oscillation. Add difficulty by improving look-ahead and retreat/target selection, not by changing physics.

Support arbitrary assignment of human or AI input to all player slots. Four AI players provide an excellent soak test for movement, collision, painting, scoring and deterministic replay.

## 16. Deterministic simulation

Make the game tick-driven from the beginning. Given an initial level and the same per-tick player inputs, the simulation must produce the same result every time. Keep animation timing out of game-state decisions. Use stable player/update ordering wherever simultaneous actions can interact.

This determinism is valuable for debugging and is the foundation for later Econet play. A recorded stream of compact inputs should be sufficient to replay a round.

## 17. Local input architecture

```
input source (joystick | AI | later Econet)
        -> {direction, fire}
        -> common player simulation
        -> movement / collision / painting
```

SPItFIRE may provide up to four local joysticks. Do not let the core simulation know whether an input came from hardware, AI or network transport.

## 18. Later Econet mode

Design the local game so Econet can be added as input/event transport rather than as a separate game implementation. One participating BBC should act as authoritative host/arbiter. All peers may run the full deterministic simulation, but the arbiter establishes canonical ordering when simultaneous actions conflict.

Transmit compact input changes/events rather than framebuffer state. Use monotonically increasing sequence/event numbers, acknowledgements/retransmission as required, and periodic checksums of the bare authoritative arena (after sprite backgrounds have been restored and before sprites are redrawn). A mismatch can trigger event replay or, rarely, an authoritative state resynchronisation.

The host's local player must enter the same tick/input ordering rules as remote players so host status does not confer a rules advantage.

## 19. Suggested implementation milestones

1. Canonical CMYK ink patterns and wall-pattern vocabulary, with lookup tables and visual test screen.
2. One canned ROT4 arena renderer from compact MOVE/DRAW data; initialise all paintable cells to (1,1,1,1).
3. One 6×6 player sprite with correct save-under, restoration and overlap-safe draw cycle.
4. Eight-direction superpixel movement and facing.
5. Wall collision using framebuffer classification.
6. 16-cell directional paint masks and ownership transition/round-robin victim logic.
7. Incremental scoring and live HUD.
8. One AI player using the normal input interface.
9. Four simultaneous AI/human players; deterministic player interaction and sprite overlap.
10. Round countdown, end-of-round scoring, tie handling and restart/next-level flow.
11. Damage/splat/respawn tuning if retained.
12. Additional ROT2/ROT4 handcrafted levels and progression.
13. Econet authoritative-input transport, event sequencing and checksum/reconciliation.

## 20. Core invariants

- Every paintable arena cell is exactly one of the 35 canonical CMYK ownership states.
- Every ownership state contains exactly four ownership quanta.
- Every successful paint application transfers exactly one quantum from a represented opponent to the painter.
- Canonical pattern depends only on ownership tuple, never on history.
- Four-player initial state is (1,1,1,1) for every paintable cell.
- Framebuffer territory is authoritative whenever transient sprites have been restored.
- Scores are cached aggregates of ownership transfers and must agree with framebuffer ownership.
- All gameplay positions and geometry use the 128×128 superpixel grid.
- All eight paint directions affect the same number of cells.
- Equivalent players/teams receive symmetry-equivalent starts and geometry.
- AI, joystick and network players enter the simulation through the same input interface.
- Simulation results depend on initial state and ordered tick inputs, not rendering timing.

## 21. Development/debug support

Exploit emulator tooling aggressively. Useful debug facilities include: pause/single-step simulation ticks; show player collision footprints and brush masks; force/fill specific ink states; cycle a selected cell through all 35 canonical states; display raw state numbers; validate that bare framebuffer contains only canonical ink or legal wall patterns; recompute scores from the framebuffer and compare with cached totals; record/replay input streams; and run four-AI soak tests.

## 22. First playable target

The first vertical slice should contain one square fourfold-symmetric arena, the maximally dithered (1,1,1,1) background, one 6×6 avatar, eight-direction movement, wall collision, and firing that applies the 16-cell directional brush and visibly moves canonical cells toward the player's solid colour. Once this looks and feels correct on BBC hardware/emulation, add scoring, AI and additional players without changing the underlying territory model.
