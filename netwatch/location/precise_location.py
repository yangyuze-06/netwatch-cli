"""Experimental precise offline location orchestration."""

from __future__ import annotations

from netwatch.device_location import DeviceLocationResult, run_browser_geolocation
from netwatch.location.china_admin_lookup import lookup_nearest_district
from netwatch.location.models import AdminLocationResult, BrowserLocationResult, PreciseLocationReport
from netwatch.location.nearby_roads import (
    RoadsDependencyError,
    find_nearby_roads,
    load_roads_dataset,
)
from netwatch.location.offline_boundary import (
    BoundaryDependencyError,
    load_boundary_dataset,
    locate_admin_by_point,
)


def build_precise_location_report(
    device_result: DeviceLocationResult,
    *,
    boundary_path: str | None = None,
    roads_path: str | None = None,
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

    _fill_admin_result(report, boundary_path=boundary_path)
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


def _fill_admin_result(report: PreciseLocationReport, *, boundary_path: str | None = None) -> None:
    assert report.browser is not None
    lat = report.browser.latitude
    lon = report.browser.longitude

    try:
        dataset = load_boundary_dataset(boundary_path)
        if dataset.is_sample:
            report.warnings.append(
                "当前行政区结果来自内置测试样例，不代表真实行政边界。"
                "请配置 NETWATCH_BOUNDARY_GEOJSON 后再使用精确行政区识别。"
            )
        admin = locate_admin_by_point(lat, lon, dataset)
        if admin is not None:
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
