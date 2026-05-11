"""User configuration for non-sensitive netwatch preferences."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from netwatch.speedtest_backends.models import SpeedtestResult

CONFIG_ENV_VAR = "NETWATCH_CONFIG_PATH"
DEFAULT_CONFIG_DIR = ".netwatch"
DEFAULT_CONFIG_FILE = "config.json"


def get_config_path() -> Path:
    """Return the config path, allowing tests to override it."""
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.home() / DEFAULT_CONFIG_DIR / DEFAULT_CONFIG_FILE


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load config, returning an empty dict when it does not exist or is invalid."""
    config_path = path or get_config_path()
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(config: dict[str, Any], path: Path | None = None) -> None:
    """Save config as JSON."""
    config_path = path or get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_preferred_speedtest(path: Path | None = None) -> dict[str, Any] | None:
    """Return preferred speedtest config when present."""
    preferred = load_config(path).get("preferred_speedtest")
    return preferred if isinstance(preferred, dict) else None


def save_preferred_speedtest(
    result: SpeedtestResult,
    interface: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Save a successful server id as preferred speedtest config."""
    if not result.server_id:
        raise ValueError("无法保存：测速结果没有 server id。")

    config = load_config(path)
    preferred = {
        "backend": result.backend,
        "server_id": result.server_id,
        "server_name": result.server_name or result.server_sponsor or "",
        "location": result.server_location or "",
        "interface": interface or extract_interface_name(result) or "",
    }
    config["preferred_speedtest"] = preferred
    save_config(config, path)
    return preferred


def clear_preferred_speedtest(path: Path | None = None) -> bool:
    """Remove preferred speedtest config while preserving other settings."""
    config = load_config(path)
    existed = "preferred_speedtest" in config
    config.pop("preferred_speedtest", None)
    save_config(config, path)
    return existed


def get_preferred_librespeed(path: Path | None = None) -> dict[str, Any] | None:
    """Return preferred LibreSpeed custom server list config when present."""
    preferred = load_config(path).get("preferred_librespeed")
    return preferred if isinstance(preferred, dict) else None


def set_preferred_librespeed(
    *,
    mode: str,
    server_json_url: str | None = None,
    local_json_path: str | None = None,
    duration: int | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Save non-sensitive LibreSpeed custom server list preferences."""
    if mode not in {"server-json", "local-json"}:
        raise ValueError("LibreSpeed 配置 mode 必须是 server-json 或 local-json。")
    if bool(server_json_url) == bool(local_json_path):
        raise ValueError("server_json_url 和 local_json_path 只能二选一。")

    config = load_config(path)
    preferred = {
        "mode": mode,
        "server_json_url": server_json_url or None,
        "local_json_path": local_json_path or None,
        "duration": duration,
    }
    config["preferred_librespeed"] = preferred
    save_config(config, path)
    return preferred


def clear_preferred_librespeed(path: Path | None = None) -> bool:
    """Remove preferred LibreSpeed config while preserving other settings."""
    config = load_config(path)
    existed = "preferred_librespeed" in config
    config.pop("preferred_librespeed", None)
    save_config(config, path)
    return existed


def extract_interface_name(result: SpeedtestResult) -> str | None:
    """Extract interface name from backend raw data when available."""
    raw = result.raw
    if not isinstance(raw, dict):
        return None
    interface = raw.get("interface")
    if not isinstance(interface, dict):
        return None
    name = interface.get("name")
    return str(name) if name else None
