# netwatch-cli

`netwatch-cli` 是一个轻量、交互式的命令行网络状态工具，用于查看本机网络、局域网设备、当前公网出口和测速结果。它面向日常排障：快速知道“我现在连在哪、出口在哪、测速走的是哪条路径”。

## 功能

- 实时网卡上传/下载流量。
- 本机局域网信息：主要网卡、IPv4、MAC、默认网关。
- 公网 IP 出口识别：国家/地区、城市、ISP/组织。
- 浏览器授权定位：用户手动允许后读取浏览器 geolocation。
- 离线中国省/市/区粗定位：本地最近区县中心点匹配。
- 局域网设备发现：Ping + ARP 扫描。
- 宽带测速：`speedtest.cn` 浏览器自动化简洁入口。
- 代理/当前出口测速：识别 CLI 出口并测速，可展开详细诊断。
- 路由器管理后台辅助打开。
- 高级功能：Ookla / LibreSpeed / Python fallback、服务器筛选、配置管理、测速摘要。

## Quick Start

### Requirements

- Python 3.10+
- macOS 或 Linux 终端环境；Windows 11 当前为 experimental 支持
- Git
- `reverse-geocoder` Python 包，用于浏览器授权定位后的离线反向地理编码
- Playwright Chromium，用于 `speedtest.cn` 浏览器自动化测速
- 可选：官方 Ookla CLI 二进制 `speedtest`，用于 Ookla 后端
- 可选：LibreSpeed CLI 二进制，用于 LibreSpeed 后端

### 安装（macOS / Linux）

```bash
git clone https://github.com/yangyuze-06/netwatch-cli.git
cd netwatch-cli
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install -e ".[browser]"
python -m playwright install chromium
netwatch
```

再次运行：

```bash
cd netwatch-cli
source .venv/bin/activate
netwatch
```

也可以直接运行模块：

```bash
python -m netwatch.cli
```

项目 Python 主依赖以 `pyproject.toml` 为准；

### Windows PowerShell

先安装 Python 3.10+，安装时勾选 **Add python.exe to PATH**。打开新的 PowerShell 后检查：

```powershell
python --version
```

如果 `py` 不存在，用 `python` 即可；如果 `python --version` 没有输出或提示找不到命令，说明 Python 或 PATH 尚未配置好。

### 一键运行

```powershell
# 1.clone项目并进入文件夹
git clone https://github.com/yangyuze-06/netwatch-cli.git
cd netwatch-cli

# 2.创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 如果 PowerShell 禁止激活脚本，先执行：
# Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# .\.venv\Scripts\Activate.ps1

# 3. 安装基础依赖
python -m pip install -U pip --no-cache-dir
python -m pip install -e . --no-cache-dir
python -m pip install -e ".[browser]" --no-cache-dir
python -m playwright install chromium

# 4. 可选：安装测试工具
python -m pip install pytest --no-cache-dir

# 5. 验证
python -m compileall netwatch
python -m pytest -q

# 6. 启动

python -m netwatch.cli
```

再次启动命令如下：

```powershell
.\.venv\Scripts\Activate.ps1
python -m netwatch.cli
```

### 安装验证

安装完成后，在项目根目录运行：

```bash
scripts/check_install.sh
```

脚本会检查 Python 依赖、`netwatch` 命令、Playwright Chromium，以及可选的 `speedtest` 命令。如果提示 Playwright Chromium 未安装，运行：

```bash
python -m playwright install chromium
```
### 同步管理

```bash
git status; git pull --ff-only origin main
```

## 可选外部工具

### 官方 Ookla CLI

`speedtest` 是官方 Ookla CLI 二进制；`speedtest-cli` 是 Python 社区包，只作为 Python fallback 后端。不要把 `speedtest-cli` 当成官方 Ookla CLI。

macOS：

```bash
brew tap teamookla/speedtest
brew install speedtest
```

Linux：

Python 依赖可以通过 `venv + pip` 安装。官方 Ookla CLI 需要按发行版从 Ookla 官方渠道安装，不由 `requirements.txt` 管理。Debian / Ubuntu 常见方式如下：

```bash
curl -s https://packagecloud.io/install/repositories/ookla/speedtest-cli/script.deb.sh | sudo bash
sudo apt install speedtest
```

### LibreSpeed CLI

LibreSpeed CLI 是外部二进制，不由 `requirements.txt` 管理。未安装时，相关后端会不可用，但其他功能仍可运行。

## 使用

```text
1. 查看实时网卡流量
2. 查看本机网络信息
3. 局域网设备发现
4. 宽带测速（speedtest.cn）
5. 代理/当前出口测速
6. 打开路由器管理后台
7. 高级功能
8. 退出
```

查看实时网卡流量时，按 `Ctrl+C` 返回菜单。主菜单按 `Ctrl+C` 会直接退出。

## 隐私说明

- 公网 IP 定位来自 IP 数据库，可能显示 VPN/TUN/代理出口位置，不代表真实所在地。
- 浏览器授权定位只在用户手动选择并允许浏览器权限时运行。
- `netwatch-cli` 不保存、不上传用户真实位置。
- 离线中国行政区划匹配完全在本地完成。
- 实验性精确离线定位只把浏览器坐标回传到本机 `127.0.0.1` 临时服务，优先用本地边界 GeoJSON 判断行政区，失败时回退到中心点最近邻。
- 高德/百度 API 不是默认依赖；默认运行不需要地图服务 Key。
- 配置文件 `~/.netwatch/config.json` 只保存非敏感偏好，不保存密码、`stok`、token、cookie 或公网 IP。

## 离线中国行政区划

`netwatch/location/data/china_district_centers.csv` 是项目内置的轻量区县中心点数据，用于把浏览器经纬度粗略显示成中国省/市/区县。

- 数据来源：[AreaCity-JsSpider-StatsGov](https://github.com/xiangyuecn/AreaCity-JsSpider-StatsGov)。
- 运行时只读取本地 `china_district_centers.csv`，不联网。
- 构建阶段可临时使用 AreaCity 的 `ok_geo.csv.7z` 提取中心点，但不把 130MB+ 解压数据放入项目。
- 当前算法是“区县中心点最近邻”，不是真实行政边界。
- 区县交界处可能误判。例如广州永和附近可能返回黄埔区或增城区。

实验性精确离线定位必须配置用户本机真实 GeoJSON 数据后，才会执行精确边界/道路识别：

```bash
python -m pip install -e ".[geo]"
python scripts/download_guangzhou_boundary.py --force
export NETWATCH_BOUNDARY_GEOJSON="$HOME/.netwatch/geo/guangzhou_districts.geojson"
export NETWATCH_BOUNDARY_COORD_SYSTEM=auto
export NETWATCH_ROADS_GEOJSON=/path/to/real_roads.geojson
netwatch
```

推荐只下载广州市区县级边界到 `~/.netwatch/geo/guangzhou_districts.geojson`：

```bash
python scripts/download_guangzhou_boundary.py --force
python scripts/download_guangzhou_boundary.py --probe-lat 23.1532 --probe-lon 113.5813
python scripts/download_guangzhou_boundary.py --probe-lat 23.379859 --probe-lon 113.435329
```

两个手动验证样例：

- 增城/永宁/凤凰城测试点：`lat=23.1532`、`lon=113.5813`，期望 `增城区` / `440118`。
- 学校/白云区测试点：`lat=23.379859`、`lon=113.435329`，期望 `白云区` / `440111`。

DataV/高德边界可能是 GCJ-02 坐标体系，而浏览器 Geolocation 通常返回 WGS84。
`NETWATCH_BOUNDARY_COORD_SYSTEM=auto` 会同时比较 WGS84 和 GCJ-02 查询，并优先使用更符合
DataV/Amap 边界数据的 GCJ-02 转换结果；如果两者命中不同区县，会输出坐标系歧义 warning。

区县级边界只能识别到白云区、花都区、增城区、黄埔区等行政区，不能识别永宁街道、学校名称或凤凰城凤雅苑。
附近地标未来应使用用户本机 `user_landmarks.json` 这类小型自定义数据解决，不下载全国 POI、全国道路或门牌级数据库。

### 地点/边界测试

真人拿着设备移动只能发现个别现象，不能系统验证边界算法。广州边界测试使用固定 probe points、
区内 representative points、边界 vertex/midpoint 和边界附近 epsilon offsets 来检查算法是否稳定。

运行本地广州区县边界 stress test：

```bash
python scripts/test_guangzhou_boundary_stress.py --boundary "$HOME/.netwatch/geo/guangzhou_districts.geojson"
python scripts/test_guangzhou_boundary_stress.py --boundary "$HOME/.netwatch/geo/guangzhou_districts.geojson" --grid-regression
```

固定 regression 点来自 `tests/fixtures/location/guangzhou_probe_points.csv`：

- `school_baiyun` 应命中 `白云区` / `440111`。
- `zengcheng_fenghuangcheng` 应命中 `增城区` / `440118`。

stress test 还会比较 WGS84 与 GCJ-02 probe。区界附近结果可能受浏览器 `accuracy_m`、
WGS84/GCJ-02 偏移和 DataV/高德边界数据版本影响；`boundary proximity warning` 不一定代表 bug，
但需要在输出中解释。中心点最近邻只是 fallback，不能作为边界附近真值。

仓库只内置很小的 sample boundary/roads 数据用于测试和演示，不提交大型全国边界或 OSM 数据。
正式 CLI 运行默认不会把 sample 当作真实定位结果；如需演示 sample，可显式设置
`NETWATCH_USE_SAMPLE_GEO=1`，输出会标注 sample/demo。CLI 只显示“附近道路/街道”，不会声称是精确门牌地址。

重建数据：

```bash
python scripts/build_china_district_centers.py
```

## 测速说明

实时网卡流量不等于最大带宽。它表示当前这一秒本机正在使用的吞吐量；Speedtest 会主动连接公网测速服务器，用于估算线路能力。

普通“宽带测速（speedtest.cn）”使用 Playwright 后台打开网页、点击测速并从 DOM 文本读取结果。它不是 `speedtest.cn` 官方 API 后端，不抓包、不读取 Cookie、不逆向私有接口，失败时不会自动 fallback 到 Ookla。

“通用测速诊断”（高级功能第 1 项）保留 Ookla / LibreSpeed / Python fallback，并包含 Result confidence、网络路径分析、VPN/TUN 检测等详细信息。

所有公网测速、subprocess、`curl`、`requests`、Playwright 浏览器访问和路由器 API 测试都必须 mock。

## 开发命令

```bash
source .venv/bin/activate
python scripts/build_china_district_centers.py
python -m compileall netwatch
pytest -q
git diff --check
```

## 项目结构

```text
netwatch-cli/
├── netwatch/                     核心代码
│   ├── cli.py                    主菜单入口和顶层调度
│   ├── cli_modules/              CLI 展示与交互模块
│   │   ├── common.py             通用 console / 兼容 helper
│   │   ├── speedtest.py          测速相关 CLI 展示与交互
│   │   ├── router.py             路由器相关 CLI 展示与交互
│   │   ├── lan.py                局域网扫描相关 CLI 展示与交互
│   │   └── location.py           定位相关 CLI 展示与交互
│   ├── config.py                 用户配置读写
│   ├── network_info.py           本机网络和网卡识别
│   ├── proxy_probe.py            当前公网出口检测
│   ├── device_location.py        浏览器授权定位
│   ├── location/                 定位与离线行政区划
│   │   ├── china_admin_lookup.py
│   │   └── data/                 轻量内置数据
│   └── speedtest/                测速领域模块
│       ├── analysis.py           测速结果一致性和路径分析
│       ├── runner.py             测速调度与诊断
│       ├── speed.py              实时网卡流量采样
│       ├── speedtest_cn*.py      speedtest.cn browser automation
│       └── backends/             Ookla / LibreSpeed / Python 测速后端
├── scripts/                      构建与维护脚本
├── tests/                        单元测试和 mock 测试
└── docs/
    ├── handoff/                  给不同 AI agent 的交接文档
    ├── plans/                    版本规划与历史路线
    └── features/                 专项功能设计文档
```

项目保持当前包布局，不迁移到 `src/`。测速相关业务模块已收敛到 `netwatch/speedtest/`，旧路径保留轻量兼容 wrapper。

## 数据与许可证

- AreaCity-JsSpider-StatsGov 使用 MIT license。
- 本项目当前未包含独立 `LICENSE` 文件，项目许可证待补充。
- 不要把 `ok_geo.csv` 或 `ok_geo.csv.7z` 放入仓库；运行时只需要轻量 CSV。
