#!/usr/bin/env python3
"""Run Guangzhou district boundary stress probes against a local GeoJSON file."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from netwatch.location.boundary_stress import (  # noqa: E402
    ProbePoint,
    is_whole_city_boundary,
    load_probe_points,
    run_boundary_stress,
    run_known_point_probes,
)
from netwatch.location.boundary_tools import probe_boundary, validate_boundary_geojson  # noqa: E402


DEFAULT_BOUNDARY = Path.home() / ".netwatch" / "geo" / "guangzhou_districts.geojson"
DEFAULT_POINTS = PROJECT_ROOT / "tests" / "fixtures" / "location" / "guangzhou_probe_points.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY, help=f"default: {DEFAULT_BOUNDARY}")
    parser.add_argument("--points", type=Path, default=DEFAULT_POINTS, help=f"default: {DEFAULT_POINTS}")
    parser.add_argument("--coord-system", choices=["auto", "wgs84", "gcj02"], default="auto")
    parser.add_argument("--grid-regression", action="store_true")
    parser.add_argument("--grid-step-m", type=int, default=50)
    parser.add_argument("--grid-radius-m", type=int, default=200)
    parser.add_argument("--json-report", type=Path)
    args = parser.parse_args()

    boundary = args.boundary.expanduser()
    points_path = args.points.expanduser()

    validation = validate_boundary_geojson(boundary)
    print_validation(validation)
    if validation.load_result != "ok":
        print("ERROR: boundary validation failed; refusing to run stress probes.", file=sys.stderr)
        return 1
    if is_whole_city_boundary(validation):
        print("ERROR: boundary is not a Guangzhou child-district boundary file.", file=sys.stderr)
        return 1

    points = load_probe_points(points_path)
    known_results = run_known_point_probes(boundary, points, coord_system=args.coord_system)  # type: ignore[arg-type]
    print_known_results(known_results)
    print_coord_compare(boundary, points)

    report = run_boundary_stress(
        boundary,
        coord_system=args.coord_system,  # type: ignore[arg-type]
        points_path=points_path,
    )
    print_representative_summary(report)
    print_boundary_warning_summary(report)

    grid_passed = True
    if args.grid_regression:
        grid_passed = print_grid_regression(boundary, points, args.grid_step_m, args.grid_radius_m, args.coord_system)

    if args.json_report:
        args.json_report.expanduser().write_text(
            json.dumps(_to_jsonable(report), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\nJSON report: {args.json_report.expanduser()}")

    if not report.passed or not grid_passed:
        print("ERROR: stress report failed.", file=sys.stderr)
        return 1
    return 0


def print_validation(validation: Any) -> None:
    print("Validation")
    print(f"  path: {validation.path}")
    print(f"  feature count: {validation.feature_count}")
    print(f"  geometry types: {validation.geometry_type_distribution}")
    print(f"  detected names: {', '.join(validation.detected_names) or '-'}")
    print(f"  detected adcodes: {', '.join(validation.detected_adcodes) or '-'}")
    print(f"  load result: {validation.load_result}")
    print(f"  warnings: {len(validation.warnings)}")
    for warning in validation.warnings:
        print(f"    - {warning}")


def print_known_results(results: list[Any]) -> None:
    print("\nKnown Regression Probes")
    for result in results:
        admin = result.probe.chosen.admin if result.probe.chosen and result.probe.chosen.admin else None
        district = admin.district if admin else "-"
        adcode = admin.adcode if admin else "-"
        status = "PASS" if result.passed else "FAIL"
        print(f"  {status} {result.point.label}: {district} / {adcode}")
        for warning in result.warnings:
            print(f"    warning: {warning}")


def print_coord_compare(boundary: Path, points: list[ProbePoint]) -> None:
    print("\nWGS84 vs GCJ-02 Compare")
    for point in points:
        wgs84 = probe_boundary(point.lat, point.lon, boundary, coord_system="wgs84")
        gcj02 = probe_boundary(point.lat, point.lon, boundary, coord_system="gcj02")
        w_admin = wgs84.chosen.admin if wgs84.chosen and wgs84.chosen.admin else None
        g_admin = gcj02.chosen.admin if gcj02.chosen and gcj02.chosen.admin else None
        differ = (w_admin.adcode if w_admin else None) != (g_admin.adcode if g_admin else None)
        suffix = " coordinate_system_difference" if differ else ""
        print(f"  {point.label}: WGS84={_admin_label(w_admin)} GCJ-02={_admin_label(g_admin)}{suffix}")


def print_representative_summary(report: Any) -> None:
    print("\nRepresentative Point Summary")
    passed = [result for result in report.representative_results if result.passed]
    print(f"  passed: {len(passed)} / {len(report.representative_results)}")
    for result in report.representative_results:
        admin = result.admin
        point = result.point
        status = "PASS" if result.passed else "FAIL"
        print(f"  {status} {point.district or '-'} / {point.adcode or '-'} -> {_admin_label(admin)}")


def print_boundary_warning_summary(report: Any) -> None:
    boundary_warnings = [warning for result in report.boundary_results for warning in result.warnings]
    epsilon_warnings = [warning for result in report.epsilon_results for warning in result.warnings]
    print("\nBoundary / Epsilon Warning Summary")
    print(f"  boundary probes: {len(report.boundary_results)}, warnings: {len(boundary_warnings)}")
    print(f"  epsilon probes: {len(report.epsilon_results)}, warnings: {len(epsilon_warnings)}")
    for warning in sorted(set(boundary_warnings + epsilon_warnings)):
        print(f"    - {warning}")


def print_grid_regression(
    boundary: Path,
    points: list[ProbePoint],
    step_m: int,
    radius_m: int,
    coord_system: str,
) -> bool:
    print("\nRegression Grid")
    offsets = list(range(-radius_m, radius_m + 1, step_m))
    all_centers_ok = True
    for point in points:
        print(f"  {point.label}:")
        center_ok = False
        for north_m in offsets:
            for east_m in offsets:
                shifted = _offset_probe_point(point, north_m=north_m, east_m=east_m)
                probe = probe_boundary(shifted.lat, shifted.lon, boundary, coord_system=coord_system)  # type: ignore[arg-type]
                admin = probe.chosen.admin if probe.chosen and probe.chosen.admin else None
                marker = "center" if north_m == 0 and east_m == 0 else "grid"
                if marker == "center":
                    center_ok = admin is not None and admin.district == point.expected_district and admin.adcode == point.expected_adcode
                print(f"    {marker} N{north_m:+}m E{east_m:+}m -> {_admin_label(admin)}")
        if not center_ok:
            all_centers_ok = False
            print(f"    ERROR: center point failed expected {point.expected_district} / {point.expected_adcode}")
    return all_centers_ok


def _offset_probe_point(point: ProbePoint, *, north_m: float, east_m: float) -> ProbePoint:
    lat = point.lat + north_m / 111320.0
    cos_lat = max(math.cos(math.radians(point.lat)), 0.000001)
    lon = point.lon + east_m / (111320.0 * cos_lat)
    return ProbePoint(
        label=point.label,
        lat=lat,
        lon=lon,
        expected_district=point.expected_district,
        expected_adcode=point.expected_adcode,
        case_type=point.case_type,
        notes=point.notes,
    )


def _admin_label(admin: Any) -> str:
    if admin is None:
        return "- / -"
    return f"{admin.district or admin.raw_name or '-'} / {admin.adcode or '-'}"


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
