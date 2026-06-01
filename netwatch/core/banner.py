"""Startup banner for the interactive CLI."""

from __future__ import annotations

import os
import shutil
import sys
import time

CREATED_BY = "Created By"

LOGO_LINES = (
    r"   __   ___            _____ __    ___",
    r"  / /  <  /___  ____ _/ ___// /_  <  /",
    r" / /   / / __ \/ __ `/\__ \/ __ \ / / ",
    r"/ /___/ / / / / /_/ /___/ / / / // /  ",
    r"\____/_/_/ /_/\__, //____/_/ /_//_/   ",
    r"             /____/                   ",
)


def terminal_width(default: int = 100) -> int:
    """Return the current terminal width with a stable fallback."""
    return shutil.get_terminal_size(fallback=(default, 24)).columns


def render_banner(width: int | None = None) -> str:
    """Render the startup banner with the logo centered for the terminal width."""
    if width is None:
        width = terminal_width()

    centered_logo = "\n".join(line.center(width) for line in LOGO_LINES)
    return f"{CREATED_BY}\n\n{centered_logo}\n"


def render_loading_bar(step: int, total: int, width: int = 18) -> str:
    """Render a compact startup loading bar."""
    if total <= 0:
        total = 1

    ratio = max(0.0, min(1.0, step / total))
    filled = int(width * ratio)
    bar = "#" * filled + "-" * (width - filled)
    percent = int(ratio * 100)
    return f"Initializing netwatch-core [{bar}] {percent:3d}%"


def clear_screen() -> None:
    """Clear the terminal screen when stdout is interactive."""
    if not sys.stdout.isatty():
        return
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def should_animate() -> bool:
    """Return True when startup animation should run."""
    if not sys.stdout.isatty():
        return False
    if os.getenv("CI"):
        return False
    if os.getenv("NETWATCH_NO_ANIMATION"):
        return False
    return True


def play_startup_animation(duration: float = 1.0) -> None:
    """Play the short interactive startup animation."""
    if not should_animate():
        print(render_banner())
        return

    width = terminal_width()
    frames = 10
    delay = duration / frames

    clear_screen()
    print(render_banner(width=width))
    print()

    for step in range(frames + 1):
        line = render_loading_bar(step, frames).center(width)
        sys.stdout.write("\r\033[K" + line)
        sys.stdout.flush()
        time.sleep(delay)

    sys.stdout.write("\n")
    sys.stdout.flush()
    clear_screen()


def print_banner() -> None:
    """Print the startup banner."""
    play_startup_animation()
