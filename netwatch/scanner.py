"""Simple local network scanner."""

from __future__ import annotations

import ipaddress
import platform
import re
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
    mac: str | None = None
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


def get_arp_table() -> dict[str, dict[str, str | None]]:
    """Read the local ARP table and return IP to MAC/hostname metadata."""
    commands = [["arp", "-a"]]
    if platform.system().lower() != "windows":
        # macOS can spend several seconds doing reverse lookups for `arp -a`.
        # Numeric mode returns MAC data quickly; plain `arp -a` is only a
        # best-effort hostname enrichment pass.
        commands = [["arp", "-an"], ["arp", "-a"]]

    entries: dict[str, dict[str, str | None]] = {}

    for command in commands:
        output = run_arp_command(command)
        if output:
            merge_arp_entries(entries, parse_arp_output(output))

    return entries


def run_arp_command(command: list[str], timeout_seconds: int = 3) -> str:
    """Run an arp command and return stdout, or an empty string on failure."""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""

    if completed.returncode != 0:
        return ""

    return completed.stdout


def merge_arp_entries(
    target: dict[str, dict[str, str | None]],
    source: dict[str, dict[str, str | None]],
) -> None:
    """Merge ARP metadata without replacing useful values with empty ones."""
    for ip_address, source_entry in source.items():
        target_entry = target.setdefault(ip_address, {"hostname": None, "mac": None})
        if source_entry.get("mac"):
            target_entry["mac"] = source_entry["mac"]
        if source_entry.get("hostname"):
            target_entry["hostname"] = source_entry["hostname"]


def parse_arp_output(output: str) -> dict[str, dict[str, str | None]]:
    """Parse common arp -a output, especially macOS IP/MAC/hostname rows."""
    entries: dict[str, dict[str, str | None]] = {}
    pattern = re.compile(
        r"^(?P<host>\S+)\s+\((?P<ip>\d{1,3}(?:\.\d{1,3}){3})\)\s+at\s+"
        r"(?P<mac>(?:[0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2}|[<(]incomplete[>)])"
    )

    for line in output.splitlines():
        match = pattern.search(line.strip())
        if not match:
            continue

        hostname = match.group("host")
        mac = normalize_mac_address(match.group("mac"))
        if mac is None:
            continue

        entries[match.group("ip")] = {
            "hostname": None if hostname == "?" else hostname,
            "mac": mac,
        }

    return entries


def normalize_mac_address(mac_address: str) -> str | None:
    """Normalize a MAC address to six two-digit lowercase hex segments."""
    if mac_address.lower() in {"<incomplete>", "(incomplete)"}:
        return None

    parts = mac_address.split(":")
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


def scan_network(
    network: ipaddress.IPv4Network | None = None,
    *,
    workers: int = 64,
) -> list[HostScanResult]:
    """Ping all usable hosts in a network and return online hosts."""
    target_network = network or infer_local_network()
    if target_network is None:
        return []

    online_hosts: list[str] = []
    hosts = [str(ip) for ip in target_network.hosts()]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(ping_host, host): host for host in hosts}
        for future in as_completed(futures):
            host = futures[future]
            is_online = future.result()
            if is_online:
                online_hosts.append(host)

    arp_table = get_arp_table()
    results = []
    for host in online_hosts:
        arp_entry = arp_table.get(host, {})
        hostname = resolve_hostname(host) or arp_entry.get("hostname")
        mac = arp_entry.get("mac")
        results.append(HostScanResult(ip=host, is_online=True, mac=mac, hostname=hostname))

    return sorted(results, key=lambda result: ipaddress.ip_address(result.ip))
