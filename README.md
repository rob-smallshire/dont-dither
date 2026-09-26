# Don't Dither!

A four-colour territory game for the BBC Micro Model B, written in 6502
assembly (beebasm) and tested in the [Beebium](https://github.com/rob-smallshire/beebium)
emulator from Python with pytest.

The arena is a 128×128 grid of 2×2 MODE 1 superpixels. Each superpixel's
dither pattern *is* its ownership state: one of the 35 mixtures of cyan,
magenta, yellow and black. See [the design](docs/dont_dither_game_design.md).

## Requirements

- [uv](https://docs.astral.sh/uv/)
- [beebasm](https://github.com/stardot/beebasm) 1.10 on the `PATH`

The Beebium client and headless server come from PyPI via uv.

## Build and test

```bash
uv run dd-build     # -> build/dont-dither.ssd (auto-booting DFS disc)
uv run pytest       # builds, boots the disc in Beebium, checks the screen
```

The tests write screenshots to `build/screenshots/`: the booted game
(`boot.png`) and the test card (`testcard.png`, `testcard_x3.png`). The test
card, `*RUN TCARD` from the same disc, shows all 35 ink textures as large
swatches, each with a wall feature, inside a walled border.

The disc also runs in the Beebium macOS app, or any BBC Micro emulator, with
a Model B + DFS: Shift-Break to boot the game.

## Layout

| Path | Contents |
|---|---|
| `asm/` | 6502 source (beebasm). `main.asm` is the game, `testcard.asm` the test card; the rest are shared modules. |
| `levels/` | Level source files (`*.lvl`): symmetric wall layouts, colouring and starts. |
| `sprites/` | Player tank and paint splats (`*.spr`, editable ASCII art); preview with `uv run dd-preview-sprites` and `uv run dd-preview-splats`. |
| `data/ink_patterns.json` | The canonical 2×2 pattern for each of the 35 ink states. Source of truth for the generated 6502 tables. |
| `tools/dontdither/` | Python: ink model, table generator, build, pattern solver. |
| `tests/` | pytest suite; `conftest.py` has the Beebium fixtures. |
| `docs/` | Design documents. |
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
