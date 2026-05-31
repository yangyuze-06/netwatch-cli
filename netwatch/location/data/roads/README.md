# Offline Roads Data

This directory is for optional road/street GeoJSON files used by the
experimental precise offline location feature.

The bundled `roads.sample.geojson` is intentionally tiny and exists only for
tests and explicit demos. CLI runs do not load it as real nearby-road data
unless `NETWATCH_USE_SAMPLE_GEO=1` is set. It is not a complete road dataset
and must not be treated as a precise address database.

To use real data, place a GeoJSON FeatureCollection on your machine and set:

```bash
export NETWATCH_ROADS_GEOJSON=/path/to/real_roads.geojson
```

Supported geometry types: `LineString` and `MultiLineString`.

Common property keys are read on a best-effort basis:

- `name`
- `highway`
- `ref`
- `type`
- `osm_id`

The CLI displays results as nearby roads/streets only. It does not infer a
doorplate address.
