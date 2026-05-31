# AGENTS.md

## Project Scope

`netwatch-cli` is a Python CLI network diagnostics tool. The goal is to keep it lightweight, maintainable, and cross-platform.

## Development Principles

- Make small commits; do not perform large rewrites in one step.
- The CLI layer should only handle interaction and presentation.
- Network speedtest backends must return structured results and must not print directly.
- All public speedtest, `curl`, `subprocess`, and `requests` tests must be mocked.
- Do not store sensitive information such as passwords, `stok`, tokens, or public IP addresses.
- Do not reverse engineer private `speedtest.cn` APIs.
- Treat `speedtest.cn` only as a browser reference entry point unless an officially authorized SDK/API becomes available in the future.

## Common Commands

```bash
source .venv/bin/activate
python -m netwatch.cli
python -m compileall netwatch
pytest -q
python -m pytest -q
git diff --check
```

## Current Focus

- Main menu item 4 uses `speedtest.cn` browser automation as the default bandwidth test entry point.
- Main menu item 5, "Proxy / Current Exit Speedtest", should use concise output by default and ask whether to show detailed diagnostics after completion; advanced menu item 1 should continue to show full diagnostics.
- Keep advanced menu item 1, "General Speedtest Diagnostics", working with Ookla / LibreSpeed / Python fallback.
- Do not automatically fall back to Ookla when `speedtest.cn` browser automation fails.
- Do not reverse engineer private `speedtest.cn` APIs.

## Required Reading Before Handoff

- `README.md`
- `AGENTS.md`
- `docs/handoff/handoff-to-codex.md`
- `docs/handoff/handoff-to-deepseek.md`
- `docs/features/speedtest-cn-browser-automation.md`

Future DeepSeek handoff details are in `docs/handoff/handoff-to-deepseek.md`.

## Current Prohibitions

- Do not reintroduce manual `speedtest.cn` result entry/paste functionality; it has been removed.
- Do not reverse engineer private `speedtest.cn` APIs.
- Do not treat `speedtest.cn` browser automation as an official API backend.
- Do not let default tests access the real `speedtest.cn` website or launch a real browser; tests must mock this behavior.
- Do not commit screenshots from `~/.netwatch/debug/`.
- Do not perform large rewrites.
- Do not modify the backend implementation logic of `run_best_speedtest()` / `show_auto_speedtest()`.
- Do not let main menu item 4 automatically fall back to Ookla when `speedtest.cn` fails.
