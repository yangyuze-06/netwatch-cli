"""Local network interface inspection."""

from __future__ import annotations

import socket
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class InterfaceInfo:
    """Useful details for a local network interface."""

    name: str
    ipv4: str | None
    mac: str | None


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


def get_primary_ipv4() -> str | None:
    """Best-effort detection of the primary non-loopback IPv4 address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if not ip.startswith("127."):
                return ip
    except OSError:
        pass

    for interface in get_network_interfaces():
        if interface.ipv4 and not interface.ipv4.startswith("127."):
            return interface.ipv4

    return None
