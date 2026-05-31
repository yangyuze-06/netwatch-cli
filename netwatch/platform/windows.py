"""Windows platform backend."""

from __future__ import annotations

import re

from netwatch.platform.base import (
    DASH_MAC_PATTERN,
    IPV4_PATTERN,
    BasePlatformBackend,
    is_ipv4_address,
    normalize_mac_address,
)

VPN_KEYWORDS = (
    "wintun",
    "wireguard",
    "clash",
    "tailscale",
    "zerotier",
    "tun",
    "tap",
)
VIRTUAL_KEYWORDS = (
    "hyper-v",
    "vethernet",
    "vmware",
    "virtualbox",
    "npcap",
    "teredo",
    "isatap",
)
PHYSICAL_KEYWORDS = ("wi-fi", "wifi", "wlan", "ethernet", "以太网")
LOOPBACK_KEYWORDS = ("loopback",)


class WindowsBackend(BasePlatformBackend):
    """Windows implementation for Phase 1 platform facts."""

    def get_default_gateway(self) -> str | None:
        """Return the default gateway using route print, then ipconfig."""
        gateway = parse_windows_route_print_gateway(self.run_command(["route", "print", "-4"]))
        if gateway:
            return gateway
        return parse_windows_ipconfig_gateway(self.run_command(["ipconfig"]))

    def build_ping_command(self, host: str, timeout_seconds: float) -> list[str]:
        """Build a Windows one-shot ping command."""
        timeout_ms = max(0, int(timeout_seconds * 1000))
        return ["ping", "-n", "1", "-w", str(timeout_ms), host]

    def get_arp_commands(self) -> list[list[str]]:
        """Return Windows ARP command."""
        return [["arp", "-a"]]

    def parse_arp_output(self, text: str) -> list[tuple[str, str]]:
        """Parse Windows `arp -a` output."""
        entries: list[tuple[str, str]] = []
        pattern = re.compile(rf"(?P<ip>{IPV4_PATTERN})\s+(?P<mac>{DASH_MAC_PATTERN})\s+\S+")
        for line in text.splitlines():
            match = pattern.search(line.strip())
            if not match:
                continue
            mac = normalize_mac_address(match.group("mac"))
            if mac is None:
                continue
            entries.append((match.group("ip"), mac))
        return entries

    def classify_interface(
        self,
        name: str,
        ipv4: str | None = None,
        mac: str | None = None,
    ) -> str:
        """Classify common Windows physical, VPN, virtual, and loopback interfaces."""
        normalized = name.lower()
        if any(keyword in normalized for keyword in LOOPBACK_KEYWORDS):
            return "loopback"
        if any(keyword in normalized for keyword in VPN_KEYWORDS):
            return "vpn"
        if any(keyword in normalized for keyword in VIRTUAL_KEYWORDS):
            return "virtual"
        if any(keyword in normalized for keyword in PHYSICAL_KEYWORDS):
            return "physical"
        return "unknown"

    def get_ookla_install_hint(self) -> str:
        """Return Windows official Ookla CLI install hint."""
        return (
            "Official Ookla CLI is not installed.\n"
            "Windows 推荐从 Ookla 官方下载 speedtest.exe，并将其所在目录加入 PATH。"
        )

    def get_ookla_candidate_names(self) -> list[str]:
        """Return Windows command names to probe via PATH."""
        return ["speedtest.exe", "speedtest"]


def parse_windows_route_print_gateway(text: str) -> str | None:
    """Parse `route print -4`, choosing the default route with the lowest metric."""
    candidates: list[tuple[int, str]] = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        if fields[0] != "0.0.0.0" or fields[1] != "0.0.0.0":
            continue
        gateway = fields[2]
        if gateway.lower() == "on-link" or not is_ipv4_address(gateway):
            continue
        try:
            metric = int(fields[-1])
        except ValueError:
            continue
        candidates.append((metric, gateway))

    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def parse_windows_ipconfig_gateway(text: str) -> str | None:
    """Parse default gateway from English or Chinese `ipconfig` output."""
    lines = text.splitlines()
    gateway_labels = ("default gateway", "默认网关")

    for index, line in enumerate(lines):
        normalized = line.lower()
        if not any(label in normalized for label in gateway_labels):
            continue

        inline_ip = first_ipv4(line)
        if inline_ip:
            return inline_ip

        for next_line in lines[index + 1 : index + 4]:
            candidate = first_ipv4(next_line)
            if candidate:
                return candidate
    return None


def first_ipv4(text: str) -> str | None:
    """Return the first valid IPv4 address from text."""
    for match in re.finditer(IPV4_PATTERN, text):
        candidate = match.group(0)
        if is_ipv4_address(candidate):
            return candidate
    return None
