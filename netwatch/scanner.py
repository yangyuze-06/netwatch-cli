"""Simple local network scanner."""

from __future__ import annotations

import ipaddress
import platform
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from netwatch.network_info import get_lan_scan_candidates


@dataclass(frozen=True)
class HostScanResult:
    """A single host scan result."""

    ip: str
    is_online: bool
    hostname: str | None = None


def infer_local_network(ip_address: str | None = None) -> ipaddress.IPv4Network | None:
    """Infer a /24 network from the primary local IPv4 address."""
    if ip_address:
        return ipaddress.ip_network(f"{ip_address}/24", strict=False)

    candidates = get_lan_scan_candidates()
    if not candidates:
        return None
    return candidates[0].network


def ping_host(ip_address: str, timeout_seconds: int = 1) -> bool:
    """Return True when a host responds to one ICMP echo request."""
    system = platform.system().lower()
    if system == "windows":
        command = ["ping", "-n", "1", "-w", str(timeout_seconds * 1000), ip_address]
    else:
        command = ["ping", "-c", "1", "-W", str(timeout_seconds), ip_address]

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout_seconds + 1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return completed.returncode == 0


def resolve_hostname(ip_address: str) -> str | None:
    """Resolve a host name if reverse DNS is available."""
    try:
        return socket.gethostbyaddr(ip_address)[0]
    except (OSError, socket.herror):
        return None


def scan_network(
    network: ipaddress.IPv4Network | None = None,
    *,
    workers: int = 64,
    resolve_names: bool = False,
) -> list[HostScanResult]:
    """Ping all usable hosts in a network and return online hosts."""
    target_network = network or infer_local_network()
    if target_network is None:
        return []

    results: list[HostScanResult] = []
    hosts = [str(ip) for ip in target_network.hosts()]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(ping_host, host): host for host in hosts}
        for future in as_completed(futures):
            host = futures[future]
            is_online = future.result()
            if is_online:
                hostname = resolve_hostname(host) if resolve_names else None
                results.append(HostScanResult(ip=host, is_online=True, hostname=hostname))

    return sorted(results, key=lambda result: ipaddress.ip_address(result.ip))
