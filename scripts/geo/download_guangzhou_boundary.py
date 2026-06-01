#!/usr/bin/env python3
"""Download and validate Guangzhou district boundary GeoJSON from DataV."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from netwatch.location.admin.boundary_tools import (
    BoundaryProbeResult,
    BoundaryProbeSingleResult,
    BoundaryValidationResult,
    probe_boundary,
    validate_boundary_geojson,
)


DATAV_GUANGZHOU_FULL_URL = "https://geo.datav.aliyun.com/areas_v3/bound/440100_full.json"
DEFAULT_OUTPUT = Path.home() / ".netwatch" / "geo" / "guangzhou_districts.geojson"
DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://datav.aliyun.com/tools/atlas",
    "Accept": "application/json,text/plain,*/*",
}
MANUAL_PROBES = [
    ("A 增城/永宁/凤凰城", 23.1532, 113.5813, "增城区", "440118"),
    ("B 学校/白云区", 23.379859, 113.435329, "白云区", "440111"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"default: {DEFAULT_OUTPUT}")
    parser.add_argument("--force", action="store_true", help="re-download even if output already exists")
    parser.add_argument("--probe-lat", type=float, help="browser WGS84 latitude to probe after validation")
    parser.add_argument("--probe-lon", type=float, help="browser WGS84 longitude to probe after validation")
    parser.add_argument(
        "--coord-system",
        choices=["auto", "wgs84", "gcj02"],
        default="auto",
        help="boundary coordinate system mode; default: auto",
    )
    args = parser.parse_args()

    output = args.output.expanduser()
    try:
        if args.force or not output.exists():
            download_boundary(output)
        else:
            print(f"Using existing file: {output}")
            print("Use --force to re-download.")

        validation = validate_boundary_geojson(output)
        print_validation(validation)
        print_manual_probe_examples()

        if (args.probe_lat is None) != (args.probe_lon is None):
            print("ERROR: --probe-lat and --probe-lon must be provided together.", file=sys.stderr)
            return 2
        if args.probe_lat is not None and args.probe_lon is not None:
            probe = probe_boundary(
                args.probe_lat,
                args.probe_lon,
                output,
                coord_system=args.coord_system,  # type: ignore[arg-type]
            )
            print_probe(probe)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def download_boundary(output: Path) -> None:
    """Download the DataV GeoJSON after validating the response shape."""
    print(f"Downloading DataV Guangzhou district boundary: {DATAV_GUANGZHOU_FULL_URL}")
    response = requests.get(DATAV_GUANGZHOU_FULL_URL, headers=DOWNLOAD_HEADERS, timeout=30)
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("downloaded response is not valid JSON") from exc
    _validate_download_payload(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")


def print_validation(result: BoundaryValidationResult) -> None:
    print("\nValidation")
    print(f"  path: {result.path}")
    print(f"  exists: {result.exists}")
    print(f"  file size: {result.file_size} bytes")
    print(f"  json type: {result.json_type}")
    print(f"  feature count: {result.feature_count}")
    print(f"  geometry type distribution: {result.geometry_type_distribution}")
    print(f"  property field coverage: {result.property_field_coverage}")
    print(f"  detected names: {', '.join(result.detected_names) or '-'}")
    print(f"  detected adcodes: {', '.join(result.detected_adcodes) or '-'}")
    print(f"  load result: {result.load_result}")
    if result.warnings:
        print("  warnings:")
        for warning in result.warnings:
            print(f"    - {warning}")
    else:
        print("  warnings: none")


def print_probe(result: BoundaryProbeResult) -> None:
    print("\nProbe")
    print(f"  raw browser latitude/longitude: {result.raw_latitude:.6f}, {result.raw_longitude:.6f}")
    print(f"  coordinate system mode: {result.coord_system_mode}")
    if result.coord_system_mode == "auto":
        print_single_probe("  WGS84 probe result", result.wgs84_result)
        print_single_probe("  GCJ-02 probe result", result.gcj02_result)
        print(f"  WGS84 and GCJ-02 results differ: {result.results_differ}")
    print_single_probe("  chosen result", result.chosen)
    if result.warnings:
        print("  warnings:")
        for warning in result.warnings:
            print(f"    - {warning}")


def print_single_probe(title: str, result: BoundaryProbeSingleResult | None) -> None:
    print(title + ":")
    if result is None:
        print("    matched: no")
        return
    print(f"    boundary query coordinate: {result.query_latitude:.6f}, {result.query_longitude:.6f} ({result.coord_system})")
    if result.coord_system == "gcj02":
        print("    boundary query note: GCJ-02 converted from browser WGS84")
    print(f"    matched: {'yes' if result.matched else 'no'}")
    admin = result.admin
    if admin is None:
        if result.error:
            print(f"    error: {result.error}")
        return
    print(f"    province/city/district/name: {admin.province or '-'} / {admin.city or '-'} / {admin.district or '-'} / {admin.raw_name or '-'}")
    print(f"    adcode: {admin.adcode or '-'}")
    print(f"    source: {admin.source}")
    print(f"    confidence: {admin.confidence}")
    print(f"    raw properties summary: {result.raw_properties}")


def print_manual_probe_examples() -> None:
    print("\nManual validation samples")
    for label, lat, lon, district, adcode in MANUAL_PROBES:
        print(f"  {label}: lat={lat}, lon={lon}, expected district={district}, expected adcode={adcode}")


def _validate_download_payload(data: Any) -> None:
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError("downloaded response is not a GeoJSON FeatureCollection")
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("downloaded FeatureCollection has no features")


if __name__ == "__main__":
    raise SystemExit(main())
