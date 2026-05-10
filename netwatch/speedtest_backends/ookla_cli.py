"""Official Ookla CLI backend."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from netwatch.speedtest_backends.models import SpeedtestResult

BACKEND_NAME = "official-ookla-cli"
INSTALL_HINT = (
    "Official Ookla CLI is not installed.\n"
    "macOS 推荐安装：\n"
    "brew tap teamookla/speedtest\n"
    "brew install speedtest"
)
OOKLA_CANDIDATE_PATHS = (
    "/opt/homebrew/bin/speedtest",
    "/usr/local/bin/speedtest",
    "/usr/bin/speedtest",
)


@dataclass(frozen=True)
class OoklaBinaryInfo:
    """Detected official Ookla CLI binary info."""

    path: str
    version_output: str


def is_available() -> bool:
    """Return True if official speedtest command is available."""
    return find_ookla_speedtest_binary() is not None


def find_ookla_speedtest_binary() -> OoklaBinaryInfo | None:
    """Find the official Ookla speedtest binary, avoiding Python speedtest-cli shadows."""
    seen: set[str] = set()
    candidates = list(OOKLA_CANDIDATE_PATHS)
    path_candidate = shutil.which("speedtest")
    if path_candidate:
        candidates.append(path_candidate)

    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if not os.path.exists(candidate):
            continue
        version_output = get_version_output(candidate)
        if is_official_ookla_version(version_output):
            return OoklaBinaryInfo(path=candidate, version_output=version_output)
    return None


def get_version_output(binary_path: str) -> str:
    """Return speedtest --version output for a candidate binary."""
    try:
        completed = subprocess.run([binary_path, "--version"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return f"{completed.stdout}\n{completed.stderr}".strip()


def is_official_ookla_version(version_output: str) -> bool:
    """Return True for official Ookla CLI version output."""
    normalized = version_output.lower()
    if "speedtest-cli" in normalized or "sivel" in normalized:
        return False
    return "ookla" in normalized or "speedtest by ookla" in normalized


def run_speedtest(
    server_id: str | None = None,
    selection_details: bool = False,
    interface: str | None = None,
) -> SpeedtestResult:
    """Run official Ookla CLI speedtest and parse JSON output."""
    binary = find_ookla_speedtest_binary()
    if binary is None:
        return SpeedtestResult(backend=BACKEND_NAME, error=INSTALL_HINT)

    command = [binary.path]
    if server_id:
        command.extend(["--server-id", server_id])
    if interface:
        command.extend(["--interface", interface])
    command.extend(["--format=json", "--accept-license", "--accept-gdpr"])
    if selection_details:
        command.append("--selection-details")

    completed = run_command(command)
    if isinstance(completed, SpeedtestResult):
        return completed

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        friendly_error = friendly_ookla_error(completed.stdout)
        if friendly_error:
            return SpeedtestResult(backend=BACKEND_NAME, raw=completed.stdout, error=friendly_error)
        return SpeedtestResult(backend=BACKEND_NAME, raw=completed.stdout, error=f"无法解析 Ookla CLI JSON：{exc}")

    return parse_ookla_result(payload)


def list_servers() -> list[dict]:
    """List available Ookla servers when supported by the installed CLI."""
    binary = find_ookla_speedtest_binary()
    if binary is None:
        return [{"error": INSTALL_HINT}]

    completed = run_command([binary.path, "--servers", "--format=json", "--accept-license", "--accept-gdpr"])
    if isinstance(completed, SpeedtestResult):
        return [{"error": completed.error or "无法获取服务器列表。"}]

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return parse_text_servers(completed.stdout)

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        servers = payload.get("servers")
        if isinstance(servers, list):
            return servers
    return [{"error": "当前后端无法获取服务器列表。"}]


def get_selection_details() -> str | dict | None:
    """Return Ookla server selection details when supported."""
    binary = find_ookla_speedtest_binary()
    if binary is None:
        return INSTALL_HINT

    completed = run_command([binary.path, "--selection-details", "--format=json", "--accept-license", "--accept-gdpr"])
    if isinstance(completed, SpeedtestResult):
        return completed.error
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return completed.stdout or None


def run_command(command: list[str]) -> subprocess.CompletedProcess[str] | SpeedtestResult:
    """Run speedtest command and convert failures into SpeedtestResult."""
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=True)
    except FileNotFoundError:
        return SpeedtestResult(backend=BACKEND_NAME, error=INSTALL_HINT)
    except subprocess.TimeoutExpired:
        return SpeedtestResult(backend=BACKEND_NAME, error="Ookla CLI 测速超时。")
    except subprocess.CalledProcessError as exc:
        message = exc.stderr or exc.stdout or str(exc)
        return SpeedtestResult(backend=BACKEND_NAME, raw=message, error=friendly_ookla_error(message) or message.strip())
    except Exception as exc:
        return SpeedtestResult(backend=BACKEND_NAME, error=str(exc))
    return completed


def parse_ookla_result(payload: dict[str, Any]) -> SpeedtestResult:
    """Parse official Ookla CLI JSON result."""
    payload_error = payload.get("error")
    if payload_error:
        return SpeedtestResult(
            backend=BACKEND_NAME,
            raw=payload,
            error=friendly_ookla_error(str(payload_error)) or str(payload_error),
        )

    download_bandwidth = optional_float(payload.get("download", {}).get("bandwidth"))
    upload_bandwidth = optional_float(payload.get("upload", {}).get("bandwidth"))
    server = payload.get("server") or {}
    ping = payload.get("ping") or {}

    return SpeedtestResult(
        backend=BACKEND_NAME,
        ping_ms=optional_float(ping.get("latency")),
        jitter_ms=optional_float(ping.get("jitter")),
        packet_loss=optional_float(payload.get("packetLoss")),
        download_mbps=download_bandwidth * 8 / 1_000_000 if download_bandwidth is not None else None,
        download_MBps=download_bandwidth / 1_000_000 if download_bandwidth is not None else None,
        upload_mbps=upload_bandwidth * 8 / 1_000_000 if upload_bandwidth is not None else None,
        upload_MBps=upload_bandwidth / 1_000_000 if upload_bandwidth is not None else None,
        server_id=str(server.get("id")) if server.get("id") is not None else None,
        server_name=server.get("name"),
        server_location=server.get("location"),
        server_sponsor=server.get("sponsor"),
        raw=payload,
    )


def parse_text_servers(output: str) -> list[dict]:
    """Best-effort parser for text server listings."""
    servers: list[dict] = []
    for line in output.splitlines():
        if ")" not in line:
            continue
        server_id, rest = line.split(")", 1)
        if server_id.strip().isdigit():
            servers.append({"id": server_id.strip(), "name": rest.strip()})
    return servers or [{"error": "当前后端无法获取服务器列表。"}]


def optional_float(value: Any) -> float | None:
    """Convert values to float when possible."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def friendly_ookla_error(message: str) -> str | None:
    """Return a user-facing Ookla CLI error without raw JSON noise."""
    if "cannot read from socket" in message.lower():
        return "Official Ookla CLI is installed but this test failed.\nError: Cannot read from socket."
    return None
