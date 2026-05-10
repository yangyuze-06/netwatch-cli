"""Speedtest backend scheduler."""

from __future__ import annotations

from netwatch.network_info import get_preferred_physical_interface
from netwatch.speedtest_backends import librespeed_cli, ookla_cli, python_speedtest
from netwatch.speedtest_backends.models import SpeedtestResult

BACKEND_PRIORITY = ("official-ookla-cli", "librespeed-cli", "python-speedtest-cli")
LAST_SUCCESSFUL_SPEEDTEST_RESULT: SpeedtestResult | None = None


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


def run_best_speedtest(use_interface: bool = True) -> SpeedtestResult:
    """Run the best available speedtest backend."""
    interface = None
    if use_interface:
        preferred_interface = get_preferred_physical_interface()
        interface = preferred_interface["name"] if preferred_interface else None

    last_error: SpeedtestResult | None = None
    for backend in BACKEND_PRIORITY:
        if backend in get_available_backends():
            result = run_speedtest_with_backend(backend, interface=interface)
            if not result.error:
                return result
            last_error = result
            if backend == "official-ookla-cli" and interface:
                retry_result = run_speedtest_with_backend(backend, interface=None)
                if not retry_result.error:
                    return retry_result
                last_error = retry_result
            continue

    if last_error is not None:
        return last_error

    return SpeedtestResult(
        backend="none",
        error=(
            "没有可用测速后端。\n"
            "推荐安装官方 Ookla CLI：\n"
            "brew tap teamookla/speedtest\n"
            "brew install speedtest"
        ),
    )


def run_configured_speedtest(preferred: dict, fallback: bool = True) -> SpeedtestResult:
    """Run a preferred speedtest server config, then optionally fall back to auto mode."""
    backend = str(preferred.get("backend") or "official-ookla-cli")
    server_id = str(preferred.get("server_id") or "").strip() or None
    interface = str(preferred.get("interface") or "").strip() or None

    result = run_speedtest_with_backend(backend, server_id=server_id, interface=interface)
    if not result.error or not fallback:
        return result
    return run_best_speedtest(use_interface=bool(interface))


def run_speedtest_with_backend(
    backend: str,
    server_id: str | None = None,
    interface: str | None = None,
) -> SpeedtestResult:
    """Run a selected backend."""
    if backend == "official-ookla-cli":
        return remember_successful_result(ookla_cli.run_speedtest(server_id=server_id, interface=interface))
    if backend == "librespeed-cli":
        if server_id:
            return SpeedtestResult(backend=backend, error="LibreSpeed CLI backend does not support Ookla server id.")
        return remember_successful_result(librespeed_cli.run_speedtest())
    if backend == "python-speedtest-cli":
        return remember_successful_result(python_speedtest.run_speedtest(server_id=server_id))
    return SpeedtestResult(backend=backend, error=f"未知测速后端：{backend}")


def remember_successful_result(result: SpeedtestResult) -> SpeedtestResult:
    """Store the latest successful speedtest result in memory."""
    global LAST_SUCCESSFUL_SPEEDTEST_RESULT
    if not result.error:
        LAST_SUCCESSFUL_SPEEDTEST_RESULT = result
    return result


def get_last_successful_speedtest_result() -> SpeedtestResult | None:
    """Return the latest successful speedtest result for saving/debug display."""
    return LAST_SUCCESSFUL_SPEEDTEST_RESULT


def list_speedtest_servers() -> list[dict]:
    """List servers from the best available server-list-capable backend."""
    if ookla_cli.is_available():
        return ookla_cli.list_servers()
    if python_speedtest.is_available():
        return python_speedtest.list_servers()
    return [{"error": "当前后端无法获取服务器列表。建议使用“带宽测速”自动模式，或安装官方 Ookla CLI。"}]


def filter_servers_by_keyword(servers: list[dict], keyword: str, limit: int | None = None) -> list[dict]:
    """Filter Ookla servers by name, location, country, or host."""
    normalized_keyword = keyword.strip().lower()
    if not normalized_keyword:
        return []

    matches: list[dict] = []
    for server in servers:
        fields = (
            server.get("name"),
            server.get("location"),
            server.get("country"),
            server.get("host"),
        )
        haystack = " ".join(str(value) for value in fields if value).lower()
        if normalized_keyword in haystack:
            matches.append(server)
            if limit is not None and len(matches) >= limit:
                break
    return matches


def get_speedtest_quality_warnings(result: SpeedtestResult) -> list[str]:
    """Return human-readable quality warning reasons for suspicious speedtest results."""
    reasons: list[str] = []
    if result.ping_ms is not None and result.ping_ms > 80:
        reasons.append("ping > 80ms")
    if result.jitter_ms is not None and result.jitter_ms > 30:
        reasons.append("jitter > 30ms")
    if result.packet_loss is not None and result.packet_loss > 1:
        reasons.append("packet loss > 1%")
    if result.download_mbps is not None and result.download_mbps < 50:
        reasons.append("download < 50 Mbps")
    return reasons


def summarize_speedtest_raw(result: SpeedtestResult) -> dict[str, str]:
    """Return a compact summary of raw speedtest details."""
    summary = {
        "backend": result.backend,
        "server_id": result.server_id or "-",
        "server_name": result.server_name or result.server_sponsor or "-",
        "location": result.server_location or "-",
        "ping": f"{result.ping_ms:.2f} ms" if result.ping_ms is not None else "-",
        "jitter": f"{result.jitter_ms:.2f} ms" if result.jitter_ms is not None else "-",
        "packet_loss": f"{result.packet_loss:.2f}%" if result.packet_loss is not None else "-",
        "interface_name": "-",
        "internal_ip": "-",
        "external_ip": "-",
    }
    raw = result.raw
    if isinstance(raw, dict):
        interface = raw.get("interface")
        if isinstance(interface, dict):
            summary["interface_name"] = str(interface.get("name") or "-")
            summary["internal_ip"] = str(interface.get("internalIp") or "-")
            summary["external_ip"] = str(interface.get("externalIp") or "-")
    return summary


def show_backend_info() -> dict:
    """Return speedtest backend information."""
    ookla_binary = ookla_cli.find_ookla_speedtest_binary()
    return {
        "priority": list(BACKEND_PRIORITY),
        "available": get_available_backends(),
        "backends": {
            "official-ookla-cli": {
                "available": ookla_binary is not None,
                "binary_path": ookla_binary.path if ookla_binary else None,
                "version_output": ookla_binary.version_output if ookla_binary else None,
            },
            "librespeed-cli": {
                "available": librespeed_cli.is_available(),
                "binary_path": librespeed_cli.shutil.which("librespeed-cli"),
                "version_output": None,
            },
            "python-speedtest-cli": {
                "available": python_speedtest.is_available(),
                "binary_path": None,
                "version_output": None,
            },
        },
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
