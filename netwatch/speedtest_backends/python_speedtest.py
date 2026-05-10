"""Python speedtest-cli fallback backend."""

from __future__ import annotations

from typing import Any

from netwatch.speedtest_backends.models import SpeedtestResult

BACKEND_NAME = "python-speedtest-cli"
FALLBACK_NOTE = "Python speedtest-cli results may be lower than official Ookla CLI or browser results."


def is_available() -> bool:
    """Return True if the Python speedtest module is importable."""
    try:
        import speedtest  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def run_speedtest(server_id: str | None = None) -> SpeedtestResult:
    """Run Python speedtest-cli fallback."""
    try:
        import speedtest
    except ModuleNotFoundError:
        return SpeedtestResult(backend=BACKEND_NAME, error="Python speedtest-cli is not installed. pip install speedtest-cli")

    try:
        tester = speedtest.Speedtest()
        if server_id:
            tester.get_servers([int(server_id)])
        server = tester.get_best_server()
        tester.download()
        tester.upload(pre_allocate=True)
    except Exception as exc:
        return SpeedtestResult(backend=BACKEND_NAME, error=str(exc))

    return result_from_bits(
        download_bits_per_second=float(tester.results.download),
        upload_bits_per_second=float(tester.results.upload),
        ping_ms=float(tester.results.ping),
        server=server,
        raw_note=FALLBACK_NOTE,
    )


def list_servers() -> list[dict]:
    """List nearby Python speedtest-cli servers."""
    try:
        import speedtest
        tester = speedtest.Speedtest()
        return tester.get_closest_servers(limit=10)
    except Exception as exc:
        return [{"error": str(exc)}]


def result_from_bits(
    *,
    download_bits_per_second: float,
    upload_bits_per_second: float,
    ping_ms: float,
    server: dict[str, Any] | None = None,
    raw_note: str | None = None,
) -> SpeedtestResult:
    """Build SpeedtestResult from bit/s values."""
    server = server or {}
    return SpeedtestResult(
        backend=BACKEND_NAME,
        ping_ms=ping_ms,
        download_mbps=download_bits_per_second / 1_000_000,
        download_MBps=download_bits_per_second / 8 / 1_000_000,
        upload_mbps=upload_bits_per_second / 1_000_000,
        upload_MBps=upload_bits_per_second / 8 / 1_000_000,
        server_id=str(server.get("id")) if server.get("id") is not None else None,
        server_name=server.get("name"),
        server_location=server.get("country"),
        server_sponsor=server.get("sponsor"),
        raw={"note": raw_note} if raw_note else None,
    )
