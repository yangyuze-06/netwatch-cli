# CLAUDE.md

你正在接手 `netwatch-cli`。

请先阅读：

1. `README.md`
2. `docs/handoff-to-codex.md`（最新交接文档）
3. `docs/handoff-to-claude.md`
4. `docs/v0.8.2-plan.md`
5. `docs/v0.8.3-plan.md`

本轮 Claude Code 已完成：

- 删除 speedtest.cn 手动录入功能和 manual parser。
- 高级功能菜单重排为 11 项。
- ISP 预设关键词优化（Hong Kong 降级为最后 fallback）。
- 测速质量诊断增强（按触发条件给出针对性建议）。
- README、handoff-to-claude.md、AGENTS.md 已更新相关边界。

后续切回 Codex 时，Codex 应先读 `docs/handoff-to-codex.md`。

当前项目重点：

- 这是一个 Python CLI 网络诊断工具。
- 用户当前最关心的是带宽测速准确性。
- 官方 Ookla CLI 已接入，但当前环境下 Ookla 自动选服经常选到 Tokyo/Hong Kong，导致结果远低于 `speedtest.cn` 网页。
- 不要把这个误判为用户网络差。
- `speedtest.cn` 网页曾能选到“广东移动_Vixtel_1”，接近千兆。
- 当前策略应是：质量诊断、保存常用 server id、网页对照入口，而不是逆向 `speedtest.cn` 私有 API。

操作要求：

- 每次修改前先看 `git status`。
- 每次只做一个明确任务。
- 修改后运行：
  ```bash
  python -m compileall netwatch
  pytest -q
  python -m pytest -q
  ```
- 不要真实跑公网测速作为自动测试。
- 需要真实测速时先征求用户确认。
- 不保存敏感信息。
- 不逆向 `speedtest.cn` 私有 API。
