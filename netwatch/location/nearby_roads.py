"""Experimental offline nearby road lookup from GeoJSON."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from netwatch.location.models import NearbyRoadResult


DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_ROADS_GEOJSON = DATA_DIR / "roads" / "roads.sample.geojson"
ROADS_ENV_VAR = "NETWATCH_ROADS_GEOJSON"
USE_SAMPLE_GEO_ENV_VAR = "NETWATCH_USE_SAMPLE_GEO"


@dataclass
class RoadFeature:
    """A road geometry and its properties."""

    geometry: Any
    properties: dict[str, Any]


@dataclass
class RoadsDataset:
    """Loaded roads dataset with a spatial index."""

    path: Path
    features: list[RoadFeature]
    tree: Any
    source: str
    is_sample: bool = False


class RoadsDependencyError(RuntimeError):
    """Raised when optional geometry dependencies are not installed."""


def get_roads_geojson_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Return the configured roads dataset path."""
    if path:
        return Path(path).expanduser()
    configured = os.environ.get(ROADS_ENV_VAR)
    if configured:
        return Path(configured).expanduser()
    if _use_sample_geo():
        return DEFAULT_ROADS_GEOJSON
    return DEFAULT_ROADS_GEOJSON


def load_roads_dataset(path: str | os.PathLike[str] | None = None) -> RoadsDataset:
    """Load LineString/MultiLineString roads from a GeoJSON FeatureCollection."""
    if path is None and not os.environ.get(ROADS_ENV_VAR) and not _use_sample_geo():
        raise FileNotFoundError(
            "roads GeoJSON not configured; set NETWATCH_ROADS_GEOJSON for real data "
            "or NETWATCH_USE_SAMPLE_GEO=1 for demo sample data"
        )

    try:
        from shapely import STRtree
        from shapely.geometry import shape
    except ImportError as exc:
        raise RoadsDependencyError(
            "offline nearby roads requires shapely; please install netwatch-cli[geo] or pip install shapely"
        ) from exc

    dataset_path = get_roads_geojson_path(path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"roads GeoJSON not found: {dataset_path}")

    with dataset_path.open(encoding="utf-8") as f:
        data = json.load(f)

    raw_features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(raw_features, list):
        raise ValueError("roads GeoJSON must be a FeatureCollection")

    features: list[RoadFeature] = []
    geoms: list[Any] = []
    for item in raw_features:
        if not isinstance(item, dict):
            continue
        geometry_data = item.get("geometry")
        if not isinstance(geometry_data, dict):
            continue
        geom = shape(geometry_data)
        if geom.is_empty or geom.geom_type not in {"LineString", "MultiLineString"}:
            continue
        props = item.get("properties") or {}
        props = props if isinstance(props, dict) else {}
        features.append(RoadFeature(geometry=geom, properties=props))
        geoms.append(geom)

    if not features:
        raise ValueError("roads GeoJSON contains no LineString or MultiLineString features")

    is_sample = dataset_path.resolve() == DEFAULT_ROADS_GEOJSON.resolve()
    return RoadsDataset(
        path=dataset_path,
        features=features,
        tree=STRtree(geoms),
        source="offline_roads_sample" if is_sample else "offline_roads",
        is_sample=is_sample,
    )


def find_nearby_roads(
    lat: float,
    lon: float,
    dataset: RoadsDataset,
    radius_m: float = 300.0,
    limit: int = 3,
) -> list[NearbyRoadResult]:
    """Return nearest roads within radius_m using local equirectangular distance."""
    try:
        from shapely.geometry import Point
    except ImportError as exc:
        raise RoadsDependencyError(
            "offline nearby roads requires shapely; please install netwatch-cli[geo] or pip install shapely"
        ) from exc

    point = Point(lon, lat)
    lat_degree_m, lon_degree_m = _degree_lengths_m(lat)
    radius_deg = radius_m / max(1.0, min(lat_degree_m, lon_degree_m))
    candidate_indices = dataset.tree.query(point.buffer(radius_deg))

    results: list[NearbyRoadResult] = []
    for raw_idx in candidate_indices:
        feature = dataset.features[int(raw_idx)]
        distance_m = _point_to_geometry_distance_m(lon, lat, feature.geometry)
        if distance_m <= radius_m:
            props = feature.properties
            results.append(
                NearbyRoadResult(
                    name=_first_text(props, "name"),
                    highway=_first_text(props, "highway", "type"),
                    ref=_first_text(props, "ref", "osm_id"),
                    distance_m=round(distance_m, 1),
                    source=dataset.source,
                )
            )

    return sorted(results, key=lambda item: item.distance_m if item.distance_m is not None else float("inf"))[:limit]


def _point_to_geometry_distance_m(lon: float, lat: float, geometry: Any) -> float:
    distances: list[float] = []
    if geometry.geom_type == "LineString":
        distances.append(_point_to_line_distance_m(lon, lat, list(geometry.coords)))
    elif geometry.geom_type == "MultiLineString":
        for line in geometry.geoms:
            distances.append(_point_to_line_distance_m(lon, lat, list(line.coords)))
    return min(distances) if distances else float("inf")


def _point_to_line_distance_m(lon: float, lat: float, coords: list[tuple[float, float]]) -> float:
    if len(coords) < 2:
        return float("inf")

    lat_degree_m, lon_degree_m = _degree_lengths_m(lat)

    def project(coord_lon: float, coord_lat: float) -> tuple[float, float]:
        return ((coord_lon - lon) * lon_degree_m, (coord_lat - lat) * lat_degree_m)

    px, py = 0.0, 0.0
    best = float("inf")
    for start, end in zip(coords, coords[1:]):
        ax, ay = project(float(start[0]), float(start[1]))
        bx, by = project(float(end[0]), float(end[1]))
        best = min(best, _point_to_segment_distance(px, py, ax, ay, bx, by))
    return best


def _point_to_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    nearest_x = ax + t * dx
    nearest_y = ay + t * dy
    return math.hypot(px - nearest_x, py - nearest_y)


def _degree_lengths_m(lat: float) -> tuple[float, float]:
    lat_degree_m = 111_320.0
    lon_degree_m = 111_320.0 * max(0.01, math.cos(math.radians(lat)))
    return lat_degree_m, lon_degree_m


def _first_text(props: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = props.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _use_sample_geo() -> bool:
    return os.environ.get(USE_SAMPLE_GEO_ENV_VAR) == "1"
