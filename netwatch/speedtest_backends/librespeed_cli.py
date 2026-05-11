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


def run_speedtest(
    server_json_url: str | None = None,
    local_json_path: str | None = None,
    duration: int | None = None,
    source_ip: str | None = None,
) -> SpeedtestResult:
    """Run LibreSpeed CLI using best-effort JSON support."""
    if not is_available():
        return SpeedtestResult(backend=BACKEND_NAME, error="LibreSpeed CLI is not installed.")
    if server_json_url and local_json_path:
        return SpeedtestResult(backend=BACKEND_NAME, error="server_json_url 和 local_json_path 只能二选一。")

    commands = build_commands(
        server_json_url=server_json_url,
        local_json_path=local_json_path,
        duration=duration,
        source_ip=source_ip,
    )
    last_error: SpeedtestResult | None = None

    for command in commands:
        result = run_command(command)
        if isinstance(result, SpeedtestResult):
            last_error = result
            continue
        raw_output = (result.stdout or "").strip() or (result.stderr or "").strip()
        try:
            return parse_librespeed_result(json.loads(raw_output))
        except json.JSONDecodeError as exc:
            last_error = SpeedtestResult(
                backend=BACKEND_NAME,
                raw=raw_output,
                error=f"无法解析 LibreSpeed CLI JSON：{exc}",
            )
        except (TypeError, ValueError) as exc:
            last_error = SpeedtestResult(
                backend=BACKEND_NAME,
                raw=raw_output,
                error=str(exc),
            )
            continue

    if last_error is not None:
        return last_error
    return SpeedtestResult(backend=BACKEND_NAME, error="当前 librespeed-cli 版本无法输出可解析 JSON。")


def build_commands(
    *,
    server_json_url: str | None = None,
    local_json_path: str | None = None,
    duration: int | None = None,
    source_ip: str | None = None,
) -> list[list[str]]:
    """Build LibreSpeed CLI command variants."""
    base = ["librespeed-cli"]
    if server_json_url:
        base.extend(["--server-json", server_json_url])
    if local_json_path:
        base.extend(["--local-json", local_json_path])
    if duration is not None:
        base.extend(["--duration", str(duration)])
    if source_ip:
        base.extend(["--source", source_ip])
    return [base + ["--json"], base + ["-f", "json"]]


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


def normalize_librespeed_payload(payload: Any) -> dict[str, Any]:
    """Normalize LibreSpeed JSON payload variants to a single result dict."""
    if isinstance(payload, list):
        if not payload:
            raise ValueError("Empty LibreSpeed result list")
        payload = payload[0]
    if not isinstance(payload, dict):
        raise TypeError(f"Unexpected LibreSpeed payload type: {type(payload)}")
    return payload


def parse_librespeed_result(payload: Any) -> SpeedtestResult:
    """Parse common LibreSpeed JSON fields."""
    payload = normalize_librespeed_payload(payload)
    download_mbps = optional_float(payload.get("download") or payload.get("download_mbps"))
    upload_mbps = optional_float(payload.get("upload") or payload.get("upload_mbps"))
    server = payload.get("server")
    if isinstance(server, dict):
        server_name = str(server.get("name") or server.get("url") or "")
    else:
        server_name = str(server) if server is not None else None
    return SpeedtestResult(
        backend=BACKEND_NAME,
        ping_ms=optional_float(payload.get("ping")),
        jitter_ms=optional_float(payload.get("jitter")),
        download_mbps=download_mbps,
        download_MBps=download_mbps / 8 if download_mbps is not None else None,
        upload_mbps=upload_mbps,
        upload_MBps=upload_mbps / 8 if upload_mbps is not None else None,
        server_name=server_name or None,
        raw=payload,
    )


def optional_float(value: Any) -> float | None:
    """Convert values to float when possible."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
