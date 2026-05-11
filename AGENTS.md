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
```

## 当前重点

- 稳定 official Ookla CLI 后端。
- 处理 Ookla 服务器选择不佳。
- 保存常用 server id。
- 做测速结果质量诊断。
- 保留 Python speedtest-cli fallback，但明确提示结果可能偏低。

## 接手前必读

- `README.md`
- `docs/handoff-to-codex.md`
- `docs/handoff-to-claude.md`
- `docs/v0.8.2-plan.md`
- `docs/v0.8.3-plan.md`

## 当前禁止

- 不要重新加入 speedtest.cn 手动录入/粘贴结果功能（已删除）。
- 不要逆向 speedtest.cn 私有 API。
- 不要大重构。
