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
```

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
