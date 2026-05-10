# netwatch-cli

`netwatch-cli` 是一个轻量级命令行网络状态工具。第一阶段提供交互式菜单，可以查看实时网卡吞吐量、本机网卡信息，用简单的 ping 扫描局域网在线设备，并运行 Speedtest 测试公网带宽。

## 功能

- 查看实时网卡流量：每秒刷新 upload speed 和 download speed，自动显示为 KB/s 或 MB/s。它表示当前网卡实时吞吐量，不代表最大带宽。
- 查看本机网络信息：显示网卡名称、IPv4 地址和 MAC 地址。
- 扫描局域网在线设备：根据本机 IPv4 推测 `/24` 网段，并通过 ping 检测在线主机。
- 运行 Speedtest 测速：显示 ping、download Mbps 和 upload Mbps。
- 使用 `rich` 美化命令行输出。

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
