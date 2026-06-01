"""Lightweight coordinate transforms for China map boundary matching.

The GCJ-02 formulas below are the common public engineering approximation.
They are suitable for reducing obvious WGS84-vs-Amap boundary mismatches, but
they are not a cadastral or survey-grade conversion.
"""

from __future__ import annotations

import math
from typing import Literal


BoundaryCoordSystem = Literal["auto", "wgs84", "gcj02"]

_A = 6378245.0
_EE = 0.00669342162296594323
_PI = math.pi


def out_of_china(lat: float, lon: float) -> bool:
    """Return True when the coordinate is outside mainland China transform bounds."""
    return lon < 72.004 or lon > 137.8347 or lat < 0.8293 or lat > 55.8271


def wgs84_to_gcj02(lat: float, lon: float) -> tuple[float, float]:
    """Convert WGS84 latitude/longitude to GCJ-02 using a public approximation."""
    if out_of_china(lat, lon):
        return lat, lon

    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * _PI
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * _PI)
    dlon = (dlon * 180.0) / (_A / sqrt_magic * math.cos(radlat) * _PI)
    return lat + dlat, lon + dlon


def gcj02_to_wgs84(lat: float, lon: float) -> tuple[float, float]:
    """Approximate GCJ-02 latitude/longitude back to WGS84."""
    if out_of_china(lat, lon):
        return lat, lon
    gcj_lat, gcj_lon = wgs84_to_gcj02(lat, lon)
    return lat * 2 - gcj_lat, lon * 2 - gcj_lon


def transform_point_for_boundary(
    lat: float, lon: float, boundary_coord_system: BoundaryCoordSystem
) -> tuple[float, float]:
    """Return the coordinate that should be used to query a boundary dataset."""
    if boundary_coord_system == "wgs84":
        return lat, lon
    if boundary_coord_system == "gcj02":
        return wgs84_to_gcj02(lat, lon)
    if boundary_coord_system == "auto":
        return wgs84_to_gcj02(lat, lon)
    raise ValueError(f"unsupported boundary coordinate system: {boundary_coord_system}")


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y
    ret += 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * _PI) + 40.0 * math.sin(y / 3.0 * _PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * _PI) + 320 * math.sin(y * _PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y
    ret += 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * _PI) + 40.0 * math.sin(x / 3.0 * _PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * _PI) + 300.0 * math.sin(x / 30.0 * _PI)) * 2.0 / 3.0
    return ret
