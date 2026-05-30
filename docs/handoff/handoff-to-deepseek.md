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

## 4. 最新完成：代理/当前出口测速输出优化（V0.10.5）

主菜单 5 "代理/当前出口测速"输出已优化为默认简洁：

- 显示当前 CLI 公网出口（IP、国家/地区、城市、ISP/组织）。
- 测速结果只显示简洁表格（Backend / Server / Location / Ping / Download / Upload）。
- 显示一句简短判断（是否检测到 VPN/TUN，代表代理出口或直连出口质量）。
- 不默认输出 Result confidence、网络路径分析、触发条件、VPN/TUN 长段说明。
- 测速完成后询问："是否查看详细诊断？[y/N]"
- 用户选择 y 后，调用现有 `print_speedtest_results_extra()` 显示完整诊断。
- 用户选择 n 或回车，直接返回主菜单。
- 失败时显示简洁错误，不输出 traceback。

现有 `print_speedtest_result(result, detailed=True)` 已拆分为：
- `print_speedtest_result_table(result)`：只输出表格 + jitter/packet_loss + fallback 提示
- `print_speedtest_results_extra(result)`：质量警告 + 路径分析（仅详细模式）
- `print_speedtest_result(result, detailed=True)`：两者组合，向后兼容

进度显示也改为真实可确认状态（不再连续打印"正在启动测速后端...""正在连接测速服务器...""正在执行下载测速...""正在执行上传测速..."等假阶段）：
- 出口检测后显示："已检测当前 CLI 公网出口。"
- 调用测速前显示："正在调用测速后端，请稍候..."
- 测速过程中使用 `console.status("测速进行中，通常需要 10~30 秒...")`
- 测速完成后显示："测速完成。"

高级功能第 1 项"通用测速诊断"继续默认 `detailed=True`，不受影响。

## 5. 最新完成：本机网络信息优化（V0.10.6）

主菜单 2 "查看本机网络信息"已改造为分两层：

默认展示：
- **本机局域网信息**：主要网卡、IPv4 地址、MAC 地址、默认网关
- **当前公网出口**：公网 IP、国家/地区、城市、ISP/组织（来自 `probe_exit_ip()`）
- 注：公网位置来自 IP 粗略定位，不保存、不读取精确地理位置
- 注：使用 VPN/TUN/代理时，显示代理出口位置，不代表真实所在地

默认隐藏：
- 全部网卡详情（en0 / anpi0 / anpi1 / en3 / en4 / en1 / en2 / ap1 等）
- 需要在 "是否查看全部网卡详情？[y/N]" 中选择 y 才展开

失败处理：
- 公网出口查询失败时显示 "未能获取当前公网出口信息。"
- 不输出 traceback

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
请先读 README.md、AGENTS.md、CLAUDE.md、docs/handoff/handoff-to-deepseek.md、docs/handoff/handoff-to-codex.md、docs/features/speedtest-cn-browser-automation.md。先运行 git status、git log --oneline -5、python -m compileall netwatch、pytest -q、python -m pytest -q。然后输出接手审计报告。当前最高优先级是 P0：把主菜单 4 改为宽带测速（speedtest.cn），调用 speedtest.cn browser automation；把原 run_best_speedtest() 移到高级功能第 1 项，命名为通用测速诊断（Ookla / LibreSpeed / Python fallback）。不要逆向 API，不抓包，不写真实公网测试。
```
