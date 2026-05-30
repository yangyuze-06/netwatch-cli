# China District Centers Data

本目录用于离线、粗略显示中国省/市/区县行政区划。

`netwatch-cli` 查询时只读取本地的 `china_district_centers.csv`，不联网、不上传位置，也不需要高德、百度或其他地图服务 Key。

## Algorithm

- `china_district_centers.csv` 内置区县级中心点。
- `netwatch.location.china_admin_lookup` 使用 Haversine 距离计算最近区县中心点。
- 当前算法是“区县中心点最近邻”，不是真实行政边界或 polygon containment。

## Limitations

- 区县交界处可能误判。例如广州永和附近靠近黄埔区/增城区边界，最近中心点结果可能在黄埔区和增城区之间摇摆。
- 中心点只适合 CLI 展示粗略行政区划，不适合作为权威地址、合规边界或地理围栏判断。
- 如需高精度，未来可以引入可选 polygon/GeoJSON 数据包，或让用户自行配置 AMap/Baidu online provider。

## Source

数据来源：

- [AreaCity-JsSpider-StatsGov](https://github.com/xiangyuecn/AreaCity-JsSpider-StatsGov)
- `raw/ok_data_level3.csv`：省/市/区三级行政区划层级数据。
- 构建时如 `ok_data_level3.csv` 不含坐标，脚本会临时读取 AreaCity 的 `ok_geo.csv.7z` 来提取中心点，但不会把大边界包内置到项目。

许可证：AreaCity-JsSpider-StatsGov 使用 MIT license。

不要默认引入 `ok_geo.csv.7z`。它解压后超过 130MB，会让 `netwatch-cli` 变得臃肿；本项目运行时只保留轻量的 `china_district_centers.csv`。

## Rebuild

```bash
python scripts/build_china_district_centers.py
```

如果需要使用本地已解压的 `ok_geo.csv`：

```bash
NETWATCH_CHINA_GEO_CSV=/path/to/ok_geo.csv python scripts/build_china_district_centers.py
```
