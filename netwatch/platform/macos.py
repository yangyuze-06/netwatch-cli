"""macOS platform backend."""

from __future__ import annotations

import re

from netwatch.platform.base import BasePlatformBackend


class MacOSBackend(BasePlatformBackend):
    """macOS implementation preserving existing command semantics."""

    def get_default_gateway(self) -> str | None:
        """Return the default gateway from `route -n get default`."""
        return parse_macos_default_gateway(self.run_command(["route", "-n", "get", "default"]))

    def build_ping_command(self, host: str, timeout_seconds: float) -> list[str]:
        """Build a macOS one-shot ping command."""
        return ["ping", "-c", "1", "-W", str(int(timeout_seconds)), host]

    def get_arp_commands(self) -> list[list[str]]:
        """Return fast numeric ARP first, then hostname enrichment."""
        return [["arp", "-an"], ["arp", "-a"]]

    def get_ookla_install_hint(self) -> str:
        """Return macOS official Ookla CLI install hint."""
        return (
            "Official Ookla CLI is not installed.\n"
            "macOS 推荐安装：\n"
            "brew tap teamookla/speedtest\n"
            "brew install speedtest"
        )


def parse_macos_default_gateway(output: str) -> str | None:
    """Parse `route -n get default` output."""
    match = re.search(r"^\s*gateway:\s*(?P<gateway>\d{1,3}(?:\.\d{1,3}){3})\s*$", output, re.MULTILINE)
    return match.group("gateway") if match else None
