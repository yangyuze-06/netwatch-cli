# netwatch-cli

`netwatch-cli` 是一个轻量级命令行网络状态工具。它提供交互式菜单，可以查看实时网卡吞吐量、本机网卡信息，用 ping 扫描局域网在线设备，并运行 Speedtest 测试公网最大带宽。

## 功能

- 查看实时网卡流量：每秒刷新 upload speed 和 download speed，自动显示为 KB/s 或 MB/s。它表示当前网卡实时吞吐量，不代表最大带宽。
- 查看本机网络信息：显示网卡名称、IPv4 地址和 MAC 地址。
- 扫描局域网在线设备：过滤 loopback、链路本地、`198.18.0.0/15` 和常见虚拟网卡，根据候选真实网卡推测 `/24` 网段，并通过 ping 检测在线主机。
- 运行 Speedtest 测速：主动连接公网测速服务器，显示 ping、download Mbps 和 upload Mbps。
- 使用 `rich` 美化命令行输出。

## 实时网卡流量 vs Speedtest 最大带宽

实时网卡流量来自 `psutil.net_io_counters()`，表示当前这一秒经过本机网卡的上传/下载流量。它适合观察“现在有没有流量”“当前应用大概用了多少吞吐”，但不代表宽带线路的最大能力。

Speedtest 测速使用 `speedtest-cli` 主动选择测速服务器，并分别压测下载和上传能力。`speedtest` 库返回的是 bit/s，`netwatch-cli` 会用 `bit/s / 1_000_000` 换算成 Mbps。

## 为什么可能需要手动选择网卡

开发机上经常会有 VPN、Docker、虚拟机、隧道或系统服务创建的虚拟网卡，例如 `utun`、`bridge`、`vmnet`、`veth`、`tailscale` 等。有些环境还会出现 `198.18.0.0/15` 这类基准测试保留网段。如果直接拿第一个 IPv4 地址扫描，可能会扫错网段，甚至得到大量无意义的 online 结果。

当存在多个可用候选网卡时，`netwatch-cli` 会让你手动选择，并在扫描前显示网卡名称、当前 IP 和推测扫描网段，确认后才开始扫描。

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
3. 扫描局域网在线设备
4. 运行 Speedtest 测速
5. 退出
```

查看实时网卡流量时，按 `Ctrl+C` 返回菜单。主菜单按 `Ctrl+C` 会优雅退出。

如果运行 Speedtest 时提示未安装依赖，请执行：

```bash
pip install speedtest-cli
```

## 功能截图占位

> TODO: 后续补充终端截图。

```text
[screenshot placeholder]
```

## Roadmap

- 增加主机名解析开关。
- 增加扫描进度显示和超时配置。
- 支持指定网段扫描。
- 支持导出扫描结果为 JSON/CSV。
- 增加单元测试和 CI。
- 增加跨平台 ping 参数适配测试。
- 支持 Speedtest 结果历史记录。

更多 V0.2 修复记录见 [docs/v0.2-plan.md](docs/v0.2-plan.md)。
