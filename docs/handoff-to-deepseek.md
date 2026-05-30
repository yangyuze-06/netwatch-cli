# Handoff to DeepSeek

## 1. 当前项目状态

- 项目：`netwatch-cli`
- 当前版本：`0.9.3`（来自 `pyproject.toml` / `netwatch/__init__.py`）
- 当前定位：轻量级网络状态工具，包含网卡流量、本机网络信息、局域网设备发现、路由器入口、Ookla / LibreSpeed / Python fallback 测速、LibreSpeed custom server list、VPN/TUN 检测、`speedtest.cn` browser automation 实验测速。

## 2. 最近完成内容

- V0.9 LibreSpeed custom server list 已完成。
- Router UX 已修复：不再把所有路由器都叫小米；自动设备名同步目前只支持小米 / Redmi `stok` API。
- V0.10 `speedtest.cn` browser automation 已实现。
- 已真实跑通 `speedtest.cn` 自动化测速，示例结果：
  - Download `782.44 Mbps`
  - Upload `68.68 Mbps`
  - Ping `7 ms`
  - Server `中国移动`
  - Location `广东移动_Vixtel_2`
- 该功能不是 `speedtest.cn` 官方 API，不抓包、不逆向。

## 3. 当前已完成：主菜单测速入口重构（V0.10.4）

已实现：

- 主菜单 4 改为：`宽带测速（speedtest.cn）`
- 主菜单 4 调用 `show_speedtest_cn_main()`，输出简洁表格（Source / Server / Location / Ping / Jitter / Download / Upload），不含 Result confidence、网络路径分析、VPN/TUN。
- 失败时不自动 fallback 到 Ookla，显示友好错误提示。
- 原 `run_best_speedtest()` 移到高级功能第 1 项：
  `通用测速诊断（Ookla / LibreSpeed / Python fallback）`
- 高级功能删除了原来的"实验：自动浏览器测速 speedtest.cn"入口（不再重复）。
- 高级功能保留复杂诊断信息（Result confidence、网络路径分析、VPN/TUN 检测等）。
- 普通用户入口结果简洁，高级用户入口保留详细诊断。

## 4. 后续任务

- P1：`speedtest.cn` automation 进度显示改成 event-driven progress，不要一次性打印假进度。
- P2：删除用户可见 debug 模式；CLI 固定 `headless=True`、`debug_screenshot=False`。

## 5. 重要边界

- 不逆向 `speedtest.cn` 私有 API。
- 不抓包。
- 不读取 Cookie。
- 不绕过验证码 / 风控。
- Playwright 是 optional dependency。
- 默认测试不能真实访问 `speedtest.cn`。
- 真实公网测速必须 mock。
- 不要重新暴露 debug 模式给普通用户。

## 6. 关键文件

- `netwatch/cli.py`：菜单和交互。
- `netwatch/speedtest_cn.py`：`speedtest.cn` parser。
- `netwatch/speedtest_cn_browser.py`：Playwright 自动化。
- `netwatch/speedtest_runner.py`：通用测速调度。
- `netwatch/speedtest_backends/librespeed_cli.py`：LibreSpeed 后端。
- `netwatch/router.py`：路由器相关。
- `tests/`：全部 mock 测试。

## 7. Suggested Prompt for DeepSeek

```text
请先读 README.md、AGENTS.md、CLAUDE.md、docs/handoff-to-deepseek.md、docs/handoff-to-codex.md、docs/speedtest-cn-browser-automation.md。先运行 git status、git log --oneline -5、python -m compileall netwatch、pytest -q、python -m pytest -q。然后输出接手审计报告。当前最高优先级是 P0：把主菜单 4 改为宽带测速（speedtest.cn），调用 speedtest.cn browser automation；把原 run_best_speedtest() 移到高级功能第 1 项，命名为通用测速诊断（Ookla / LibreSpeed / Python fallback）。不要逆向 API，不抓包，不写真实公网测试。
```
