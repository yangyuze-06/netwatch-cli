"""Router integration helpers for netwatch-cli."""

from __future__ import annotations

import ipaddress
import platform
import re
import subprocess
import webbrowser
from dataclasses import dataclass
from typing import Any

import requests

from netwatch.scanner import HostScanResult


@dataclass(frozen=True)
class RouterDevice:
    """A device reported by a router API."""

    name: str | None
    ip: str | None
    mac: str | None
    online: bool
    connect_type: str | None
    source: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class NetworkDevice:
    """Unified network device shown by the CLI."""

    name: str
    ip: str
    mac: str
    hostname: str
    router_name: str
    status: str
    source: str
    connect_type: str


class RouterApiError(RuntimeError):
    """Raised when a router API call fails in a user-facing way."""


def get_default_gateway() -> str | None:
    """Return the default gateway IP address when it can be detected."""
    system = platform.system().lower()
    if system == "darwin":
        return parse_macos_default_gateway(run_command(["route", "-n", "get", "default"]))
    if system == "linux":
        gateway = parse_linux_ip_route_gateway(run_command(["ip", "route", "show", "default"]))
        if gateway:
            return gateway
        return parse_linux_route_n_gateway(run_command(["route", "-n"]))
    return None


def run_command(command: list[str], timeout_seconds: int = 3) -> str:
    """Run a command and return stdout, or an empty string on failure."""
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


def parse_macos_default_gateway(output: str) -> str | None:
    """Parse `route -n get default` output."""
    match = re.search(r"^\s*gateway:\s*(?P<gateway>\d{1,3}(?:\.\d{1,3}){3})\s*$", output, re.MULTILINE)
    return match.group("gateway") if match else None


def parse_linux_ip_route_gateway(output: str) -> str | None:
    """Parse `ip route show default` output."""
    match = re.search(r"\bdefault\s+via\s+(?P<gateway>\d{1,3}(?:\.\d{1,3}){3})\b", output)
    return match.group("gateway") if match else None


def parse_linux_route_n_gateway(output: str) -> str | None:
    """Parse `route -n` output."""
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "0.0.0.0":
            return fields[1]
    return None


def open_router_admin(router_ip: str | None = None) -> str | None:
    """Open the router admin page and return the URL that was opened."""
    gateway = router_ip or get_default_gateway()
    if not gateway:
        return None
    url = f"http://{gateway}/"
    webbrowser.open(url)
    return url


def extract_xiaomi_stok(input_text: str) -> str | None:
    """Extract a Xiaomi LuCI stok token from pasted text."""
    match = re.search(r";stok=([^/?#]+)", input_text)
    return match.group(1) if match else None


def mask_stok(stok: str) -> str:
    """Mask a stok token for display."""
    if len(stok) <= 8:
        return f"{stok[:2]}...{stok[-2:]}" if len(stok) > 4 else "****"
    return f"{stok[:4]}...{stok[-4:]}"


def fetch_xiaomi_device_list(router_ip: str, stok: str) -> list[RouterDevice]:
    """Fetch and normalize Xiaomi router device list data."""
    first_error: RouterApiError | None = None
    try:
        payload = _fetch_xiaomi_json(router_ip, stok, mlo=True)
    except RouterApiError as exc:
        first_error = exc
        payload = {"code": -1, "msg": str(exc)}

    if payload.get("code") != 0:
        try:
            payload = _fetch_xiaomi_json(router_ip, stok, mlo=False)
        except RouterApiError:
            if first_error is not None:
                raise first_error
            raise

    code = payload.get("code")
    if code == 401:
        raise RouterApiError("token 无效或已过期，请重新登录路由器后台并复制登录后的 URL。")
    if code not in (None, 0):
        raise RouterApiError(str(payload.get("msg") or f"路由器 API 返回 code={code}"))

    raw_devices = extract_device_records(payload)
    devices = [device for raw in raw_devices if (device := normalize_xiaomi_device(raw)) is not None]
    return deduplicate_router_devices(devices)


def _fetch_xiaomi_json(router_ip: str, stok: str, *, mlo: bool) -> dict[str, Any]:
    suffix = "/api/misystem/devicelist?mlo=1" if mlo else "/api/misystem/devicelist"
    url = f"http://{router_ip}/cgi-bin/luci/;stok={stok}{suffix}"
    try:
        response = requests.get(url, timeout=5)
        return response.json()
    except requests.exceptions.RequestException as exc:
        raise RouterApiError(f"无法连接路由器 API：{exc}") from exc
    except ValueError as exc:
        raise RouterApiError("路由器 API 返回的不是有效 JSON。") from exc


def extract_device_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract possible device dictionaries from variant Xiaomi payloads."""
    records: list[dict[str, Any]] = []
    collect_device_records(payload, records)
    return records


def collect_device_records(value: Any, records: list[dict[str, Any]]) -> None:
    """Recursively collect dictionaries that look like device records."""
    if isinstance(value, list):
        for item in value:
            collect_device_records(item, records)
        return
    if not isinstance(value, dict):
        return

    has_device_key = any(key in value for key in ("ip", "mac", "name", "devname", "hostname", "nickname"))
    if has_device_key:
        records.append(value)

    for child in value.values():
        if isinstance(child, (list, dict)):
            collect_device_records(child, records)


def normalize_xiaomi_device(raw: dict[str, Any]) -> RouterDevice | None:
    """Normalize Xiaomi device records across firmware variants."""
    ip_address = normalize_ip(raw.get("ip"))
    mac = normalize_mac(raw.get("mac"))
    name = first_text(raw, ("name", "devname", "hostname", "nickname"))
    connect_type = first_text(raw, ("connect_type", "type", "ifname", "ssid"))
    online = normalize_online(raw.get("online", raw.get("is_online", raw.get("status", True))))

    if not ip_address and not mac:
        return None

    return RouterDevice(
        name=name,
        ip=ip_address,
        mac=mac,
        online=online,
        connect_type=connect_type,
        source="xiaomi-router-api",
        raw=raw,
    )


def deduplicate_router_devices(devices: list[RouterDevice]) -> list[RouterDevice]:
    """Deduplicate router devices by MAC first, then IP."""
    merged: list[RouterDevice] = []

    for device in devices:
        match_index = find_matching_router_device(merged, device)
        if match_index is None:
            merged.append(device)
            continue

        merged[match_index] = merge_router_device_pair(merged[match_index], device)

    return sorted(merged, key=lambda device: ip_sort_key(device.ip or "-"))


def find_matching_router_device(devices: list[RouterDevice], candidate: RouterDevice) -> int | None:
    """Find an existing router device by MAC first, then IP."""
    candidate_mac = candidate.mac or ""
    if candidate_mac:
        for index, device in enumerate(devices):
            if device.mac and device.mac == candidate_mac:
                return index

    candidate_ip = candidate.ip
    if candidate_ip:
        for index, device in enumerate(devices):
            if device.ip == candidate_ip:
                return index
    return None


def merge_router_device_pair(first: RouterDevice, second: RouterDevice) -> RouterDevice:
    """Merge two router records for the same device."""
    return RouterDevice(
        name=preferred_text(first.name, second.name),
        ip=preferred_text(first.ip, second.ip),
        mac=preferred_text(first.mac, second.mac),
        online=first.online or second.online,
        connect_type=merge_connect_type(first.connect_type, second.connect_type),
        source="xiaomi-router-api",
        raw={"merged": [first.raw, second.raw]},
    )


def preferred_text(*values: str | None) -> str | None:
    """Return the first meaningful non-placeholder text value."""
    for value in values:
        if value and value.strip() and value.strip() != "-":
            return value
    return None


def merge_connect_type(*values: str | None) -> str | None:
    """Merge non-empty connection type fields."""
    seen: list[str] = []
    for value in values:
        if value and value.strip() and value.strip() != "-" and value not in seen:
            seen.append(value)
    return ", ".join(seen) if seen else None


def normalize_ip(value: Any) -> str | None:
    """Normalize Xiaomi IP fields that may be strings or arrays."""
    candidates: list[Any]
    if isinstance(value, list):
        candidates = [item.get("ip") if isinstance(item, dict) else item for item in value]
    else:
        candidates = [value]

    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        try:
            ipaddress.ip_address(text)
        except ValueError:
            continue
        return text
    return None


def normalize_mac(value: Any) -> str | None:
    """Normalize a MAC address to lowercase when present."""
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def first_text(raw: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty text value for a list of keys."""
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def normalize_online(value: Any) -> bool:
    """Normalize online flags from router payloads."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "offline", "down"}
    return True


def scan_results_to_network_devices(scan_results: list[HostScanResult]) -> list[NetworkDevice]:
    """Convert scanner results to unified network devices."""
    devices: list[NetworkDevice] = []
    for result in scan_results:
        hostname = result.hostname or "-"
        mac = result.mac or "-"
        source = "reverse-dns" if result.hostname else "arp" if result.mac else "scanner"
        devices.append(
            NetworkDevice(
                name=hostname if hostname != "-" else "-",
                ip=result.ip,
                mac=mac,
                hostname=hostname,
                router_name="-",
                status="online",
                source=source,
                connect_type="-",
            )
        )
    return devices


def router_devices_to_network_devices(router_devices: list[RouterDevice]) -> list[NetworkDevice]:
    """Convert router API devices to unified network devices."""
    devices: list[NetworkDevice] = []
    for device in router_devices:
        router_name = device.name or "-"
        devices.append(
            NetworkDevice(
                name=router_name,
                ip=device.ip or "-",
                mac=device.mac or "-",
                hostname="-",
                router_name=router_name,
                status="online" if device.online else "router-only",
                source="router-api",
                connect_type=device.connect_type or "-",
            )
        )
    return devices


def merge_devices(
    scan_devices: list[NetworkDevice],
    router_devices: list[RouterDevice],
) -> list[NetworkDevice]:
    """Merge scanner and router API devices by MAC first, then IP."""
    merged: list[NetworkDevice] = list(scan_devices)

    for router_device in router_devices:
        match_index = find_matching_device(merged, router_device)
        router_name = router_device.name or "-"
        router_mac = router_device.mac or "-"
        router_ip = router_device.ip or "-"
        router_connect_type = router_device.connect_type or "-"

        if match_index is None:
            merged.append(
                NetworkDevice(
                    name=router_name,
                    ip=router_ip,
                    mac=router_mac,
                    hostname="-",
                    router_name=router_name,
                    status="router-only",
                    source="router-api",
                    connect_type=router_connect_type,
                )
            )
            continue

        current = merged[match_index]
        hostname = current.hostname
        mac = current.mac if current.mac != "-" else router_mac
        name = first_preferred_name(router_name, hostname, current.name)
        merged[match_index] = NetworkDevice(
            name=name,
            ip=current.ip if current.ip != "-" else router_ip,
            mac=mac,
            hostname=hostname,
            router_name=router_name,
            status="online" if current.status == "online" or router_device.online else "router-only",
            source="mixed",
            connect_type=router_connect_type if router_connect_type != "-" else current.connect_type,
        )

    return sorted(merged, key=lambda device: ip_sort_key(device.ip))


def find_matching_device(devices: list[NetworkDevice], router_device: RouterDevice) -> int | None:
    """Find a matching network device by MAC first, then IP."""
    router_mac = (router_device.mac or "").lower()
    if router_mac:
        for index, device in enumerate(devices):
            if device.mac != "-" and device.mac.lower() == router_mac:
                return index

    router_ip = router_device.ip
    if router_ip:
        for index, device in enumerate(devices):
            if device.ip == router_ip:
                return index
    return None


def first_preferred_name(router_name: str, hostname: str, current_name: str) -> str:
    """Choose router name over hostname over existing name."""
    for value in (router_name, hostname, current_name):
        if value and value != "-":
            return value
    return "-"


def ip_sort_key(ip_address: str) -> tuple[int, int]:
    """Sort valid IPs before invalid placeholder values."""
    try:
        return (0, int(ipaddress.ip_address(ip_address)))
    except ValueError:
        return (1, 0)
