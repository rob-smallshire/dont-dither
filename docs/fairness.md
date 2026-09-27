# Fairness

*Don't Dither!* is a game of small advantages: a round is thousands of
hits, each moving one quantum of one cell. A rule that favoured one ink,
one facing or one player slot even slightly would add up. So fairness is
designed in: by symmetry wherever possible, and otherwise by rules that
treat every player alike under relabelling.

This note covers:
- how a hit chooses its **victim**, the ink that loses a quantum when the
  painter's ink gains one;
- the game's other fairness measures, with where each lives.

## 1. Choosing the victim

A cell holds four quanta of ink, counted as (C, M, Y, K) summing to 4 (see
[ink_patterns.md](ink_patterns.md)). The total can't change, so a hit
doesn't just *add* the painter's ink: it **moves one quantum**. The
painter's count goes up by one, and one other ink present in the cell, the
victim, loses one. Choosing that victim is the only real decision in
painting.

### The rule: round-robin, per player

Each player keeps a *last victim*. To paint a cell (`paint.py`,
`paint_cell`; `paint.asm` on the 6502):

1. If the cell is already solidly the painter's (4 quanta), nothing
   happens, and the last victim stays as it is.
2. Otherwise, starting at the ink after the last victim and going round
   C → M → Y → K → C, take the first ink that isn't the painter's own
   and has at least one quantum in the cell. In a two-player game, the
   second player goes round the other way, K → Y → M → C → K (see below
   for why).
3. Move one quantum from it to the painter, and remember it as the last
   victim.

- **The starting point:** a player starts with their own ink as the last
  victim, so the first victim is the next ink round. In a four-player
  game, cyan's first is magenta, magenta's is yellow, yellow's is black,
  and black's is cyan. In a two-player game, cyan's first is magenta and
  magenta's is cyan: each hits its opponent first.
- **Per player, not per cell:** the last victim belongs to the painter,
  not the cell. A splat paints its cells in a fixed order (its ray tree's),
  so a single shot's 16 cells pass the rotation along. Consecutive cells
  of a grey region lose different inks, and the rotation carries on into
  the next shot.
- **Absent inks are skipped:** an absent ink doesn't take a turn in the
  rotation, so no hit is ever wasted on an ink that isn't there.

### Why this rule

- **It's the same rule for every player.** Relabel the inks one step round
  (C→M, M→Y, Y→K, K→C) and each player's rule becomes the next player's
  exactly, starting point included. No ink is built to hit any particular
  ink first or most. That's the symmetry of a four-player game; for two
  players, see below.
- **It spreads the losses.** Over a player's hits, the other inks present
  take turns losing. On the grey (1,1,1,1) start, each run of three hits
  takes one quantum from each of the other three inks. No opponent is
  singled out, and none is spared.
- **It's deterministic.** There are no random numbers, so a round replays
  exactly from its inputs. That's what lets the tests hold the 6502 to the
  Python model byte for byte, tick after tick.
- **It's cheap.** It uses one byte per player and a short search. The 6502
  finds the new state by table arithmetic (`state_index_of`, `ink_weight`,
  `state_of_counts`), with no counting.

### Alternatives, and why not

- **A random victim:** it would need a random generator that the model and
  the machine share exactly. Fairness would also hold only on average, so
  one unlucky round could tilt a close game.
- **Always the largest other ink (or the leader's):** this is
  deterministic but uneven. The same opponent would keep losing, and it
  would build in a "rich get poorer" or "poor get poorer" pressure that
  distorts play. It also needs comparisons, and ties to break, and a
  tie-break favours someone.
- **A fixed order (always hit C first, then M...):** this favours whichever
  inks come late in the order. It breaks the relabelling symmetry.
- **Per-cell memory:** each cell would need its own rotation state, which
  the screen doesn't have room to hold (the pattern *is* the cell's
  entire state).

### Two-player games: the second player goes round the other way

A two-player game (C against M) starts from the same grey as four-player,
so yellow and black are present as **neutral** inks. They are victims like
any other ink, so they can only lose ground, and the scores count only the
players' inks.

Four-player arenas are symmetric under the colour cycle (C→M→Y→K), which
is exactly the symmetry the forwards rotation respects. A two-player
arena's symmetry is different: the half turn swaps C with M, and Y with K.
The first version of the rule used the same cyclic order for both players,
and that isn't symmetric under the swap:

| Player | First version | Mirrored (the rule now) |
|---|---|---|
| Cyan | M, Y, K (opponent first) | M, Y, K (opponent first) |
| Magenta | Y, K, C (opponent last) | C, K, Y (opponent first) |

**Measuring it.** Two identical AIs played a full five-minute round on
every two-player level. They used the level's own facings, so the arena
and the starts were perfectly symmetric, and the only difference between
the sides was the victim rule:

| Victim rotation | Cyan − magenta, mean over the 16 levels | Cyan ahead on |
|---|---|---|
| cyclic (the first version) | +910 quanta (about 1.6% of the arena) | 11 of 16 levels (up to 38% against 32%) |
| mirrored for the second player (the rule now) | −123 quanta | 7 of 16; 5 levels end exactly level |

In real games each computer player starts facing a random direction (and
humans play however they play). The same comparison was repeated with
random facings: 128 two-minute games, 8 seeds on each of the 16 levels:

| Victim rotation | Cyan − magenta, mean | Cyan ahead in |
|---|---|---|
| cyclic (the first version) | +0.12% of the arena (standard error 0.14) | 68 of 128 games |
| mirrored (the rule now) | −0.04% (standard error 0.13) | 46 of 128 games |

So:
- **The first version was asymmetric.** A perfectly symmetric start
  exposed it clearly, as the same favourable phase repeated every time.
- **In play its effect was lost in the noise:** well under half a percent
  of the arena against a game-to-game standard deviation of about 1.5%.
- **The rest of the game** accounts for the remaining swings in the
  symmetric experiment: once tanks meet, small differences, such as the
  alternating first mover, play out differently.

**The fix, adopted:** in two-player games the second player goes round the
rotation the other way (`game.victim_step`; `player_victim_step` on the
6502). That's the true mirror image under the two-player symmetry.
Four-player games keep the forwards rotation, which is exactly symmetric
for them. The effect in games with random facings was below measurement,
but a fairness rule should be right in principle, not merely close.

Tests in `test_paint.py` check the property directly, for every state and
last victim:
- in a two-player game, relabelling by the swap turns the second player's
  rule into exactly the first player's;
- in a four-player game, relabelling by the cycle turns each player's rule
  into the next player's.

The first version broke the two-player property in 52 of those 140 cases.

## 2. The game's other fairness measures

| Where | What | How |
|---|---|---|
| **Arenas** | Every player has the same map | Levels store a quarter (four players) or half (two) of their walls; the game repeats it under rotation, so symmetry is structural (`levels.py`, `level.asm`). |
| **Starts** | Every player the same start | Player 1's start is rotated for each other player; player *k* plays ink *k* throughout a session. |
| **Ink textures** | No colour looks noisier or stripier | Cycling the inks equals rotating the pattern tile (up to a one-pixel shift): see [ink_patterns.md](ink_patterns.md). |
| **Movement** | No facing moves better | Speeds are axial 200, diagonal 141 (200/√2). The slide rule for blocked diagonals is the same under every rotation. |
| **Turn order** | No slot always moves or fires first | The first mover rotates with the tick. Firing follows the same order. |
| **Firing** | No tick is overloaded, nobody delayed | Players fire only on ticks where tick + player is even. The fire period is even, so a held fire is never delayed. |
| **Splats** | Every facing shoots alike | Drawn for E and NE and rotated. The tests require 16 cells per splat, equal reach, and centroids within 6° of the facing. Wall shadows come from rotated ray trees. |
| **The ground** | Refill and speed fair under rotation | A tank's ground level reads the four centre cells of its footprint, the only cells every rotation treats alike. |
| **Tunnels** | Same tunnels for everyone | Mouths are centred on the edges the symmetry pairs, the only placement that wraps straight across under rotation. |
| **Computer players** | No AI slot favoured | The same deterministic rule for every AI. Each thinks on its own tick (tick + player mod 4). Random starting facings differ between AIs, but are fair on average. Humans keep the level's facing. |
| **Scores** | Ties are ties | Tied players share the better rank, so two tied for first both score 3. |

**How it's checked:**
- the model tests check level symmetry, splat fairness, and colour
  cycling of the patterns;
- identical AIs, given the level's own facings, play symmetric rounds.
  Measured over a full round on each four-player level:
  - 6 of the 16 levels end exactly level;
  - the others diverge once tanks meet. The turn order and firing ticks
    are symmetric only up to a shift in time (player *k* moves first on
    tick *k*, and fires on ticks of its parity), so collisions and near
    misses play out differently;
  - there's no consistent winner: each slot's mean share is 24.5–25.3%.
    Yellow and black win more of the diverging levels (5 and 3 of 10),
    but that's within what 16 levels can tell apart.

  in two-player arenas, the first version of the victim rule gave cyan
  an edge from a perfectly symmetric start (see section 1), and the rule
  is now mirrored for the second player;
- the 6502 must match the model tick for tick, so what the model proves
  fair, the machine plays fair.
