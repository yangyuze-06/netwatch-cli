"""Windows platform backend."""

from __future__ import annotations

import re
import socket
from dataclasses import dataclass

import psutil

from netwatch.platform.base import (
    DASH_MAC_PATTERN,
    IPV4_PATTERN,
    BasePlatformBackend,
    infer_common_home_gateway_from_ipv4,
    is_ipv4_address,
    is_usable_lan_gateway_address,
    is_virtual_gateway_address,
    normalize_mac_address,
)

VPN_KEYWORDS = (
    "wintun",
    "wireguard",
    "vpn",
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
PHYSICAL_KEYWORDS = (
    "wi-fi",
    "wifi",
    "wlan",
    "ethernet",
    "以太网",
    "realtek",
    "intel",
    "qualcomm",
    "mediatek",
)
LOOPBACK_KEYWORDS = ("loopback",)


@dataclass(frozen=True)
class WindowsGatewayCandidate:
    """Gateway candidate explicitly reported by Windows route/ipconfig output."""

    gateway: str
    interface_ipv4: str | None
    interface_name: str | None = None
    metric: int = 9999


class WindowsBackend(BasePlatformBackend):
    """Windows implementation for Phase 1 platform facts."""

    def get_default_route_gateway(self) -> str | None:
        """Return the default gateway using route print, then ipconfig."""
        route_output = self.run_command(["route", "print", "-4"])
        gateway = parse_windows_route_print_gateway(route_output)
        if gateway:
            return gateway
        return parse_windows_ipconfig_gateway(self.run_command(["ipconfig"]))

    def get_lan_router_gateway(self) -> str | None:
        """Return the likely real LAN router gateway, ignoring VPN/TUN gateways."""
        interface_ipv4s = get_windows_interface_ipv4s()
        physical_lan_ipv4s: list[tuple[str, str]] = []
        for name, ipv4 in interface_ipv4s:
            interface_type = self.classify_interface(name, ipv4, None)
            if interface_type in {"loopback", "vpn", "virtual"}:
                continue
            if is_usable_lan_gateway_address(ipv4):
                physical_lan_ipv4s.append((name, ipv4))

        explicit_gateway = self.find_explicit_lan_gateway(physical_lan_ipv4s)
        if explicit_gateway:
            return explicit_gateway

        candidates: list[tuple[int, str]] = []
        for _name, ipv4 in physical_lan_ipv4s:
            gateway = infer_common_home_gateway_from_ipv4(ipv4)
            if gateway:
                candidates.append((lan_ip_preference_rank(ipv4), gateway))
        if candidates:
            return sorted(candidates, key=lambda item: item[0])[0][1]

        default_gateway = self.get_default_route_gateway()
        if default_gateway and is_usable_lan_gateway_address(default_gateway):
            return default_gateway
        return None

    def find_explicit_lan_gateway(self, physical_lan_ipv4s: list[tuple[str, str]]) -> str | None:
        """Prefer Windows-reported same-/24 LAN gateways before heuristic .1 guesses."""
        route_output = self.run_command(["route", "print", "-4"])
        ipconfig_output = self.run_command(["ipconfig"])
        candidates = parse_windows_route_print_default_routes(route_output)
        candidates.extend(parse_windows_ipconfig_adapter_gateways(ipconfig_output))

        ranked: list[tuple[int, int, str]] = []
        for candidate in candidates:
            if not is_usable_lan_gateway_address(candidate.gateway):
                continue
            match = matching_physical_lan_ip(candidate, physical_lan_ipv4s, self)
            if not match:
                continue
            ranked.append((lan_ip_preference_rank(match), candidate.metric, candidate.gateway))

        if not ranked:
            return None
        return sorted(ranked, key=lambda item: (item[0], item[1]))[0][2]

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
        if "clash meta" in normalized or ("meta" in normalized and "tun" in normalized):
            return "vpn"
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
    candidates = parse_windows_route_print_default_routes(text)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.metric)[0].gateway


def parse_windows_route_print_default_routes(text: str) -> list[WindowsGatewayCandidate]:
    """Parse default-route gateway candidates from `route print -4` output."""
    candidates: list[WindowsGatewayCandidate] = []
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
        interface_ipv4 = fields[3] if is_ipv4_address(fields[3]) else None
        candidates.append(WindowsGatewayCandidate(gateway, interface_ipv4, metric=metric))
    return candidates


def parse_windows_ipconfig_gateway(text: str) -> str | None:
    """Parse default gateway from English or Chinese `ipconfig` output."""
    adapter_gateways = parse_windows_ipconfig_adapter_gateways(text)
    if adapter_gateways:
        return adapter_gateways[0].gateway

    # Fallback for unusual ipconfig layouts that do not split output by adapter.
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


def parse_windows_ipconfig_adapter_gateways(text: str) -> list[WindowsGatewayCandidate]:
    """Parse per-adapter IPv4/default-gateway candidates from ipconfig output."""
    candidates: list[WindowsGatewayCandidate] = []
    current_name: str | None = None
    current_ipv4: str | None = None
    current_gateway: str | None = None
    lines = text.splitlines()
    gateway_labels = ("default gateway", "默认网关")
    ipv4_labels = ("ipv4", "ipv4 地址")

    def flush_current() -> None:
        nonlocal current_ipv4, current_gateway
        if current_gateway:
            candidates.append(WindowsGatewayCandidate(current_gateway, current_ipv4, current_name))
        current_ipv4 = None
        current_gateway = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        lower = stripped.lower()
        if stripped.endswith(":") and ("adapter" in lower or "适配器" in lower):
            flush_current()
            current_name = stripped[:-1]
            continue

        if any(label in lower for label in ipv4_labels):
            current_ipv4 = first_ipv4(stripped) or current_ipv4
            continue

        if any(label in lower for label in gateway_labels):
            current_gateway = first_ipv4(stripped)
            if current_gateway:
                continue
            for next_line in lines[index + 1 : index + 4]:
                candidate = first_ipv4(next_line)
                if candidate:
                    current_gateway = candidate
                    break

    flush_current()
    return candidates


def first_ipv4(text: str) -> str | None:
    """Return the first valid IPv4 address from text."""
    for match in re.finditer(IPV4_PATTERN, text):
        candidate = match.group(0)
        if is_ipv4_address(candidate):
            return candidate
    return None


def get_windows_interface_ipv4s() -> list[tuple[str, str]]:
    """Return Windows interface names and IPv4 addresses from psutil."""
    interfaces: list[tuple[str, str]] = []
    for name, addresses in psutil.net_if_addrs().items():
        for address in addresses:
            if address.family == socket.AF_INET and is_ipv4_address(address.address):
                interfaces.append((name, address.address))
    return interfaces


def matching_physical_lan_ip(
    candidate: WindowsGatewayCandidate,
    physical_lan_ipv4s: list[tuple[str, str]],
    backend: WindowsBackend,
) -> str | None:
    """Return the matching physical LAN IPv4 when candidate gateway is same /24."""
    possible_ips: list[tuple[str | None, str]] = []
    if candidate.interface_ipv4:
        possible_ips.append((candidate.interface_name, candidate.interface_ipv4))
    possible_ips.extend(physical_lan_ipv4s)

    for name, ipv4 in possible_ips:
        if name and backend.classify_interface(name, ipv4, None) in {"loopback", "vpn", "virtual"}:
            continue
        if not is_usable_lan_gateway_address(ipv4):
            continue
        if same_ipv4_24(ipv4, candidate.gateway):
            return ipv4
    return None


def same_ipv4_24(first: str, second: str) -> bool:
    """Return True when two IPv4 addresses are in the same /24 network."""
    first_parts = first.split(".")
    second_parts = second.split(".")
    return len(first_parts) == 4 and len(second_parts) == 4 and first_parts[:3] == second_parts[:3]


def lan_ip_preference_rank(ipv4: str) -> int:
    """Rank common home LAN ranges before broader private ranges."""
    if ipv4.startswith("192.168."):
        return 0
    if ipv4.startswith("10."):
        return 1
    if ipv4.startswith("172."):
        return 2
    return 3
