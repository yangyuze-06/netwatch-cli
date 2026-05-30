import io

from rich.console import Console

from netwatch.speedtest.speedtest_cn import SpeedtestCnResult, is_valid_speedtest_cn_label, parse_speedtest_cn_text


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


def test_parse_speedtest_cn_filters_ui_noise_from_metadata() -> None:
    text = """
为检测真实网络状况，建议：
不再提醒
继续测速
允许此网站使用您的位置信息？
访问该网站时允许
仅这次访问时允许
一律不允许
>>
取消
下载/Mbps
616.10
上传/Mbps
68.59
时延/ms
6
抖动/ms
1.89
更换测速点 >>
广东移动_Vixtel_1
广州移动
"""

    result = parse_speedtest_cn_text(text)

    assert result.error is None
    assert result.download_mbps == 616.10
    assert result.upload_mbps == 68.59
    assert result.ping_ms == 6
    assert result.jitter_ms == 1.89
    assert result.server_name == "广东移动_Vixtel_1"
    assert result.location == "广州移动"
    assert result.server_name not in {">>", "取消"}
    assert result.location not in {">>", "取消"}


def test_parse_speedtest_cn_core_metrics_without_metadata_still_succeeds() -> None:
    text = """
下载/Mbps
616.10
上传/Mbps
68.59
时延/ms
6
抖动/ms
1.89
"""

    result = parse_speedtest_cn_text(text)

    assert result.error is None
    assert result.download_mbps == 616.10
    assert result.upload_mbps == 68.59
    assert result.ping_ms == 6
    assert result.server_name is None
    assert result.location is None


def test_parse_speedtest_cn_ui_noise_only_does_not_pollute_metadata() -> None:
    text = """
下载/Mbps
616.10
上传/Mbps
68.59
时延/ms
6
抖动/ms
1.89
>>
取消
继续测速
不再提醒
访问该网站时允许
"""

    result = parse_speedtest_cn_text(text)

    assert result.error is None
    assert result.server_name is None
    assert result.location is None


def test_speedtest_cn_label_validator_rejects_ui_noise() -> None:
    invalid_values = [
        ">>",
        ">",
        "取消",
        "确定",
        "关闭",
        "继续测速",
        "不再提醒",
        "开始测速",
        "测速",
        "允许",
        "仅这次访问时允许",
        "访问该网站时允许",
        "一律不允许",
        "",
        "12345",
        "////",
    ]

    for value in invalid_values:
        assert not is_valid_speedtest_cn_label(value)

    assert is_valid_speedtest_cn_label("广东移动_Vixtel_1")
    assert is_valid_speedtest_cn_label("Guangzhou")


def test_speedtest_cn_cli_label_fallback_filters_ui_noise() -> None:
    from netwatch.cli import format_speedtest_cn_label

    assert format_speedtest_cn_label(">>") == "-"
    assert format_speedtest_cn_label("取消") == "-"
    assert format_speedtest_cn_label(None) == "-"
    assert format_speedtest_cn_label("广东移动_Vixtel_1") == "广东移动_Vixtel_1"


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


def test_build_advanced_menu_contains_general_diagnosis_entry() -> None:
    from netwatch.cli import build_advanced_menu

    rendered = build_advanced_menu().renderable

    assert "1[/bold cyan]. 通用测速诊断（Ookla / LibreSpeed / Python fallback）" in rendered
    assert "13[/bold cyan]. 返回主菜单" in rendered
    assert "实验：自动浏览器测速" not in rendered


def test_show_speedtest_cn_browser_automation_cancel_does_not_run(monkeypatch) -> None:
    from netwatch import cli as cli_mod

    called = []
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *args, **kwargs: "n")
    monkeypatch.setattr(cli_mod, "run_speedtest_cn_browser_automation", lambda options: called.append(options))

    cli_mod.show_speedtest_cn_browser_automation()

    assert called == []


def test_show_speedtest_cn_browser_automation_prints_result(monkeypatch) -> None:
    from netwatch import cli as cli_mod

    answers = iter(["y"])
    calls = []
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *args, **kwargs: next(answers))

    def fake_run(options, progress_callback=None):
        calls.append(options)
        assert progress_callback is not None
        progress_callback("已打开 speedtest.cn")
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
    assert "headless=True" not in output
    assert "debug_screenshot" not in output
    assert "模拟位置" not in output
    assert "geolocation" not in output
    assert "speedtest.cn Browser Automation" in output
    assert "717.68 Mbps / 89.71 MB/s" in output
    assert "来源：speedtest.cn 浏览器自动化实验结果，非官方 API。" in output


def run_speedtest_cn_browser_cli_with_answers(monkeypatch, answers, result=None):
    from netwatch import cli as cli_mod

    calls = []
    prompts = []
    answer_iter = iter(answers)

    def fake_prompt(prompt, *args, **kwargs):
        prompts.append(prompt)
        return next(answer_iter)

    monkeypatch.setattr(cli_mod.Prompt, "ask", fake_prompt)

    def fail_webbrowser_open(url):
        raise AssertionError(f"experimental automation must not call webbrowser.open: {url}")

    monkeypatch.setattr("webbrowser.open", fail_webbrowser_open)

    def fake_run(options, progress_callback=None):
        calls.append(options)
        if progress_callback is not None:
            progress_callback("已打开 speedtest.cn")
        if result is not None:
            return result
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
    return calls, buf.getvalue(), prompts


def test_speedtest_cn_browser_cli_default_options_are_headless_without_screenshot(monkeypatch) -> None:
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
        lambda options, progress_callback=None: calls.append(options)
        or SpeedtestCnResult(download_mbps=1, upload_mbps=1, ping_ms=1),
    )

    cli_mod.show_speedtest_cn_browser_automation()

    assert calls[0].headless is True
    assert calls[0].debug_screenshot is False
    assert calls[0].timeout_seconds == 90


def test_speedtest_cn_browser_cli_only_asks_continue_prompt(monkeypatch) -> None:
    calls, output, prompts = run_speedtest_cn_browser_cli_with_answers(monkeypatch, ["y"])

    assert calls[0].headless is True
    assert calls[0].debug_screenshot is False
    assert prompts == ["是否继续？"]
    assert "正在执行 speedtest.cn 后台测速，请稍候" in output
    assert "已打开 speedtest.cn" in output
    assert "正在后台启动浏览器" not in output
    assert "正在打开 speedtest.cn" not in output
    assert "正在等待测速按钮" not in output
    assert "正在开始测速" not in output
    assert "正在等待结果，大约需要 20~90 秒" not in output
    assert "正在解析结果" not in output
    assert "进入 debug 模式" not in "\n".join(prompts)
    assert "保存 debug screenshot" not in "\n".join(prompts)
    assert "使用可见浏览器调试" not in "\n".join(prompts)
    assert "headless=True" not in output
    assert "headless=" not in output
    assert "debug_screenshot" not in output
    assert "screenshot path" not in output
    assert "模拟位置" not in output
    assert "geolocation" not in output


def test_speedtest_cn_browser_cli_never_prints_screenshot_path(monkeypatch) -> None:
    result = SpeedtestCnResult(
        download_mbps=1,
        upload_mbps=1,
        ping_ms=1,
        debug_screenshot_path="/tmp/speedtest-cn-debug.png",
    )
    normal_calls, normal_output, _ = run_speedtest_cn_browser_cli_with_answers(monkeypatch, ["y"], result=result)

    assert normal_calls[0].headless is True
    assert normal_calls[0].debug_screenshot is False
    assert "/tmp/speedtest-cn-debug.png" not in normal_output
    assert "Debug screenshot" not in normal_output


def test_speedtest_cn_browser_cli_error_does_not_open_webbrowser(monkeypatch) -> None:
    from netwatch import cli as cli_mod

    answers = iter(["y"])
    calls = []
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(
        "webbrowser.open",
        lambda url: (_ for _ in ()).throw(AssertionError(f"unexpected webbrowser.open: {url}")),
    )

    def fake_run(options, progress_callback=None):
        calls.append(options)
        return SpeedtestCnResult(error="Playwright is not installed.")

    monkeypatch.setattr(cli_mod, "run_speedtest_cn_browser_automation", fake_run)

    cli_mod.show_speedtest_cn_browser_automation()

    assert calls
    assert calls[0].headless is True


def test_speedtest_cn_browser_cli_normal_error_is_short_without_traceback(monkeypatch) -> None:
    error = "Page.goto failed\nTraceback (most recent call last):\n  File example.py"
    calls, output, _ = run_speedtest_cn_browser_cli_with_answers(
        monkeypatch,
        ["y"],
        result=SpeedtestCnResult(error=error),
    )

    assert calls[0].headless is True
    assert calls[0].debug_screenshot is False
    assert "speedtest.cn 浏览器自动化失败：Page.goto failed" in output
    assert "Traceback" not in output
    assert "详细错误" not in output


def test_speedtest_cn_browser_cli_headless_http2_error_does_not_retry_visible_browser(monkeypatch) -> None:
    calls, output, prompts = run_speedtest_cn_browser_cli_with_answers(
        monkeypatch,
        ["y"],
        result=SpeedtestCnResult(error="speedtest.cn 在 headless Chromium 下访问失败：ERR_HTTP2_PROTOCOL_ERROR。"),
    )

    assert len(calls) == 1
    assert calls[0].headless is True
    assert calls[0].debug_screenshot is False
    assert prompts == ["是否继续？"]
    assert "ERR_HTTP2_PROTOCOL_ERROR" in output
    assert "是否切换到可见浏览器调试模式重试" not in output
    assert "Debug mode enabled" not in output


# --- Tests for show_speedtest_cn_main() (main menu item 4) ---


def run_speedtest_cn_main_with_answers(monkeypatch, answers, result=None):
    """Helper: run show_speedtest_cn_main with mocked answers and optional result."""
    from netwatch import cli as cli_mod

    calls = []
    prompts = []
    answer_iter = iter(answers)

    def fake_prompt(prompt, *args, **kwargs):
        prompts.append(prompt)
        return next(answer_iter)

    monkeypatch.setattr(cli_mod.Prompt, "ask", fake_prompt)

    def fake_run(options, progress_callback=None):
        calls.append(options)
        if progress_callback is not None:
            progress_callback("已打开 speedtest.cn")
        if result is not None:
            return result
        return SpeedtestCnResult(download_mbps=1, upload_mbps=1, ping_ms=1)

    monkeypatch.setattr(cli_mod, "run_speedtest_cn_browser_automation", fake_run)
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=140)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_speedtest_cn_main()
    finally:
        cli_mod.console = original_console
    return calls, buf.getvalue(), prompts


def test_show_speedtest_cn_main_cancel_does_not_run(monkeypatch) -> None:
    """Main menu speedtest.cn: cancel should not run the browser automation."""
    from netwatch import cli as cli_mod

    called = []
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *args, **kwargs: "n")
    monkeypatch.setattr(cli_mod, "run_speedtest_cn_browser_automation", lambda options: called.append(options))

    cli_mod.show_speedtest_cn_main()

    assert called == []


def test_show_speedtest_cn_main_prints_simplified_result(monkeypatch) -> None:
    """Main menu speedtest.cn success output must use simplified table without advanced diagnostics."""
    from netwatch.speedtest.speedtest_cn import SpeedtestCnResult

    result = SpeedtestCnResult(
        download_mbps=717.68,
        upload_mbps=64.2,
        ping_ms=8,
        jitter_ms=2.44,
        server_name="广东移动_Vixtel_1",
        location="广州移动",
    )

    calls, output, _ = run_speedtest_cn_main_with_answers(monkeypatch, ["y"], result=result)

    assert calls
    assert calls[0].headless is True
    assert "宽带测速结果" in output
    assert "717.68 Mbps / 89.71 MB/s" in output
    assert "来源：speedtest.cn 浏览器自动化实验结果，非官方 API。" in output


def test_show_speedtest_cn_main_no_advanced_diagnostics(monkeypatch) -> None:
    """Main menu speedtest.cn must NOT output Result confidence, network path, or VPN/TUN."""
    result = SpeedtestCnResult(
        download_mbps=717.68,
        upload_mbps=64.2,
        ping_ms=8,
        jitter_ms=2.44,
        server_name="广东移动_Vixtel_1",
        location="广州移动",
    )

    _, output, _ = run_speedtest_cn_main_with_answers(monkeypatch, ["y"], result=result)

    assert "Result confidence" not in output
    assert "网络路径分析" not in output
    assert "VPN/TUN" not in output
    assert "server pool" not in output
    assert "confidence" not in output.lower() or "Result confidence" not in output
    assert "headless" not in output
    assert "debug_screenshot" not in output
    assert "geolocation" not in output
    assert "模拟位置" not in output


def test_show_speedtest_cn_main_error_no_ookla_fallback(monkeypatch) -> None:
    """Main menu speedtest.cn failure must NOT fallback to Ookla."""
    error_result = SpeedtestCnResult(error="speedtest.cn 在 headless Chromium 下访问失败：ERR_HTTP2_PROTOCOL_ERROR。")

    calls, output, prompts = run_speedtest_cn_main_with_answers(monkeypatch, ["y"], result=error_result)

    assert len(calls) == 1
    assert "speedtest.cn 浏览器自动化测速失败" in output
    assert "ERR_HTTP2_PROTOCOL_ERROR" in output
    assert "可尝试：重新运行、使用高级功能里的通用测速诊断" in output
    # Should NOT suggest Ookla directly or auto-fallback
    assert "Ookla CLI" not in output
    assert "自动 fallback" not in output.lower()
