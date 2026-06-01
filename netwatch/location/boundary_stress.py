"""Stress-test helpers for Guangzhou district boundary datasets."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from netwatch.location.boundary_tools import (
    BoundaryProbeResult,
    BoundaryValidationResult,
    probe_boundary,
    validate_boundary_geojson,
)
from netwatch.location.coord_transform import BoundaryCoordSystem
from netwatch.location.models import AdminLocationResult
from netwatch.location.offline_boundary import BoundaryDataset, load_boundary_dataset, locate_admin_by_point


@dataclass
class ProbePoint:
    label: str
    lat: float
    lon: float
    expected_district: str | None = None
    expected_adcode: str | None = None
    case_type: str = "exploratory"
    notes: str = ""


@dataclass
class KnownPointProbeResult:
    point: ProbePoint
    probe: BoundaryProbeResult
    passed: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class GeneratedPoint:
    label: str
    district: str | None
    adcode: str | None
    lat: float
    lon: float
    source: str


@dataclass
class GeneratedBoundaryPoint(GeneratedPoint):
    point_kind: str = "boundary"


@dataclass
class OffsetPoint:
    label: str
    origin_label: str
    direction: str
    meters: float
    lat: float
    lon: float


@dataclass
class GeneratedProbeResult:
    point: GeneratedPoint | GeneratedBoundaryPoint | OffsetPoint
    admin: AdminLocationResult | None
    passed: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class StressReport:
    boundary_path: Path
    coord_system: BoundaryCoordSystem
    validation: BoundaryValidationResult
    known_results: list[KnownPointProbeResult] = field(default_factory=list)
    representative_results: list[GeneratedProbeResult] = field(default_factory=list)
    boundary_results: list[GeneratedProbeResult] = field(default_factory=list)
    epsilon_results: list[GeneratedProbeResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.validation.load_result == "ok"
            and not _has_whole_city_warning(self.validation)
            and all(result.passed for result in self.known_results)
            and all(result.passed for result in self.representative_results)
            and all(result.passed for result in self.boundary_results)
            and all(result.passed for result in self.epsilon_results)
        )


def load_probe_points(csv_path: str | Path) -> list[ProbePoint]:
    """Load fixed probe points from a CSV fixture."""
    path = Path(csv_path)
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    points: list[ProbePoint] = []
    for row in rows:
        label = (row.get("label") or "").strip()
        if not label:
            continue
        points.append(
            ProbePoint(
                label=label,
                lat=float(str(row.get("lat") or "").strip()),
                lon=float(str(row.get("lon") or "").strip()),
                expected_district=_blank_to_none(row.get("expected_district")),
                expected_adcode=_blank_to_none(row.get("expected_adcode")),
                case_type=(row.get("case_type") or "exploratory").strip() or "exploratory",
                notes=(row.get("notes") or "").strip(),
            )
        )
    return points


def run_known_point_probes(
    boundary_path: str | Path,
    points: Iterable[ProbePoint],
    coord_system: BoundaryCoordSystem = "auto",
) -> list[KnownPointProbeResult]:
    """Probe fixed browser WGS84 points and assert known regression expectations."""
    results: list[KnownPointProbeResult] = []
    for point in points:
        probe = probe_boundary(point.lat, point.lon, boundary_path, coord_system=coord_system)
        admin = probe.chosen.admin if probe.chosen and probe.chosen.admin else None
        warnings = list(probe.warnings)
        passed = True
        if point.expected_district:
            passed = passed and admin is not None and admin.district == point.expected_district
        if point.expected_adcode:
            passed = passed and admin is not None and admin.adcode == point.expected_adcode
        if not passed:
            warnings.append(
                f"expected {point.expected_district or '-'} / {point.expected_adcode or '-'} "
                f"but got {_admin_label(admin)}"
            )
        results.append(KnownPointProbeResult(point=point, probe=probe, passed=passed, warnings=warnings))
    return results


def generate_representative_points(dataset: BoundaryDataset) -> list[GeneratedPoint]:
    """Generate one stable interior representative point for each district geometry."""
    points: list[GeneratedPoint] = []
    for idx, feature in enumerate(dataset.features):
        rep = feature.geometry.representative_point()
        district = _district_name(feature.properties)
        adcode = _adcode(feature.properties)
        points.append(
            GeneratedPoint(
                label=f"representative_{adcode or idx}",
                district=district,
                adcode=adcode,
                lat=float(rep.y),
                lon=float(rep.x),
                source="representative_point",
            )
        )
    return points


def generate_boundary_points(
    dataset: BoundaryDataset, max_points_per_district: int = 5
) -> list[GeneratedBoundaryPoint]:
    """Sample a few exterior vertices/midpoints from each district boundary."""
    generated: list[GeneratedBoundaryPoint] = []
    for feature_idx, feature in enumerate(dataset.features):
        district = _district_name(feature.properties)
        adcode = _adcode(feature.properties)
        count = 0
        for ring in _exterior_rings(feature.geometry):
            coords = list(ring.coords)
            if len(coords) < 2:
                continue
            sample_indices = _sample_indices(len(coords) - 1, max_points_per_district)
            for coord_idx in sample_indices:
                if count >= max_points_per_district:
                    break
                lon, lat = coords[coord_idx]
                generated.append(
                    GeneratedBoundaryPoint(
                        label=f"boundary_vertex_{adcode or feature_idx}_{count}",
                        district=district,
                        adcode=adcode,
                        lat=float(lat),
                        lon=float(lon),
                        source="boundary_vertex",
                        point_kind="vertex",
                    )
                )
                count += 1
                if count >= max_points_per_district:
                    break
                next_lon, next_lat = coords[(coord_idx + 1) % (len(coords) - 1)]
                generated.append(
                    GeneratedBoundaryPoint(
                        label=f"boundary_midpoint_{adcode or feature_idx}_{count}",
                        district=district,
                        adcode=adcode,
                        lat=float((lat + next_lat) / 2.0),
                        lon=float((lon + next_lon) / 2.0),
                        source="boundary_midpoint",
                        point_kind="midpoint",
                    )
                )
                count += 1
            if count >= max_points_per_district:
                break
    return generated


def generate_epsilon_points_around(
    point: Any, meters: Iterable[float] = (1, 10, 50, 100)
) -> list[OffsetPoint]:
    """Generate north/east/south/west meter offsets around a point."""
    lat, lon, label = _point_lat_lon_label(point)
    offsets: list[OffsetPoint] = []
    for distance_m in meters:
        dlat = distance_m / 111320.0
        cos_lat = max(math.cos(math.radians(lat)), 0.000001)
        dlon = distance_m / (111320.0 * cos_lat)
        for direction, off_lat, off_lon in (
            ("north", lat + dlat, lon),
            ("east", lat, lon + dlon),
            ("south", lat - dlat, lon),
            ("west", lat, lon - dlon),
        ):
            offsets.append(
                OffsetPoint(
                    label=f"{label}_{direction}_{int(distance_m)}m",
                    origin_label=label,
                    direction=direction,
                    meters=float(distance_m),
                    lat=off_lat,
                    lon=off_lon,
                )
            )
    return offsets


def run_boundary_stress(
    boundary_path: str | Path,
    coord_system: BoundaryCoordSystem = "auto",
    *,
    points_path: str | Path | None = None,
) -> StressReport:
    """Run a compact non-network stress report for a Guangzhou district boundary."""
    path = Path(boundary_path).expanduser()
    validation = validate_boundary_geojson(path)
    report = StressReport(boundary_path=path, coord_system=coord_system, validation=validation)
    if validation.load_result != "ok":
        report.warnings.append("boundary validation failed; stress probes were not executed")
        return report
    if _has_whole_city_warning(validation):
        report.warnings.append("boundary appears to be whole-city data, not precise district child boundaries")
        return report

    dataset = load_boundary_dataset(path)
    if points_path is not None:
        points = load_probe_points(points_path)
        report.known_results = run_known_point_probes(path, points, coord_system=coord_system)

    representative_points = generate_representative_points(dataset)
    report.representative_results = [
        _direct_probe_generated_point(dataset, point, expected_adcode=point.adcode) for point in representative_points
    ]

    boundary_points = generate_boundary_points(dataset)
    report.boundary_results = [_direct_probe_generated_point(dataset, point) for point in boundary_points]
    if boundary_points:
        epsilon_points: list[OffsetPoint] = []
        for point in boundary_points[: min(5, len(boundary_points))]:
            epsilon_points.extend(generate_epsilon_points_around(point, meters=(1, 10, 50, 100)))
        report.epsilon_results = [_direct_probe_generated_point(dataset, point) for point in epsilon_points]
    return report


def is_whole_city_boundary(validation: BoundaryValidationResult) -> bool:
    """Return True when validation indicates a city-level file rather than child districts."""
    return _has_whole_city_warning(validation)


def _direct_probe_generated_point(
    dataset: BoundaryDataset,
    point: GeneratedPoint | GeneratedBoundaryPoint | OffsetPoint,
    *,
    expected_adcode: str | None = None,
) -> GeneratedProbeResult:
    admin = locate_admin_by_point(point.lat, point.lon, dataset)
    warnings = list(admin.boundary_warnings) if admin else []
    passed = True
    if expected_adcode:
        passed = passed and admin is not None and admin.adcode == expected_adcode
    return GeneratedProbeResult(point=point, admin=admin, passed=passed, warnings=warnings)


def _admin_label(admin: AdminLocationResult | None) -> str:
    if admin is None:
        return "no match"
    return f"{admin.district or admin.raw_name or '-'} / {admin.adcode or '-'}"


def _district_name(props: dict[str, Any]) -> str | None:
    return _first_text(props, "district", "county", "name", "fullname", "full_name")


def _adcode(props: dict[str, Any]) -> str | None:
    return _first_text(props, "adcode", "code")


def _first_text(props: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = props.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _exterior_rings(geometry: Any) -> list[Any]:
    if geometry.geom_type == "Polygon":
        return [geometry.exterior]
    if geometry.geom_type == "MultiPolygon":
        return [poly.exterior for poly in geometry.geoms]
    return []


def _sample_indices(count: int, limit: int) -> list[int]:
    if count <= 0:
        return []
    if count <= limit:
        return list(range(count))
    step = max(count // limit, 1)
    return [min(idx * step, count - 1) for idx in range(limit)]


def _point_lat_lon_label(point: Any) -> tuple[float, float, str]:
    if isinstance(point, tuple):
        lat, lon = point[:2]
        return float(lat), float(lon), "point"
    lat = getattr(point, "lat")
    lon = getattr(point, "lon")
    label = str(getattr(point, "label", "point"))
    return float(lat), float(lon), label


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _has_whole_city_warning(validation: BoundaryValidationResult) -> bool:
    return any("whole-city" in warning for warning in validation.warnings)
