# CLAUDE.md

You are taking over `netwatch-cli`.

Please read these first:

1. `README.md`
2. `docs/handoff/handoff-to-codex.md` (latest handoff document)
3. `docs/handoff/handoff-to-claude.md`
4. `docs/plans/v0.8.2-plan.md`
5. `docs/plans/v0.8.3-plan.md`

This Claude Code round completed:

- Removed the manual `speedtest.cn` entry feature and manual parser.
- Reordered the advanced feature menu into 11 items.
- Improved ISP preset keywords, with Hong Kong downgraded to the final fallback.
- Enhanced speedtest quality diagnostics with targeted advice by trigger condition.
- Updated README, `handoff-to-claude.md`, and `AGENTS.md` with the relevant boundaries.

When switching back to Codex, Codex should read `docs/handoff/handoff-to-codex.md` first.

When handing off to DeepSeek, read `docs/handoff/handoff-to-deepseek.md` first.

Current project focus:

- This is a Python CLI network diagnostics tool.
- The user currently cares most about bandwidth test accuracy.
- The official Ookla CLI has been integrated, but in the current environment Ookla automatic server selection often chooses Tokyo/Hong Kong, which produces results far below the `speedtest.cn` web test.
- Do not misdiagnose this as poor user network quality.
- The `speedtest.cn` website was previously able to select a Guangdong Mobile Vixtel node and reach near-gigabit results.
- The current strategy should be quality diagnostics, saving frequently used server IDs, and a browser reference entry point, not reverse engineering private `speedtest.cn` APIs.

Operational requirements:

- Check `git status` before each change.
- Do only one clearly defined task at a time.
- After changes, run:
  ```bash
  python -m compileall netwatch
  pytest -q
  python -m pytest -q
  ```
- Do not run real public speedtests as automated tests.
- Ask the user for confirmation before any real speedtest.
- Do not store sensitive information.
- Do not reverse engineer private `speedtest.cn` APIs.
