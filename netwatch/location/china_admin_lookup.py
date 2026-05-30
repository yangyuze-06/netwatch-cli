"""Offline Chinese administrative division lookup via nearest district center.

Uses a pre-built CSV of district/county center points and Haversine distance.
No network calls, no external API keys, no polygon data.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent / "data"
_DISTRICT_CSV = _DATA_DIR / "china_district_centers.csv"

_cache: list[dict[str, Any]] | None = None
_REQUIRED_FIELDS = {"adcode", "province", "city", "district", "lon", "lat"}
_MIN_RECORDS = 2000


def _load_district_data() -> list[dict[str, Any]]:
    """Load district center CSV into memory. Results are cached."""
    global _cache
    if _cache is not None:
        return _cache

    records: list[dict[str, Any]] = []
    if not _DISTRICT_CSV.exists():
        _cache = records
        return records

    try:
        with open(_DISTRICT_CSV, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or not _REQUIRED_FIELDS.issubset(reader.fieldnames):
                _cache = []
                return []
            for row in reader:
                try:
                    adcode = (row.get("adcode") or "").strip()
                    province = (row.get("province") or "").strip()
                    city = (row.get("city") or "").strip()
                    district = (row.get("district") or "").strip()
                    lon = float(row.get("lon") or "")
                    lat = float(row.get("lat") or "")
                except (ValueError, TypeError):
                    continue
                if not (adcode and province and city and district):
                    continue
                records.append({
                    "adcode": adcode,
                    "province": province,
                    "city": city,
                    "district": district,
                    "lon": lon,
                    "lat": lat,
                })
    except (OSError, csv.Error, UnicodeDecodeError):
        records = []

    if len(records) < _MIN_RECORDS:
        records = []

    _cache = records
    return records


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Compute Haversine distance between two points in kilometers."""
    r = 6371.0
    dlon = math.radians(lon2 - lon1)
    dlat = math.radians(lat2 - lat1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def lookup_nearest_district(
    lon: float, lat: float, max_km: float = 80.0
) -> dict[str, Any] | None:
    """Find the nearest Chinese administrative district center point.

    Args:
        lon: Longitude (east-positive).
        lat: Latitude (north-positive).
        max_km: Maximum search radius in kilometers.

    Returns:
        A dict with country/province/city/district/adcode/distance_km/source,
        or None if no district within max_km.
    """
    records = _load_district_data()
    if not records:
        return None

    best: dict[str, Any] | None = None
    best_dist = float("inf")

    for rec in records:
        dist = _haversine_km(lon, lat, rec["lon"], rec["lat"])
        if dist < best_dist:
            best_dist = dist
            best = rec

    if best is None or best_dist > max_km:
        return None

    return {
        "country": "CN",
        "province": best.get("province") or "",
        "city": best.get("city") or "",
        "district": best.get("district") or "",
        "adcode": best.get("adcode") or "",
        "distance_km": round(best_dist, 1),
        "source": "offline_china_district_centers",
    }


def get_cache_info() -> dict[str, Any]:
    """Return cache status for testing."""
    records = _load_district_data()
    return {
        "loaded": _cache is not None,
        "record_count": len(records),
    }
