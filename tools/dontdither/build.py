"""Build the Don't Dither! disc image.

Generates the table sources into build/generated/, then assembles each
file in PROGRAMS with beebasm onto one DFS disc image. The disc's !BOOT runs
SPLASH (title screen and choice of players), which runs the game; the test
card is started with *RUN TCARD.
Then the level sets LEVELS2 and LEVELS4, which the game's loader loads (one
of them, as the player chooses), are generated for the game's level area and
added. Each file's labels are written to build/labels/<NAME>.txt.

    uv run dd-build
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from dontdither.gen_tables import LEVEL_TEMP, generate_all, generate_level_set
from dontdither.inks import PROJECT_DIRPATH, InkTable
from dontdither.levels import PLAYER_COUNTS

BUILD_DIRPATH = PROJECT_DIRPATH / "build"
GENERATED_DIRPATH = BUILD_DIRPATH / "generated"
DISC_FILEPATH = BUILD_DIRPATH / "dont-dither.ssd"
LABELS_DIRPATH = BUILD_DIRPATH / "labels"
ASM_DIRPATH = PROJECT_DIRPATH / "asm"

DISC_TITLE = "DONT DITHER"

# DFS file name -> source. The first is run by !BOOT; each source must SAVE
# a file of the same name.
PROGRAMS = {
    "SPLASH": ASM_DIRPATH / "splash.asm",
    "DITHER": ASM_DIRPATH / "main.asm",
    "TCARD": ASM_DIRPATH / "testcard.asm",
    "LOGO": GENERATED_DIRPATH / "logo.asm",
    "TUNE": ASM_DIRPATH / "tune.asm",
}
BOOT_PROGRAM = "SPLASH"
GAME_PROGRAM = "DITHER"


@dataclass(frozen=True)
class BuildResult:
    disc_filepath: Path
    labels: dict[str, dict[str, int]]   # program name -> label -> address


def find_beebasm() -> str:
    beebasm = shutil.which("beebasm")
    if beebasm is None:
        raise FileNotFoundError("beebasm not found on PATH")
    return beebasm


def parse_labels(text: str) -> dict[str, int]:
    """Parse beebasm's -labels output, a list of dict literals such as
    [{'start':6400L,...}], into a single name-to-address mapping."""
    scopes = ast.literal_eval(re.sub(r"(\d+)L\b", r"\1", text.strip()))
    return {name: address for scope in scopes for name, address in scope.items()}


def _assemble(source_filepath: Path, labels_filepath: Path, disc_args: list[str]) -> None:
    # beebasm resolves INCLUDE paths relative to its working directory, so
    # assemble from the project root.
    result = subprocess.run(
        [
            find_beebasm(),
            "-i", str(source_filepath.relative_to(PROJECT_DIRPATH)),
            *disc_args,
            "-d", "-labels", str(labels_filepath.relative_to(PROJECT_DIRPATH)),
        ],
        cwd=PROJECT_DIRPATH,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"beebasm failed on {source_filepath.name}:\n{result.stdout}\n{result.stderr}")


def build() -> BuildResult:
    generate_all(GENERATED_DIRPATH)
    LABELS_DIRPATH.mkdir(parents=True, exist_ok=True)
    disc = str(DISC_FILEPATH.relative_to(PROJECT_DIRPATH))
    staging = str(DISC_FILEPATH.with_suffix(".staging.ssd").relative_to(PROJECT_DIRPATH))

    labels = {}
    for name, source_filepath in PROGRAMS.items():
        labels_filepath = LABELS_DIRPATH / f"{name}.txt"
        if name == BOOT_PROGRAM:
            # Create a fresh disc with a !BOOT that runs the game.
            disc_args = ["-do", disc, "-boot", name, "-title", DISC_TITLE]
            _assemble(source_filepath, labels_filepath, disc_args)
        else:
            # Add to the existing disc via a staging copy.
            _assemble(source_filepath, labels_filepath, ["-di", disc, "-do", staging])
            (PROJECT_DIRPATH / staging).replace(DISC_FILEPATH)
        labels[name] = parse_labels(labels_filepath.read_text())

    # Level sets: assembled at the game's level area (known only now), and
    # saved to load at LEVEL_TEMP, from where the game's loader copies them.
    game = labels[GAME_PROGRAM]
    table = InkTable.load()
    for players in PLAYER_COUNTS:
        source_filepath = GENERATED_DIRPATH / f"levels{players}.asm"
        source_filepath.write_text(generate_level_set(table, players, game["level_area"]))
        name = f"LEVELS{players}"
        labels_filepath = LABELS_DIRPATH / f"{name}.txt"
        _assemble(source_filepath, labels_filepath, ["-di", disc, "-do", staging])
        (PROJECT_DIRPATH / staging).replace(DISC_FILEPATH)
        labels[name] = parse_labels(labels_filepath.read_text())
        size = labels[name]["level_set_end"] - labels[name]["level_set_start"]
        if LEVEL_TEMP + size > 0x7C00:
            raise RuntimeError(f"{name} ({size} bytes) would reach MODE 7 screen memory when loaded")
    return BuildResult(DISC_FILEPATH, labels)


def main() -> None:
    try:
        result = build()
    except (RuntimeError, FileNotFoundError) as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    print(f"Built {result.disc_filepath.relative_to(PROJECT_DIRPATH)} "
          f"with {', '.join(result.labels)}")


if __name__ == "__main__":
    main()
