"""Speedtest backend scheduler."""

from __future__ import annotations

from netwatch.analysis import (
    build_network_path_summary,
    detect_vpn_tun,
    get_analysis_summary,
    get_result_confidence,
)
from netwatch.config import get_preferred_librespeed
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


def run_librespeed_custom_speedtest(
    *,
    server_json_url: str | None = None,
    local_json_path: str | None = None,
    duration: int | None = None,
    source_ip: str | None = None,
    use_preferred: bool = False,
) -> SpeedtestResult:
    """Run LibreSpeed with a custom server list or saved LibreSpeed config."""
    if use_preferred:
        preferred = get_preferred_librespeed()
        if not preferred:
            return SpeedtestResult(backend="librespeed-cli", error="当前没有保存的 LibreSpeed 配置。")
        server_json_url = str(preferred.get("server_json_url") or "").strip() or None
        local_json_path = str(preferred.get("local_json_path") or "").strip() or None
        duration = parse_optional_int(preferred.get("duration"))

    return remember_successful_result(
        librespeed_cli.run_speedtest(
            server_json_url=server_json_url,
            local_json_path=local_json_path,
            duration=duration,
            source_ip=source_ip,
        )
    )


def parse_optional_int(value: object) -> int | None:
    """Parse an optional positive integer value."""
    try:
        parsed = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return parsed if parsed and parsed > 0 else None


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


def build_isp_preset_keywords(org: str = "", city: str = "", region: str = "") -> list[str]:
    """Build priority keywords for ISP/city-based server selection.

    Returns deduplicated keywords in priority order. Hong Kong is only
    a fallback candidate and may not be optimal for mainland China Mobile lines.
    """
    keywords: list[str] = []
    org = org or ""
    city = city or ""
    region = region or ""

    is_china_mobile = "China Mobile" in org or "移动" in org
    is_guangzhou = "Guangzhou" in city
    is_guangdong = "Guangdong" in region

    if is_china_mobile:
        if is_guangzhou or is_guangdong:
            keywords.extend(["Guangzhou", "Guangdong", "China Mobile", "Mobile", "Shenzhen"])
        else:
            keywords.extend(["China Mobile", "Mobile", "Guangzhou", "Guangdong", "Shenzhen"])

    if city:
        keywords.append(city)
    if region:
        keywords.append(region)

    for kw in ["Guangzhou", "Guangdong"]:
        if kw not in keywords:
            keywords.append(kw)

    # Hong Kong is only a last-resort fallback
    keywords.append("Hong Kong")

    seen: set[str] = set()
    result: list[str] = []
    for kw in keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            result.append(kw)
    return result


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


def get_speedtest_quality_details(result: SpeedtestResult) -> list[dict]:
    """Return specific quality warnings with actionable advice."""
    details: list[dict] = []

    if result.ping_ms is not None and result.ping_ms > 80:
        details.append({
            "condition": "ping > 80ms",
            "advice": [
                "测速服务器延迟较高，可能距离过远或线路绕路。",
                "建议使用高级功能 → 按关键词筛选服务器测速，优先尝试 Guangzhou / Guangdong / China Mobile / Shenzhen。",
                "如果已有稳定 server id，建议保存为默认测速服务器。",
            ],
        })

    if result.jitter_ms is not None and result.jitter_ms > 30:
        details.append({
            "condition": "jitter > 30ms",
            "advice": [
                "网络抖动较高，测速结果可能不稳定。",
                "建议关闭大流量下载/代理切换后重试，或更换测速服务器。",
            ],
        })

    if result.packet_loss is not None and result.packet_loss > 1:
        details.append({
            "condition": "packet loss > 1%",
            "advice": [
                "存在丢包，测速结果可能明显偏低。",
                "建议检查 Wi-Fi 信号、路由器负载、代理/TUN/VPN 状态。",
            ],
        })

    if result.download_mbps is not None and result.download_mbps < 50:
        details.append({
            "condition": "download < 50 Mbps",
            "advice": [
                "下载结果明显偏低，可能是服务器带宽不足、Ookla 自动选服不适合当前运营商，或当前走了代理/TUN。",
                "建议：",
                "  a. 使用 speedtest.cn 网页对照测速。",
                "  b. 使用高级功能 → 指定 server id 测速并保存。",
                "  c. 使用高级功能 → 按关键词筛选服务器测速。",
            ],
        })

    raw = result.raw
    if isinstance(raw, dict):
        interface = raw.get("interface")
        if isinstance(interface, dict):
            name = str(interface.get("name") or "").lower()
            internal_ip = str(interface.get("internalIp") or "")
            is_virtual_iface = any(kw in name for kw in ("utun", "tun", "tap"))
            is_virtual_ip = internal_ip.startswith("198.18.")
            if is_virtual_iface or is_virtual_ip:
                details.append({
                    "condition": f"interface={interface.get('name')}, internalIp={interface.get('internalIp')}",
                    "advice": [
                        "当前测速可能经过 TUN/VPN/代理虚拟网卡。",
                        "普通带宽测速建议使用物理网卡 en0；代理/当前出口测速才使用当前 CLI 出口。",
                    ],
                })

    return details


def summarize_speedtest_raw(result: SpeedtestResult) -> dict[str, str]:
    """Return a compact summary of raw speedtest details."""
    confidence, _ = get_result_confidence(result)
    path_summary = build_network_path_summary(result)
    summary = {
        "backend": result.backend,
        "server_id": result.server_id or "-",
        "server_name": result.server_name or result.server_sponsor or "-",
        "location": result.server_location or "-",
        "ping": f"{result.ping_ms:.2f} ms" if result.ping_ms is not None else "-",
        "jitter": f"{result.jitter_ms:.2f} ms" if result.jitter_ms is not None else "-",
        "packet_loss": f"{result.packet_loss:.2f}%" if result.packet_loss is not None else "-",
        "confidence": confidence,
        "vpn_tun": "yes" if detect_vpn_tun(result) else "no",
        "current_exit": path_summary["current_exit"],
        "speedtest_server": path_summary["speedtest_server"],
        "analysis_summary": get_analysis_summary(result),
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
