from netwatch.speedtest_backends.models import SpeedtestResult
from netwatch.speedtest_backends.ookla_cli import parse_ookla_result
from netwatch.speedtest_backends.python_speedtest import result_from_bits
from netwatch import speedtest_runner


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
    monkeypatch.setattr(speedtest_runner.ookla_cli, "run_speedtest", lambda server_id=None: SpeedtestResult("official-ookla-cli"))

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
