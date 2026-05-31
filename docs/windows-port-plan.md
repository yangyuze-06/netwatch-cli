# Windows 初步适配计划

## Background

`netwatch-cli` 当前 README 明确面向 macOS / Linux 终端环境，但项目定位已经是轻量、可维护、跨平台的 Python CLI 网络诊断工具。Windows 适配目标应当是渐进式增加平台能力，不改变现有 macOS / Linux 行为，不把平台判断散落到业务层，也不引入会迫使测速、路由器或定位模块大重构的设计。

本计划基于当前代码审计，目标是让后续实现可以小步 patch、可 mock、可回滚、可验证。

## Current Architecture Findings

### 总体结构

- `netwatch/cli.py` 是交互式主菜单入口，主要调度 `cli_modules/*`。
- `netwatch/cli_modules/location.py` 负责本机局域网信息、公网出口和可选浏览器定位展示。
- `netwatch/network_info.py` 负责本机网卡、IPv4、MAC、LAN 扫描候选网卡和测速物理网卡选择。
- `netwatch/router.py` 负责默认网关、路由器后台 URL、Xiaomi/Redmi 设备同步和设备合并。
- `netwatch/scanner.py` 负责 LAN Ping + ARP 扫描、ARP 解析、反向 DNS。
- `netwatch/speedtest/speed.py` 负责实时网卡吞吐采样。
- `netwatch/speedtest/runner.py` 负责 Ookla / LibreSpeed / Python fallback 调度和诊断摘要。
- `netwatch/speedtest/backends/*.py` 是测速后端适配器。
- `netwatch/config.py` 负责 `~/.netwatch/config.json` 非敏感配置。
- `netwatch/speedtest_runner.py`、`netwatch/speed.py`、`netwatch/analysis.py`、`netwatch/speedtest_backends/*` 是兼容 wrapper，不应作为 Windows 适配主入口。

### 可能包含平台相关逻辑的文件

| 文件 | 平台相关点 | 当前状态 |
|---|---|---|
| `netwatch/network_info.py` | `psutil.net_if_addrs()`、`psutil.AF_LINK`、虚拟网卡关键词、`en0/en1` 偏好、`8.8.8.8` UDP 主 IP 探测、固定 `/24` LAN 推断 | 部分跨平台，但接口评分明显偏 macOS/Linux |
| `netwatch/scanner.py` | `platform.system()`、`ping` 参数、`arp -a/-an`、ARP 输出解析、`subprocess.run(text=True)` 编码 | Ping 已有 Windows 分支；ARP parser 主要适配 macOS 格式 |
| `netwatch/router.py` | `route -n get default`、`ip route show default`、`route -n` | 只支持 Darwin/Linux；Windows 返回 `None` |
| `netwatch/speedtest/speed.py` | `psutil.net_io_counters()` | 天然跨平台，可作为 Phase 1 保留 |
| `netwatch/speedtest/backends/ookla_cli.py` | macOS/Linux 固定候选路径、PATH 检测、安装提示、`--interface` 参数 | PATH 检测部分跨平台；候选路径和提示偏 macOS |
| `netwatch/speedtest/backends/librespeed_cli.py` | `shutil.which("librespeed-cli")`、subprocess | 基本跨平台，前提是 Windows PATH 中存在可执行文件 |
| `netwatch/speedtest/runner.py` | 依赖 `get_preferred_physical_interface()`，提示里写 brew，诊断只识别 `utun/tun/tap/198.18.*` | 业务逻辑基本跨平台，平台事实来源需抽象 |
| `netwatch/speedtest/analysis.py` | VPN/TUN 判断仅覆盖 `utun/tun/tap/198.18.*` | 诊断规则偏 macOS/Linux，需要扩展 Windows 网卡关键词 |
| `netwatch/proxy_probe.py` | 优先 `curl`，再 `requests`，subprocess 文本解码 | 功能跨平台；Windows 无 curl 时可走 requests；编码仍需注意 |
| `netwatch/config.py` | `Path.home()`、`NETWATCH_CONFIG_PATH`、UTF-8 JSON | 基本跨平台；PowerShell/CMD 设置环境变量方式需文档提示 |
| `netwatch/device_location.py` | `webbrowser.open()`、本地 `HTTPServer`、UTF-8 HTML | 基本跨平台；浏览器权限和防火墙提示需手测 |
| `netwatch/cli_modules/location.py` | 展示主要网卡、IPv4、MAC、默认网关 | 展示层跨平台，但依赖底层 `network_info/router` |
| `netwatch/cli_modules/lan.py` | 调用 LAN 候选网卡和扫描 | 展示层跨平台，但 LAN 扫描结果取决于 Windows Ping/ARP 适配 |
| `netwatch/cli_modules/router.py` | 打开浏览器和默认网关 | 展示层基本跨平台，默认网关来源需 Windows backend |
| `netwatch/cli_modules/speedtest.py` | 展示物理网卡测速、brew 安装提示、VPN/TUN 判断 | 展示层需把安装提示和接口选择改为平台感知 |
| `tests/*` | 大量 monkeypatch/mocked tests；已有 scanner/router/speedtest/config/proxy/location 覆盖 | 适合新增 Windows parser/backend 单测，避免真实公网/浏览器/subprocess |

### 目前可能只适用于 macOS/Linux 的逻辑

- `netwatch/router.py:get_default_gateway()` 只识别 `Darwin` 和 `Linux`，Windows 上直接返回 `None`。
- `netwatch/router.py:parse_macos_default_gateway()`、`parse_linux_ip_route_gateway()`、`parse_linux_route_n_gateway()` 只覆盖 Unix 命令输出。
- `netwatch/scanner.py:parse_arp_output()` 只解析 `? (192.168.1.1) at aa:bb:...` 这种 macOS/BSD 风格，不解析 Windows `192.168.1.1  aa-bb-cc-dd-ee-ff  dynamic`。
- `netwatch/network_info.py:PREFERRED_PHYSICAL_INTERFACE_NAMES = ("en0", "en1")` 明显偏 macOS。
- `netwatch/network_info.py:VIRTUAL_INTERFACE_KEYWORDS` 缺少 Windows 常见虚拟网卡关键词，例如 `wintun`、`wireguard`、`clash`、`hyper-v`、`vethernet`、`vmware`、`virtualbox`。
- `netwatch/speedtest/backends/ookla_cli.py:OOKLA_CANDIDATE_PATHS` 只列 `/opt/homebrew/bin`、`/usr/local/bin`、`/usr/bin`。
- `netwatch/speedtest/backends/ookla_cli.py:INSTALL_HINT` 和 `netwatch/speedtest/runner.py` / `cli_modules/speedtest.py` 的安装提示只写 brew。
- `netwatch/speedtest/analysis.py:detect_vpn_tun()` 和 `netwatch/speedtest/runner.py:get_speedtest_quality_details()` 只识别 `utun/tun/tap/198.18.*`。
- `subprocess.run(..., text=True)` 在 `router.py`、`scanner.py`、`ookla_cli.py`、`librespeed_cli.py`、`proxy_probe.py` 中依赖默认 locale；中文 Windows 可能出现 cp936/UTF-8 输出混合问题。

### 已经天然跨平台或风险较低的逻辑

- `netwatch/speedtest/speed.py:sample_network_speed()` 使用 `psutil.net_io_counters()` 采样总上传/下载字节，Windows 可用。
- `netwatch/network_info.py:get_network_interfaces()` 使用 `psutil.net_if_addrs()`，Windows 可用，但 MAC family 和接口名称仍需实测。
- `netwatch/network_info.py:get_primary_ipv4()` 的 UDP socket route trick 通常跨平台。
- `netwatch/proxy_probe.py:probe_exit_ip()` 在无 curl 时会 fallback 到 `requests.get()`，Windows 可用。
- `netwatch/config.py` 使用 `Path.home()`、UTF-8 JSON、环境变量 override，Windows 可用。
- `netwatch/device_location.py` 的本地 HTTP server + `webbrowser.open()` 基本跨平台。
- Ookla/LibreSpeed/Python speedtest 的 JSON 解析逻辑本身跨平台；主要风险是二进制发现、PATH、`--interface` 参数和安装提示。

## Platform-Specific Risk Points

### 默认网关获取

当前 `netwatch/router.py:get_default_gateway()` 在 Windows 返回 `None`。Phase 1 应新增 Windows gateway backend，优先选择稳定且易 mock 的实现：

- 首选 `psutil.net_if_stats()` + `psutil.net_if_addrs()` 无法直接给默认网关，因此不够。
- 可选 `netifaces` 能取 gateways，但会增加依赖，不建议 Phase 1 引入。
- 建议 Phase 1 使用 Windows 命令解析，按优先级：
  - `route print -4`，解析 `0.0.0.0 0.0.0.0 <gateway> <interface> <metric>`。
  - `ipconfig` 作为 fallback，解析 `Default Gateway` / `默认网关` 后面的 IPv4。
  - PowerShell `Get-NetRoute -DestinationPrefix 0.0.0.0/0 | Sort-Object RouteMetric,InterfaceMetric` 作为 Phase 2 可选，不作为 Phase 1 首选，避免 PowerShell 执行策略和启动慢的问题。

### 网卡列表与主网卡选择

`psutil.net_if_addrs()` 能列出 Windows 接口，但接口名称可能是 `Wi-Fi`、`Ethernet`、`以太网`、`vEthernet (Default Switch)`、`VMware Network Adapter VMnet8`、`Tailscale`、`WireGuard Tunnel`、`Wintun Userspace Tunnel` 等。当前 `en0/en1` 偏好在 Windows 无意义。

建议把“主网卡选择”从简单名称排序升级为平台 backend 的评分函数，先保持保守规则：

- 有 IPv4，且不是 loopback/link-local/198.18.*。
- 优先默认网关所在 interface 或默认路由出接口。
- 优先常见物理名称：`Wi-Fi`、`WLAN`、`Ethernet`、`以太网`。
- 降低虚拟/隧道/容器接口分数：`vEthernet`、`Hyper-V`、`VMware`、`VirtualBox`、`Tailscale`、`WireGuard`、`Wintun`、`Clash`、`TUN`、`TAP`、`Loopback`。

### IPv4 / MAC 获取

当前 `network_info.get_network_interfaces()` 依赖 `socket.AF_INET` 和 `psutil.AF_LINK`。在 Windows 上 `psutil.AF_LINK` 通常可用，但 MAC 可能为空、全零或虚拟接口 MAC。Phase 1 应保留 psutil 实现并加 Windows fixture 测试，不急于引入 WMI。

### 实时流量统计

`sample_network_speed()` 使用全局 `psutil.net_io_counters()`，Windows 可用。Phase 1 不建议改成 per-interface，因为总吞吐更稳定，且不会受 Windows 接口名称变化影响。Phase 2/3 如需显示“物理网卡吞吐”，再由 platform backend 暴露 per-interface counters。

### ping 命令参数差异

`scanner.ping_host()` 已区分 Windows `ping -n 1 -w <ms>` 和 Unix `ping -c 1 -W <seconds>`。需要补单测覆盖 Windows 命令构造和 timeout 行为。注意 Windows `-w` 是每次 echo 超时毫秒，不是进程总超时；当前外层 `timeout=timeout_seconds + 1` 可以保留。

### arp -a 输出格式差异

当前 parser 不支持 Windows ARP 输出。Windows 典型输出：

```text
Interface: 192.168.1.20 --- 0x12
  Internet Address      Physical Address      Type
  192.168.1.1           aa-bb-cc-dd-ee-ff     dynamic
```

Phase 1 可把 LAN 扫描标记为 experimental；Phase 2 应新增 `parse_windows_arp_output()` 或让 `parse_arp_output()` 同时支持 `:` 和 `-` 分隔 MAC。

### speedtest.exe 路径与 PATH 检测

当前 `shutil.which("speedtest")` 理论上会在 Windows 识别 `speedtest.exe`，但 `os.path.exists()` 和固定候选路径只覆盖 Unix。Phase 1 建议：

- 在 Windows 候选中加入 `shutil.which("speedtest.exe")` 和 `shutil.which("speedtest")`。
- 不扫描 Program Files，避免误报和权限/路径本地化复杂度。
- 保留 `is_official_ookla_version()` 防止 Python `speedtest-cli` shadow。
- 安装提示改为平台感知：Windows 提示“从 Ookla 官方下载 speedtest.exe 并加入 PATH”，不要只显示 brew。

### PowerShell / CMD 环境变量差异

`NETWATCH_CONFIG_PATH` 当前通过 `os.environ.get()` 读取，代码跨平台。文档和测试需要覆盖两种 shell：

- PowerShell: `$env:NETWATCH_CONFIG_PATH="C:\Users\...\config.json"`
- CMD: `set NETWATCH_CONFIG_PATH=C:\Users\...\config.json`

实现层不需要区分 PowerShell/CMD。

### Windows 中文系统编码问题

`subprocess.run(..., text=True)` 会使用当前 locale。中文 Windows 常见 cp936/gbk，某些工具输出 UTF-8 或混合编码时可能 decode 失败或乱码。建议 platform 命令 runner 支持：

- `encoding="utf-8", errors="replace"` 优先用于已知 UTF-8 工具 JSON 输出。
- Windows 系统命令可先用 `encoding="mbcs", errors="replace"` 或 `locale.getpreferredencoding(False)`。
- parser 必须基于数字/IP/MAC 结构，不依赖中文标题。

### VPN / TUN / Wintun / Clash / Tailscale / VMware / Hyper-V 虚拟网卡干扰

当前排除关键词覆盖 docker、bridge、utun、tun、tap、awdl、llw、lo、vmnet、veth、tailscale。Windows 需要增加：

- `wintun`
- `wireguard`
- `clash`
- `tailscale`
- `zerotier`
- `hyper-v`
- `vethernet`
- `vmware`
- `virtualbox`
- `npcap`
- `loopback`
- `teredo`
- `isatap`

但不要简单“一刀切”全部隐藏：Phase 3 的“代理/当前出口测速”需要能提示当前走的是隧道/代理出口。建议平台 backend 同时返回 interface role/tag，例如 `physical`、`virtual`、`vpn`、`container`、`unknown`。

## Recommended Architecture

建议引入轻量平台抽象层，但只放“平台事实获取”和“平台命令解析”，不迁移业务逻辑。

建议结构：

```text
netwatch/
  platform/
    __init__.py
    base.py
    linux.py
    macos.py
    windows.py
```

### 应进入 platform backend 的函数

- `get_default_gateway()`：从 `netwatch/router.py` 迁移为平台 backend 提供，`router.py` 保留同名 facade。
- `get_network_interfaces()`：当前 `network_info.py` 可保留 facade，底层可委托 backend 处理 MAC family、接口 tag、编码/名称差异。
- `get_lan_scan_candidates()` / `get_preferred_physical_interface()` 的评分依据：业务层仍使用 `NetworkCandidate`，评分细节进入 backend 或 helper。
- `build_ping_command(ip, timeout_seconds)`：从 `scanner.ping_host()` 中抽出，便于测试 Windows/Unix 命令差异。
- `get_arp_commands()` / `parse_arp_output()`：平台 backend 提供命令和 parser，`scanner.get_arp_table()` 保留合并逻辑。
- `run_platform_command()`：统一 subprocess 编码和 timeout 策略，尤其处理 Windows 中文系统。
- `find_ookla_speedtest_binary()` 的候选路径生成或平台安装提示：保留后端解析 JSON，平台 backend 只提供候选和提示。
- `classify_interface(name, ipv4, mac)`：识别 physical/vpn/virtual/container/loopback。

### 应继续留在业务层的函数

- `scanner.scan_network()`：扫描流程、线程池、合并 ARP/reverse DNS 属于业务流程。
- `router.fetch_xiaomi_device_list()`、`merge_devices()` 等路由器 API 和设备合并逻辑。
- `speedtest/runner.py` 的后端优先级、fallback、最近结果缓存。
- `speedtest/analysis.py` 的指标质量判断可以保留，但 VPN/TUN 判断应调用接口分类 helper。
- `cli_modules/*` 的展示、提示、菜单和交互。
- `config.py` 的配置读写和非敏感偏好保存。
- `proxy_probe.py` 的公网出口业务逻辑。

### 避免业务层散落 `platform.system()`

应避免在 `network_info.py`、`router.py`、`scanner.py`、`speedtest/backends/ookla_cli.py` 中继续扩散平台判断。推荐：

- `netwatch.platform.get_backend()` 集中根据 `platform.system().lower()` 选择 backend。
- 旧公共函数保留原名称，内部委托 backend，保证 import 路径兼容。
- 测试通过 monkeypatch backend 或命令 runner，不需要真实 Windows 命令。

### 向后兼容策略

- 保留 `netwatch.network_info.*`、`netwatch.router.get_default_gateway()`、`netwatch.scanner.*`、`netwatch.speedtest.runner.*` 对外函数名。
- 兼容 wrapper 文件不改或只跟随底层实现。
- macOS/Linux backend 初期可以复用现有逻辑，避免行为漂移。
- Windows backend 新增能力时，先覆盖 Phase 1 函数，不一次性迁移所有模块。

## Phase 1 Scope

目标：“Windows 上能启动且核心功能可用”。

包含：

- `netwatch` CLI 能在 Windows 11 PowerShell/CMD 启动，不因平台判断或编码崩溃。
- 能显示公网 IP / 国家地区 / 城市 / ISP，即 `proxy_probe.probe_exit_ip()` 可走 `requests` fallback。
- 能显示本机主要网卡、IPv4、MAC、默认网关。
- 能显示实时上传/下载速度，使用现有 `psutil.net_io_counters()`。
- 能检测官方 `speedtest.exe` 是否存在，且能区分 Python `speedtest-cli` shadow。
- LAN 扫描保守支持：可以运行 Ping，ARP/MAC 在 Windows 上若不可解析则显示 `-`，并标记 experimental。
- Windows 安装提示不再只显示 brew。

不包含：

- 不要求 LAN 扫描在 Windows 上完整识别 MAC/hostname。
- 不要求精确识别所有虚拟/VPN 网卡。
- 不要求 speedtest.cn browser automation 在 Windows 默认真实跑通。
- 不要求 PowerShell `Get-NetRoute` 深度集成。
- 不引入 WMI/netifaces 等新依赖。

### Phase 1 验收标准

- `python -m compileall netwatch` 通过。
- `pytest -q` 通过，新增 Windows parser/command 单测全部 mock。
- 在 Windows 11 PowerShell 中 `python -m netwatch.cli` 可启动并进入菜单。
- 主菜单 2 能显示主要网卡、IPv4、MAC、默认网关、公网出口；失败时友好显示 `-` 或错误摘要。
- 主菜单 1 能显示实时网卡流量。
- 高级功能 9 能显示 Ookla 后端可用性；Windows 未安装时提示 `speedtest.exe` / PATH，不出现仅 brew 提示。
- 主菜单 3 在 Windows 上不崩溃；若 ARP 未适配完整，输出中明确 experimental/可能缺少 MAC。

## Phase 2 Scope

目标：完善 Windows LAN 扫描和主网卡选择。

包含：

- Windows `ping` 命令构造单测和 timeout 单测。
- Windows `arp -a` parser，支持 `aa-bb-cc-dd-ee-ff` 转为 `aa:bb:cc:dd:ee:ff`。
- `route print -4` 默认路由解析单测，必要时补 `ipconfig` fallback parser。
- 主网卡评分系统：
  - 默认路由出接口优先。
  - 物理接口优先。
  - 虚拟/VPN/容器接口降权。
  - link-local、loopback、198.18.* 排除。
- 虚拟网卡过滤关键词扩展：Wintun、WireGuard、Clash、Tailscale、VMware、Hyper-V、VirtualBox、ZeroTier。
- LAN 扫描 Windows 输出结果中尽量填充 MAC/hostname。

### Phase 2 验收标准

- 新增 `tests/test_windows_platform.py` 或拆分到现有 `test_scanner.py` / `test_router.py`，覆盖 Windows ARP、route print、ipconfig、interface scoring。
- Windows 11 普通用户权限下，快速扫描不会因 ICMP/ARP 权限或编码失败崩溃。
- 有 VMware/Hyper-V 虚拟网卡时，默认选择真实 Wi-Fi/Ethernet。
- 有 Tailscale/WireGuard/Clash 时，默认 LAN 扫描不误选隧道网卡。
- macOS/Linux 既有测试和行为不回退。

## Phase 3 Scope

目标：完善 VPN / 代理 / 当前出口诊断。

包含：

- 默认路由路径识别：展示当前默认路由出接口和当前 CLI 出口之间的关系。
- TUN/TAP/Wintun 网卡识别统一由 `classify_interface()` 输出。
- 浏览器授权定位 vs IP 定位差异提示：
  - 浏览器定位接近本机位置，公网 IP 定位是出口位置。
  - VPN/代理/Tailscale 场景下明确提示“显示的是出口，不代表真实所在地”。
- Speedtest 是否走 VPN/代理提示：
  - Ookla raw `interface` 字段识别 Windows VPN/虚拟接口。
  - speedtest 当前出口与 `probe_exit_ip()` 信息做弱关联。
- `show_proxy_exit_speedtest()` 和高级诊断复用同一套 interface classification。

### Phase 3 验收标准

- Windows 下开启 Clash/Tailscale/WireGuard 时，代理/当前出口测速能明确提示可能经过虚拟网卡或代理出口。
- 未开启 VPN/代理时，不误报常见物理 Wi-Fi/Ethernet。
- 浏览器定位与 IP 定位差异提示清晰，不保存公网 IP、真实位置、token、cookie。
- 所有公网访问、speedtest、browser automation 测试仍然 mock。

## Testing Plan

### 自动化测试

- `python -m compileall netwatch`
- `pytest -q`
- `python -m pytest -q`
- `git diff --check`

新增测试建议：

- `tests/test_router.py`：Windows `route print -4`、`ipconfig` 默认网关 parser。
- `tests/test_scanner.py`：Windows `ping` 命令参数、Windows `arp -a` parser。
- `tests/test_network_info.py`：Windows 接口分类和主网卡评分。
- `tests/test_speedtest_backends.py`：Windows `speedtest.exe` PATH 检测、官方 Ookla version 判断、Windows 安装提示。
- `tests/test_analysis.py`：Wintun/WireGuard/Tailscale/Clash/Hyper-V/VMware 诊断规则。

### 手动测试矩阵

- Windows 11 + PowerShell。
- Windows 11 + CMD。
- Windows 11 中文系统，终端默认编码 cp936/gbk。
- 无管理员权限环境。
- 已安装官方 Ookla `speedtest.exe` 且在 PATH。
- 未安装 `speedtest.exe`，但 Python `speedtest-cli` 存在。
- VMware / Hyper-V 存在，包含 `vEthernet`、`VMware Network Adapter VMnet*`。
- Clash / Tailscale / WireGuard 存在，包含 Wintun/TUN/TAP 类接口。
- 普通家庭网络 Wi-Fi/Ethernet，仅有一个真实网卡。
- ICMP 被防火墙限制时的 LAN 扫描失败路径。

## Compatibility Notes

- 现有 macOS/Linux 行为应通过 facade 保持：旧函数名不变，backend 初期复用现有命令和 parser。
- 不修改 `run_best_speedtest()` / `show_auto_speedtest()` 的后端实现逻辑；Windows 适配只改善其输入事实和安装提示。
- 主菜单 4 的 `speedtest.cn` browser automation 失败时仍不得 fallback 到 Ookla。
- 所有公网测速、curl、subprocess、requests、browser automation 测试必须 mock。
- 不保存密码、stok、token、cookie、公网 IP 或真实位置。
- 不逆向 speedtest.cn 私有 API。

## Open Questions

- Windows 是否允许新增可选依赖 `netifaces` 或 `ifaddr`？Phase 1 建议不加，Phase 2 再评估。
- 官方 Ookla Windows CLI 的 `--interface` 是否接受接口名称、IP、还是网卡索引更稳定？需要手测。
- Windows `route print -4` 在中文系统中的列宽和标题是否稳定？parser 应尽量只依赖数字行。
- 是否需要在 README 中把 Requirements 从“macOS 或 Linux”改为“macOS/Linux，Windows experimental”？建议 Phase 1 实现后再改。
- Windows LAN 扫描是否需要限制默认 workers，避免防火墙/杀软误报？Phase 2 手测后决定。

## Suggested File Changes

建议新增：

- `netwatch/platform/__init__.py`
- `netwatch/platform/base.py`
- `netwatch/platform/macos.py`
- `netwatch/platform/linux.py`
- `netwatch/platform/windows.py`
- `tests/test_platform_windows.py`
- `docs/windows-port-plan.md`

建议小步修改：

- `netwatch/router.py`：保留 `get_default_gateway()` facade，委托 platform backend。
- `netwatch/network_info.py`：保留 dataclass 和公共函数，逐步引入 interface classification/scoring。
- `netwatch/scanner.py`：抽出 ping/arp 命令和 parser 到 platform backend，保留扫描流程。
- `netwatch/speedtest/backends/ookla_cli.py`：平台感知候选路径和安装提示。
- `netwatch/speedtest/runner.py`：不要改调度逻辑，只调整平台化提示和 VPN/interface helper。
- `netwatch/speedtest/analysis.py`：调用统一 interface classification，扩展 Windows VPN/虚拟网卡识别。
- `netwatch/cli_modules/speedtest.py`：安装提示从 brew-only 改为平台感知。
- `README.md`：Phase 1 完成并手测后再标注 Windows experimental。

## Top 5 Risks

1. 默认网关解析错误导致主网卡选择错误，进而影响 LAN 扫描和 `--interface` 测速。
2. Windows ARP 输出和中文编码差异导致 LAN 扫描缺 MAC 或解析失败。
3. 虚拟/VPN 网卡数量多，错误选择 Wintun/Tailscale/Hyper-V/VMware 作为物理网卡。
4. `speedtest.exe` 与 Python `speedtest-cli` shadow 混淆，或 Windows `--interface` 参数不兼容。
5. 中文 Windows subprocess 解码问题导致 route/arp/ipconfig 输出乱码或异常。

## TODO for Next Codex Run

- [ ] 新增 `netwatch/platform/` 最小骨架和 backend selector。
- [ ] 将 `router.get_default_gateway()` 改为 facade，并为 Windows 新增 `route print -4` parser 单测。
- [ ] 新增 Windows `arp -a` fixture 和 parser 单测，先不改变 macOS parser 行为。
- [ ] 新增 interface classification helper，覆盖 Wintun / WireGuard / Clash / Tailscale / VMware / Hyper-V。
- [ ] 调整 Ookla binary detection：支持 `speedtest.exe` PATH 检测和 Windows 安装提示。
- [ ] 运行 `python -m compileall netwatch`、`pytest -q`、`python -m pytest -q`、`git diff --check`。
- [ ] 在 Windows 11 PowerShell 和 CMD 做 Phase 1 手动验收，并记录结果。
