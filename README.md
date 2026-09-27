# Don't Dither!

A four-colour territory game for the BBC Micro Model B, written in 6502
assembly (beebasm) and tested in the [Beebium](https://github.com/rob-smallshire/beebium)
emulator from Python with pytest.

The arena is a 128×128 grid of 2×2 MODE 1 superpixels. Each superpixel's
dither pattern *is* its ownership state: one of the 35 mixtures of cyan,
magenta, yellow and black. See [the design](docs/dont_dither_game_design.md),
[the decisions since](docs/decisions.md) and
[the architecture and implementation](docs/architecture.md).

<p align="center">
  <img src="docs/images/title_screen.png" width="48%"
       alt="The title screen: the Don't Dither! logo, the question of two or four players, each player's keys, and how ink works">
  <img src="docs/images/four_player_game.png" width="48%"
       alt="A four-player game on Four Corners, three minutes in: the arena painted in dithered cyan, magenta, yellow and black, with the ink gauges and the clock in the HUD">
</p>
<p align="center"><em>The title screen, and four computer players three minutes into a round on Four Corners.</em></p>

## Playing

Boot the disc (Shift-Break) on a Model B with DFS.

- **Two or four players:** the title screen asks; press 2 or 4. Each mode
  has its own set of levels.
- **Joining:** during the 10-second countdown, press your fire key to join.
  Up to four people can play on one keyboard, one per ink (two in a
  two-player game: cyan and magenta):

| Player | Up | Left | Down | Right | Fire |
|---|---|---|---|---|---|
| C (cyan) | W | A | S | D | SHIFT |
| M (magenta) | I | J | K | L | M |
| Y (yellow) | F | C | V | B | SPACE |
| K (black) | ↑ | ← | ↓ | → | \ |

  To change a player's keys, press f1–f4 on the title screen and press
  each key asked for (another player's keys, and ESCAPE, are refused).
  Keys you choose are kept when you press BREAK; CTRL-BREAK restores the
  defaults. The computer plays everyone else. If nobody joins, the computer plays a
  demo until you press a key. (The BBC keyboard has no diodes, so some
  combinations of three or more held keys can make another key appear
  pressed.)
- **A session** plays every level of the set, each a 5-minute round. Each
  shot splats paint that moves the cells it hits a step towards your ink.
  When time runs out the territory is tallied, and points are awarded by
  rank (3/2/1/0, or 3/0 with two players).
- **Music:** the title screen plays an original theme in the spirit of
  Splatoon's punk battle music (`docs/music.md`). `*RUN TUNE` plays it
  alone; `uv run dd-render-music` renders it to
  `build/music/splash_theme.wav` for listening on the host.
- **Tunnels:** on the later levels, gaps in the middle of the arena's
  edges lead through to the far side. Drive out of one and, after a
  moment out of sight, you come out of the other.
- **Ink:** firing uses ink from your reservoir, shown by the gauges at the
  bottom of the HUD. Release fire to refill. How fast you refill, and how
  fast you drive, depends on how much of your own ink is under you: your
  own colour is a fast road and a filling station; enemy ink slows you.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- [beebasm](https://github.com/stardot/beebasm) 1.10 on the `PATH`

The Beebium client and headless server come from PyPI via uv.

## Build and test

```bash
uv run dd-build     # -> build/dont-dither.ssd (auto-booting DFS disc)
uv run pytest       # builds, boots the disc in Beebium, checks the screen
```

The tests write screenshots to `build/screenshots/`, among them the title
screen (`splash.png`), the booted game (`boot.png`), the ink gauges
(`gauges.png`), every level and the test card (`testcard.png`,
`testcard_x3.png`). Music goes to `build/music/`: the title theme rendered
from the model (`splash_theme.wav`, also `uv run dd-render-music`) and
recorded from Beebium (`beebium_theme.wav`). The test
card, `*RUN TCARD` from the same disc, shows all 35 ink textures as large
swatches, each with a wall feature, inside a walled border.

The disc also runs in the Beebium macOS app, or any BBC Micro emulator, with
a Model B + DFS: Shift-Break to boot the game.

## Layout

| Path | Contents |
|---|---|
| `asm/` | 6502 source (beebasm). `splash.asm` is the title screen (the disc boots it), `main.asm` the game, `testcard.asm` the test card, `tune.asm` the title music alone; the rest are shared modules, among them `music.asm`, the music player. |
| `art/splash.png` | The logo, converted by the build for the title screen and the HUD. |
| `levels/` | Level source files (`*.lvl`): symmetric wall layouts, colouring and starts; 16 in each of the two- and four-player sets. Preview them all with `uv run dd-preview-levels`. |
| `sprites/` | Player tank and paint splats (`*.spr`, editable ASCII art); preview with `uv run dd-preview-sprites` and `uv run dd-preview-splats`. |
| `data/ink_patterns.json` | The canonical 2×2 pattern for each of the 35 ink states. Source of truth for the generated 6502 tables. |
| `tools/dontdither/` | Python: ink model, table generator, build, pattern solver. |
| `tests/` | pytest suite; `conftest.py` has the Beebium fixtures. |
| `docs/` | Design documents: the design, decisions since, and the architecture. |
| `build/` | Build output (generated tables, disc image, labels, screenshots). |

## The canonical ink patterns

`data/ink_patterns.json` is produced by `uv run --group solver dd-solve-patterns`,
which solves for the table exactly with OR-tools CP-SAT under three hard
constraints:

- every 2+2 state (50:50 mixture) is a checkerboard;
- in every 2+1+1 state the doubled ink lies on a diagonal, so it tiles as a
  checkerboard rather than one-pixel stripes;
- cycling inks C→M→Y→K corresponds to a clockwise 90° rotation of the tile,
  up to a one-pixel translation of the repeating texture.

Subject to those, it minimises the pixels changed by a one-quantum ownership
transfer: of the 120 adjacent state pairs, 78 change one pixel, 32 two,
6 three and 4 four (proved optimal). Without the diagonal constraint it
would be 78/36/6/0, and without any constraints 84/36/0/0. The checkerboard
and colour-cycling constraints cannot both hold strictly (without
translation): see `tools/dontdither/solve_patterns.py`.

This supersedes the table in `docs/dont_dither_35_minimal_churn_patterns.md`,
which is the unconstrained churn optimum.

## Licence

MIT: see [LICENSE](LICENSE).
