from netwatch.speedtest_backends.models import SpeedtestResult
from netwatch.speedtest_backends import ookla_cli
from netwatch.speedtest_backends.ookla_cli import parse_ookla_result
from netwatch.speedtest_backends.python_speedtest import result_from_bits
from netwatch import speedtest_runner
from netwatch.network_info import InterfaceInfo
from netwatch import network_info


def test_speedtest_result_dataclass() -> None:
    result = SpeedtestResult(backend="test", ping_ms=1.2, download_mbps=100)

    assert result.backend == "test"
    assert result.ping_ms == 1.2
    assert result.download_mbps == 100


def test_ookla_json_bandwidth_bytes_per_second_conversion() -> None:
    result = parse_ookla_result(
        {
            "ping": {"latency": 8.5, "jitter": 1.25},
            "packetLoss": 0.5,
            "download": {"bandwidth": 50_000_000},
            "upload": {"bandwidth": 10_000_000},
            "server": {
                "id": 1234,
                "name": "Shanghai",
                "location": "Shanghai",
                "sponsor": "Example ISP",
            },
        }
    )

    assert result.download_mbps == 400
    assert result.download_MBps == 50
    assert result.upload_mbps == 80
    assert result.upload_MBps == 10
    assert result.ping_ms == 8.5
    assert result.jitter_ms == 1.25
    assert result.packet_loss == 0.5
    assert result.server_id == "1234"


def test_python_speedtest_bits_per_second_conversion() -> None:
    result = result_from_bits(
        download_bits_per_second=400_000_000,
        upload_bits_per_second=80_000_000,
        ping_ms=12.0,
        server={"id": "1", "name": "Test", "sponsor": "ISP"},
    )

    assert result.download_mbps == 400
    assert result.download_MBps == 50
    assert result.upload_mbps == 80
    assert result.upload_MBps == 10
    assert result.backend == "python-speedtest-cli"


def test_backend_priority_official_first(monkeypatch) -> None:
    monkeypatch.setattr(speedtest_runner.ookla_cli, "is_available", lambda: True)
    monkeypatch.setattr(speedtest_runner.librespeed_cli, "is_available", lambda: True)
    monkeypatch.setattr(speedtest_runner.python_speedtest, "is_available", lambda: True)
    monkeypatch.setattr(
        speedtest_runner.ookla_cli,
        "run_speedtest",
        lambda server_id=None, interface=None: SpeedtestResult("official-ookla-cli"),
    )

    assert speedtest_runner.run_best_speedtest().backend == "official-ookla-cli"


def test_backend_priority_librespeed_second(monkeypatch) -> None:
    monkeypatch.setattr(speedtest_runner.ookla_cli, "is_available", lambda: False)
    monkeypatch.setattr(speedtest_runner.librespeed_cli, "is_available", lambda: True)
    monkeypatch.setattr(speedtest_runner.python_speedtest, "is_available", lambda: True)
    monkeypatch.setattr(speedtest_runner.librespeed_cli, "run_speedtest", lambda: SpeedtestResult("librespeed-cli"))

    assert speedtest_runner.run_best_speedtest().backend == "librespeed-cli"


def test_backend_priority_python_fallback(monkeypatch) -> None:
    monkeypatch.setattr(speedtest_runner.ookla_cli, "is_available", lambda: False)
    monkeypatch.setattr(speedtest_runner.librespeed_cli, "is_available", lambda: False)
    monkeypatch.setattr(speedtest_runner.python_speedtest, "is_available", lambda: True)
    monkeypatch.setattr(speedtest_runner.python_speedtest, "run_speedtest", lambda server_id=None: SpeedtestResult("python-speedtest-cli"))

    assert speedtest_runner.run_best_speedtest().backend == "python-speedtest-cli"


def test_no_backend_available_returns_friendly_error(monkeypatch) -> None:
    monkeypatch.setattr(speedtest_runner.ookla_cli, "is_available", lambda: False)
    monkeypatch.setattr(speedtest_runner.librespeed_cli, "is_available", lambda: False)
    monkeypatch.setattr(speedtest_runner.python_speedtest, "is_available", lambda: False)

    result = speedtest_runner.run_best_speedtest()

    assert result.backend == "none"
    assert "brew install speedtest" in (result.error or "")


def test_find_ookla_binary_prefers_homebrew_over_venv_shadow(monkeypatch) -> None:
    monkeypatch.setattr(ookla_cli, "OOKLA_CANDIDATE_PATHS", ("/opt/homebrew/bin/speedtest",))
    monkeypatch.setattr(ookla_cli.shutil, "which", lambda name: "/project/.venv/bin/speedtest")
    monkeypatch.setattr(ookla_cli.os.path, "exists", lambda path: True)

    def fake_version(path: str) -> str:
        if path == "/opt/homebrew/bin/speedtest":
            return "Speedtest by Ookla 1.2.0"
        return "speedtest-cli 2.1.3"

    monkeypatch.setattr(ookla_cli, "get_version_output", fake_version)

    binary = ookla_cli.find_ookla_speedtest_binary()

    assert binary is not None
    assert binary.path == "/opt/homebrew/bin/speedtest"


def test_ookla_run_uses_detected_absolute_binary(monkeypatch) -> None:
    commands = []
    monkeypatch.setattr(
        ookla_cli,
        "find_ookla_speedtest_binary",
        lambda: ookla_cli.OoklaBinaryInfo("/opt/homebrew/bin/speedtest", "Speedtest by Ookla 1.2.0"),
    )

    class Completed:
        stdout = (
            '{"ping":{"latency":1},"download":{"bandwidth":1000000},'
            '"upload":{"bandwidth":500000},"server":{"id":1,"name":"A"}}'
        )

    def fake_run_command(command):
        commands.append(command)
        return Completed()

    monkeypatch.setattr(ookla_cli, "run_command", fake_run_command)

    result = ookla_cli.run_speedtest(server_id="123")

    assert commands[0][0] == "/opt/homebrew/bin/speedtest"
    assert "--server-id" in commands[0]
    assert result.backend == "official-ookla-cli"


def test_preferred_physical_interface_excludes_utun_and_198_18(monkeypatch) -> None:
    monkeypatch.setattr(
        network_info,
        "get_network_interfaces",
        lambda: [
            InterfaceInfo("utun8", "198.18.0.1", None),
            InterfaceInfo("en0", "192.168.31.75", "aa:bb:cc:dd:ee:ff"),
        ],
    )

    preferred = network_info.get_preferred_physical_interface()

    assert preferred == {
        "name": "en0",
        "ip": "192.168.31.75",
        "reason": "preferred private LAN interface",
    }


def test_ookla_command_includes_interface(monkeypatch) -> None:
    commands = []
    monkeypatch.setattr(
        ookla_cli,
        "find_ookla_speedtest_binary",
        lambda: ookla_cli.OoklaBinaryInfo("/opt/homebrew/bin/speedtest", "Speedtest by Ookla 1.2.0"),
    )

    class Completed:
        stdout = (
            '{"ping":{"latency":1},"download":{"bandwidth":1000000},'
            '"upload":{"bandwidth":500000},"server":{"id":1,"name":"A"}}'
        )

    def fake_run_command(command):
        commands.append(command)
        return Completed()

    monkeypatch.setattr(ookla_cli, "run_command", fake_run_command)

    result = ookla_cli.run_speedtest(server_id="123", interface="en0")

    assert result.backend == "official-ookla-cli"
    assert commands[0][0] == "/opt/homebrew/bin/speedtest"
    assert commands[0][1:5] == ["--server-id", "123", "--interface", "en0"]


def test_filter_servers_by_keyword_matches_fields() -> None:
    servers = [
        {"id": 1, "name": "CM", "location": "Guangzhou", "country": "China", "host": "a.example"},
        {"id": 2, "name": "IPA", "location": "Tokyo", "country": "Japan", "host": "tokyo.example"},
        {"id": 3, "name": "HK", "location": "Central", "country": "Hong Kong", "host": "hk.example"},
    ]

    assert [server["id"] for server in speedtest_runner.filter_servers_by_keyword(servers, "guang")] == [1]
    assert [server["id"] for server in speedtest_runner.filter_servers_by_keyword(servers, "japan")] == [2]
    assert [server["id"] for server in speedtest_runner.filter_servers_by_keyword(servers, "hk.example")] == [3]


def test_cannot_read_socket_is_not_install_error() -> None:
    result = ookla_cli.parse_ookla_result({"error": "Cannot read from socket: "})

    assert result.error is not None
    assert "Cannot read from socket" in result.error
    assert "brew install speedtest" not in result.error


def test_proxy_exit_speedtest_does_not_force_interface(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(speedtest_runner.ookla_cli, "is_available", lambda: True)
    monkeypatch.setattr(speedtest_runner.librespeed_cli, "is_available", lambda: False)
    monkeypatch.setattr(speedtest_runner.python_speedtest, "is_available", lambda: False)

    def fake_run(server_id=None, interface=None):
        calls.append(interface)
        return SpeedtestResult("official-ookla-cli")

    monkeypatch.setattr(speedtest_runner.ookla_cli, "run_speedtest", fake_run)

    result = speedtest_runner.run_best_speedtest(use_interface=False)

    assert result.backend == "official-ookla-cli"
    assert calls == [None]


def test_quality_diagnosis_warns_for_high_ping_jitter_and_low_download() -> None:
    result = SpeedtestResult(
        backend="official-ookla-cli",
        ping_ms=120,
        jitter_ms=45,
        packet_loss=2,
        download_mbps=12,
    )

    warnings = speedtest_runner.get_speedtest_quality_warnings(result)

    assert "ping > 80ms" in warnings
    assert "jitter > 30ms" in warnings
    assert "packet loss > 1%" in warnings
    assert "download < 50 Mbps" in warnings


def test_configured_speedtest_uses_preferred_server(monkeypatch) -> None:
    calls = []

    def fake_run(backend, server_id=None, interface=None):
        calls.append((backend, server_id, interface))
        return SpeedtestResult(backend=backend, server_id=server_id)

    monkeypatch.setattr(speedtest_runner, "run_speedtest_with_backend", fake_run)

    result = speedtest_runner.run_configured_speedtest(
        {
            "backend": "official-ookla-cli",
            "server_id": "98765",
            "interface": "en0",
        }
    )

    assert result.server_id == "98765"
    assert calls == [("official-ookla-cli", "98765", "en0")]


def test_configured_speedtest_fallbacks_when_preferred_fails(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(speedtest_runner, "get_available_backends", lambda: ["official-ookla-cli"])

    def fake_run(backend, server_id=None, interface=None):
        calls.append((backend, server_id, interface))
        if server_id == "bad":
            return SpeedtestResult(backend=backend, error="server failed")
        return SpeedtestResult(backend=backend, server_id=server_id or "auto")

    monkeypatch.setattr(speedtest_runner, "run_speedtest_with_backend", fake_run)

    result = speedtest_runner.run_configured_speedtest(
        {
            "backend": "official-ookla-cli",
            "server_id": "bad",
            "interface": "en0",
        }
    )

    assert result.error is None
    assert result.server_id == "auto"
    assert calls[0] == ("official-ookla-cli", "bad", "en0")
    assert calls[1] == ("official-ookla-cli", None, "en0")


# --- Patch 1: ISP preset keywords ---


def test_isp_preset_china_mobile_excludes_hong_kong_from_priority() -> None:
    """Hong Kong must not appear in China Mobile priority keywords."""
    keywords = speedtest_runner.build_isp_preset_keywords(
        org="China Mobile", city="", region=""
    )
    # Priority segment (before fallback) must not include Hong Kong
    priority_segment = keywords[:5]
    assert "Hong Kong" not in priority_segment
    # Hong Kong must only appear at the very end
    assert keywords[-1] == "Hong Kong"


def test_isp_preset_guangzhou_city_has_top_priority() -> None:
    """When city is Guangzhou, it should be first keyword."""
    keywords = speedtest_runner.build_isp_preset_keywords(
        org="China Mobile", city="Guangzhou", region="Guangdong"
    )
    assert keywords[0] == "Guangzhou"
    assert keywords[1] == "Guangdong"
    assert "China Mobile" in keywords[:5]
    assert keywords[-1] == "Hong Kong"


def test_isp_preset_guangdong_region_has_top_priority() -> None:
    """When region is Guangdong, it should place Guangzhou/Guangdong first."""
    keywords = speedtest_runner.build_isp_preset_keywords(
        org="China Mobile", city="Shenzhen", region="Guangdong"
    )
    assert keywords[0] == "Guangzhou"
    assert keywords[1] == "Guangdong"
    assert keywords[-1] == "Hong Kong"


def test_isp_preset_non_china_mobile_no_hong_kong_priority() -> None:
    """Non-China-Mobile ISPs should not get Hong Kong in priority segment."""
    keywords = speedtest_runner.build_isp_preset_keywords(
        org="China Telecom", city="Shanghai", region="Shanghai"
    )
    # Hong Kong is still present but only as final fallback
    assert keywords[-1] == "Hong Kong"
    # No China Mobile specific keywords
    assert "China Mobile" not in keywords


def test_isp_preset_hong_kong_not_duplicated() -> None:
    """Hong Kong must appear exactly once in the keyword list."""
    keywords = speedtest_runner.build_isp_preset_keywords(
        org="China Mobile", city="Hong Kong", region="Hong Kong"
    )
    assert keywords.count("Hong Kong") == 1


def test_isp_preset_deduplicates_case_insensitive() -> None:
    """Keywords differing only in case should be deduplicated."""
    keywords = speedtest_runner.build_isp_preset_keywords(
        org="China Mobile", city="guangzhou", region="guangdong"
    )
    lower_keywords = [kw.lower() for kw in keywords]
    assert len(lower_keywords) == len(set(lower_keywords))


# --- Patch 3: quality diagnosis ---


def test_quality_details_high_ping_triggers_distance_advice() -> None:
    """High ping should trigger server distance / rerouting advice."""
    result = SpeedtestResult(backend="official-ookla-cli", ping_ms=120)
    details = speedtest_runner.get_speedtest_quality_details(result)
    assert any("ping > 80ms" == d["condition"] for d in details)
    ping_detail = next(d for d in details if d["condition"] == "ping > 80ms")
    assert any("距离过远" in line for line in ping_detail["advice"])


def test_quality_details_low_download_triggers_speedtest_cn_reference() -> None:
    """Low download should reference speedtest.cn and server id save advice."""
    result = SpeedtestResult(backend="official-ookla-cli", download_mbps=12)
    details = speedtest_runner.get_speedtest_quality_details(result)
    assert any("download < 50 Mbps" == d["condition"] for d in details)
    download_detail = next(d for d in details if d["condition"] == "download < 50 Mbps")
    combined = " ".join(download_detail["advice"])
    assert "speedtest.cn" in combined
    assert "指定 server id" in combined


def test_quality_details_utun_interface_triggers_vpn_warning() -> None:
    """utun interface in raw data should trigger TUN/VPN warning."""
    result = SpeedtestResult(
        backend="official-ookla-cli",
        raw={"interface": {"name": "utun8", "internalIp": "198.18.0.1"}},
    )
    details = speedtest_runner.get_speedtest_quality_details(result)
    assert any("utun8" in d["condition"] for d in details)
    vpn_detail = next(d for d in details if "utun8" in d["condition"])
    assert any("TUN/VPN" in line for line in vpn_detail["advice"])


def test_quality_details_198_18_ip_triggers_vpn_warning() -> None:
    """198.18.x.x internal IP should trigger TUN/VPN warning."""
    result = SpeedtestResult(
        backend="official-ookla-cli",
        raw={"interface": {"name": "en0", "internalIp": "198.18.0.1"}},
    )
    details = speedtest_runner.get_speedtest_quality_details(result)
    assert any("198.18.0.1" in d["condition"] for d in details)
    vpn_detail = next(d for d in details if "198.18.0.1" in d["condition"])
    assert any("TUN/VPN" in line for line in vpn_detail["advice"])


def test_quality_details_normal_en0_no_vpn_warning() -> None:
    """Normal en0 with 192.168.x.x should NOT trigger TUN/VPN warning."""
    result = SpeedtestResult(
        backend="official-ookla-cli",
        raw={"interface": {"name": "en0", "internalIp": "192.168.31.75"}},
    )
    details = speedtest_runner.get_speedtest_quality_details(result)
    assert not any("en0" in d.get("condition", "") for d in details)


def test_quality_details_jitter_triggers_stability_advice() -> None:
    """High jitter should trigger stability advice."""
    result = SpeedtestResult(backend="official-ookla-cli", jitter_ms=45)
    details = speedtest_runner.get_speedtest_quality_details(result)
    assert any("jitter > 30ms" == d["condition"] for d in details)
    jitter_detail = next(d for d in details if d["condition"] == "jitter > 30ms")
    assert any("不稳定" in line for line in jitter_detail["advice"])


def test_quality_details_packet_loss_triggers_wifi_check() -> None:
    """Packet loss should suggest checking Wi-Fi/router/VPN."""
    result = SpeedtestResult(backend="official-ookla-cli", packet_loss=2.5)
    details = speedtest_runner.get_speedtest_quality_details(result)
    assert any("packet loss > 1%" == d["condition"] for d in details)
    loss_detail = next(d for d in details if d["condition"] == "packet loss > 1%")
    assert any("Wi-Fi" in line for line in loss_detail["advice"])
