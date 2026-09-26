# Don't Dither! --- Minimal-Churn Canonical Superpixel State Evolution

## Purpose

This note records the "Gray-code-like" work on the evolution of a single
2×2 CMYK superpixel in *Don't Dither!*.

The objective is to assign **one canonical physical 2×2 dither pattern
to each logical ink state** so that a one-quantum ownership change
normally requires as little rewriting of the physical pixels as
possible.

This is a rendering optimisation and visual-coherence problem. It is
deliberately separate from the game rule that decides **which opponent
loses an ownership quantum**.

## Logical state space

A superpixel contains four physical MODE 1 pixels. Each physical pixel
is one of the four ink colours:

-   C --- cyan
-   M --- magenta
-   Y --- yellow
-   K --- black/key

A logical ink state is the count tuple

\[ (C,M,Y,K) \]

with

\[ C+M+Y+K=4. \]

The number of distinct count tuples is therefore

\[ `\binom{4+4-1}{4}`{=tex}=`\binom{7}{4}`{=tex}=35. \]

These 35 states are the useful apparent colours/ownership mixtures.
Spatial permutations of the same four physical colours are considered
the **same logical state**.

For example, all of these literal patterns have logical state
`(2,1,1,0)`:

``` text
C M    C C    Y C
Y C    M Y    C M
```

There are (4\^4=256) literal 2×2 arrangements but only 35 logical
compositions.

## Canonical-pattern requirement

For visual coherence, *Don't Dither!* chooses **exactly one** of the
available literal 2×2 arrangements as the canonical rendering of each of
the 35 logical states.

Thus every region having the same ownership mixture has the same
repeated dither texture.

This is important. Allowing the physical arrangement to depend on the
history of a cell would make large uniform regions look like coloured
noise rather than deliberate halftone patterns.

The renderer therefore implements a function

\[ f:S`\rightarrow `{=tex}P \]

where:

-   \(S\) is the set of 35 logical ownership states;
-   \(P\) is the set of 256 literal 2×2 patterns;
-   (f(s)) is a literal pattern whose colour counts are exactly those of
    (s).

## Logical state transitions

One successful paint application transfers one ownership quantum from an
opponent (j) to the painter (i):

\[ s' = s + e_i - e_j \]

where (i`\ne `{=tex}j) and the victim currently has at least one
quantum:

\[ s_j\>0. \]

Two logical states are therefore adjacent if one can be obtained from
the other by moving one of the four ownership quanta from one colour to
another.

Across the complete 35-state space there are **120 undirected adjacent
state pairs**.

These edges form the state-transition graph whose physical rendering we
want to make Gray-code-like.

## Physical churn

For two canonical 2×2 patterns, define the churn as their **Hamming
distance**: the number of physical pixel positions whose colour differs.

A perfect one-quantum transition has

\[ d_H(f(s),f(s'))=1. \]

That is the ideal case: the logical operation transfers one ownership
quantum and the display update changes exactly one physical pixel.

For example:

``` text
before      after

C M         C C
Y C    ->   Y C
```

Only one physical pixel changes, and the logical C count increases from
2 to 3 while M decreases from 1 to 0.

A distance of 2 means the ownership change is still only one quantum,
but maintaining the chosen canonical dither phase requires one
additional physical pixel to change position/colour. Distances 3 and 4
are progressively less desirable.

## The Gray-code-like optimisation problem

The design problem is:

> Choose one legal literal representative for each of the 35 logical
> states so as to minimise Hamming-distance churn across the 120 logical
> adjacency edges.

This resembles a Gray code, but it is not a linear ordering. We are
trying to embed an entire 35-vertex adjacency graph into the
four-position, four-symbol Hamming space while respecting the
colour-count composition of every vertex.

The primary objective used in the search was to maximise the number of
adjacency edges with Hamming distance 1. Secondary objectives can
minimise distance-2 and especially distance-3/4 transitions.

## Best solution found

The search produced a canonical assignment with the following
distribution over all 120 logical adjacency edges:

    Physical pixels changed   Number of state transitions    Fraction
  ------------------------- ----------------------------- -----------
                          1                        **84**   **70.0%**
                          2                        **35**   **29.2%**
                          3                         **1**    **0.8%**
                          4                         **0**      **0%**
                  **Total**                       **120**    **100%**

Thus **119 of the 120 transitions require at most two physical pixel
changes**, and 84 transitions---the substantial majority---are perfect
one-pixel transitions.

This is already excellent for the game: a logical ownership change is
visually very local, and gross rearrangement of a dither cell is
essentially absent.

### Status of optimality

The 84/35/1/0 result is a **demonstrated solution**, not a proved global
optimum.

A heuristic search found the 84 one-pixel-edge assignment. An exact
integer optimisation formulation was also attempted, but it did not
complete a proof of optimality within the available solve time.

Accordingly, do **not** encode "84 is mathematically optimal" as a
design assumption. A later exhaustive/constraint search may improve it.

Likewise, a perfect 120/120 canonical embedding was **not found**, but
the work recorded here did not establish a formal impossibility proof
for the unconstrained canonical-pattern problem.

There *is* a separate impossibility result concerning fully symmetric
deterministic victim selection; see below.

## Why not retain arbitrary physical phases?

If a cell were allowed to retain any of the literal arrangements
belonging to its logical state, every paint operation could trivially
change the actual victim pixel in place. Physical churn could then
always be one pixel.

That approach was rejected because it loses a valuable visual invariant:

> **Equal ownership ratios should produce equal spatial patterns.**

With arbitrary phases, a large `(2,1,1,0)` region would contain many
permutations of C, C, M and Y and would appear noisy. Canonical patterns
instead make it a coherent repeated halftone texture.

Minimal churn is therefore subordinate to canonical visual uniformity.

## Fairness is a separate problem

The canonical-pattern optimisation must not decide game fairness.

Suppose the current state is

\[ (1,1,1,1) \]

and C paints it. C must take one quantum from M, Y or K.

No deterministic rule based solely on this perfectly symmetric
composition can choose one of M, Y and K while remaining invariant under
**all** permutations of the four colour labels. Choosing M, for example,
necessarily distinguishes M from the otherwise equivalent Y and K.

This is the genuine symmetry obstruction discovered during the work. It
concerns **victim selection**, not the 84/120 canonical-rendering
result.

The game therefore separates:

1.  **ownership mechanics** --- decide fairly which represented opponent
    loses one quantum;
2.  **canonical rendering** --- render the resulting logical state using
    its unique curated 2×2 pattern.

## Chosen victim rule

Each player keeps a small round-robin victim state.

For a painter:

1.  Begin after the opponent most recently displaced by that player.
2.  Scan cyclically through the other colours.
3.  Skip colours having zero ownership in the target cell.
4.  The first represented opponent found loses one quantum.
5.  The painter gains that quantum.
6.  Record the actual victim as the painter's new `last_victim`.
7.  If the cell is already 100% owned by the painter, do nothing and do
    not advance the victim state.

Conceptually:

``` text
paint(state, painter):
    if state[painter] == 4:
        return state

    victim = colour_after(last_victim[painter])

    while victim == painter or state[victim] == 0:
        victim = colour_after(victim)

    state[victim]  -= 1
    state[painter] += 1
    last_victim[painter] = victim

    return state
```

This is deterministic, very cheap on a 6502, avoids pseudorandom
generation, and distributes displacement among represented opponents
over successive paint operations.

## Example evolution

The four-player initial state is:

\[ (1,1,1,1). \]

If C paints the same cell without interruption, three successful
transfers make it solid C:

\[ (1,1,1,1) `\rightarrow`{=tex} (2,0,1,1) `\rightarrow`{=tex} (3,0,0,1)
`\rightarrow`{=tex} (4,0,0,0) \]

for one possible round-robin victim phase.

Each arrow is **one logical ownership transfer**. Under the chosen
canonical dither table, most such arrows will also change exactly one
physical pixel; nearly all remaining arrows change only two.

A cell already solidly owned by M,

\[ (0,4,0,0), \]

requires four C applications:

\[ (0,4,0,0) `\rightarrow`{=tex} (1,3,0,0) `\rightarrow`{=tex} (2,2,0,0)
`\rightarrow`{=tex} (3,1,0,0) `\rightarrow`{=tex} (4,0,0,0). \]

## Implementation consequences

The runtime should treat the 35-state ownership tuple and its canonical
pattern as distinct concepts even if the framebuffer is the
authoritative storage.

Useful precomputed tables include:

``` text
pattern_to_state[256]
state_to_pattern[35]
state_counts[35][4]
```

and, if ROM space is preferable to arithmetic:

``` text
transition[state][painter][victim] -> new_state
```

Only transitions with `victim != painter` and a non-zero victim count
are legal.

The renderer then replaces the old canonical 2×2 pattern with the
canonical pattern of `new_state`. Depending on the edge, this changes
one, two, or exceptionally three physical pixels.

Because the screen buffer itself stores the canonical pattern, no
separate 16 KB ownership grid is required.

## Further optimisation work

If revisiting the search, use lexicographic objectives rather than
merely maximising Hamming-1 edges:

1.  maximise the number of distance-1 edges;
2.  subject to that, minimise distance-3 and distance-4 edges
    aggressively;
3.  minimise total Hamming distance;
4.  impose aesthetic constraints on the five partition families:
    -   `4`
    -   `3+1`
    -   `2+2`
    -   `2+1+1`
    -   `1+1+1+1`
5.  favour equivalent-looking motifs under colour substitution;
6.  inspect the resulting repeated textures over large filled regions,
    not merely individual 2×2 cells.

It may be preferable to accept slightly fewer than 84 one-pixel
transitions if doing so eliminates the sole three-pixel transition or
produces substantially better-looking canonical dithers.

## Design invariants

The final implementation should preserve these properties:

-   There are exactly **35 logical ink states**.
-   Every logical state has exactly **one canonical 2×2 rendering**.
-   Every successful paint application transfers exactly **one ownership
    quantum**.
-   Victim selection is determined by the fair round-robin game rule,
    not by whichever canonical transition happens to be cheapest to
    render.
-   Physical rendering churn is minimised but is not itself game state.
-   Equal ownership tuples always look identical wherever they occur.
-   The framebuffer therefore remains both a visually coherent dithered
    image and a compact encoding of territory state.
