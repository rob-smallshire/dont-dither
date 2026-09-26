"""Fixtures for driving Don't Dither! in Beebium.

`launch_bbc` is a factory: call it to launch a BBC Micro with a chosen preset
and extra server arguments; every machine it launched is shut down at the end
of the test. `bbc` shadows the beebium plugin's fixture of the same name with
one launched through the factory, so it gets a disc controller.

This mirrors the fixture design proposed upstream in beebium issue #105 and
can be replaced by the plugin's own fixtures when that lands. Preset lookup
by name works around beebium issue #104.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from beebium.client import Beebium
from beebium.client.exceptions import ServerNotFoundError
from beebium.client.installation import ServerInstallation

from dontdither.build import BuildResult, build

DEFAULT_PRESET = "model-b-disc"   # Model B, Acorn 1770 FDC, DFS 2.26 in slot 14
BOOT_TIMEOUT_EMULATED_SECONDS = 20.0
SETTLE_EMULATED_SECONDS = 0.04     # two frames

Launcher = Callable[..., Beebium]


def resolve_preset_filepath(preset: str | Path, server_filepath: Path | None) -> Path:
    """Accept a preset file path, or the name of one of the server's built-in presets."""
    if Path(preset).is_file():
        return Path(preset)
    installation = (
        ServerInstallation.coerce(server_filepath) if server_filepath else ServerInstallation.default()
    )
    if installation.preset_dirpath is None:
        raise FileNotFoundError(f"Server {installation.describe()} has no preset directory")
    filepath = installation.preset_dirpath / f"{preset}.preset.beebium"
    if not filepath.is_file():
        raise FileNotFoundError(f"No preset {preset!r} at {filepath}")
    return filepath


@contextlib.contextmanager
def _launcher(
    mos_filepath: Path,
    basic_filepath: Path | None,
    server_filepath: Path | None,
    default_preset: str | Path | None,
) -> Iterator[Launcher]:
    with contextlib.ExitStack() as stack:

        def launch(
            *,
            preset: str | Path | None = default_preset,
            variant: str = "model-b",
            extra_args: tuple[str, ...] = (),
        ) -> Beebium:
            args = list(extra_args)
            if preset is not None:
                args = ["--preset", str(resolve_preset_filepath(preset, server_filepath)), *args]
            try:
                return stack.enter_context(
                    Beebium.launch(
                        mos_filepath=mos_filepath,
                        basic_filepath=basic_filepath,
                        server=server_filepath,
                        variant=variant,
                        extra_args=args,
                    )
                )
            except ServerNotFoundError as e:
                pytest.skip(str(e))

        yield launch


@pytest.fixture(scope="session")
def beebium_preset() -> str | Path | None:
    """The preset `bbc` and `launch_bbc` use by default. Override to change it."""
    return DEFAULT_PRESET


@pytest.fixture
def launch_bbc(mos_filepath, basic_filepath, beebium_server_filepath, beebium_preset) -> Iterator[Launcher]:
    with _launcher(mos_filepath, basic_filepath, beebium_server_filepath, beebium_preset) as launch:
        yield launch


@pytest.fixture
def bbc(launch_bbc: Launcher) -> Beebium:
    return launch_bbc()


@pytest.fixture(scope="session")
def game_build() -> BuildResult:
    """Build the game disc once per test session."""
    try:
        return build()
    except FileNotFoundError as e:
        pytest.skip(str(e))


BOOT_READY = 0xFF   # asm/zeropage.asm; `=` constants are not exported as labels


def _run_until_ready(bbc: Beebium, labels: dict[str, int], what: str) -> None:
    status_address = labels["zp_boot_status"]
    bbc.debugger.stop()
    ready = bbc.run_until_or_timeout(
        lambda: bbc.memory.address.peek[status_address] == BOOT_READY,
        BOOT_TIMEOUT_EMULATED_SECONDS,
    )
    assert ready, f"{what} did not become ready within {BOOT_TIMEOUT_EMULATED_SECONDS} emulated seconds"
    # Screen text and captured frames reflect what has been displayed, not
    # what is in screen memory. Run two more 50 Hz frames so the final
    # screen has been scanned out.
    bbc.run_for_emulated_seconds(SETTLE_EMULATED_SECONDS)


def enter_routine(bbc: Beebium, labels: dict[str, int], routine: str, what: str) -> None:
    """Jump the idling program to one of its routines and run until ready.

    The program must be idling in its `idle` loop. Running to `idle` first
    stops the CPU at an instruction boundary: after cycle-based stepping it
    may be part-way through an instruction, and writing PC then corrupts the
    instruction in flight (reported to beebium-architect).
    """
    bbc.debugger.run_to(labels["idle"])
    bbc.cpu.pc = labels[routine]
    _run_until_ready(bbc, labels, what)


def boot_game(bbc: Beebium, game_build: BuildResult) -> None:
    """Shift-Break boot the game disc and run until the game reports it is ready.

    Leaves the machine stopped.
    """
    bbc.boot_disc(game_build.disc_filepath)
    _run_until_ready(bbc, game_build.labels["DITHER"], "Game")


def run_program(bbc: Beebium, game_build: BuildResult, program: str) -> None:
    """Insert the game disc, *RUN one of its programs from the BASIC prompt,
    and run until it reports it is ready. Leaves the machine stopped."""
    bbc.expect("BASIC")
    bbc.disc.drive(0).insert(str(game_build.disc_filepath))
    bbc.keyboard.type(f"*RUN {program}")
    bbc.keyboard.press_return()
    _run_until_ready(bbc, game_build.labels[program], program)


@pytest.fixture(scope="module")
def module_launch_bbc(mos_filepath, basic_filepath, beebium_server_filepath, beebium_preset) -> Iterator[Launcher]:
    """Like launch_bbc, but machines live for the whole test module."""
    with _launcher(mos_filepath, basic_filepath, beebium_server_filepath, beebium_preset) as launch:
        yield launch


@pytest.fixture(scope="module")
def booted_game(module_launch_bbc: Launcher, game_build: BuildResult) -> Beebium:
    """One machine per test module with the game booted and stopped.

    Tests sharing it must only observe, not change, the machine state.
    """
    bbc = module_launch_bbc()
    boot_game(bbc, game_build)
    return bbc


@pytest.fixture(scope="module")
def testcard(module_launch_bbc: Launcher, game_build: BuildResult) -> Beebium:
    """One machine per test module showing the test card, stopped.

    Tests sharing it must only observe, not change, the machine state.
    """
    bbc = module_launch_bbc()
    run_program(bbc, game_build, "TCARD")
    return bbc
