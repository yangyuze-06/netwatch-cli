"""Shared speedtest backend models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SpeedtestResult:
    """Unified speedtest result across all backends."""

    backend: str
    ping_ms: float | None = None
    jitter_ms: float | None = None
    packet_loss: float | None = None
    download_mbps: float | None = None
    download_MBps: float | None = None
    upload_mbps: float | None = None
    upload_MBps: float | None = None
    server_id: str | None = None
    server_name: str | None = None
    server_location: str | None = None
    server_sponsor: str | None = None
    raw: dict | str | None = None
    error: str | None = None
