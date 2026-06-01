# Offline Boundary Data

This directory is for optional administrative boundary GeoJSON files used by
the experimental precise offline location feature.

The bundled `china_districts.sample.geojson` is intentionally tiny and exists
only for tests and explicit demos. It is not a complete China boundary dataset,
and CLI runs do not load it as real data unless `NETWATCH_USE_SAMPLE_GEO=1` is
set.

To use real data, place a GeoJSON FeatureCollection on your machine and set:

```bash
export NETWATCH_BOUNDARY_GEOJSON=/path/to/real_boundary.geojson
export NETWATCH_BOUNDARY_COORD_SYSTEM=auto
```

For the current Guangzhou-only workflow, download only Guangzhou district
boundaries:

```bash
python scripts/geo/download_guangzhou_boundary.py --force
export NETWATCH_BOUNDARY_GEOJSON="$HOME/.netwatch/geo/guangzhou_districts.geojson"
export NETWATCH_BOUNDARY_COORD_SYSTEM=auto
python scripts/geo/download_guangzhou_boundary.py --probe-lat 23.1532 --probe-lon 113.5813
python scripts/geo/download_guangzhou_boundary.py --probe-lat 23.379859 --probe-lon 113.435329
```

Expected manual probe samples:

- `23.1532, 113.5813` should resolve to `增城区` / `440118`.
- `23.379859, 113.435329` should resolve to `白云区` / `440111`.

DataV/Amap-style boundary data may use GCJ-02 coordinates while browser
Geolocation normally returns WGS84. In `auto` mode netwatch compares both WGS84
and GCJ-02 probes, then prefers GCJ-02 for DataV/Amap-style boundary files and
warns when the two results differ.

Supported geometry types: `Polygon` and `MultiPolygon`.

Common property keys are read on a best-effort basis:

- `province`
- `city`
- `district`
- `name`
- `fullname`
- `adcode`
- `code`
- `level`

Do not commit large nationwide boundary files to this repository.
Do not commit downloaded `~/.netwatch/geo/guangzhou_districts.geojson` data.
