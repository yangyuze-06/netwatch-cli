# netwatch-cli

`netwatch-cli` 是一个轻量级命令行网络状态工具。它提供交互式菜单，可以查看实时网卡吞吐量、本机网卡信息，用 ping 扫描局域网在线设备，并运行 Speedtest 测试公网最大带宽。

## 功能

- 查看实时网卡流量：每秒刷新 upload speed 和 download speed，自动显示为 KB/s 或 MB/s。它表示当前网卡实时吞吐量，不代表最大带宽。
- 查看本机网络信息：显示网卡名称、IPv4 地址和 MAC 地址。
- 局域网设备发现：支持快速扫描、增强扫描、仅从路由器同步设备列表。
- 运行带宽测速：主动连接公网测速服务器，默认优先使用真实物理网卡，显示 ping、download Mbps/MB/s 和 upload Mbps/MB/s。
- 代理/当前出口测速：显示 CLI 当前公网出口，再使用最佳可用测速后端测速，不强制指定物理网卡。
- 打开路由器管理后台：自动识别默认网关，并提供常见品牌后台入口。
- 高级功能：指定 Ookla server id 测速、按关键词筛选服务器、按运营商/城市预设优选服务器、保存常用服务器、查看测速后端信息、Ookla selection details，以及打开 `speedtest.cn` 网页对照。
- 使用 `rich` 美化命令行输出。

## 实时网卡流量 vs Speedtest 最大带宽

实时网卡流量来自 `psutil.net_io_counters()`，表示当前这一秒经过本机网卡的上传/下载流量。它适合观察“现在有没有流量”“当前应用大概用了多少吞吐”，但不代表宽带线路的最大能力。

V0.8 以后测速使用多后端架构，优先级是：

1. `official-ookla-cli`：官方 Ookla CLI，推荐，通常更接近网页测速或官方客户端。
2. `librespeed-cli`：开源备选测速后端，测速网络和 Ookla 不同。V0.9 支持自定义 `server-json` URL 或本地 `local-json` 文件。
3. `python-speedtest-cli`：Python 社区版 fallback，结果可能低于网页测速或官方客户端。

macOS 推荐安装官方 Ookla CLI：

```bash
brew tap teamookla/speedtest
brew install speedtest
```

不要把 `brew install speedtest-cli` 当成官方 Ookla CLI；`speedtest-cli` 是社区版工具，Homebrew 已标记为 deprecated。Python fallback 可通过 `pip install speedtest-cli` 安装。

如果项目虚拟环境里的 `.venv/bin/speedtest` shadow 了 Homebrew 的官方命令，`netwatch-cli` 会优先探测常见官方路径，例如 `/opt/homebrew/bin/speedtest` 和 `/usr/local/bin/speedtest`，并通过 `speedtest --version` 判断是否为 `Speedtest by Ookla`，避免误用 Python 社区版。

`Mbps` 是 megabits per second，常用于运营商宽带标称速度；`MB/s` 是 megabytes per second，更接近日常下载文件时看到的速度。换算规则：

```text
Mbps = bit/s / 1_000_000
MB/s = bit/s / 8 / 1_000_000
```

普通“带宽测速”会优先识别真实 LAN/Wi-Fi 网卡，例如 macOS 上的 `en0` / `en1`，并把它传给官方 Ookla CLI 的 `--interface` 参数，尽量避开 `utun`、`tun`、`tap`、`198.18.0.0/15` 等 TUN/VPN 或虚拟出口。如果官方 CLI 不支持该参数或该网卡测速失败，工具会不带 interface 重试，再按后端优先级 fallback。

Ookla 自动选服可能受公网出口、运营商路由、服务器负载和 TUN/VPN 影响。它和 `speedtest.cn` 网页使用的服务器池不一定相同，例如网页能选到“广东移动_Vixtel_1”并不代表 Ookla CLI 一定能选到同一节点。`speedtest.cn` SDK/API 目前不作为默认后端，因为没有公开免费 CLI API；后续可以作为授权后端扩展。

如果结果明显异常，可以进入“高级功能”，用“按关键词筛选服务器测速”，输入 `Guangzhou`、`Guangdong`、`China Mobile`、`Mobile`、`Hong Kong`、`Tokyo`、`IPA` 等关键词筛选 Ookla 服务器，然后手动指定 server id 或让工具自动测试前 3 个候选。找到相对稳定的服务器后，可以保存为默认测速服务器。

V0.9 起，高级功能也支持 LibreSpeed 自定义服务器列表测速：

- 远程列表：`--server-json <url>`
- 本地列表：`--local-json <file>`
- 可保存常用 LibreSpeed 配置到 `~/.netwatch/config.json`

LibreSpeed 是开源测速后端，公共节点免费但质量不保证；测速结果取决于 server list 中的服务器质量。自建或可信的近距离节点通常更可靠，但它仍不能承诺复现 `speedtest.cn` 网页中的“广东移动_Vixtel_1”结果。

## 常用测速服务器配置

V0.8.3 起，`netwatch-cli` 支持把最近一次成功测速的 Ookla server id 保存为默认配置：

```text
~/.netwatch/config.json
```

配置只保存非敏感信息，例如 backend、server id、server name、location、interface，不保存密码、token、stok 或公网 IP。普通“带宽测速”检测到默认服务器后会先询问是否使用；如果该服务器测速失败，会自动回退到自动测速。

LibreSpeed 自定义列表配置会保存在同一文件的 `preferred_librespeed` 中，只保存 URL/path/duration，不保存 token、cookie 或公网 IP。

测速结果展示后会做基础质量诊断。如果出现高 ping、高 jitter、丢包或下载速度明显偏低，会提示“当前测速结果可能不代表真实最大带宽”，并建议尝试指定测速服务器或用浏览器测速对照。

当前推荐做法：

- `official-ookla-cli` 作为默认通用后端。
- 保存本地实测最快、最稳定的 Ookla server id。
- 如有可信 LibreSpeed server list，可用高级功能保存远程 `server-json` 或本地 `local-json`。
- 把 `speedtest.cn` 网页作为对照基准。
- 高级功能支持“打开 speedtest.cn 网页对照测速”，通过浏览器打开对照页面。netwatch-cli 不会自动读取 speedtest.cn 网页结果、不逆向私有 API、不支持手动回填。
- 本项目暂不逆向 `speedtest.cn` 私有网页 API；未来如果有正式 SDK/API 授权，会作为独立后端接入。自动浏览器读取（如 Playwright）可作为未来实验方向，但当前版本不实现。

## 代理/当前出口测速

“代理/当前出口测速”会先请求 `https://ipinfo.io/json`，显示当前 CLI 进程看到的公网出口 IP、城市、国家/地区和 ISP/组织，然后调用最佳可用测速后端。这个功能保留当前进程出口行为，不会强制指定 `en0` / `en1`。

限制：

- TUN/VPN 模式通常会影响 CLI 出口。
- 浏览器代理通常只影响浏览器，不一定影响 CLI。
- 本工具只检测当前 CLI 进程实际看到的公网出口，不保存公网 IP。
- 如果看到 Ookla JSON 中 `interface.name = utun*`、`internalIp = 198.18.*`，说明测速可能走了 TUN/VPN 出口；普通“带宽测速”会尝试避开它，而“代理/当前出口测速”会保留它。

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

## AI Agent Handoff

本项目可由 Codex / Claude Code 等 coding agent 协作维护。

- 交接文档见 [docs/handoff-to-codex.md](docs/handoff-to-codex.md)（推荐，最新）。
- Claude Code 接手文档见 [docs/handoff-to-claude.md](docs/handoff-to-claude.md)。
- Agent 项目指令见 [AGENTS.md](AGENTS.md)。
- Claude Code 专用入口见 [CLAUDE.md](CLAUDE.md)。

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
- 增加授权的 speedtest.cn 或运营商专用测速后端扩展。
- 增强 Ookla 服务器关键词筛选和多服务器自动对比策略。
- 增强 LibreSpeed 自定义服务器列表体验。

更多 V0.2 修复记录见 [docs/v0.2-plan.md](docs/v0.2-plan.md)。
更多 V0.3 修复记录见 [docs/v0.3-plan.md](docs/v0.3-plan.md)。
更多 V0.5 修复记录见 [docs/v0.5-plan.md](docs/v0.5-plan.md)。
更多 V0.6 修复记录见 [docs/v0.6-plan.md](docs/v0.6-plan.md)。
更多 V0.7 修复记录见 [docs/v0.7-plan.md](docs/v0.7-plan.md)。
更多 V0.8 修复记录见 [docs/v0.8-plan.md](docs/v0.8-plan.md)。
更多 V0.8.2 修复记录见 [docs/v0.8.2-plan.md](docs/v0.8.2-plan.md)。
更多 V0.8.3 修复记录见 [docs/v0.8.3-plan.md](docs/v0.8.3-plan.md)。
更多 V0.9 修复记录见 [docs/v0.9-plan.md](docs/v0.9-plan.md)。

## 为什么部分设备无法显示主机名

局域网扫描会优先用 `socket.gethostbyaddr(ip)` 做反向解析，然后尝试从 `arp -a` 输出中读取 hostname。仍然显示 `-` 通常是正常现象，常见原因包括：

- 设备未开放或未广播 hostname。
- 路由器不提供反向 DNS。
- iOS/macOS 使用隐私地址或限制局域网发现。
- 防火墙阻止发现或 ICMP/ARP 信息不完整。
