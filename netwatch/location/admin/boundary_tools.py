"""Validation and probe helpers for offline administrative boundary GeoJSON."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from netwatch.location.admin.coord_transform import BoundaryCoordSystem, wgs84_to_gcj02
from netwatch.location.models import AdminLocationResult
from netwatch.location.admin.offline_boundary import load_boundary_dataset, locate_admin_by_point


GUANGZHOU_EXPECTED_NAMES = {
    "越秀区",
    "荔湾区",
    "海珠区",
    "天河区",
    "白云区",
    "黄埔区",
    "番禺区",
    "花都区",
    "南沙区",
    "从化区",
    "增城区",
}
GUANGZHOU_EXPECTED_ADCODES = {
    "440111": "白云区",
    "440114": "花都区",
    "440112": "黄埔区",
    "440118": "增城区",
}


@dataclass
class BoundaryValidationResult:
    path: Path
    exists: bool
    file_size: int = 0
    json_type: str | None = None
    feature_count: int = 0
    geometry_type_distribution: dict[str, int] = field(default_factory=dict)
    property_field_coverage: dict[str, int] = field(default_factory=dict)
    detected_names: list[str] = field(default_factory=list)
    detected_adcodes: list[str] = field(default_factory=list)
    load_result: str = "not_loaded"
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exists and self.json_type == "FeatureCollection" and self.feature_count > 0


@dataclass
class BoundaryProbeSingleResult:
    coord_system: str
    query_latitude: float
    query_longitude: float
    matched: bool
    admin: AdminLocationResult | None = None
    raw_properties: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class BoundaryProbeResult:
    raw_latitude: float
    raw_longitude: float
    coord_system_mode: BoundaryCoordSystem
    chosen: BoundaryProbeSingleResult | None = None
    wgs84_result: BoundaryProbeSingleResult | None = None
    gcj02_result: BoundaryProbeSingleResult | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def results_differ(self) -> bool:
        if self.wgs84_result is None or self.gcj02_result is None:
            return False
        return _result_identity(self.wgs84_result) != _result_identity(self.gcj02_result)


def validate_boundary_geojson(path: str | Path) -> BoundaryValidationResult:
    """Validate a Guangzhou district boundary GeoJSON without mutating it."""
    boundary_path = Path(path).expanduser()
    result = BoundaryValidationResult(path=boundary_path, exists=boundary_path.exists())
    if not result.exists:
        result.warnings.append(f"file does not exist: {boundary_path}")
        result.load_result = "missing"
        return result

    result.file_size = boundary_path.stat().st_size
    if result.file_size <= 0:
        result.warnings.append("file is empty")
        result.load_result = "empty"
        return result

    try:
        data = json.loads(boundary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result.warnings.append(f"invalid JSON: {exc}")
        result.load_result = "invalid_json"
        return result

    result.json_type = str(data.get("type")) if isinstance(data, dict) else type(data).__name__
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        result.warnings.append("GeoJSON root type is not FeatureCollection")
        result.load_result = "invalid_type"
        return result

    features = data.get("features")
    if not isinstance(features, list):
        result.warnings.append("FeatureCollection.features is not a list")
        result.load_result = "invalid_features"
        return result

    result.feature_count = len(features)
    geom_counter: Counter[str] = Counter()
    field_counter: Counter[str] = Counter()
    names: set[str] = set()
    adcodes: set[str] = set()

    for feature in features:
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        if isinstance(geometry, dict):
            geom_counter[str(geometry.get("type") or "")] += 1
        props = feature.get("properties")
        if not isinstance(props, dict):
            continue
        for field in props:
            field_counter[str(field)] += 1
        name = _first_text(props, "name", "fullname", "full_name", "district", "county")
        adcode = _first_text(props, "adcode", "code")
        if name:
            names.add(name)
        if adcode:
            adcodes.add(adcode)

    result.geometry_type_distribution = dict(sorted(geom_counter.items()))
    result.property_field_coverage = dict(sorted(field_counter.items()))
    result.detected_names = sorted(names)
    result.detected_adcodes = sorted(adcodes)

    if not 8 <= result.feature_count <= 20:
        result.warnings.append(f"feature count looks unusual for Guangzhou districts: {result.feature_count}")
    if not (set(result.geometry_type_distribution) & {"Polygon", "MultiPolygon"}):
        result.warnings.append("no Polygon/MultiPolygon geometry detected")
    if not ({"name", "fullname", "full_name", "district", "county"} & set(result.property_field_coverage)):
        result.warnings.append("properties do not expose a recognizable name field")
    if not ({"adcode", "code"} & set(result.property_field_coverage)):
        result.warnings.append("properties do not expose a recognizable adcode/code field")
    if result.feature_count == 1:
        result.warnings.append(
            "boundary appears to contain one whole-city polygon, not Guangzhou child district boundaries"
        )

    missing_names = GUANGZHOU_EXPECTED_NAMES - names
    if missing_names:
        result.warnings.append("missing expected Guangzhou district names: " + ", ".join(sorted(missing_names)))
    missing_adcodes = set(GUANGZHOU_EXPECTED_ADCODES) - adcodes
    if missing_adcodes:
        pairs = [f"{code} {GUANGZHOU_EXPECTED_ADCODES[code]}" for code in sorted(missing_adcodes)]
        result.warnings.append("missing expected Guangzhou adcodes: " + ", ".join(pairs))

    try:
        load_boundary_dataset(boundary_path)
    except Exception as exc:
        result.load_result = f"failed: {exc}"
        result.warnings.append(f"boundary loader failed: {exc}")
    else:
        result.load_result = "ok"
    return result


def probe_boundary(
    lat: float,
    lon: float,
    path: str | Path,
    *,
    coord_system: BoundaryCoordSystem = "auto",
) -> BoundaryProbeResult:
    """Probe a boundary file with browser WGS84 coordinates."""
    dataset = load_boundary_dataset(path)
    result = BoundaryProbeResult(raw_latitude=lat, raw_longitude=lon, coord_system_mode=coord_system)

    if coord_system == "wgs84":
        result.chosen = _probe_single(dataset, lat, lon, "wgs84")
        result.warnings.extend(result.chosen.warnings)
        return result
    if coord_system == "gcj02":
        query_lat, query_lon = wgs84_to_gcj02(lat, lon)
        result.chosen = _probe_single(dataset, query_lat, query_lon, "gcj02")
        result.warnings.extend(result.chosen.warnings)
        return result
    if coord_system != "auto":
        raise ValueError(f"unsupported boundary coordinate system: {coord_system}")

    result.wgs84_result = _probe_single(dataset, lat, lon, "wgs84")
    gcj_lat, gcj_lon = wgs84_to_gcj02(lat, lon)
    result.gcj02_result = _probe_single(dataset, gcj_lat, gcj_lon, "gcj02")
    result.chosen = result.gcj02_result
    if result.results_differ:
        result.warnings.append(
            "coordinate system ambiguity: WGS84 and GCJ-02 boundary probes returned different results; "
            "using GCJ-02 because DataV/Amap-style boundary data is likely GCJ-02"
        )
    else:
        result.warnings.append("auto mode used GCJ-02 conversion for DataV/Amap-style boundary data")
    for single in (result.wgs84_result, result.gcj02_result):
        if single is not None:
            result.warnings.extend(single.warnings)
    return result


def summarize_properties(props: dict[str, Any], *, limit: int = 10) -> dict[str, Any]:
    """Return a compact stable property summary for CLI/script output."""
    preferred = ["name", "fullname", "full_name", "adcode", "code", "level", "province", "city", "district"]
    summary: dict[str, Any] = {}
    for key in preferred:
        if key in props:
            summary[key] = props[key]
    for key in sorted(props):
        if key not in summary:
            summary[key] = props[key]
        if len(summary) >= limit:
            break
    return summary


def _probe_single(dataset: Any, lat: float, lon: float, coord_system: str) -> BoundaryProbeSingleResult:
    admin = locate_admin_by_point(lat, lon, dataset)
    props = getattr(admin, "raw_properties", None) if admin is not None else None
    warnings = getattr(admin, "boundary_warnings", []) if admin is not None else []
    return BoundaryProbeSingleResult(
        coord_system=coord_system,
        query_latitude=lat,
        query_longitude=lon,
        matched=admin is not None,
        admin=admin,
        raw_properties=summarize_properties(props) if isinstance(props, dict) else {},
        warnings=list(warnings),
    )


def _result_identity(result: BoundaryProbeSingleResult) -> tuple[str | None, str | None, bool]:
    admin = result.admin
    if admin is None:
        return None, None, result.matched
    return admin.adcode, admin.district or admin.raw_name, result.matched


def _first_text(props: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = props.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
