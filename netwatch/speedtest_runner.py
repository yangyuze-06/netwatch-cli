"""Speedtest backend scheduler."""

from __future__ import annotations

from netwatch.speedtest_backends import librespeed_cli, ookla_cli, python_speedtest
from netwatch.speedtest_backends.models import SpeedtestResult

BACKEND_PRIORITY = ("official-ookla-cli", "librespeed-cli", "python-speedtest-cli")


def get_available_backends() -> list[str]:
    """Return available speedtest backends in priority order."""
    available: list[str] = []
    if ookla_cli.is_available():
        available.append("official-ookla-cli")
    if librespeed_cli.is_available():
        available.append("librespeed-cli")
    if python_speedtest.is_available():
        available.append("python-speedtest-cli")
    return available


def run_best_speedtest() -> SpeedtestResult:
    """Run the best available speedtest backend."""
    for backend in BACKEND_PRIORITY:
        if backend in get_available_backends():
            return run_speedtest_with_backend(backend)

    return SpeedtestResult(
        backend="none",
        error=(
            "没有可用测速后端。\n"
            "推荐安装官方 Ookla CLI：\n"
            "brew tap teamookla/speedtest\n"
            "brew install speedtest"
        ),
    )


def run_speedtest_with_backend(backend: str, server_id: str | None = None) -> SpeedtestResult:
    """Run a selected backend."""
    if backend == "official-ookla-cli":
        return ookla_cli.run_speedtest(server_id=server_id)
    if backend == "librespeed-cli":
        if server_id:
            return SpeedtestResult(backend=backend, error="LibreSpeed CLI backend does not support Ookla server id.")
        return librespeed_cli.run_speedtest()
    if backend == "python-speedtest-cli":
        return python_speedtest.run_speedtest(server_id=server_id)
    return SpeedtestResult(backend=backend, error=f"未知测速后端：{backend}")


def list_speedtest_servers() -> list[dict]:
    """List servers from the best available server-list-capable backend."""
    if ookla_cli.is_available():
        return ookla_cli.list_servers()
    if python_speedtest.is_available():
        return python_speedtest.list_servers()
    return [{"error": "当前后端无法获取服务器列表。建议使用“带宽测速”自动模式，或安装官方 Ookla CLI。"}]


def show_backend_info() -> dict:
    """Return speedtest backend information."""
    return {
        "priority": list(BACKEND_PRIORITY),
        "available": get_available_backends(),
        "install_ookla_macos": ["brew tap teamookla/speedtest", "brew install speedtest"],
        "notes": {
            "official-ookla-cli": "推荐后端，最接近官方客户端和网页测速。",
            "librespeed-cli": "开源备选后端，测速网络和 Ookla 不同。",
            "python-speedtest-cli": "最后 fallback，结果可能低于网页测速或官方 Ookla CLI。",
        },
    }


def get_selection_details() -> str | dict | None:
    """Return Ookla server selection details when available."""
    return ookla_cli.get_selection_details()
