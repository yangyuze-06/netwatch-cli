"""Network speed sampling helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class NetworkSpeed:
    """Upload and download speed in bytes per second."""

    upload_bps: float
    download_bps: float


def format_speed(bytes_per_second: float) -> str:
    """Format a byte-per-second value as KB/s or MB/s."""
    kib = bytes_per_second / 1024
    if kib >= 1024:
        return f"{kib / 1024:.2f} MB/s"
    return f"{kib:.2f} KB/s"


def sample_network_speed(interval: float = 1.0) -> NetworkSpeed:
    """Sample total network upload/download speed over an interval."""
    first = psutil.net_io_counters()
    time.sleep(interval)
    second = psutil.net_io_counters()

    upload = max(0, second.bytes_sent - first.bytes_sent) / interval
    download = max(0, second.bytes_recv - first.bytes_recv) / interval
    return NetworkSpeed(upload_bps=upload, download_bps=download)
