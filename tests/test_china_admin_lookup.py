"""Tests for offline Chinese admin division lookup."""

from __future__ import annotations

import csv
from pathlib import Path

from netwatch.location.china_admin_lookup import (
    _haversine_km,
    _load_district_data,
    get_cache_info,
    lookup_nearest_district,
)


DATA_PATH = Path(__file__).resolve().parent.parent / "netwatch/location/data/china_district_centers.csv"


# --- Haversine tests ---


def test_haversine_zero_distance() -> None:
    """Same point must return zero distance."""
    dist = _haversine_km(113.2644, 23.1292, 113.2644, 23.1292)
    assert dist == 0.0


def test_haversine_guangzhou_beijing() -> None:
    """Guangzhou to Beijing should be roughly 1900 km."""
    dist = _haversine_km(113.2644, 23.1292, 116.4074, 39.9042)
    assert 1800 < dist < 2100, f"Expected ~1900 km, got {dist}"


def test_haversine_short_distance() -> None:
    """Short distance must be plausible."""
    # Tianhe to Yuexiu: ~2-3 km
    dist = _haversine_km(113.3616, 23.1247, 113.2668, 23.1287)
    assert 5 < dist < 15, f"Expected ~10 km, got {dist}"


# --- Data loading ---


def test_load_district_data() -> None:
    """Data must load without error and return records."""
    records = _load_district_data()
    assert len(records) > 2000, "District center data is unexpectedly small"
    # Every record must have required fields
    for rec in records:
        assert "adcode" in rec
        assert "lon" in rec
        assert "lat" in rec
        assert isinstance(rec["lon"], float)
        assert isinstance(rec["lat"], float)


def test_cache_info() -> None:
    """Cache must report loaded status."""
    info = get_cache_info()
    assert info["loaded"] is True
    assert info["record_count"] > 2000


def test_data_contains_required_districts() -> None:
    """Bundled CSV must contain key province/city/district records."""
    with DATA_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) > 2000
    existing = {(row["province"], row["city"], row["district"]) for row in rows}
    assert ("广东省", "广州市", "黄埔区") in existing
    assert ("广东省", "广州市", "增城区") in existing
    assert ("北京市", "北京市", "海淀区") in existing
    assert ("上海市", "上海市", "浦东新区") in existing


# --- Lookup tests ---


def test_lookup_nearest_district_guangzhou_yonghe() -> None:
    """Coordinates near Zengcheng must return a Guangdong district."""
    # Coordinates near 23.15, 113.58 (Yonghe area, near Zengcheng/Huangpu border)
    result = lookup_nearest_district(113.581404, 23.153126, max_km=100.0)
    assert result is not None, "Should find a district near Guangzhou"
    assert result["country"] == "CN"
    assert result["province"] == "广东省"
    assert result["city"] == "广州市"
    assert result["district"] in {"黄埔区", "增城区"}
    assert result["distance_km"] < 100.0


def test_lookup_nearest_district_singapore_returns_none() -> None:
    """Far-away coordinates must return None."""
    result = lookup_nearest_district(103.8198, 1.3521, max_km=80.0)
    assert result is None


def test_lookup_nearest_district_tokyo_returns_none() -> None:
    """Japan coordinates must not be misclassified as China."""
    result = lookup_nearest_district(139.6917, 35.6895, max_km=80.0)
    assert result is None


def test_lookup_nearest_district_beijing_haidian() -> None:
    """Beijing Haidian coordinates should find a Beijing district."""
    result = lookup_nearest_district(116.2981, 39.9599, max_km=80.0)
    assert result is not None
    assert result["country"] == "CN"
    assert result["province"] == "北京市"
    assert result["city"] == "北京市"
    assert result["district"] == "海淀区"


def test_lookup_max_km_boundary() -> None:
    """A point near China border should work within max_km."""
    # Shenzhen coordinates
    result = lookup_nearest_district(114.0579, 22.5431, max_km=10.0)
    assert result is not None
    assert result["distance_km"] < 10.0
    # Same point with very tight radius might still find it
    result2 = lookup_nearest_district(114.0579, 22.5431, max_km=5.0)
    if result2 is not None:
        assert result2["distance_km"] < 5.0
