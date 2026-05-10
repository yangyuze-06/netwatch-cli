"""Current CLI network exit probe."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass

import requests


@dataclass
class ExitIPInfo:
    """Current public exit IP information."""

    ip: str | None
    city: str | None
    region: str | None
    country: str | None
    org: str | None
    raw: dict | None = None
    error: str | None = None


def probe_exit_ip() -> ExitIPInfo:
    """Probe current CLI process public exit IP."""
    if shutil.which("curl"):
        try:
            completed = subprocess.run(
                ["curl", "-s", "--max-time", "8", "https://ipinfo.io/json"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if completed.returncode == 0 and completed.stdout:
                return parse_ipinfo_json(completed.stdout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ExitIPInfo(None, None, None, None, None, error=str(exc))

    try:
        response = requests.get("https://ipinfo.io/json", timeout=8)
        return parse_ipinfo_payload(response.json())
    except requests.exceptions.RequestException as exc:
        return ExitIPInfo(None, None, None, None, None, error=str(exc))
    except ValueError as exc:
        return ExitIPInfo(None, None, None, None, None, error=f"无法解析出口 IP JSON：{exc}")


def parse_ipinfo_json(text: str) -> ExitIPInfo:
    """Parse ipinfo.io JSON text."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return ExitIPInfo(None, None, None, None, None, error=f"无法解析出口 IP JSON：{exc}")
    return parse_ipinfo_payload(payload)


def parse_ipinfo_payload(payload: dict) -> ExitIPInfo:
    """Parse ipinfo.io payload."""
    return ExitIPInfo(
        ip=payload.get("ip"),
        city=payload.get("city"),
        region=payload.get("region"),
        country=payload.get("country"),
        org=payload.get("org"),
        raw=payload,
    )
