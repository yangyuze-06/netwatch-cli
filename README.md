# netwatch-cli

`netwatch-cli` 是一个轻量级命令行网络状态工具。它提供交互式菜单，可以查看实时网卡吞吐量、本机网卡信息，用 ping 扫描局域网在线设备，并运行 Speedtest 测试公网最大带宽。

## 功能

- 查看实时网卡流量：每秒刷新 upload speed 和 download speed，自动显示为 KB/s 或 MB/s。它表示当前网卡实时吞吐量，不代表最大带宽。
- 查看本机网络信息：显示网卡名称、IPv4 地址和 MAC 地址。
- 局域网设备发现：支持快速扫描、增强扫描、仅从路由器同步设备列表。
- 运行带宽测速：主动连接公网测速服务器，显示 ping、download Mbps/MB/s 和 upload Mbps/MB/s。
- 代理/当前出口测速：显示 CLI 当前公网出口，再使用最佳可用测速后端测速。
- 打开路由器管理后台：自动识别默认网关，并提供常见品牌后台入口。
- 高级功能：列出 Speedtest 服务器、手动指定 server id 测速、显示测速后端信息和 Ookla selection details。
- 使用 `rich` 美化命令行输出。

## 实时网卡流量 vs Speedtest 最大带宽

实时网卡流量来自 `psutil.net_io_counters()`，表示当前这一秒经过本机网卡的上传/下载流量。它适合观察“现在有没有流量”“当前应用大概用了多少吞吐”，但不代表宽带线路的最大能力。

V0.8 以后测速使用多后端架构，优先级是：

1. `official-ookla-cli`：官方 Ookla CLI，推荐，通常更接近网页测速或官方客户端。
2. `librespeed-cli`：开源备选测速后端，测速网络和 Ookla 不同。
3. `python-speedtest-cli`：Python 社区版 fallback，结果可能低于网页测速或官方客户端。

macOS 推荐安装官方 Ookla CLI：

```bash
brew tap teamookla/speedtest
brew install speedtest
```

不要把 `brew install speedtest-cli` 当成官方 Ookla CLI；`speedtest-cli` 是社区版工具，Homebrew 已标记为 deprecated。Python fallback 可通过 `pip install speedtest-cli` 安装。

`Mbps` 是 megabits per second，常用于运营商宽带标称速度；`MB/s` 是 megabytes per second，更接近日常下载文件时看到的速度。换算规则：

```text
Mbps = bit/s / 1_000_000
MB/s = bit/s / 8 / 1_000_000
```

自动测速的服务器选择可能受地理位置、运营商路由、服务器负载影响而波动。如果结果明显异常，可以使用“选择服务器测速”，先列出附近服务器，再手动输入 server id。

## 代理/当前出口测速

“代理/当前出口测速”会先请求 `https://ipinfo.io/json`，显示当前 CLI 进程看到的公网出口 IP、城市、国家/地区和 ISP/组织，然后调用最佳可用测速后端。

限制：

- TUN/VPN 模式通常会影响 CLI 出口。
- 浏览器代理通常只影响浏览器，不一定影响 CLI。
- 本工具只检测当前 CLI 进程实际看到的公网出口，不保存公网 IP。

## 为什么可能需要手动选择网卡

开发机上经常会有 VPN、Docker、虚拟机、隧道或系统服务创建的虚拟网卡，例如 `utun`、`bridge`、`vmnet`、`veth`、`tailscale` 等。有些环境还会出现 `198.18.0.0/15` 这类基准测试保留网段。如果直接拿第一个 IPv4 地址扫描，可能会扫错网段，甚至得到大量无意义的 online 结果。

当存在多个可用候选网卡时，`netwatch-cli` 会让你手动选择，并在扫描前显示网卡名称、当前 IP 和推测扫描网段，确认后才开始扫描。

## MAC 地址来源

局域网扫描中的 MAC 地址来自本机 ARP cache。工具会先 ping 扫描在线 IP，扫描结束后重新执行一次 `arp -a`，再用 IP 补全 MAC 地址。

这意味着 MAC 解析通常要求设备和本机处在同一个二层局域网内。如果目标设备在不同 VLAN、不同子网、隔着路由器，或系统 ARP cache 中没有对应记录，MAC 可能显示为 `-`。

## 局域网设备发现

局域网设备发现有三种模式：

- 快速扫描：`Ping + ARP`，用于确认当前可连通设备，并从本机 ARP cache 补 MAC。
- 增强扫描：`Ping + ARP + 路由器设备名`，先扫描连通性，再可选同步小米/Redmi 路由器设备名，并合并结果。
- 仅从路由器同步设备列表：不跑 ping，只读取路由器 API 中的设备列表。

增强扫描融合：

- Ping 连通性。
- ARP MAC 缓存。
- 路由器设备名。

最终表格显示：

```text
Name | IP | MAC | Source | Status
```

## 小米路由器设备名同步

很多设备不会暴露 hostname，ARP 和 reverse DNS 经常只能拿到 IP/MAC。小米/Redmi 路由器后台通常有更完整的设备名、IP 和 MAC。本工具可以在你已经登录路由器后台后，只读调用设备列表 API，把路由器设备名和扫描结果合并。

使用流程：

1. 选择“打开路由器管理后台”，登录小米/Redmi 路由器。
2. 登录后复制浏览器地址栏中的完整 URL，通常包含 `;stok=xxxx`。
3. 回到 CLI，进入“局域网设备发现”，选择“增强扫描”或“仅从路由器同步设备列表”，粘贴该 URL。
4. 工具会请求：
   ```text
   http://<router-ip>/cgi-bin/luci/;stok=<STOK>/api/misystem/devicelist?mlo=1
   http://<router-ip>/cgi-bin/luci/;stok=<STOK>/api/misystem/devicelist
   ```
5. 同步成功后，设备表会按 MAC 优先、IP 其次合并路由器名称和扫描结果。

安全边界：

- 不自动爆破。
- 不绕过登录。
- 不保存路由器密码。
- `stok` 默认只在本次运行内存中使用，不落盘。
- 只读取设备列表，不实现任何修改路由器配置的 API。
- API 失败时回退到 ARP / reverse DNS / mDNS 可获得的信息。

该功能目前主要适配小米路由器 / Redmi 路由器，其他品牌后续支持。

## 路由器管理后台入口

“打开路由器管理后台”支持：

- 当前默认网关。
- `192.168.31.1` / `miwifi.com`
- `192.168.0.1`
- `192.168.1.1`
- `192.168.50.1`
- `tplinkwifi.net`
- `router.asus.com`
- 手动输入 IP、域名或完整 URL。

## 安装方法

```bash
cd /Users/y4n9/Workspace/Projects/My-github-projects/netwatch-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

也可以用可编辑安装启用 `netwatch` 命令：

```bash
pip install -e .
```

## 开发测试

```bash
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest
pytest -q
```

## 使用方法

直接运行模块：

```bash
python -m netwatch.cli
```

如果已经执行 `pip install -e .`，也可以运行：

```bash
netwatch
```

启动后会看到交互式菜单：

```text
1. 查看实时网卡流量
2. 查看本机网络信息
3. 局域网设备发现
4. 带宽测速
5. 代理/当前出口测速
6. 打开路由器管理后台
7. 高级功能
8. 退出
```

查看实时网卡流量时，按 `Ctrl+C` 返回菜单。主菜单按 `Ctrl+C` 会优雅退出。

如果只能使用 Python fallback，可执行：

```bash
pip install speedtest-cli
```

## 功能截图占位

> TODO: 后续补充终端截图。

```text
[screenshot placeholder]
```

## Roadmap

- 增加厂商信息识别，例如基于 MAC OUI 查询 vendor。
- 增加扫描进度显示和超时配置。
- 支持指定网段扫描。
- 支持导出扫描结果为 JSON/CSV。
- 增加单元测试和 CI。
- 增加跨平台 ping 参数适配测试。
- 支持 Speedtest 结果历史记录。
- 集成官方 Ookla CLI 安装检测和更丰富的 selection details 展示。
- 支持更多测速后端和结果对比。

更多 V0.2 修复记录见 [docs/v0.2-plan.md](docs/v0.2-plan.md)。
更多 V0.3 修复记录见 [docs/v0.3-plan.md](docs/v0.3-plan.md)。
更多 V0.5 修复记录见 [docs/v0.5-plan.md](docs/v0.5-plan.md)。
更多 V0.6 修复记录见 [docs/v0.6-plan.md](docs/v0.6-plan.md)。
更多 V0.7 修复记录见 [docs/v0.7-plan.md](docs/v0.7-plan.md)。
更多 V0.8 修复记录见 [docs/v0.8-plan.md](docs/v0.8-plan.md)。

## 为什么部分设备无法显示主机名

局域网扫描会优先用 `socket.gethostbyaddr(ip)` 做反向解析，然后尝试从 `arp -a` 输出中读取 hostname。仍然显示 `-` 通常是正常现象，常见原因包括：

- 设备未开放或未广播 hostname。
- 路由器不提供反向 DNS。
- iOS/macOS 使用隐私地址或限制局域网发现。
- 防火墙阻止发现或 ICMP/ARP 信息不完整。
