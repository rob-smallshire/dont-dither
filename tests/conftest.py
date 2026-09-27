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

from dontdither.levels import PLAYER_COUNTS, level_set

# Every level, as (players, index within that level set), for tests that
# cover both sets; the game must be loaded with that many players.
SET_LEVELS = [(players, index) for players in (4, 2) for index in range(len(level_set(players)))]
SET_LEVEL_IDS = [f"{players}p-{level_set(players)[index].name}" for players, index in SET_LEVELS]

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


TICK_BOUNDARY = "tick_done"      # reached once per tick, between ticks


def align_to_tick(bbc: Beebium, labels: dict[str, int]) -> None:
    """Stop the game between ticks, at tick_done, with the tanks drawn."""
    if bbc.cpu.pc != labels[TICK_BOUNDARY]:
        bbc.debugger.run_to(labels[TICK_BOUNDARY])


def step_ticks(bbc: Beebium, labels: dict[str, int], count: int = 1) -> None:
    """Run the game for exactly `count` ticks, stopping at tick_done.

    From tick_done (where run_to would stop at once) each tick first steps
    one instruction off it; from anywhere else, running to tick_done
    completes the tick in progress (or, from main_loop, the first tick).
    """
    for _ in range(count):
        if bbc.cpu.pc == labels[TICK_BOUNDARY]:
            bbc.debugger.step(1)
        bbc.debugger.run_to(labels[TICK_BOUNDARY])


def enter_level(bbc: Beebium, labels: dict[str, int], level_number: int) -> None:
    """Start a level and stop just before its first tick, at main_loop.

    Nothing of the level's time has passed, so a model started from the
    level stays exactly in step.
    """
    align_to_tick(bbc, labels)
    bbc.memory.address.bus[labels["zp_level"]] = level_number
    bbc.cpu.pc = labels["enter_level"]
    bbc.debugger.run_to(labels["main_loop"])


def enter_routine(bbc: Beebium, labels: dict[str, int], routine: str, what: str) -> None:
    """Jump the running game to one of its routines and run until ready.

    Stopping at tick_done first puts the CPU at an instruction boundary:
    after cycle-based stepping it may be part-way through an instruction,
    and writing PC then corrupts the instruction in flight (beebium #106).
    """
    align_to_tick(bbc, labels)
    bbc.cpu.pc = labels[routine]
    _run_until_ready(bbc, labels, what)
    align_to_tick(bbc, labels)


def show_display(bbc: Beebium, labels: dict[str, int], seconds: float = SETTLE_EMULATED_SECONDS) -> None:
    """Scan out a few fields without the game running, so screen text and
    captured frames show the current screen memory. The game must be stopped
    at main_loop or tick_done (instruction boundaries); it is returned there,
    no tick having run."""
    resume = bbc.cpu.pc
    bbc.cpu.pc = labels["hold_display"]
    bbc.run_for_emulated_seconds(seconds)
    bbc.debugger.run_to(labels["hold_display"])     # back to a boundary
    bbc.cpu.pc = resume


def load_game(bbc: Beebium, game_build: BuildResult, players: int = 4) -> dict[str, int]:
    """Shift-Break boot the game disc, answer the loader's menu with the
    number of players (2 or 4, choosing that level set), and stop at the
    start of player selection. Returns the game's labels."""
    labels = game_build.labels["DITHER"]
    bbc.boot_disc(game_build.disc_filepath)
    bbc.debugger.run_to(labels["loader_key"], timeout=60)
    bbc.keyboard.type(str(players))
    bbc.debugger.run_to(labels["select_players"], timeout=60)
    return labels


def boot_game(bbc: Beebium, game_build: BuildResult, players: int = 4) -> None:
    """Load the game with a level set, skip player selection, and stop just
    before the set's first level's first tick, at main_loop, with the screen
    displayed.

    This enters level 0 directly, with the default session (players 1 and 2
    human, the rest the computer) and the default round length. No game time
    has passed, so a Game.start model is exactly in step."""
    labels = load_game(bbc, game_build, players)
    bbc.cpu.pc = labels["enter_level"]
    bbc.memory.address.bus[labels["zp_level"]] = 0
    bbc.debugger.run_to(labels["main_loop"])
    show_display(bbc, labels)


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
