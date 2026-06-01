"""Experimental offline administrative boundary point-in-polygon lookup."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from netwatch.location.models import AdminLocationResult


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_BOUNDARY_GEOJSON = DATA_DIR / "boundaries" / "china_districts.sample.geojson"
DEFAULT_GUANGZHOU_BOUNDARY_GEOJSON = Path.home() / ".netwatch" / "geo" / "guangzhou_districts.geojson"
BOUNDARY_ENV_VAR = "NETWATCH_BOUNDARY_GEOJSON"
USE_SAMPLE_GEO_ENV_VAR = "NETWATCH_USE_SAMPLE_GEO"


@dataclass
class BoundaryFeature:
    """A geometry and its source properties."""

    geometry: Any
    properties: dict[str, Any]


@dataclass
class BoundaryDataset:
    """Loaded boundary dataset with a spatial index."""

    path: Path
    features: list[BoundaryFeature]
    tree: Any
    source: str
    is_sample: bool = False


class BoundaryDependencyError(RuntimeError):
    """Raised when optional geometry dependencies are not installed."""


def get_boundary_geojson_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Return the configured boundary dataset path."""
    if path:
        return Path(path).expanduser()
    configured = os.environ.get(BOUNDARY_ENV_VAR)
    if configured:
        return Path(configured).expanduser()
    if _use_sample_geo():
        return DEFAULT_BOUNDARY_GEOJSON
    if DEFAULT_GUANGZHOU_BOUNDARY_GEOJSON.exists():
        return DEFAULT_GUANGZHOU_BOUNDARY_GEOJSON
    return DEFAULT_BOUNDARY_GEOJSON


def load_boundary_dataset(path: str | os.PathLike[str] | None = None) -> BoundaryDataset:
    """Load a Polygon/MultiPolygon GeoJSON FeatureCollection into an STRtree."""
    if (
        path is None
        and not os.environ.get(BOUNDARY_ENV_VAR)
        and not DEFAULT_GUANGZHOU_BOUNDARY_GEOJSON.exists()
        and not _use_sample_geo()
    ):
        raise FileNotFoundError(
            "boundary GeoJSON not configured; set NETWATCH_BOUNDARY_GEOJSON for real data "
            f"or run scripts/geo/download_guangzhou_boundary.py --force to create {DEFAULT_GUANGZHOU_BOUNDARY_GEOJSON}"
        )

    try:
        from shapely import STRtree
        from shapely.geometry import shape
    except ImportError as exc:
        raise BoundaryDependencyError(
            "precise offline boundary requires shapely; please install netwatch-cli[geo] or pip install shapely"
        ) from exc

    dataset_path = get_boundary_geojson_path(path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"boundary GeoJSON not found: {dataset_path}")

    with dataset_path.open(encoding="utf-8") as f:
        data = json.load(f)

    raw_features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(raw_features, list):
        raise ValueError("boundary GeoJSON must be a FeatureCollection")

    features: list[BoundaryFeature] = []
    geoms: list[Any] = []
    for item in raw_features:
        if not isinstance(item, dict):
            continue
        geometry_data = item.get("geometry")
        if not isinstance(geometry_data, dict):
            continue
        geom = shape(geometry_data)
        if geom.is_empty or geom.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        props = item.get("properties") or {}
        props = props if isinstance(props, dict) else {}
        features.append(BoundaryFeature(geometry=geom, properties=props))
        geoms.append(geom)

    if not features:
        raise ValueError("boundary GeoJSON contains no Polygon or MultiPolygon features")

    is_sample = dataset_path.resolve() == DEFAULT_BOUNDARY_GEOJSON.resolve()
    return BoundaryDataset(
        path=dataset_path,
        features=features,
        tree=STRtree(geoms),
        source="offline_boundary_sample" if is_sample else "offline_boundary",
        is_sample=is_sample,
    )


def locate_admin_by_point(
    lat: float, lon: float, dataset: BoundaryDataset
) -> AdminLocationResult | None:
    """Locate an administrative region by point-in-polygon."""
    try:
        from shapely.geometry import Point
    except ImportError as exc:
        raise BoundaryDependencyError(
            "precise offline boundary requires shapely; please install netwatch-cli[geo] or pip install shapely"
        ) from exc

    point = Point(lon, lat)
    candidate_indices = dataset.tree.query(point)
    matches: list[tuple[float, BoundaryFeature]] = []

    for raw_idx in candidate_indices:
        idx = int(raw_idx)
        feature = dataset.features[idx]
        if feature.geometry.covers(point):
            matches.append((float(feature.geometry.area), feature))

    if not matches:
        return None

    _, best = min(matches, key=lambda item: (_level_rank(item[1].properties), item[0]))
    result = _admin_result_from_properties(best.properties, dataset.source, is_sample=dataset.is_sample)
    result.boundary_match_count = len(matches)
    if len(matches) > 1:
        result.boundary_warnings.append("multiple administrative polygons cover this point")
        if result.confidence == "high":
            result.confidence = "ambiguous_boundary"

    distance_m = _distance_to_boundary_m(point, best.geometry)
    result.boundary_distance_m = distance_m
    if distance_m is not None and distance_m < 100.0:
        result.boundary_warnings.append(
            "point is close to district boundary; coordinate system or browser accuracy may affect result"
        )
    return result


def _level_rank(props: dict[str, Any]) -> int:
    """Return a sort rank where more specific levels win."""
    level = str(props.get("level") or "").lower()
    if level in {"district", "county", "区县", "区", "县"}:
        return 0
    if props.get("district"):
        return 0
    if level in {"city", "prefecture", "市"}:
        return 1
    if props.get("city"):
        return 1
    if level in {"province", "省"}:
        return 2
    return 3


def _admin_result_from_properties(props: dict[str, Any], source: str, *, is_sample: bool) -> AdminLocationResult:
    raw_name = _first_text(props, "fullname", "full_name", "name")
    district = _first_text(props, "district", "county")
    name = _first_text(props, "name")
    adcode = _first_text(props, "adcode", "code")
    province = _first_text(props, "province")
    city = _first_text(props, "city")
    level = str(props.get("level") or "").lower()
    if not district and level in {"district", "county"}:
        district = name
    if adcode and adcode.startswith("4401"):
        province = province or "广东省"
        city = city or "广州市"

    return AdminLocationResult(
        country=_first_text(props, "country") or "CN",
        province=province,
        city=city,
        district=district,
        adcode=adcode,
        confidence="sample_only" if is_sample else "high",
        source=source,
        raw_name=raw_name,
        raw_properties=dict(props),
    )


def _use_sample_geo() -> bool:
    return os.environ.get(USE_SAMPLE_GEO_ENV_VAR) == "1"


def _first_text(props: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = props.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _distance_to_boundary_m(point: Any, geometry: Any) -> float | None:
    try:
        from shapely.ops import nearest_points
    except ImportError:
        return None
    try:
        nearest = nearest_points(point, geometry.boundary)[1]
    except Exception:
        return None
    return _approx_distance_m(point.y, point.x, nearest.y, nearest.x)


def _approx_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    avg_lat = math.radians((lat1 + lat2) / 2.0)
    dy = (lat1 - lat2) * 111320.0
    dx = (lon1 - lon2) * 111320.0 * math.cos(avg_lat)
    return math.hypot(dx, dy)
