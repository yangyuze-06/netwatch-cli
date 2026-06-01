"""Tests for Guangzhou boundary stress helpers."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from netwatch.location.admin.boundary_stress import (
    generate_boundary_points,
    generate_epsilon_points_around,
    generate_representative_points,
    is_whole_city_boundary,
    load_probe_points,
    run_boundary_stress,
    run_known_point_probes,
)
from netwatch.location.admin.boundary_tools import validate_boundary_geojson
from netwatch.location.admin.offline_boundary import DEFAULT_BOUNDARY_GEOJSON, load_boundary_dataset, locate_admin_by_point

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "location"

try:
    import shapely  # noqa: F401

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


def test_load_probe_points() -> None:
    points = load_probe_points(FIXTURE_DIR / "guangzhou_probe_points.csv")

    assert [point.label for point in points] == ["school_baiyun", "zengcheng_fenghuangcheng"]
    assert points[0].expected_district == "白云区"
    assert points[0].expected_adcode == "440111"
    assert points[0].case_type == "known_regression"


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_known_regression_points_fixture_parse_with_synthetic_boundary(tmp_path: Path) -> None:
    boundary = _write_known_regression_boundary(tmp_path)
    points = load_probe_points(FIXTURE_DIR / "guangzhou_probe_points.csv")

    results = run_known_point_probes(boundary, points, coord_system="wgs84")

    assert all(result.passed for result in results)
    assert [result.probe.chosen.admin.adcode for result in results if result.probe.chosen and result.probe.chosen.admin] == [
        "440111",
        "440118",
    ]


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_representative_point_generation_using_sample_boundary(monkeypatch) -> None:
    monkeypatch.setenv("NETWATCH_USE_SAMPLE_GEO", "1")
    dataset = load_boundary_dataset(DEFAULT_BOUNDARY_GEOJSON)

    points = generate_representative_points(dataset)

    assert len(points) == 2
    assert {point.district for point in points} == {"黄埔区", "增城区"}
    for point in points:
        result = locate_admin_by_point(point.lat, point.lon, dataset)
        assert result is not None
        assert result.adcode == point.adcode


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_boundary_midpoint_shared_edge_ambiguity(monkeypatch) -> None:
    monkeypatch.setenv("NETWATCH_USE_SAMPLE_GEO", "1")
    dataset = load_boundary_dataset(DEFAULT_BOUNDARY_GEOJSON)

    result = locate_admin_by_point(23.15, 113.63, dataset)

    assert result is not None
    assert result.boundary_match_count == 2
    assert result.confidence in {"ambiguous_boundary", "sample_only"}
    assert any("multiple administrative polygons" in warning for warning in result.boundary_warnings)


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_boundary_point_generation_using_sample_boundary(monkeypatch) -> None:
    monkeypatch.setenv("NETWATCH_USE_SAMPLE_GEO", "1")
    dataset = load_boundary_dataset(DEFAULT_BOUNDARY_GEOJSON)

    points = generate_boundary_points(dataset, max_points_per_district=3)

    assert points
    assert len(points) <= 6
    assert {point.point_kind for point in points} <= {"vertex", "midpoint"}


def test_epsilon_point_generation() -> None:
    class Point:
        label = "edge"
        lat = 23.0
        lon = 113.0

    points = generate_epsilon_points_around(Point(), meters=(1, 10))

    assert len(points) == 8
    assert {point.direction for point in points} == {"north", "east", "south", "west"}
    assert {point.meters for point in points} == {1.0, 10.0}


def test_malformed_validation_warning() -> None:
    result = validate_boundary_geojson(FIXTURE_DIR / "malformed.geojson")

    assert result.load_result == "invalid_json"
    assert any("invalid JSON" in warning for warning in result.warnings)


def test_whole_only_validation_warning() -> None:
    result = validate_boundary_geojson(FIXTURE_DIR / "guangzhou_whole_only.geojson")

    assert result.load_result == "ok"
    assert is_whole_city_boundary(result)
    assert any("whole-city" in warning for warning in result.warnings)


def test_missing_fields_validation_warning() -> None:
    result = validate_boundary_geojson(FIXTURE_DIR / "missing_name_adcode.geojson")

    assert any("name field" in warning for warning in result.warnings)
    assert any("adcode/code field" in warning for warning in result.warnings)


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_stress_report_object_can_be_generated_without_network(monkeypatch) -> None:
    monkeypatch.setenv("NETWATCH_USE_SAMPLE_GEO", "1")

    report = run_boundary_stress(DEFAULT_BOUNDARY_GEOJSON, coord_system="auto")

    assert report.validation.load_result == "ok"
    assert report.representative_results
    assert report.boundary_results
    assert report.epsilon_results


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_coord_system_auto_compare_does_not_crash(tmp_path: Path) -> None:
    boundary = _write_known_regression_boundary(tmp_path)
    points = load_probe_points(FIXTURE_DIR / "guangzhou_probe_points.csv")

    results = run_known_point_probes(boundary, points, coord_system="auto")

    assert len(results) == 2
    assert all(result.probe.chosen is not None for result in results)


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_stress_script_refuses_whole_only_boundary() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/geo/test_guangzhou_boundary_stress.py",
            "--boundary",
            str(FIXTURE_DIR / "guangzhou_whole_only.geojson"),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "not a Guangzhou child-district boundary" in completed.stderr


def _write_known_regression_boundary(tmp_path: Path) -> Path:
    path = tmp_path / "known-regression.geojson"
    data = {
        "type": "FeatureCollection",
        "features": [
            _feature("白云区", "440111", 113.43, 23.37, 113.45, 23.39),
            _feature("增城区", "440118", 113.57, 23.14, 113.60, 23.16),
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
