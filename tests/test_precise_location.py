"""Tests for experimental precise offline location."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from netwatch.device_location import DeviceLocationResult
from netwatch.location.models import AdminLocationResult, BrowserLocationResult, PreciseLocationReport
from netwatch.location.offline_boundary import (
    BoundaryDependencyError,
    DEFAULT_GUANGZHOU_BOUNDARY_GEOJSON,
    DEFAULT_BOUNDARY_GEOJSON,
    get_boundary_geojson_path,
    load_boundary_dataset,
    locate_admin_by_point,
)
from netwatch.location.nearby_roads import (
    DEFAULT_ROADS_GEOJSON,
    RoadsDependencyError,
    find_nearby_roads,
    get_roads_geojson_path,
    load_roads_dataset,
)
from netwatch.location.precise_location import build_precise_location_report

try:
    import shapely  # noqa: F401

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


def test_default_data_paths_exist() -> None:
    assert DEFAULT_BOUNDARY_GEOJSON.exists()
    assert DEFAULT_ROADS_GEOJSON.exists()


def test_env_paths_override_defaults(monkeypatch, tmp_path: Path) -> None:
    boundary = tmp_path / "boundary.geojson"
    roads = tmp_path / "roads.geojson"
    monkeypatch.setenv("NETWATCH_BOUNDARY_GEOJSON", str(boundary))
    monkeypatch.setenv("NETWATCH_ROADS_GEOJSON", str(roads))

    assert get_boundary_geojson_path() == boundary
    assert get_roads_geojson_path() == roads


def test_boundary_missing_shapely_message(monkeypatch) -> None:
    import builtins

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "shapely":
            raise ImportError("No module named shapely")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setenv("NETWATCH_USE_SAMPLE_GEO", "1")

    with pytest.raises(BoundaryDependencyError, match="pip install shapely"):
        load_boundary_dataset()


def test_roads_missing_shapely_message(monkeypatch) -> None:
    import builtins

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "shapely":
            raise ImportError("No module named shapely")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setenv("NETWATCH_USE_SAMPLE_GEO", "1")

    with pytest.raises(RoadsDependencyError, match="pip install shapely"):
        load_roads_dataset()


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_sample_boundary_locates_huangpu(monkeypatch) -> None:
    monkeypatch.setenv("NETWATCH_USE_SAMPLE_GEO", "1")
    dataset = load_boundary_dataset()
    result = locate_admin_by_point(23.153126, 113.581404, dataset)

    assert result is not None
    assert result.province == "广东省"
    assert result.city == "广州市"
    assert result.district == "黄埔区"
    assert result.adcode == "440112"
    assert result.confidence == "sample_only"
    assert result.source == "offline_boundary_sample"


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_sample_boundary_uses_covers_for_border_point(monkeypatch) -> None:
    monkeypatch.setenv("NETWATCH_USE_SAMPLE_GEO", "1")
    dataset = load_boundary_dataset()
    result = locate_admin_by_point(23.15, 113.63, dataset)

    assert result is not None
    assert result.district in {"黄埔区", "增城区"}


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_sample_roads_find_nearby_roads(monkeypatch) -> None:
    monkeypatch.setenv("NETWATCH_USE_SAMPLE_GEO", "1")
    dataset = load_roads_dataset()
    results = find_nearby_roads(23.153126, 113.581404, dataset)

    assert results
    assert results[0].distance_m is not None
    assert results[0].distance_m < 100
    assert {road.name for road in results} & {"永和大道", "新业路"}
    assert {road.source for road in results} == {"offline_roads_sample"}


def test_precise_report_without_config_does_not_use_sample_boundary(monkeypatch) -> None:
    monkeypatch.delenv("NETWATCH_BOUNDARY_GEOJSON", raising=False)
    monkeypatch.delenv("NETWATCH_ROADS_GEOJSON", raising=False)
    monkeypatch.delenv("NETWATCH_USE_SAMPLE_GEO", raising=False)
    monkeypatch.setattr(
        "netwatch.location.offline_boundary.DEFAULT_GUANGZHOU_BOUNDARY_GEOJSON",
        Path("/tmp/netwatch-test-missing-guangzhou-boundary.geojson"),
    )
    device = DeviceLocationResult(latitude=23.153126, longitude=113.581404, accuracy_m=30.0)

    report = build_precise_location_report(device)

    assert report.admin is not None
    assert report.admin.source != "offline_boundary_sample"
    assert report.admin.confidence != "high"
    assert report.admin.source == "offline_china_district_centers"
    assert report.fallback_used is True
    assert report.nearby_roads == []
    assert any("NETWATCH_BOUNDARY_GEOJSON" in warning for warning in report.warnings)
    assert any("NETWATCH_ROADS_GEOJSON" in warning for warning in report.warnings)


def test_default_guangzhou_boundary_path_used_when_present(monkeypatch) -> None:
    monkeypatch.delenv("NETWATCH_BOUNDARY_GEOJSON", raising=False)
    monkeypatch.delenv("NETWATCH_USE_SAMPLE_GEO", raising=False)

    assert get_boundary_geojson_path() in {DEFAULT_GUANGZHOU_BOUNDARY_GEOJSON, DEFAULT_BOUNDARY_GEOJSON}


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_precise_report_sample_geo_requires_explicit_env(monkeypatch) -> None:
    monkeypatch.delenv("NETWATCH_BOUNDARY_GEOJSON", raising=False)
    monkeypatch.delenv("NETWATCH_ROADS_GEOJSON", raising=False)
    monkeypatch.setenv("NETWATCH_USE_SAMPLE_GEO", "1")
    device = DeviceLocationResult(latitude=23.153126, longitude=113.581404, accuracy_m=30.0)

    report = build_precise_location_report(device)

    assert report.admin is not None
    assert report.admin.source == "offline_boundary_sample"
    assert report.admin.confidence == "sample_only"
    assert report.nearby_roads
    assert {road.source for road in report.nearby_roads} == {"offline_roads_sample"}
    assert any("内置测试样例" in warning and "NETWATCH_BOUNDARY_GEOJSON" in warning for warning in report.warnings)
    assert any("内置测试样例" in warning and "NETWATCH_ROADS_GEOJSON" in warning for warning in report.warnings)


def test_precise_report_falls_back_when_boundary_unavailable(monkeypatch, tmp_path: Path) -> None:
    missing_boundary = tmp_path / "missing-boundary.geojson"
    missing_roads = tmp_path / "missing-roads.geojson"
    device = DeviceLocationResult(latitude=23.153126, longitude=113.581404, accuracy_m=30.0)

    report = build_precise_location_report(
        device,
        boundary_path=str(missing_boundary),
        roads_path=str(missing_roads),
    )

    assert report.browser is not None
    assert report.fallback_used is True
    assert report.admin is not None
    assert report.admin.source == "offline_china_district_centers"
    assert report.admin.confidence == "medium"
    assert any("precise boundary unavailable" in warning for warning in report.warnings)
    assert any("nearby street unavailable" in warning for warning in report.warnings)


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely not installed")
def test_precise_report_auto_boundary_coord_system_prefers_gcj02(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("NETWATCH_USE_SAMPLE_GEO", raising=False)
    monkeypatch.setenv("NETWATCH_BOUNDARY_COORD_SYSTEM", "auto")
    boundary = tmp_path / "boundary.geojson"
    boundary.write_text(
        """{
          "type": "FeatureCollection",
          "features": [
            {
              "type": "Feature",
              "properties": {
                "province": "广东省",
                "city": "广州市",
                "district": "花都区",
                "name": "花都区",
                "adcode": "440114",
                "level": "district"
              },
              "geometry": {
                "type": "Polygon",
                "coordinates": [[[113.42, 23.36], [113.438, 23.36], [113.438, 23.40], [113.42, 23.40], [113.42, 23.36]]]
              }
            },
            {
              "type": "Feature",
              "properties": {
                "province": "广东省",
                "city": "广州市",
                "district": "白云区",
                "name": "白云区",
                "adcode": "440111",
                "level": "district"
              },
              "geometry": {
                "type": "Polygon",
                "coordinates": [[[113.438, 23.36], [113.46, 23.36], [113.46, 23.40], [113.438, 23.40], [113.438, 23.36]]]
              }
            }
          ]
        }""",
        encoding="utf-8",
    )
    device = DeviceLocationResult(latitude=23.379859, longitude=113.435329, accuracy_m=30.0)

    report = build_precise_location_report(device, boundary_path=str(boundary))

    assert report.admin is not None
    assert report.admin.district == "白云区"
    assert report.admin.adcode == "440111"
    assert report.admin.source == "offline_boundary"
    assert report.admin.confidence == "high_with_coord_transform"
    assert report.admin.boundary_coord_system == "gcj02"
    assert any("coordinate system ambiguity" in warning for warning in report.warnings)
    assert any("GCJ-02 conversion" in warning for warning in report.warnings)


def test_precise_report_browser_error_returns_warning() -> None:
    report = build_precise_location_report(DeviceLocationResult(error="Permission denied"))

    assert report.browser is None
    assert report.admin is None
    assert report.warnings == ["Permission denied"]


def test_print_precise_location_report(monkeypatch) -> None:
    from netwatch import cli as cli_mod

    report = PreciseLocationReport(
        browser=BrowserLocationResult(latitude=23.153126, longitude=113.581404, accuracy_m=30.0),
        admin=AdminLocationResult(
            province="广东省",
            city="广州市",
            district="黄埔区",
            adcode="440112",
            confidence="sample_only",
            source="offline_boundary_sample",
        ),
        warnings=["当前行政区结果来自内置测试样例，不代表真实行政边界。请配置 NETWATCH_BOUNDARY_GEOJSON 后再使用精确行政区识别。"],
    )

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.print_precise_location_report(report)
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert "netwatch precise location" in output
    assert "黄埔区" in output
    assert "[样例数据]" in output
    assert "sample_only" in output
    assert "Data mode" in output
    assert "Nothing was uploaded" in output
    assert "Traceback" not in output
