"""Speedtest result consistency and network path analysis."""

from __future__ import annotations

from typing import Any

from netwatch.speedtest_backends.models import SpeedtestResult

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"


def analyze_speedtest_consistency(result: SpeedtestResult) -> list[str]:
    """Return human-readable consistency and path analysis messages."""
    messages: list[str] = []

    if has_high_loss_high_throughput(result):
        messages.append(
            "检测到高丢包但吞吐仍较高。当前 packet loss 指标可能受 VPN/TUN、"
            "测速服务器实现或 UDP 测量方式影响。建议：更换测速服务器；关闭 VPN/TUN 后复测；"
            "使用 speedtest.cn 本地节点交叉验证。"
        )

    if has_high_ping_to_asia_server(result):
        messages.append(
            "检测到亚洲节点但延迟异常偏高。当前可能存在：VPN/TUN 绕路、国际出口中转、"
            "校园网 QoS、非物理网卡测速。"
        )

    if detect_vpn_tun(result):
        messages.append(
            "当前测速经过 TUN/VPN 虚拟网卡。测速结果代表当前代理出口路径，"
            "而不一定代表本地宽带裸连质量。"
        )

    if result.download_mbps is not None and 95 <= result.download_mbps <= 100:
        messages.append("当前测速结果已接近典型 100 Mbps 网络理论上限（≈12.5 MB/s）。")

    return messages


def get_result_confidence(result: SpeedtestResult) -> tuple[str, list[str]]:
    """Return a simple confidence level and reasons."""
    reasons: list[str] = []

    if result.packet_loss is not None and result.packet_loss > 20:
        reasons.append("packet loss > 20%")
    if result.ping_ms is not None and result.ping_ms > 100:
        reasons.append("ping > 100ms")
    if detect_vpn_tun(result):
        reasons.append("VPN/TUN detected")
    if has_high_loss_high_throughput(result):
        reasons.append("高丢包但吞吐仍较高")

    if reasons:
        return CONFIDENCE_LOW, reasons

    has_complete_clean_metrics = (
        result.ping_ms is not None
        and result.packet_loss is not None
        and result.jitter_ms is not None
        and result.ping_ms < 50
        and result.packet_loss < 1
        and result.jitter_ms < 10
    )
    if has_complete_clean_metrics:
        return CONFIDENCE_HIGH, ["ping < 50ms", "packet loss < 1%", "jitter < 10ms"]

    medium_reasons: list[str] = []
    if result.ping_ms is not None and result.ping_ms >= 50:
        medium_reasons.append("ping >= 50ms")
    if result.packet_loss is not None and result.packet_loss >= 1:
        medium_reasons.append("packet loss >= 1%")
    if result.jitter_ms is not None and result.jitter_ms >= 10:
        medium_reasons.append("jitter >= 10ms")
    return CONFIDENCE_MEDIUM, medium_reasons or ["指标不完整，无法判定为 HIGH"]


def build_network_path_summary(result: SpeedtestResult) -> dict[str, str]:
    """Return compact network path facts for CLI display and summaries."""
    is_vpn = detect_vpn_tun(result)
    high_ping_route = has_high_ping_to_asia_server(result)
    contradiction = has_high_loss_high_throughput(result)
    return {
        "current_exit": get_current_exit_label(result),
        "speedtest_server": get_server_label(result),
        "vpn_tun": "yes" if is_vpn else "no",
        "high_latency_route": "yes" if high_ping_route else "no",
        "metric_contradiction": "yes" if contradiction else "no",
        "likely_represents": "代理出口路径" if is_vpn else "当前 CLI 网络路径",
        "not_necessarily": "本地宽带裸连质量" if is_vpn else "-",
    }


def get_analysis_summary(result: SpeedtestResult) -> str:
    """Return a compact one-line analysis summary."""
    messages = analyze_speedtest_consistency(result)
    return " | ".join(messages) if messages else "未检测到明显路径或指标矛盾。"


def detect_vpn_tun(result: SpeedtestResult) -> bool:
    """Return True when raw data indicates a TUN/VPN virtual interface."""
    raw = result.raw
    if not isinstance(raw, dict):
        return False
    interface = raw.get("interface")
    if not isinstance(interface, dict):
        return False
    name = str(interface.get("name") or "").lower()
    internal_ip = str(interface.get("internalIp") or "")
    return any(keyword in name for keyword in ("utun", "tun", "tap")) or internal_ip.startswith("198.18.")


def has_high_loss_high_throughput(result: SpeedtestResult) -> bool:
    """Return True for high packet loss with still-high throughput."""
    return (
        result.packet_loss is not None
        and result.packet_loss > 20
        and result.download_mbps is not None
        and result.download_mbps > 50
    )


def has_high_ping_to_asia_server(result: SpeedtestResult) -> bool:
    """Return True for high ping to Tokyo/Japan/Hong Kong-like servers."""
    if result.ping_ms is None or result.ping_ms <= 100:
        return False
    server_text = get_server_label(result).lower()
    return any(keyword in server_text for keyword in ("tokyo", "japan", "hong kong"))


def get_current_exit_label(result: SpeedtestResult) -> str:
    """Return best-effort current exit country/city label from backend raw data."""
    raw = result.raw
    if not isinstance(raw, dict):
        return "-"
    client = raw.get("client")
    if isinstance(client, dict):
        return join_label(client.get("country"), client.get("city"))
    interface = raw.get("interface")
    if isinstance(interface, dict):
        external_ip = interface.get("externalIp")
        return f"externalIp={external_ip}" if external_ip else "-"
    return "-"


def get_server_label(result: SpeedtestResult) -> str:
    """Return best-effort speedtest server location label."""
    raw = result.raw
    raw_server = raw.get("server") if isinstance(raw, dict) else None
    if isinstance(raw_server, dict):
        label = join_label(raw_server.get("country"), raw_server.get("location"), raw_server.get("name"))
        if label != "-":
            return label
    return result.server_location or result.server_name or result.server_sponsor or "-"


def join_label(*values: Any) -> str:
    """Join meaningful label fields."""
    parts = [str(value) for value in values if value]
    return " / ".join(parts) if parts else "-"
