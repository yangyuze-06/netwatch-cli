"""Speedtest.net bandwidth test helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SpeedtestResult:
    """Measured internet bandwidth test result."""

    ping_ms: float
    download_mbps: float
    upload_mbps: float
    server_name: str
    server_sponsor: str


class SpeedtestUnavailableError(RuntimeError):
    """Raised when speedtest-cli is not installed."""


class SpeedtestRunError(RuntimeError):
    """Raised when speedtest-cli fails to complete a test."""


def run_speedtest(progress: Callable[[str], None] | None = None) -> SpeedtestResult:
    """Run a Speedtest.net test and return ping/download/upload metrics."""
    try:
        import speedtest
    except ModuleNotFoundError as exc:
        raise SpeedtestUnavailableError("speedtest-cli is not installed") from exc

    try:
        tester = speedtest.Speedtest()
        if progress:
            progress("正在选择最佳服务器...")
        server = tester.get_best_server()
        if progress:
            progress("正在测试下载速度...")
        tester.download()
        if progress:
            progress("正在测试上传速度...")
        tester.upload(pre_allocate=True)
    except speedtest.SpeedtestException as exc:
        raise SpeedtestRunError(str(exc)) from exc
    except OSError as exc:
        raise SpeedtestRunError(str(exc)) from exc
    except Exception as exc:
        raise SpeedtestRunError(str(exc)) from exc

    return SpeedtestResult(
        ping_ms=float(tester.results.ping),
        download_mbps=float(tester.results.download) / 1_000_000,
        upload_mbps=float(tester.results.upload) / 1_000_000,
        server_name=str(server.get("name", "-")),
        server_sponsor=str(server.get("sponsor", "-")),
    )
