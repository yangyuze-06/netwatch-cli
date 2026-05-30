import io

from rich.console import Console

from netwatch.speedtest_cn import SpeedtestCnResult, parse_speedtest_cn_text


def test_parse_speedtest_cn_multiline_chinese_text() -> None:
    text = """
下载/Mbps
717.68
上传/Mbps
64.2
时延/ms
8
抖动/ms
2.44
广东移动_Vixtel_1
广州移动
"""

    result = parse_speedtest_cn_text(text)

    assert result.error is None
    assert result.download_mbps == 717.68
    assert result.upload_mbps == 64.2
    assert result.ping_ms == 8
    assert result.jitter_ms == 2.44
    assert result.server_name == "广东移动_Vixtel_1"
    assert result.location == "广州移动"


def test_parse_speedtest_cn_inline_chinese_text() -> None:
    text = """
下载 997.83 Mbps
上传 69.41 Mbps
Ping 7 ms
抖动 1.00 ms
测速点 广东移动_Vixtel_1
位置 广州移动
"""

    result = parse_speedtest_cn_text(text)

    assert result.error is None
    assert result.download_mbps == 997.83
    assert result.upload_mbps == 69.41
    assert result.ping_ms == 7
    assert result.jitter_ms == 1.0
    assert result.server_name == "广东移动_Vixtel_1"
    assert result.location == "广州移动"


def test_parse_speedtest_cn_english_mixed_text() -> None:
    text = """
Download 780.22 Mbps
Upload 69.63 Mbps
Ping 5 ms
Jitter 0.89 ms
Server Guangdong Mobile_Vixtel_1
Location Guangzhou
"""

    result = parse_speedtest_cn_text(text)

    assert result.error is None
    assert result.download_mbps == 780.22
    assert result.upload_mbps == 69.63
    assert result.ping_ms == 5
    assert result.jitter_ms == 0.89
    assert result.server_name == "Guangdong Mobile_Vixtel_1"
    assert result.location == "Guangzhou"


def test_parse_speedtest_cn_missing_required_fields_returns_error() -> None:
    result = parse_speedtest_cn_text("下载 717.68 Mbps\n测速点 广东移动_Vixtel_1")

    assert result.download_mbps == 717.68
    assert result.error is not None
    assert "upload" in result.error
    assert "ping" in result.error


def test_parse_speedtest_cn_converts_MBps_to_mbps() -> None:
    text = """
下载 10 MB/s
上传 5 MB/s
Ping 8 ms
"""

    result = parse_speedtest_cn_text(text)

    assert result.error is None
    assert result.download_mbps == 80
    assert result.upload_mbps == 40
    assert result.download_MBps == 10
    assert result.upload_MBps == 5


def test_build_advanced_menu_contains_experimental_speedtest_cn_entry() -> None:
    from netwatch.cli import build_advanced_menu

    rendered = build_advanced_menu().renderable

    assert "12[/bold cyan]. 实验：自动浏览器测速 speedtest.cn" in rendered
    assert "13[/bold cyan]. 返回主菜单" in rendered


def test_show_speedtest_cn_browser_automation_cancel_does_not_run(monkeypatch) -> None:
    from netwatch import cli as cli_mod

    called = []
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *args, **kwargs: "n")
    monkeypatch.setattr(cli_mod, "run_speedtest_cn_browser_automation", lambda options: called.append(options))

    cli_mod.show_speedtest_cn_browser_automation()

    assert called == []


def test_show_speedtest_cn_browser_automation_prints_result(monkeypatch) -> None:
    from netwatch import cli as cli_mod

    answers = iter(["y", "n", "n"])
    calls = []
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *args, **kwargs: next(answers))

    def fake_run(options):
        calls.append(options)
        return SpeedtestCnResult(
            download_mbps=717.68,
            upload_mbps=64.2,
            ping_ms=8,
            jitter_ms=2.44,
            server_name="广东移动_Vixtel_1",
            location="广州移动",
        )

    monkeypatch.setattr(cli_mod, "run_speedtest_cn_browser_automation", fake_run)
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=140)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_speedtest_cn_browser_automation()
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert calls
    assert calls[0].headless is True
    assert calls[0].debug_screenshot is False
    assert "headless=True" in output
    assert "speedtest.cn Browser Automation" in output
    assert "717.68 Mbps / 89.71 MB/s" in output
    assert "不是 speedtest.cn 官方 API 后端" in output


def run_speedtest_cn_browser_cli_with_answers(monkeypatch, answers):
    from netwatch import cli as cli_mod

    calls = []
    answer_iter = iter(answers)
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *args, **kwargs: next(answer_iter))

    def fail_webbrowser_open(url):
        raise AssertionError(f"experimental automation must not call webbrowser.open: {url}")

    monkeypatch.setattr("webbrowser.open", fail_webbrowser_open)

    def fake_run(options):
        calls.append(options)
        return SpeedtestCnResult(download_mbps=1, upload_mbps=1, ping_ms=1)

    monkeypatch.setattr(cli_mod, "run_speedtest_cn_browser_automation", fake_run)
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=140)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_speedtest_cn_browser_automation()
    finally:
        cli_mod.console = original_console
    return calls, buf.getvalue()


def test_speedtest_cn_browser_cli_default_debug_prompt_is_headless(monkeypatch) -> None:
    from netwatch import cli as cli_mod

    calls = []

    def fake_prompt(prompt, *args, **kwargs):
        if "是否继续" in prompt:
            return "y"
        return kwargs["default"]

    monkeypatch.setattr(cli_mod.Prompt, "ask", fake_prompt)
    monkeypatch.setattr(
        "webbrowser.open",
        lambda url: (_ for _ in ()).throw(AssertionError(f"unexpected webbrowser.open: {url}")),
    )
    monkeypatch.setattr(
        cli_mod,
        "run_speedtest_cn_browser_automation",
        lambda options: calls.append(options) or SpeedtestCnResult(download_mbps=1, upload_mbps=1, ping_ms=1),
    )

    cli_mod.show_speedtest_cn_browser_automation()

    assert calls[0].headless is True
    assert calls[0].timeout_seconds == 90


def test_speedtest_cn_browser_cli_n_keeps_headless(monkeypatch) -> None:
    calls, output = run_speedtest_cn_browser_cli_with_answers(monkeypatch, ["y", "n", "n"])

    assert calls[0].headless is True
    assert "实验测速将以 headless 后台模式运行，不会打开可见浏览器窗口" in output
    assert "正在以后台模式启动浏览器" in output


def test_speedtest_cn_browser_cli_y_uses_visible_debug_browser(monkeypatch) -> None:
    calls, output = run_speedtest_cn_browser_cli_with_answers(monkeypatch, ["y", "y", "n"])

    assert calls[0].headless is False
    assert "你已选择可见浏览器调试模式，将打开浏览器窗口" in output
    assert "正在以可见浏览器调试模式启动浏览器" in output


def test_speedtest_cn_browser_cli_debug_screenshot_does_not_change_headless(monkeypatch) -> None:
    calls, output = run_speedtest_cn_browser_cli_with_answers(monkeypatch, ["y", "n", "y"])

    assert calls[0].headless is True
    assert calls[0].debug_screenshot is True
    assert "debug_screenshot=True" in output
    assert "正在以后台模式启动浏览器" in output


def test_speedtest_cn_browser_cli_error_does_not_open_webbrowser(monkeypatch) -> None:
    from netwatch import cli as cli_mod

    answers = iter(["y", "n", "n"])
    calls = []
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(
        "webbrowser.open",
        lambda url: (_ for _ in ()).throw(AssertionError(f"unexpected webbrowser.open: {url}")),
    )

    def fake_run(options):
        calls.append(options)
        return SpeedtestCnResult(error="Playwright is not installed.")

    monkeypatch.setattr(cli_mod, "run_speedtest_cn_browser_automation", fake_run)

    cli_mod.show_speedtest_cn_browser_automation()

    assert calls
    assert calls[0].headless is True


def test_speedtest_cn_browser_cli_headless_http2_error_declines_visible_retry(monkeypatch) -> None:
    from netwatch import cli as cli_mod

    answers = iter(["y", "n", "y", "n"])
    calls = []
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(
        "webbrowser.open",
        lambda url: (_ for _ in ()).throw(AssertionError(f"unexpected webbrowser.open: {url}")),
    )

    def fake_run(options):
        calls.append(options)
        return SpeedtestCnResult(error="speedtest.cn 在 headless Chromium 下访问失败：ERR_HTTP2_PROTOCOL_ERROR。")

    monkeypatch.setattr(cli_mod, "run_speedtest_cn_browser_automation", fake_run)
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=140)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_speedtest_cn_browser_automation()
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert len(calls) == 1
    assert calls[0].headless is True
    assert calls[0].debug_screenshot is True
    assert "后台浏览器访问 speedtest.cn 失败" in output
    assert "ERR_HTTP2_PROTOCOL_ERROR" in output


def test_speedtest_cn_browser_cli_headless_http2_error_retries_visible_only_after_yes(monkeypatch) -> None:
    from netwatch import cli as cli_mod

    answers = iter(["y", "n", "y", "y"])
    calls = []
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(
        "webbrowser.open",
        lambda url: (_ for _ in ()).throw(AssertionError(f"unexpected webbrowser.open: {url}")),
    )

    def fake_run(options):
        calls.append(options)
        if len(calls) == 1:
            return SpeedtestCnResult(error="speedtest.cn 在 headless Chromium 下访问失败：ERR_HTTP2_PROTOCOL_ERROR。")
        return SpeedtestCnResult(download_mbps=100, upload_mbps=20, ping_ms=8)

    monkeypatch.setattr(cli_mod, "run_speedtest_cn_browser_automation", fake_run)
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=140)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_speedtest_cn_browser_automation()
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert len(calls) == 2
    assert calls[0].headless is True
    assert calls[1].headless is False
    assert calls[1].debug_screenshot is True
    assert "你已选择可见浏览器调试模式，将打开浏览器窗口" in output
    assert "speedtest.cn Browser Automation" in output
