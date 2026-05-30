# AGENTS.md

## 项目定位

`netwatch-cli` 是一个 Python CLI 网络诊断工具，目标是轻量、可维护、跨平台。

## 开发原则

- 小步提交，不要一次性大重构。
- CLI 层只做交互展示。
- 网络测速后端必须返回结构化结果，不直接 print。
- 所有公网测速、curl、subprocess、requests 测试都必须 mock。
- 不保存密码、stok、token、公网 IP 等敏感信息。
- 不逆向 `speedtest.cn` 私有 API。
- `speedtest.cn` 只作为网页对照入口，除非未来有正式 SDK/API 授权。

## 常用命令

```bash
source .venv/bin/activate
python -m netwatch.cli
python -m compileall netwatch
pytest -q
python -m pytest -q
git diff --check
```

## 当前重点

- 主菜单 4 使用 `speedtest.cn` browser automation 作为默认带宽测速入口。
- 保持高级功能第 1 项"通用测速诊断"的 Ookla / LibreSpeed / Python fallback 可用。
- 普通用户入口输出简洁，高级用户入口保留完整诊断。
- `speedtest.cn` browser automation 失败时不自动 fallback 到 Ookla。
- 不逆向 speedtest.cn 私有 API。

## 接手前必读

- `README.md`
- `AGENTS.md`
- `docs/handoff-to-codex.md`
- `docs/handoff-to-deepseek.md`
- `docs/speedtest-cn-browser-automation.md`

后续由 DeepSeek 接手，详见 `docs/handoff-to-deepseek.md`。

## 当前禁止

- 不要重新加入 speedtest.cn 手动录入/粘贴结果功能（已删除）。
- 不要逆向 speedtest.cn 私有 API。
- 不要把 speedtest.cn browser automation 当成官方 API 后端。
- 不要让默认测试真实访问 speedtest.cn 或真实启动浏览器，必须 mock。
- 不要提交 `~/.netwatch/debug/` screenshot。
- 不要大重构。
- 不要修改 `run_best_speedtest()` / `show_auto_speedtest()` 的后端实现逻辑。
- 不要让主菜单 4 在 speedtest.cn 失败时自动 fallback 到 Ookla。
