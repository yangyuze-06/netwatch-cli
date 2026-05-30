"""Shared CLI presentation helpers."""

from __future__ import annotations

import sys

from rich.console import Console

_default_console = Console()


class ConsoleProxy:
    """Use netwatch.cli.console when tests or callers replace it."""

    def __getattr__(self, name: str):
        cli_module = sys.modules.get("netwatch.cli")
        active_console = getattr(cli_module, "console", None) if cli_module is not None else None
        return getattr(active_console or _default_console, name)


console = ConsoleProxy()


def cli_override(name: str, default, current=None):
    """Return a monkeypatched legacy netwatch.cli attribute when present."""
    cli_module = sys.modules.get("netwatch.cli")
    if cli_module is None:
        return default
    candidate = getattr(cli_module, name, None)
    if candidate is None or candidate is current:
        return default
    return candidate
