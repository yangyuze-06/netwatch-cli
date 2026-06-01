"""Experimental precise offline location orchestration."""

from __future__ import annotations

import os

from netwatch.location.admin.coord_transform import BoundaryCoordSystem, wgs84_to_gcj02
from netwatch.device_location import DeviceLocationResult, run_browser_geolocation
from netwatch.location.admin.china_admin_lookup import lookup_nearest_district
from netwatch.location.models import AdminLocationResult, BrowserLocationResult, PreciseLocationReport
from netwatch.location.roads.nearby_roads import (
    RoadsDependencyError,
    find_nearby_roads,
    load_roads_dataset,
)
from netwatch.location.admin.offline_boundary import (
    BoundaryDependencyError,
    load_boundary_dataset,
    locate_admin_by_point,
)


BOUNDARY_COORD_SYSTEM_ENV_VAR = "NETWATCH_BOUNDARY_COORD_SYSTEM"
BOUNDARY_COORD_SYSTEMS: set[str] = {"auto", "wgs84", "gcj02"}


def build_precise_location_report(
    device_result: DeviceLocationResult,
    *,
    boundary_path: str | None = None,
    roads_path: str | None = None,
    boundary_coord_system: BoundaryCoordSystem | None = None,
) -> PreciseLocationReport:
    """Build an offline precise location report from browser coordinates."""
    report = PreciseLocationReport()

    if device_result.error:
        report.warnings.append(device_result.error)
        return report
    if device_result.latitude is None or device_result.longitude is None:
        report.warnings.append("browser geolocation did not return coordinates")
        return report

    report.browser = BrowserLocationResult(
        latitude=device_result.latitude,
        longitude=device_result.longitude,
        accuracy_m=device_result.accuracy_m,
        altitude=device_result.altitude,
        altitude_accuracy=device_result.altitude_accuracy,
        heading=device_result.heading,
        speed=device_result.speed,
        timestamp=device_result.timestamp,
    )

    _fill_admin_result(report, boundary_path=boundary_path, coord_system=boundary_coord_system)
    _fill_nearby_roads(report, roads_path=roads_path)
    return report


def run_precise_location_report(timeout_seconds: int = 60) -> PreciseLocationReport:
    """Request browser geolocation once, then process location offline."""
    try:
        device_result = run_browser_geolocation(timeout_seconds=timeout_seconds)
    except Exception as exc:
        report = PreciseLocationReport()
        report.warnings.append(f"browser geolocation failed: {exc}")
        return report
    return build_precise_location_report(device_result)


def _fill_admin_result(
    report: PreciseLocationReport,
    *,
    boundary_path: str | None = None,
    coord_system: BoundaryCoordSystem | None = None,
) -> None:
    assert report.browser is not None
    lat = report.browser.latitude
    lon = report.browser.longitude

    try:
        dataset = load_boundary_dataset(boundary_path)
        selected_coord_system = _get_boundary_coord_system(coord_system)
        if dataset.is_sample:
            report.warnings.append(
                "当前行政区结果来自内置测试样例，不代表真实行政边界。"
                "请配置 NETWATCH_BOUNDARY_GEOJSON 后再使用精确行政区识别。"
            )
        admin = _locate_with_coord_system(lat, lon, dataset, selected_coord_system, report.warnings)
        if admin is not None:
            _append_admin_boundary_warnings(report, admin)
            report.admin = admin
            return
        report.warnings.append("precise boundary did not contain this point; falling back to nearest district center")
    except (BoundaryDependencyError, FileNotFoundError, ValueError, OSError) as exc:
        report.warnings.append(f"precise boundary unavailable: {exc}")

    center = lookup_nearest_district(lon, lat, max_km=80.0)
    if center is None:
        report.fallback_used = True
        report.warnings.append("nearest district center fallback found no match within 80 km")
        return

    report.fallback_used = True
    report.admin = AdminLocationResult(
        country=center.get("country") or "CN",
        province=center.get("province"),
        city=center.get("city"),
        district=center.get("district"),
        adcode=center.get("adcode"),
        confidence="medium",
        source=center.get("source") or "offline_china_district_centers",
        distance_km=center.get("distance_km"),
    )


def _fill_nearby_roads(report: PreciseLocationReport, *, roads_path: str | None = None) -> None:
    assert report.browser is not None
    try:
        roads = load_roads_dataset(roads_path)
        if roads.is_sample:
            report.warnings.append(
                "当前附近道路结果来自内置测试样例，不代表真实附近道路。"
                "请配置 NETWATCH_ROADS_GEOJSON 后再使用附近道路识别。"
            )
        report.nearby_roads = find_nearby_roads(
            report.browser.latitude,
            report.browser.longitude,
            roads,
            radius_m=300.0,
            limit=3,
        )
        if not report.nearby_roads:
            report.warnings.append("nearby street unavailable: no offline road matched within 300 m")
    except (RoadsDependencyError, FileNotFoundError, ValueError, OSError) as exc:
        report.warnings.append(f"nearby street unavailable: {exc}")


def _append_admin_boundary_warnings(report: PreciseLocationReport, admin: AdminLocationResult) -> None:
    for warning in admin.boundary_warnings:
        report.warnings.append(warning)
    if (
        report.browser is not None
        and report.browser.accuracy_m is not None
        and admin.boundary_distance_m is not None
        and report.browser.accuracy_m > admin.boundary_distance_m
    ):
        report.warnings.append("browser accuracy radius overlaps district boundary")


def _get_boundary_coord_system(explicit: BoundaryCoordSystem | None = None) -> BoundaryCoordSystem:
    value = explicit or os.environ.get(BOUNDARY_COORD_SYSTEM_ENV_VAR) or "auto"
    normalized = str(value).strip().lower()
    if normalized not in BOUNDARY_COORD_SYSTEMS:
        raise ValueError(
            f"{BOUNDARY_COORD_SYSTEM_ENV_VAR} must be one of auto, wgs84, gcj02; got {value!r}"
        )
    return normalized  # type: ignore[return-value]


def _locate_with_coord_system(
    lat: float,
    lon: float,
    dataset: object,
    coord_system: BoundaryCoordSystem,
    warnings: list[str],
) -> AdminLocationResult | None:
    if coord_system == "wgs84":
        admin = locate_admin_by_point(lat, lon, dataset)  # type: ignore[arg-type]
        _annotate_boundary_query(admin, "wgs84", lat, lon)
        return admin

    gcj_lat, gcj_lon = wgs84_to_gcj02(lat, lon)
    if coord_system == "gcj02":
        admin = locate_admin_by_point(gcj_lat, gcj_lon, dataset)  # type: ignore[arg-type]
        _annotate_boundary_query(admin, "gcj02", gcj_lat, gcj_lon)
        _mark_coord_transform_confidence(admin)
        warnings.append("boundary query used GCJ-02 conversion for DataV/Amap-style boundary data")
        return admin

    wgs84_admin = locate_admin_by_point(lat, lon, dataset)  # type: ignore[arg-type]
    gcj02_admin = locate_admin_by_point(gcj_lat, gcj_lon, dataset)  # type: ignore[arg-type]
    _annotate_boundary_query(wgs84_admin, "wgs84", lat, lon)
    _annotate_boundary_query(gcj02_admin, "gcj02", gcj_lat, gcj_lon)
    _mark_coord_transform_confidence(gcj02_admin)
    warnings.append("boundary query used GCJ-02 conversion for DataV/Amap-style boundary data")
    if _admin_identity(wgs84_admin) != _admin_identity(gcj02_admin):
        warnings.append("coordinate system ambiguity: WGS84 and GCJ-02 boundary probes returned different results")
    return gcj02_admin or wgs84_admin


def _annotate_boundary_query(
    admin: AdminLocationResult | None, coord_system: str, lat: float, lon: float
) -> None:
    if admin is None:
        return
    admin.boundary_coord_system = coord_system
    admin.boundary_query_latitude = lat
    admin.boundary_query_longitude = lon


def _mark_coord_transform_confidence(admin: AdminLocationResult | None) -> None:
    if admin is None or admin.confidence == "sample_only":
        return
    admin.confidence = "high_with_coord_transform"


def _admin_identity(admin: AdminLocationResult | None) -> tuple[str | None, str | None] | None:
    if admin is None:
        return None
    return admin.adcode, admin.district or admin.raw_name
