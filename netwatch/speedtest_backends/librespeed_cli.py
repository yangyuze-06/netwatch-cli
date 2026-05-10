"""LibreSpeed CLI backend."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from netwatch.speedtest_backends.models import SpeedtestResult

BACKEND_NAME = "librespeed-cli"


def is_available() -> bool:
    """Return True if librespeed-cli is available."""
    return shutil.which("librespeed-cli") is not None


def run_speedtest() -> SpeedtestResult:
    """Run LibreSpeed CLI using best-effort JSON support."""
    if not is_available():
        return SpeedtestResult(backend=BACKEND_NAME, error="LibreSpeed CLI is not installed.")

    for command in (["librespeed-cli", "--json"], ["librespeed-cli", "-f", "json"]):
        result = run_command(command)
        if isinstance(result, SpeedtestResult):
            continue
        try:
            return parse_librespeed_result(json.loads(result.stdout))
        except json.JSONDecodeError:
            continue

    return SpeedtestResult(backend=BACKEND_NAME, error="当前 librespeed-cli 版本无法输出可解析 JSON。")


def run_command(command: list[str]) -> subprocess.CompletedProcess[str] | SpeedtestResult:
    """Run librespeed-cli command."""
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=120, check=True)
    except FileNotFoundError:
        return SpeedtestResult(backend=BACKEND_NAME, error="LibreSpeed CLI is not installed.")
    except subprocess.TimeoutExpired:
        return SpeedtestResult(backend=BACKEND_NAME, error="LibreSpeed CLI 测速超时。")
    except subprocess.CalledProcessError as exc:
        return SpeedtestResult(backend=BACKEND_NAME, raw=exc.stderr or exc.stdout, error=(exc.stderr or exc.stdout or str(exc)).strip())
    except Exception as exc:
        return SpeedtestResult(backend=BACKEND_NAME, error=str(exc))


def parse_librespeed_result(payload: dict[str, Any]) -> SpeedtestResult:
    """Parse common LibreSpeed JSON fields."""
    download_mbps = optional_float(payload.get("download") or payload.get("download_mbps"))
    upload_mbps = optional_float(payload.get("upload") or payload.get("upload_mbps"))
    return SpeedtestResult(
        backend=BACKEND_NAME,
        ping_ms=optional_float(payload.get("ping")),
        jitter_ms=optional_float(payload.get("jitter")),
        download_mbps=download_mbps,
        download_MBps=download_mbps / 8 if download_mbps is not None else None,
        upload_mbps=upload_mbps,
        upload_MBps=upload_mbps / 8 if upload_mbps is not None else None,
        server_name=str(payload.get("server")) if payload.get("server") is not None else None,
        raw=payload,
    )


def optional_float(value: Any) -> float | None:
    """Convert values to float when possible."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
