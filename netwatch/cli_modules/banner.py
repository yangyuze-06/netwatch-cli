"""Startup banner for the interactive CLI."""

from __future__ import annotations

from shutil import get_terminal_size

CREATED_BY = "Created By"

LOGO_LINES = (
    r"   __   ___            _____ __    ___",
    r"  / /  <  /___  ____ _/ ___// /_  <  /",
    r" / /   / / __ \/ __ `/\__ \/ __ \ / / ",
    r"/ /___/ / / / / /_/ /___/ / / / // /  ",
    r"\____/_/_/ /_/\__, //____/_/ /_//_/   ",
    r"             /____/                   ",
)


def render_banner(width: int | None = None) -> str:
    """Render the startup banner with the logo centered for the terminal width."""
    if width is None:
        width = get_terminal_size(fallback=(100, 24)).columns

    centered_logo = "\n".join(line.center(width) for line in LOGO_LINES)
    return f"{CREATED_BY}\n\n{centered_logo}\n"


def print_banner() -> None:
    """Print the startup banner."""
    print(render_banner())
