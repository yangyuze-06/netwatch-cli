"""Structured result models for experimental offline precise location."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrowserLocationResult:
    """One-shot browser geolocation coordinates."""

    latitude: float
    longitude: float
    accuracy_m: float | None = None
    altitude: float | None = None
    altitude_accuracy: float | None = None
    heading: float | None = None
    speed: float | None = None
    timestamp: float | None = None
    source: str = "browser_geolocation"


@dataclass
class AdminLocationResult:
    """Administrative region result from offline data."""

    country: str | None = None
    province: str | None = None
    city: str | None = None
    district: str | None = None
    adcode: str | None = None
    confidence: str = "unknown"
    source: str = "unknown"
    raw_name: str | None = None
    distance_km: float | None = None
    raw_properties: dict[str, Any] | None = None
    boundary_coord_system: str | None = None
    boundary_query_latitude: float | None = None
    boundary_query_longitude: float | None = None
    boundary_distance_m: float | None = None
    boundary_match_count: int = 0
    boundary_warnings: list[str] = field(default_factory=list)


@dataclass
class NearbyRoadResult:
    """Nearby road/street result from an offline roads dataset."""

    name: str | None = None
    highway: str | None = None
    ref: str | None = None
    distance_m: float | None = None
    source: str = "offline_roads"


@dataclass
class PreciseLocationReport:
    """Combined experimental precise location report."""

    browser: BrowserLocationResult | None = None
    admin: AdminLocationResult | None = None
    nearby_roads: list[NearbyRoadResult] = field(default_factory=list)
    fallback_used: bool = False
    warnings: list[str] = field(default_factory=list)
