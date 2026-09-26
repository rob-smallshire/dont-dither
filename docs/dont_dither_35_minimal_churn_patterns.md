# Don't Dither! --- 35 Canonical Minimal-Churn Ink Patterns

This document enumerates a newly regenerated canonical 2×2 pattern
assignment for all 35 CMYK ownership states.

## Verified churn result

The assignment was found by heuristic optimisation over the complete
35-state adjacency graph and independently checked after generation.

-   Logical states: **35**
-   Undirected one-quantum adjacency edges: **120**
-   Edges rendered by changing exactly **1 physical pixel: 84 (70%)**
-   Edges rendered by changing exactly **2 physical pixels: 36 (30%)**
-   Edges requiring 3 or 4 pixel changes: **0**
-   Maximum physical churn for any legal adjacent-state transition: **2
    pixels**

This improves on the earlier retained 84/35/1 result by eliminating its
sole three-pixel transition. It is a very good demonstrated assignment,
but **84 one-pixel edges is not claimed to be a proved global optimum**.

## Encoding

Each pattern is written in row-major order as `TL TR / BL BR`. The
hexadecimal code is a convenient machine-independent packed
representation with `C=0`, `M=1`, `Y=2`, `K=3`:

``` text
bits 7..6 = top-left
bits 5..4 = top-right
bits 3..2 = bottom-left
bits 1..0 = bottom-right
```

This packed code is **not** the BBC MODE 1 screen-byte representation;
it is simply a compact identifier suitable for tables/tools. Convert it
to the appropriate `&CC`/`&33` MODE 1 half-byte patterns when generating
BBC runtime tables.

## Canonical patterns

    \#  State `(C,M,Y,K)`         2×2 pattern         Row-major     Code
  ---- ------------------- ------------------------- ----------- -------
    00   `(0, 0, 0, 4)`     `K K``<br>`{=html}`K K`    `KKKK`      `&FF`
    01   `(0, 0, 1, 3)`     `K K``<br>`{=html}`K Y`    `KKKY`      `&FE`
    02   `(0, 0, 2, 2)`     `K K``<br>`{=html}`Y Y`    `KKYY`      `&FA`
    03   `(0, 0, 3, 1)`     `Y K``<br>`{=html}`Y Y`    `YKYY`      `&BA`
    04   `(0, 0, 4, 0)`     `Y Y``<br>`{=html}`Y Y`    `YYYY`      `&AA`
    05   `(0, 1, 0, 3)`     `M K``<br>`{=html}`K K`    `MKKK`      `&7F`
    06   `(0, 1, 1, 2)`     `M K``<br>`{=html}`K Y`    `MKKY`      `&7E`
    07   `(0, 1, 2, 1)`     `M K``<br>`{=html}`Y Y`    `MKYY`      `&7A`
    08   `(0, 1, 3, 0)`     `M Y``<br>`{=html}`Y Y`    `MYYY`      `&6A`
    09   `(0, 2, 0, 2)`     `M K``<br>`{=html}`M K`    `MKMK`      `&77`
    10   `(0, 2, 1, 1)`     `M K``<br>`{=html}`M Y`    `MKMY`      `&76`
    11   `(0, 2, 2, 0)`     `M Y``<br>`{=html}`M Y`    `MYMY`      `&66`
    12   `(0, 3, 0, 1)`     `M K``<br>`{=html}`M M`    `MKMM`      `&75`
    13   `(0, 3, 1, 0)`     `M M``<br>`{=html}`M Y`    `MMMY`      `&56`
    14   `(0, 4, 0, 0)`     `M M``<br>`{=html}`M M`    `MMMM`      `&55`
    15   `(1, 0, 0, 3)`     `K K``<br>`{=html}`C K`    `KKCK`      `&F3`
    16   `(1, 0, 1, 2)`     `K K``<br>`{=html}`C Y`    `KKCY`      `&F2`
    17   `(1, 0, 2, 1)`     `Y K``<br>`{=html}`C Y`    `YKCY`      `&B2`
    18   `(1, 0, 3, 0)`     `Y Y``<br>`{=html}`C Y`    `YYCY`      `&A2`
    19   `(1, 1, 0, 2)`     `M K``<br>`{=html}`C K`    `MKCK`      `&73`
    20   `(1, 1, 1, 1)`     `M K``<br>`{=html}`C Y`    `MKCY`      `&72`
    21   `(1, 1, 2, 0)`     `M Y``<br>`{=html}`C Y`    `MYCY`      `&62`
    22   `(1, 2, 0, 1)`     `M K``<br>`{=html}`C M`    `MKCM`      `&71`
    23   `(1, 2, 1, 0)`     `M M``<br>`{=html}`C Y`    `MMCY`      `&52`
    24   `(1, 3, 0, 0)`     `M M``<br>`{=html}`C M`    `MMCM`      `&51`
    25   `(2, 0, 0, 2)`     `C K``<br>`{=html}`C K`    `CKCK`      `&33`
    26   `(2, 0, 1, 1)`     `C K``<br>`{=html}`C Y`    `CKCY`      `&32`
    27   `(2, 0, 2, 0)`     `Y C``<br>`{=html}`C Y`    `YCCY`      `&82`
    28   `(2, 1, 0, 1)`     `M K``<br>`{=html}`C C`    `MKCC`      `&70`
    29   `(2, 1, 1, 0)`     `M C``<br>`{=html}`C Y`    `MCCY`      `&42`
    30   `(2, 2, 0, 0)`     `M M``<br>`{=html}`C C`    `MMCC`      `&50`
    31   `(3, 0, 0, 1)`     `C K``<br>`{=html}`C C`    `CKCC`      `&30`
    32   `(3, 0, 1, 0)`     `C C``<br>`{=html}`C Y`    `CCCY`      `&02`
    33   `(3, 1, 0, 0)`     `M C``<br>`{=html}`C C`    `MCCC`      `&40`
    34   `(4, 0, 0, 0)`     `C C``<br>`{=html}`C C`    `CCCC`      `&00`

## Machine-readable table

The following table uses the state numbering above. Each four-character
string is `TL,TR,BL,BR`:

``` text
00  (0, 0, 0, 4)  KKKK  &FF
01  (0, 0, 1, 3)  KKKY  &FE
02  (0, 0, 2, 2)  KKYY  &FA
03  (0, 0, 3, 1)  YKYY  &BA
04  (0, 0, 4, 0)  YYYY  &AA
05  (0, 1, 0, 3)  MKKK  &7F
06  (0, 1, 1, 2)  MKKY  &7E
07  (0, 1, 2, 1)  MKYY  &7A
08  (0, 1, 3, 0)  MYYY  &6A
09  (0, 2, 0, 2)  MKMK  &77
10  (0, 2, 1, 1)  MKMY  &76
11  (0, 2, 2, 0)  MYMY  &66
12  (0, 3, 0, 1)  MKMM  &75
13  (0, 3, 1, 0)  MMMY  &56
14  (0, 4, 0, 0)  MMMM  &55
15  (1, 0, 0, 3)  KKCK  &F3
16  (1, 0, 1, 2)  KKCY  &F2
17  (1, 0, 2, 1)  YKCY  &B2
18  (1, 0, 3, 0)  YYCY  &A2
19  (1, 1, 0, 2)  MKCK  &73
20  (1, 1, 1, 1)  MKCY  &72
21  (1, 1, 2, 0)  MYCY  &62
22  (1, 2, 0, 1)  MKCM  &71
23  (1, 2, 1, 0)  MMCY  &52
24  (1, 3, 0, 0)  MMCM  &51
25  (2, 0, 0, 2)  CKCK  &33
26  (2, 0, 1, 1)  CKCY  &32
27  (2, 0, 2, 0)  YCCY  &82
28  (2, 1, 0, 1)  MKCC  &70
29  (2, 1, 1, 0)  MCCY  &42
30  (2, 2, 0, 0)  MMCC  &50
31  (3, 0, 0, 1)  CKCC  &30
32  (3, 0, 1, 0)  CCCY  &02
33  (3, 1, 0, 0)  MCCC  &40
34  (4, 0, 0, 0)  CCCC  &00
```

## Runtime use

The logical game operation remains a one-quantum ownership transfer.
Victim selection is performed by the game's fair round-robin rule. Once
the new `(C,M,Y,K)` state is known, render the canonical pattern listed
here. Therefore the renderer may rewrite two physical pixels even though
only one ownership quantum changed; this is intentional and preserves a
unique, coherent dither phase for each logical state.

Recommended generated tables are:

``` text
state_to_pattern[35]
pattern_to_state[256]
state_counts[35][4]
transition[state][painter][victim]
```

Only the 35 patterns above are canonical ink patterns. Other literal 2×2
CMYK arrangements can be treated as invalid/non-canonical in the bare
arena framebuffer.

## Verification invariant

For every adjacent logical state pair, the canonical patterns in this
document differ in either one or two physical positions, never three or
four. Any later aesthetic editing of an individual pattern must
therefore rerun the complete 120-edge verification rather than assuming
the property is preserved.
