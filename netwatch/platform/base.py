"""Platform backend primitives for OS-specific network facts."""

from __future__ import annotations

import re
import subprocess

IPV4_PATTERN = r"\d{1,3}(?:\.\d{1,3}){3}"
COLON_MAC_PATTERN = r"(?:[0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2}"
DASH_MAC_PATTERN = r"(?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2}"


class BasePlatformBackend:
    """Conservative default backend for platform-specific operations."""

    def get_default_gateway(self) -> str | None:
        """Return the default gateway IPv4 address when available."""
        return None

    def build_ping_command(self, host: str, timeout_seconds: float) -> list[str]:
        """Build a one-shot ping command."""
        return ["ping", "-c", "1", "-W", str(int(timeout_seconds)), host]

    def get_arp_commands(self) -> list[list[str]]:
        """Return ARP commands to run for this platform."""
        return [["arp", "-a"]]

    def parse_arp_output(self, text: str) -> list[tuple[str, str]]:
        """Parse ARP output into (ip, normalized_mac) pairs."""
        return parse_bsd_arp_output(text)

    def classify_interface(
        self,
        name: str,
        ipv4: str | None = None,
        mac: str | None = None,
    ) -> str:
        """Classify an interface as physical/vpn/virtual/loopback/unknown."""
        normalized = name.lower()
        if "loopback" in normalized or normalized in {"lo", "lo0"}:
            return "loopback"
        if any(
            keyword in normalized
            for keyword in (
                "utun",
                "wintun",
                "wireguard",
                "clash",
                "tailscale",
                "zerotier",
                "tun",
                "tap",
            )
        ):
            return "vpn"
        if any(
            keyword in normalized
            for keyword in (
                "docker",
                "bridge",
                "vmnet",
                "veth",
                "hyper-v",
                "vethernet",
                "vmware",
                "virtualbox",
                "npcap",
                "teredo",
                "isatap",
            )
        ):
            return "virtual"
        return "unknown"

    def get_ookla_install_hint(self) -> str:
        """Return a platform-appropriate official Ookla CLI install hint."""
        return (
            "Official Ookla CLI is not installed.\n"
            "请从 Ookla 官方渠道安装 speedtest，并确保 speedtest 在 PATH 中。"
        )

    def get_ookla_candidate_names(self) -> list[str]:
        """Return command names to probe via PATH."""
        return ["speedtest"]

    def run_command(self, command: list[str], timeout_seconds: int = 3) -> str:
        """Run a platform command and return stdout, or empty string on failure."""
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                errors="replace",
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if completed.returncode != 0:
            return ""
        return completed.stdout


def parse_bsd_arp_output(text: str) -> list[tuple[str, str]]:
    """Parse macOS/BSD-like ARP output."""
    entries: list[tuple[str, str]] = []
    pattern = re.compile(
        rf"^(?P<host>\S+)\s+\((?P<ip>{IPV4_PATTERN})\)\s+at\s+"
        rf"(?P<mac>{COLON_MAC_PATTERN}|[<(]incomplete[>)])"
    )
    for line in text.splitlines():
        match = pattern.search(line.strip())
        if not match:
            continue
        mac = normalize_mac_address(match.group("mac"))
        if mac is None:
            continue
        entries.append((match.group("ip"), mac))
    return entries


def normalize_mac_address(mac_address: str) -> str | None:
    """Normalize colon or dash separated MAC addresses to lowercase colon form."""
    lowered = mac_address.strip().lower()
    if lowered in {"<incomplete>", "(incomplete)", "incomplete"}:
        return None

    separator = "-" if "-" in lowered else ":"
    parts = lowered.split(separator)
    if len(parts) != 6:
        return None

    normalized_parts: list[str] = []
    for part in parts:
        if not 1 <= len(part) <= 2:
            return None
        try:
            value = int(part, 16)
        except ValueError:
            return None
        normalized_parts.append(f"{value:02x}")
    return ":".join(normalized_parts)


def is_ipv4_address(value: str) -> bool:
    """Return True when value is a syntactically valid IPv4 address."""
    parts = value.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False
