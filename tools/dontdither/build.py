"""Build the Don't Dither! disc image.

Generates the table sources into build/generated/, then assembles
asm/main.asm with beebasm into an auto-booting DFS disc image.

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

from dontdither.gen_tables import generate
from dontdither.inks import PROJECT_DIRPATH, InkTable

BUILD_DIRPATH = PROJECT_DIRPATH / "build"
GENERATED_DIRPATH = BUILD_DIRPATH / "generated"
DISC_FILEPATH = BUILD_DIRPATH / "dont-dither.ssd"
LABELS_FILEPATH = BUILD_DIRPATH / "labels.txt"
MAIN_ASM_FILEPATH = PROJECT_DIRPATH / "asm" / "main.asm"

BOOT_FILENAME = "DITHER"
DISC_TITLE = "DONT DITHER"


@dataclass(frozen=True)
class BuildResult:
    disc_filepath: Path
    labels: dict[str, int]


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


def build() -> BuildResult:
    GENERATED_DIRPATH.mkdir(parents=True, exist_ok=True)
    (GENERATED_DIRPATH / "ink_tables.asm").write_text(generate(InkTable.load()))

    # beebasm resolves INCLUDE paths relative to its working directory, so
    # assemble from the project root.
    result = subprocess.run(
        [
            find_beebasm(),
            "-i", str(MAIN_ASM_FILEPATH.relative_to(PROJECT_DIRPATH)),
            "-do", str(DISC_FILEPATH.relative_to(PROJECT_DIRPATH)),
            "-boot", BOOT_FILENAME,
            "-title", DISC_TITLE,
            "-d", "-labels", str(LABELS_FILEPATH.relative_to(PROJECT_DIRPATH)),
        ],
        cwd=PROJECT_DIRPATH,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"beebasm failed:\n{result.stdout}\n{result.stderr}")
    return BuildResult(DISC_FILEPATH, parse_labels(LABELS_FILEPATH.read_text()))


def main() -> None:
    try:
        result = build()
    except (RuntimeError, FileNotFoundError) as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    print(f"Built {result.disc_filepath.relative_to(PROJECT_DIRPATH)} "
          f"({len(result.labels)} labels)")


if __name__ == "__main__":
    main()
