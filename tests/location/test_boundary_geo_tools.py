"""Tests for Guangzhou boundary validation/probe helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from netwatch.location.admin.boundary_tools import probe_boundary, validate_boundary_geojson
from netwatch.location.admin.coord_transform import out_of_china, wgs84_to_gcj02

try:
    import shapely  # noqa: F401

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


def test_coord_transform_out_of_china() -> None:
    assert out_of_china(37.7749, -122.4194) is True
    assert out_of_china(23.1291, 113.2644) is False


def test_wgs84_to_gcj02_changes_guangzhou_coordinate_slightly() -> None:
    lat, lon = 23.1532, 113.5813
    gcj_lat, gcj_lon = wgs84_to_gcj02(lat, lon)

    assert abs(gcj_lat - lat) > 0.001
    assert abs(gcj_lon - lon) > 0.001
    assert abs(gcj_lat - lat) < 0.01
    assert abs(gcj_lon - lon) < 0.01


def test_validate_sample_boundary_loads() -> None:
    sample = Path("netwatch/location/data/boundaries/china_districts.sample.geojson")
    result = validate_boundary_geojson(sample)

    assert result.exists is True
    assert result.json_type == "FeatureCollection"
    assert result.feature_count == 2
    assert result.load_result == "ok"
    assert {"黄埔区", "增城区"} <= set(result.detected_names)


def test_validate_missing_boundary_friendly_failure(tmp_path: Path) -> None:
    result = validate_boundary_geojson(tmp_path / "missing.geojson")

    assert result.exists is False
    assert result.load_result == "missing"
    assert any("does not exist" in warning for warning in result.warnings)


def test_validate_malformed_json_friendly_failure(tmp_path: Path) -> None:
    path = tmp_path / "bad.geojson"
    path.write_text("{not json", encoding="utf-8")

    result = validate_boundary_geojson(path)

    assert result.exists is True
    assert result.load_result == "invalid_json"
    assert any("invalid JSON" in warning for warning in result.warnings)


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_boundary_probe_wgs84_and_gcj02_modes(tmp_path: Path) -> None:
    path = _write_probe_boundary(tmp_path)

    wgs84 = probe_boundary(23.1532, 113.5813, path, coord_system="wgs84")
    gcj02 = probe_boundary(23.1532, 113.5813, path, coord_system="gcj02")

    assert wgs84.chosen is not None
    assert wgs84.chosen.matched is True
    assert wgs84.chosen.admin is not None
    assert wgs84.chosen.admin.district == "黄埔区"
    assert gcj02.chosen is not None
    assert gcj02.chosen.matched is True
    assert gcj02.chosen.admin is not None
    assert gcj02.chosen.admin.district == "增城区"


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_boundary_probe_auto_compares_both_results(tmp_path: Path) -> None:
    path = _write_probe_boundary(tmp_path)

    result = probe_boundary(23.379859, 113.435329, path, coord_system="auto")

    assert result.wgs84_result is not None
    assert result.gcj02_result is not None
    assert result.chosen is result.gcj02_result
    assert result.results_differ is True
    assert result.wgs84_result.admin is not None
    assert result.gcj02_result.admin is not None
    assert result.wgs84_result.admin.district == "花都区"
    assert result.gcj02_result.admin.district == "白云区"
    assert any("coordinate system ambiguity" in warning for warning in result.warnings)


def _write_probe_boundary(tmp_path: Path) -> Path:
    path = tmp_path / "guangzhou-probe.geojson"
    data = {
        "type": "FeatureCollection",
        "features": [
            _feature("黄埔区", "440112", 113.55, 23.10, 113.585, 23.20),
            _feature("增城区", "440118", 113.585, 23.10, 113.72, 23.20),
            _feature("花都区", "440114", 113.42, 23.36, 113.438, 23.40),
            _feature("白云区", "440111", 113.438, 23.36, 113.46, 23.40),
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _feature(name: str, adcode: str, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> dict[str, object]:
    return {
        "type": "Feature",
        "properties": {
            "province": "广东省",
            "city": "广州市",
            "district": name,
            "name": name,
            "adcode": adcode,
            "level": "district",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat],
                ]
            ],
        },
    }
