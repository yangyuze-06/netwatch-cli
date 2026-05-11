# Handoff to Codex

## 1. 本轮 Claude Code 完成了什么

最近几轮实际完成的工作：

- **删除 speedtest.cn 手动录入/粘贴结果功能**：移除高级菜单中"记录 speedtest.cn 网页测速结果"入口。
- **删除 speedtest.cn manual parser**：移除 `parse_speedtest_cn_manual_input()` 及全部 helper 函数、常量和 14 个相关测试。
- **高级功能菜单重排为 11 项**：按逻辑顺序排列——server 选择工具在前，配置管理居中，诊断和网页对照在末尾。
- **speedtest.cn 只保留"打开网页对照测速"**：`show_open_speedtest_cn()` 使用 `webbrowser.open()`，不询问用户粘贴结果，不要求手动录入。
- **明确 netwatch-cli 不自动读取 speedtest.cn 网页结果**：文档和代码注释中已写明。
- **明确不逆向 speedtest.cn 私有 API**。
- **保留以下高级功能**：指定 Ookla server id 测速、关键词筛选、运营商/城市预设、保存默认服务器、查看/清除测速配置、测速摘要、测速后端信息、Ookla selection details。
- **新增测速质量诊断**：`get_speedtest_quality_details()` — 按触发条件（高 ping、高 jitter、丢包、低 download、TUN/VPN）返回针对性建议。
- **新增 ISP 预设关键词优化**：`build_isp_preset_keywords()` — China Mobile 优先关键词不含 Hong Kong，Guangzhou/Guangdong 优先排序，Hong Kong 仅作为最后 fallback 并显示警告。
- **测试通过：58 passed**。
- **README 和 docs/handoff-to-claude.md 已更新相关边界说明**。

当前版本：**V0.8.3**。最近提交：

```
27e097d refactor: Remove manual speedtest.cn entry, reorganize advanced menu
0ce4b93 fix: Improve ISP preset keywords and add targeted speedtest quality advice
```

## 2. 当前高级功能菜单

```
1. 指定 Ookla server id 测速
2. 按关键词筛选 Ookla 服务器测速
3. 按当前运营商/城市优选服务器
4. 保存最近一次成功测速服务器为默认
5. 清除默认测速服务器
6. 查看当前测速配置
7. 显示最近一次测速摘要
8. 显示测速后端信息
9. 显示 Ookla server selection details
10. 打开 speedtest.cn 网页对照测速
11. 返回主菜单
```

对应函数均在 `netwatch/cli.py` 中。

## 3. 当前测速模块定位

- **Official Ookla CLI**：默认通用测速后端（`netwatch/speedtest_backends/ookla_cli.py`）。使用绝对路径 `/opt/homebrew/bin/speedtest`，已验证可区分 `.venv/bin/speedtest` 的 Python shadow。
- **Python speedtest-cli**：仅作为 fallback（`netwatch/speedtest_backends/python_speedtest.py`），结果可能偏低，已标注提示。
- **LibreSpeed CLI**：雏形后端（`netwatch/speedtest_backends/librespeed_cli.py`），目前仅尝试 `--json` / `-f json` 两种参数，不支持指定 server id。后续可扩展 custom server list。
- **speedtest.cn**：只是浏览器网页对照入口，**不是 CLI 后端**。不使用、不调用、不抓包、不逆向 speedtest.cn 私有 API。未来如有 speedtest.cn 官方 SDK/API 授权，可作为独立后端接入。
- **Playwright 自动浏览器测速**：未来实验方向，不在当前稳定菜单里实现。
- **LibreSpeed / iperf3 / HTTP file download test**：后续更现实的可控测速方向。

## 4. 已知真实网络现象

- 用户 `speedtest.cn` 网页可以选到**"广东移动_Vixtel_1"**，Ping 约 7–8ms，下载可达 700–1000 Mbps。
- Official Ookla CLI 在当前环境下经常选到 **Hong Kong / Tokyo / Korea / Russia** 等节点，结果可能只有几 Mbps。
- 根因主要是**测速服务器池不匹配**（Ookla server pool 与 speedtest.cn server pool 不同），**不代表用户本地宽带差**。
- `--interface en0` 可以避开 `utun` / TUN 出口，但不能保证 Ookla 找到广州移动优质节点。
- 免费公共后端不一定能复现 speedtest.cn 的专属/合作节点结果。

## 5. 当前代码关键文件

| 文件 | 职责 |
|------|------|
| `netwatch/cli.py` | 主菜单、高级菜单、展示逻辑 |
| `netwatch/speedtest_runner.py` | 测速调度、fallback、质量诊断、server keyword filter、ISP 预设关键词、最近一次测速结果缓存 |
| `netwatch/config.py` | `~/.netwatch/config.json` 配置读写，仅保存非敏感信息（server id、name、location、interface） |
| `netwatch/network_info.py` | 网卡识别、物理接口选择、TUN/utun/198.18.0.0/15 过滤 |
| `netwatch/proxy_probe.py` | 当前 CLI 公网出口 IP 检测（ipinfo.io） |
| `netwatch/router.py` | 默认网关、路由器后台 URL、小米 LuCI API、设备合并 |
| `netwatch/scanner.py` | 局域网扫描、ARP/MAC/hostname |
| `netwatch/speed.py` | 实时网卡流量采样 |
| `netwatch/speedtest_backends/models.py` | `SpeedtestResult` 数据结构 |
| `netwatch/speedtest_backends/ookla_cli.py` | 官方 Ookla CLI 后端 |
| `netwatch/speedtest_backends/python_speedtest.py` | Python speedtest-cli fallback |
| `netwatch/speedtest_backends/librespeed_cli.py` | LibreSpeed CLI 后端（雏形） |
| `tests/test_speedtest_backends.py` | 测速相关测试（58 total，含后端、质量诊断、ISP 预设、网页对照） |
| `tests/test_proxy_probe.py` | 出口 IP 检测测试 |
| `tests/test_config.py` | 配置读写测试 |
| `tests/test_router.py` | 路由器相关测试 |
| `tests/test_scanner.py` | 局域网扫描测试 |

## 6. 下一步建议给 Codex

### P0
- [x] 确认当前代码已提交（commit `27e097d`）。
- [ ] 继续保持 `compileall + pytest` 全绿（当前 58 passed）。
- [ ] 避免再加入 speedtest.cn 手动录入功能。

### P1
- [ ] 完善保存常用 Ookla server id 的体验（当前已支持保存/清除/查看，但交互可优化）。
- [ ] 完善测速质量诊断（当前已有针对性建议，可进一步细化）。
- [ ] 完善最近一次测速摘要（当前 `show_last_speedtest_raw_summary` 展示字段有限）。

### P2
- [ ] 调研并实现 **LibreSpeed custom server list**：
  - 支持 `--server-json URL`。
  - 支持 `--local-json` 文件。
  - 支持保存常用 LibreSpeed server list。
  - 明确公共节点质量不保证。
- [ ] 调研 **HTTP file download test**（不依赖任何测速 CLI 后端）：
  - HTTP/HTTPS 大文件下载。
  - 固定时长（例如 10 秒）。
  - 多连接（可选）。
  - 只统计 bytes，不落盘。
  - 说明结果取决于文件服务器质量。

### P3
- [ ] 设计 Playwright speedtest.cn browser automation 实验功能文档：
  - 后台浏览器打开 speedtest.cn。
  - 自动点击测速。
  - 优先读取 DOM 文本。
  - 截图/OCR 只作为未来 fallback。
  - 不调用私有 API。
  - 不绕过验证码/风控。
  - 不作为默认功能。
- [ ] iperf3 局域网/自控服务器测速。

## 7. 给 Codex 的注意事项

- **不要逆向 speedtest.cn 私有 API**。当前以及未来都不应该对 speedtest.cn 做抓包、逆向、私有接口调用。
- **不要承诺 CLI 一定能跑满千兆**。Ookla server pool 与 speedtest.cn server pool 不同是客观事实。
- **不要把 Ookla 低速误判为用户网络差**。当前质量诊断已经区分"服务器距离远/选服不佳"和"本地网络差"。
- **不要重新加入手动录入 speedtest.cn 结果**。这个功能已被删除，体验差且无自动化价值。
- **真实公网测速不要放进单元测试**，测试必须 mock。
- **涉及公网 IP、stok、token、cookie 的内容不要落盘**。`~/.netwatch/config.json` 只能保存非敏感配置。
- **每次改动后运行**：
  ```bash
  source .venv/bin/activate
  python -m compileall netwatch
  pytest -q
  python -m pytest -q
  ```
- **小步提交，不要大重构**。
- **接手前先读文档**：README.md → AGENTS.md → CLAUDE.md → docs/handoff-to-codex.md → docs/handoff-to-claude.md。

## 8. Suggested Prompt for Codex

> 请阅读 README.md、AGENTS.md、CLAUDE.md、docs/handoff-to-codex.md、docs/handoff-to-claude.md。先不要写代码，先做接手审计：确认当前版本号、高级菜单结构、测速后端优先级、测试状态。然后评估下一步 V0.9 方向。优先考虑 LibreSpeed custom server list 或 HTTP file download test 作为下一个可控测速后端。不要逆向 speedtest.cn 私有 API，不要重新加入 speedtest.cn 手动录入功能。给出 Patch Plan 后等我确认再执行。
