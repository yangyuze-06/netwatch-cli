# netwatch-cli

`netwatch-cli` 是一个轻量、交互式的命令行网络诊断工具，用于查看本机网络状态、发现局域网设备，并通过多个后端运行公网测速。

## 功能

- 查看实时网卡上传/下载吞吐量。
- 查看本机网卡名称、IPv4 地址和 MAC 地址。
- 通过 Ping + ARP 发现局域网在线设备。
- 打开默认网关和常见路由器管理后台。
- 使用多后端运行公网带宽测速。
- 检查代理/当前 CLI 出口并测速。
- 支持测速服务器筛选、常用配置保存和结果质量提示。
- 高级功能中提供 `speedtest.cn` browser automation 实验入口。

## Quick Start

```bash
cd /Users/y4n9/Workspace/Projects/My-github-projects/netwatch-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m netwatch.cli
```

可选：启用 `netwatch` 命令。

```bash
source .venv/bin/activate
pip install -e .
netwatch
```

macOS 推荐安装官方 Ookla CLI：

```bash
brew tap teamookla/speedtest
brew install speedtest
```

不要把 `brew install speedtest-cli` 当成官方 Ookla CLI；`speedtest-cli` 是 Python 社区版工具，Homebrew 已标记为 deprecated。

## 使用

```bash
python -m netwatch.cli
```

主菜单：

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

## 测速后端

测速后端按以下顺序 fallback：

1. `official-ookla-cli`：官方 Ookla CLI，推荐使用。
2. `librespeed-cli`：开源备选后端，支持自定义 `server-json` URL 或本地 `local-json` 文件。
3. `python-speedtest-cli`：Python 社区版 fallback，结果可能低于浏览器测速或官方客户端。

普通“带宽测速”会尽量选择真实 LAN/Wi-Fi 网卡，例如 macOS 上的 `en0` / `en1`，并避开 `utun`、`tun`、`tap`、`198.18.0.0/15` 等 TUN/VPN 或虚拟出口。

“代理/当前出口测速”会保留当前 CLI 进程实际出口，先显示公网出口信息，再调用最佳可用后端测速。公网 IP 只用于诊断展示，不会保存。

## 测速边界

实时网卡流量不等于最大带宽。它表示当前这一秒本机正在使用的吞吐量；Speedtest 会主动连接公网测速服务器，用于估算线路能力。

Ookla、LibreSpeed 和 `speedtest.cn` 的服务器池不同。某个后端测速偏低，可能是选服、距离、负载、运营商路由或代理/TUN 影响，不一定代表本地宽带异常。

`speedtest.cn` 只作为网页对照入口。本项目不逆向 `speedtest.cn` 私有 API，不抓取隐藏接口，也不支持手动粘贴测速结果回填。

V0.10 增加了实验功能：`speedtest.cn` browser automation。它默认以 `headless=True` 后台启动 Playwright/Chromium，不打开可见浏览器窗口；只在用户明确选择 debug 可见浏览器模式时才使用 `headless=False`。它会打开网页、点击测速并从 DOM 文本读取结果，但不等同于官方 API 后端，不抓包、不读取 Cookie、不逆向私有接口，也不会进入默认带宽测速主流程。当前稳定后端仍是 Ookla / LibreSpeed / Python fallback。

启用该实验功能需要可选依赖：

```bash
pip install -e ".[browser]"
playwright install chromium
```

也可以直接安装：

```bash
pip install playwright
playwright install chromium
```

默认不保存截图。只有用户在实验入口中确认保存 debug screenshot 时，才会写入 `~/.netwatch/debug/`；截图可能包含页面状态，不要上传或提交到 Git。Debug screenshot 和可见浏览器是两个独立选项，保存截图不代表浏览器会变成可见窗口。

`speedtest.cn` 页面/CDN 可能对 headless Chromium、HTTP/2 或自动化环境不友好，已知失败模式包括 `ERR_HTTP2_PROTOCOL_ERROR`。工具会先在 headless 模式下用兼容参数自动重试一次；如果仍失败，只会询问是否切换到可见浏览器调试模式，不会静默打开可见窗口。

## 配置

配置文件：

```text
~/.netwatch/config.json
```

只保存非敏感偏好，例如：

- 常用 Ookla backend、server id、server name、location、interface。
- 常用 LibreSpeed `server-json` URL 或本地 `local-json` 路径。
- 测试 duration。

不会保存密码、路由器凭据、`stok`、token、cookie 或公网 IP。

## 路由器与局域网

局域网设备发现依赖 Ping 和本机 ARP cache。MAC 地址通常只对同一二层局域网内的设备可靠。

路由器设备名同步是实验功能，目前只支持小米/Redmi `stok` API 的只读设备列表。GSWIFI / OpenWrt / LuCI / 其他厂商后台暂不自动同步，请优先使用快速扫描。

## 开发测试

```bash
source .venv/bin/activate
python -m compileall netwatch
pytest -q
python -m pytest -q
git diff --check
```

所有公网测速、subprocess、`curl`、`requests`、Playwright 浏览器访问和路由器 API 测试都必须 mock。

## 文档

- [Codex handoff](docs/handoff-to-codex.md)
- [Claude handoff](docs/handoff-to-claude.md)
- [V0.8.2 plan](docs/v0.8.2-plan.md)
- [V0.8.3 plan](docs/v0.8.3-plan.md)
- [V0.9 plan](docs/v0.9-plan.md)
- [V0.9.3 plan](docs/v0.9.3-plan.md)
- [speedtest.cn browser automation experiment](docs/speedtest-cn-browser-automation.md)
