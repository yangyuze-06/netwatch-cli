from netwatch.analysis import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    analyze_speedtest_consistency,
    build_network_path_summary,
    detect_vpn_tun,
    get_result_confidence,
)
from netwatch.speedtest_backends.models import SpeedtestResult


def test_high_packet_loss_with_high_throughput_warns_metric_conflict() -> None:
    result = SpeedtestResult(
        backend="official-ookla-cli",
        packet_loss=59,
        download_mbps=96,
    )

    messages = analyze_speedtest_consistency(result)

    assert any("高丢包但吞吐仍较高" in message for message in messages)
    assert any("VPN/TUN" in message for message in messages)
    assert any("speedtest.cn" in message for message in messages)


def test_tokyo_server_with_high_ping_warns_route_issue() -> None:
    result = SpeedtestResult(
        backend="official-ookla-cli",
        ping_ms=140,
        server_location="Tokyo",
    )

    messages = analyze_speedtest_consistency(result)

    assert any("亚洲节点但延迟异常偏高" in message for message in messages)
    assert any("国际出口中转" in message for message in messages)


def test_vpn_tun_detection_from_interface() -> None:
    result = SpeedtestResult(
        backend="official-ookla-cli",
        raw={"interface": {"name": "utun8", "internalIp": "198.18.0.1"}},
    )

    assert detect_vpn_tun(result) is True
    assert any("TUN/VPN 虚拟网卡" in message for message in analyze_speedtest_consistency(result))


def test_100_mbps_upper_bound_explanation() -> None:
    result = SpeedtestResult(backend="librespeed-cli", download_mbps=96)

    messages = analyze_speedtest_consistency(result)

    assert any("100 Mbps" in message for message in messages)
    assert any("12.5 MB/s" in message for message in messages)


def test_confidence_high() -> None:
    result = SpeedtestResult(
        backend="official-ookla-cli",
        ping_ms=20,
        jitter_ms=2,
        packet_loss=0.1,
    )

    confidence, reasons = get_result_confidence(result)

    assert confidence == CONFIDENCE_HIGH
    assert "ping < 50ms" in reasons


def test_confidence_medium() -> None:
    result = SpeedtestResult(
        backend="official-ookla-cli",
        ping_ms=70,
        jitter_ms=12,
        packet_loss=0.5,
    )

    confidence, reasons = get_result_confidence(result)

    assert confidence == CONFIDENCE_MEDIUM
    assert "ping >= 50ms" in reasons


def test_confidence_low_for_vpn_and_high_loss() -> None:
    result = SpeedtestResult(
        backend="official-ookla-cli",
        ping_ms=140,
        jitter_ms=50,
        packet_loss=59,
        download_mbps=96,
        raw={"interface": {"name": "utun8", "internalIp": "198.18.0.1"}},
    )

    confidence, reasons = get_result_confidence(result)

    assert confidence == CONFIDENCE_LOW
    assert "packet loss > 20%" in reasons
    assert "VPN/TUN detected" in reasons


def test_network_path_summary_for_librespeed_client_and_server() -> None:
    result = SpeedtestResult(
        backend="librespeed-cli",
        raw={
            "client": {"country": "JP", "city": "Tokyo"},
            "server": {"name": "Amsterdam, Netherlands", "url": "http://spd-nlsrv.hostkey.com/"},
        },
    )

    summary = build_network_path_summary(result)

    assert summary["current_exit"] == "JP / Tokyo"
    assert summary["speedtest_server"] == "Amsterdam, Netherlands"
    assert summary["vpn_tun"] == "no"
