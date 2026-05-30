#!/usr/bin/env python3
"""Build the offline China district center-point CSV.

The runtime lookup uses only:
  netwatch/location/data/china_district_centers.csv

The default raw administrative hierarchy is AreaCity-JsSpider-StatsGov's
ok_data_level3.csv. Current upstream ok_data_level3.csv does not always include
coordinates, so this builder can temporarily download AreaCity's ok_geo.csv.7z,
extract only district center points, and discard the large archive/extract.
"""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = PROJECT_ROOT / "netwatch/location/data/raw/ok_data_level3.csv"
OUT_PATH = PROJECT_ROOT / "netwatch/location/data/china_district_centers.csv"
GEOCSV_ENV = "NETWATCH_CHINA_GEO_CSV"
GEO_URL = (
    "https://github.com/xiangyuecn/AreaCity-JsSpider-StatsGov/releases/download/"
    "2025.251231.260403/ok_geo.csv.7z"
)

OUTPUT_FIELDS = ["adcode", "province", "city", "district", "lon", "lat"]
PLACEHOLDER_DISTRICTS = {
    "",
    "市辖区",
    "县",
    "省直辖县级行政区划",
    "自治区直辖县级行政区划",
}
DIRECT_MUNICIPALITIES = {"北京市", "天津市", "上海市", "重庆市"}
SPECIAL_ADMIN_REGIONS = {"香港特别行政区", "澳门特别行政区"}
REQUIRED_RECORDS = {
    ("广东省", "广州市", "黄埔区"),
    ("广东省", "广州市", "增城区"),
    ("北京市", "北京市", "海淀区"),
    ("上海市", "上海市", "浦东新区"),
}
COORD_FIELD_SETS = [
    ("lon", "lat"),
    ("lng", "lat"),
    ("longitude", "latitude"),
]


def _die(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def _open_csv_with_encoding(path: Path) -> tuple[str, list[dict[str, str]], list[str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            with path.open(newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                headers = reader.fieldnames or []
            return encoding, rows, headers
        except UnicodeDecodeError as exc:
            last_error = exc
    _die(f"无法按 UTF-8/UTF-8-SIG 读取 CSV: {path} ({last_error})")


def _require_raw_file() -> None:
    if RAW_PATH.exists():
        return
    print("找不到 AreaCity-JsSpider-StatsGov 的 ok_data_level3.csv。", file=sys.stderr)
    print("请下载：", file=sys.stderr)
    print(
        "https://raw.githubusercontent.com/xiangyuecn/AreaCity-JsSpider-StatsGov/"
        "master/src/采集到的数据/ok_data_level3.csv",
        file=sys.stderr,
    )
    print(f"推荐保存路径：{RAW_PATH}", file=sys.stderr)
    raise SystemExit(1)


def _safe_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _normalize_adcode(row: dict[str, str]) -> str:
    ext_id = (row.get("ext_id") or "").strip()
    if ext_id and ext_id != "0":
        return ext_id[:6]
    for key in ("adcode", "ad_code", "id", "code", "行政代码", "行政区划代码"):
        value = (row.get(key) or "").strip()
        if value:
            return value[:6]
    return ""


def _node_id(row: dict[str, str]) -> str:
    value = (row.get("id") or row.get("adcode") or row.get("code") or "").strip()
    if value:
        return value
    return _normalize_adcode(row)


def _row_level(row: dict[str, str]) -> int | None:
    for key in ("deep", "level", "层级"):
        level = _safe_int((row.get(key) or "").strip())
        if level is not None:
            return level
    adcode = _normalize_adcode(row)
    if len(adcode) == 2:
        return 0
    if len(adcode) == 4:
        return 1
    if len(adcode) == 6:
        return 2
    return None


def _row_name(row: dict[str, str]) -> str:
    for key in ("ext_name", "name", "地名", "地名名称"):
        value = (row.get(key) or "").strip()
        if value:
            return value
    return ""


def _district_name(row: dict[str, str]) -> str:
    return ((row.get("ext_name") or row.get("name") or "").strip())


def _build_hierarchy(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for row in rows:
        node_id = _node_id(row)
        adcode = _normalize_adcode(row)
        if not node_id or not adcode:
            continue
        nodes[node_id] = {
            "row": row,
            "id": node_id,
            "adcode": adcode,
            "pid": (row.get("pid") or "").strip(),
            "level": _row_level(row),
            "name": _row_name(row),
        }
    return nodes


def _parent_node(nodes: dict[str, dict[str, Any]], node: dict[str, Any]) -> dict[str, Any] | None:
    pid = node.get("pid") or ""
    if pid in nodes:
        return nodes[pid]
    return None


def _province_city_district(
    nodes: dict[str, dict[str, Any]], node: dict[str, Any]
) -> tuple[str, str, str]:
    district = _district_name(node["row"])
    city_node = _parent_node(nodes, node)
    province_node = _parent_node(nodes, city_node) if city_node else None

    city = city_node["name"] if city_node else ""
    province = province_node["name"] if province_node else ""

    if province in DIRECT_MUNICIPALITIES:
        city = province
    if province in SPECIAL_ADMIN_REGIONS and not city:
        city = province
    if not province and city in DIRECT_MUNICIPALITIES:
        province = city
    if province in SPECIAL_ADMIN_REGIONS:
        city = city or province

    return province, city, district


def _parse_geo_point(value: str | None) -> tuple[float, float] | None:
    if not value:
        return None
    value = value.strip().strip('"')
    if not value or value.upper() == "EMPTY":
        return None
    parts = value.replace(",", " ").split()
    if len(parts) < 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def _coords_from_row(row: dict[str, str]) -> tuple[float, float] | None:
    for lon_key, lat_key in COORD_FIELD_SETS:
        if lon_key in row and lat_key in row:
            try:
                return float((row.get(lon_key) or "").strip()), float((row.get(lat_key) or "").strip())
            except ValueError:
                pass
    for key in ("geo", "center", "坐标", "中心点"):
        point = _parse_geo_point(row.get(key))
        if point:
            return point
    return None


def _coords_from_raw_rows(rows: list[dict[str, str]]) -> dict[str, tuple[float, float]]:
    coords: dict[str, tuple[float, float]] = {}
    for row in rows:
        keys = {_node_id(row), _normalize_adcode(row)}
        point = _coords_from_row(row)
        if point:
            for key in keys:
                if key:
                    coords[key] = point
    return coords


def _find_7z() -> str | None:
    for name in ("7z", "7zz"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _download_geo_archive(target: Path) -> None:
    print(f"ok_data_level3.csv 未包含坐标，临时下载 AreaCity 坐标包：{GEO_URL}")
    with urllib.request.urlopen(GEO_URL, timeout=60) as response, target.open("wb") as f:
        shutil.copyfileobj(response, f)


def _extract_geo_csv_from_archive(archive: Path, workdir: Path) -> Path:
    seven_zip = _find_7z()
    if not seven_zip:
        _die(
            "ok_data_level3.csv 不含可用坐标，且系统未找到 7z/7zz，无法临时解压 ok_geo.csv.7z。"
            f"可手动解压 ok_geo.csv 后用 {GEOCSV_ENV}=/path/to/ok_geo.csv 运行。"
        )
    subprocess.run(
        [seven_zip, "e", "-y", str(archive), f"-o{workdir}"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    geo_csv = workdir / "ok_geo.csv"
    if not geo_csv.exists():
        _die("ok_geo.csv.7z 解压后未找到 ok_geo.csv。")
    return geo_csv


def _load_geo_coords() -> dict[str, tuple[float, float]]:
    env_path = os.environ.get(GEOCSV_ENV)
    if env_path:
        geo_csv = Path(env_path).expanduser()
        if not geo_csv.exists():
            _die(f"{GEOCSV_ENV} 指向的文件不存在：{geo_csv}")
        return _coords_from_geo_csv(geo_csv)

    with tempfile.TemporaryDirectory(prefix="netwatch-china-geo-") as tmp:
        tmpdir = Path(tmp)
        archive = tmpdir / "ok_geo.csv.7z"
        _download_geo_archive(archive)
        geo_csv = _extract_geo_csv_from_archive(archive, tmpdir)
        return _coords_from_geo_csv(geo_csv)


def _coords_from_geo_csv(path: Path) -> dict[str, tuple[float, float]]:
    csv.field_size_limit(sys.maxsize)
    coords: dict[str, tuple[float, float]] = {}
    encoding, rows, headers = _open_csv_with_encoding(path)
    print(f"读取坐标 CSV: {path} ({encoding})")
    if "geo" not in headers:
        _die(f"坐标 CSV 缺少 geo 字段：{headers}")
    for row in rows:
        keys = {_node_id(row), _normalize_adcode(row)}
        point = _parse_geo_point(row.get("geo"))
        if point:
            for key in keys:
                if key:
                    coords[key] = point
    return coords


def _build_records(
    rows: list[dict[str, str]], coords: dict[str, tuple[float, float]]
) -> list[dict[str, str]]:
    nodes = _build_hierarchy(rows)
    records: list[dict[str, str]] = []
    for adcode, node in nodes.items():
        if node["level"] != 2:
            continue
        province, city, district = _province_city_district(nodes, node)
        if district in PLACEHOLDER_DISTRICTS:
            continue
        point = coords.get(node["id"]) or coords.get(adcode)
        if not point:
            continue
        lon, lat = point
        records.append(
            {
                "adcode": adcode,
                "province": province,
                "city": city,
                "district": district,
                "lon": f"{lon:.6f}".rstrip("0").rstrip("."),
                "lat": f"{lat:.6f}".rstrip("0").rstrip("."),
            }
        )
    return sorted(records, key=lambda item: item["adcode"])


def _quality_stats(raw_count: int, records: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "raw_count": raw_count,
        "output_count": len(records),
        "province_non_empty_count": sum(1 for r in records if r["province"]),
        "city_non_empty_count": sum(1 for r in records if r["city"]),
        "district_non_empty_count": sum(1 for r in records if r["district"]),
        "unique_province_count": len({r["province"] for r in records if r["province"]}),
        "unique_city_count": len({r["city"] for r in records if r["city"]}),
        "unique_district_count": len({r["district"] for r in records if r["district"]}),
        "output_path": str(OUT_PATH),
    }


def _assert_quality(stats: dict[str, Any], records: list[dict[str, str]]) -> None:
    output_count = stats["output_count"]
    if output_count <= 2000:
        _die(f"output_count 必须 > 2000，当前为 {output_count}")
    for field, stat_key in (
        ("province", "province_non_empty_count"),
        ("city", "city_non_empty_count"),
        ("district", "district_non_empty_count"),
    ):
        ratio = stats[stat_key] / output_count
        if ratio <= 0.95:
            _die(f"{field} 非空比例必须 > 95%，当前为 {ratio:.2%}")

    existing = {(r["province"], r["city"], r["district"]) for r in records}
    missing = sorted(REQUIRED_RECORDS - existing)
    if missing:
        _die(f"缺少必要记录：{missing}")


def main() -> None:
    _require_raw_file()
    encoding, rows, headers = _open_csv_with_encoding(RAW_PATH)
    print(f"读取行政区划 CSV: {RAW_PATH} ({encoding})")
    print(f"检测到字段: {', '.join(headers)}")

    coords = _coords_from_raw_rows(rows)
    if not coords:
        coords = _load_geo_coords()
    if not coords:
        _die("ok_data_level3.csv 不含可用 lon/lat/geo/center 坐标，无法生成中心点数据。")

    records = _build_records(rows, coords)
    stats = _quality_stats(len(rows), records)
    _assert_quality(stats, records)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(records)

    print("构建完成，质量统计：")
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
