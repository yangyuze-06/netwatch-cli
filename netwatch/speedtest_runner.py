"""Speedtest.net bandwidth test helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SpeedtestResult:
    """Measured internet bandwidth test result."""

    ping_ms: float
    download_bps: float
    upload_bps: float
    server_name: str
    server_sponsor: str
    server_id: str

    @property
    def download_mbps(self) -> float:
        """Download speed in megabits per second."""
        return self.download_bps / 1_000_000

    @property
    def download_mbs(self) -> float:
        """Download speed in megabytes per second."""
        return self.download_bps / 8 / 1_000_000

    @property
    def upload_mbps(self) -> float:
        """Upload speed in megabits per second."""
        return self.upload_bps / 1_000_000

    @property
    def upload_mbs(self) -> float:
        """Upload speed in megabytes per second."""
        return self.upload_bps / 8 / 1_000_000


@dataclass(frozen=True)
class SpeedtestServer:
    """A nearby Speedtest server option."""

    id: str
    sponsor: str
    name: str
    country: str
    distance_km: float | None
    latency_ms: float | None = None


class SpeedtestUnavailableError(RuntimeError):
    """Raised when speedtest-cli is not installed."""


class SpeedtestRunError(RuntimeError):
    """Raised when speedtest-cli fails to complete a test."""


def list_nearby_servers(limit: int = 10) -> list[SpeedtestServer]:
    """Return nearby Speedtest servers for manual selection."""
    try:
        import speedtest
    except ModuleNotFoundError as exc:
        raise SpeedtestUnavailableError("speedtest-cli is not installed") from exc

    try:
        tester = speedtest.Speedtest()
        servers = tester.get_closest_servers(limit=limit)
    except speedtest.SpeedtestException as exc:
        raise SpeedtestRunError(str(exc)) from exc
    except OSError as exc:
        raise SpeedtestRunError(str(exc)) from exc
    except Exception as exc:
        raise SpeedtestRunError(str(exc)) from exc

    return [
        SpeedtestServer(
            id=str(server.get("id", "-")),
            sponsor=str(server.get("sponsor", "-")),
            name=str(server.get("name", "-")),
            country=str(server.get("country", "-")),
            distance_km=_optional_float(server.get("d")),
            latency_ms=_optional_float(server.get("latency")),
        )
        for server in servers
    ]


def run_speedtest(
    progress: Callable[[str], None] | None = None,
    server_id: str | None = None,
) -> SpeedtestResult:
    """Run a Speedtest.net test and return ping/download/upload metrics."""
    try:
        import speedtest
    except ModuleNotFoundError as exc:
        raise SpeedtestUnavailableError("speedtest-cli is not installed") from exc

    try:
        tester = speedtest.Speedtest()
        if progress:
            progress("正在选择最佳服务器..." if server_id is None else f"正在选择服务器 {server_id}...")
        if server_id is not None:
            tester.get_servers([int(server_id)])
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
        download_bps=float(tester.results.download),
        upload_bps=float(tester.results.upload),
        server_name=str(server.get("name", "-")),
        server_sponsor=str(server.get("sponsor", "-")),
        server_id=str(server.get("id", server_id or "-")),
    )


def _optional_float(value: object) -> float | None:
    """Convert speedtest metadata to float when available."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
