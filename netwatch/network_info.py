"""Local network interface inspection."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class InterfaceInfo:
    """Useful details for a local network interface."""

    name: str
    ipv4: str | None
    mac: str | None


@dataclass(frozen=True)
class NetworkCandidate:
    """A local interface that is safe to use for LAN scanning."""

    name: str
    ipv4: str
    mac: str | None
    network: ipaddress.IPv4Network


EXCLUDED_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "127.0.0.0/8",
        "169.254.0.0/16",
        "198.18.0.0/15",
    )
)
PREFERRED_LAN_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "192.168.0.0/16",
        "10.0.0.0/8",
        "172.16.0.0/12",
    )
)
VIRTUAL_INTERFACE_KEYWORDS = (
    "docker",
    "bridge",
    "utun",
    "tun",
    "tap",
    "awdl",
    "llw",
    "lo",
    "vmnet",
    "veth",
    "tailscale",
)

PREFERRED_PHYSICAL_INTERFACE_NAMES = ("en0", "en1")


def get_network_interfaces() -> list[InterfaceInfo]:
    """Return local interfaces that have an IPv4 address or a MAC address."""
    interfaces: list[InterfaceInfo] = []

    for name, addresses in psutil.net_if_addrs().items():
        ipv4: str | None = None
        mac: str | None = None

        for address in addresses:
            if address.family == socket.AF_INET:
                ipv4 = address.address
            elif address.family == psutil.AF_LINK:
                mac = address.address

        if ipv4 or mac:
            interfaces.append(InterfaceInfo(name=name, ipv4=ipv4, mac=mac))

    return interfaces


def get_display_network_interfaces() -> list[InterfaceInfo]:
    """Return interfaces suitable for user-facing local network information."""
    interfaces: list[InterfaceInfo] = []

    for interface in get_network_interfaces():
        if is_excluded_interface_name(interface.name):
            continue
        if interface.ipv4 and is_excluded_ip(interface.ipv4):
            continue
        interfaces.append(interface)

    return interfaces


def is_excluded_interface_name(name: str) -> bool:
    """Return True for loopback, VPN, container, and virtual interfaces."""
    normalized = name.lower()
    return any(keyword in normalized for keyword in VIRTUAL_INTERFACE_KEYWORDS)


def is_excluded_ip(ip_address: str) -> bool:
    """Return True when an IP belongs to a non-scannable local range."""
    ip = ipaddress.ip_address(ip_address)
    return any(ip in network for network in EXCLUDED_NETWORKS)


def lan_preference_rank(ip_address: str) -> int:
    """Rank common real LAN ranges before less useful private ranges."""
    ip = ipaddress.ip_address(ip_address)
    for index, network in enumerate(PREFERRED_LAN_NETWORKS):
        if ip in network:
            return index
    return len(PREFERRED_LAN_NETWORKS)


def get_lan_scan_candidates() -> list[NetworkCandidate]:
    """Return filtered and ranked interface candidates for LAN scanning."""
    candidates: list[NetworkCandidate] = []

    for interface in get_network_interfaces():
        if not interface.ipv4:
            continue
        if is_excluded_interface_name(interface.name):
            continue
        if is_excluded_ip(interface.ipv4):
            continue

        network = ipaddress.ip_network(f"{interface.ipv4}/24", strict=False)
        candidates.append(
            NetworkCandidate(
                name=interface.name,
                ipv4=interface.ipv4,
                mac=interface.mac,
                network=network,
            )
        )

    return sorted(candidates, key=lambda item: (lan_preference_rank(item.ipv4), item.name))


def get_preferred_physical_interface() -> dict[str, str] | None:
    """Return the best real LAN/Wi-Fi interface for direct bandwidth tests."""
    candidates = get_lan_scan_candidates()
    if not candidates:
        return None

    def rank(candidate: NetworkCandidate) -> tuple[int, int, str]:
        name_rank = (
            PREFERRED_PHYSICAL_INTERFACE_NAMES.index(candidate.name)
            if candidate.name in PREFERRED_PHYSICAL_INTERFACE_NAMES
            else len(PREFERRED_PHYSICAL_INTERFACE_NAMES)
        )
        return (lan_preference_rank(candidate.ipv4), name_rank, candidate.name)

    preferred = sorted(candidates, key=rank)[0]
    return {
        "name": preferred.name,
        "ip": preferred.ipv4,
        "reason": "preferred private LAN interface",
    }


def get_primary_ipv4() -> str | None:
    """Best-effort detection of the primary non-loopback IPv4 address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if not is_excluded_ip(ip):
                return ip
    except OSError:
        pass

    candidates = get_lan_scan_candidates()
    if candidates:
        return candidates[0].ipv4

    return None
