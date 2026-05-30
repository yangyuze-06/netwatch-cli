from pathlib import Path

from netwatch.speedtest import speedtest_cn_browser as browser_mod
from netwatch.speedtest.speedtest_cn_browser import BrowserAutomationOptions


class FakeTimeoutError(Exception):
    pass


class FakeLocator:
    def __init__(self, page=None, text=None, *, click_error: Exception | None = None):
        self.page = page
        self.text = text
        self.click_error = click_error

    @property
    def first(self):
        return self

    def filter(self, **kwargs):
        return self

    def click(self, **kwargs):
        if self.click_error:
            raise self.click_error
        if kwargs.get("trial"):
            return
        if self.page is not None and self.text is not None:
            self.page.clicked_texts.append(self.text)

    def inner_text(self, **kwargs):
        return self.page.next_body_text()


class FakePage:
    def __init__(
        self,
        body_texts: list[str] | None = None,
        *,
        goto_error: BaseException | None = None,
        goto_errors: list[BaseException | None] | None = None,
        screenshot_error: Exception | None = None,
        available_texts: set[str] | None = None,
    ):
        self.body_texts = body_texts or []
        self.goto_error = goto_error
        self.goto_errors = goto_errors
        self.screenshot_error = screenshot_error
        self.available_texts = available_texts if available_texts is not None else {"测速", "开始测速"}
        self.clicked_texts = []
        self.body_reads = 0
        self.screenshot_path = None
        self.dismiss_prompt_calls = 0

    def goto(self, *args, **kwargs):
        if self.goto_errors is not None:
            error = self.goto_errors.pop(0) if self.goto_errors else None
            if error:
                raise error
            return
        if self.goto_error:
            raise self.goto_error

    def get_by_text(self, text, **kwargs):
        if text in self.available_texts:
            return FakeLocator(self, text=text)
        return FakeLocator(self, text=text, click_error=Exception("not found"))

    def locator(self, selector):
        if selector == "body":
            return FakeLocator(self)
        if selector.startswith("text="):
            text = selector.removeprefix("text=")
            if text in self.available_texts:
                return FakeLocator(self, text=text)
            return FakeLocator(self, text=text, click_error=Exception("not found"))
        return FakeLocator(self)

    def next_body_text(self):
        if not self.body_texts:
            return ""
        index = min(self.body_reads, len(self.body_texts) - 1)
        self.body_reads += 1
        return self.body_texts[index]

    def screenshot(self, path):
        if self.screenshot_error:
            raise self.screenshot_error
        self.screenshot_path = path
        Path(path).write_bytes(b"fake screenshot")


class FakeContext:
    def __init__(self, page):
        self.page = page
        self.closed = False
        self.grant_permissions_calls = []

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True

    def grant_permissions(self, permissions, **kwargs):
        self.grant_permissions_calls.append((permissions, kwargs))


class FakeBrowser:
    def __init__(self, page, chromium):
        self.page = page
        self.chromium = chromium
        self.context = FakeContext(page)
        self.closed = False

    def new_context(self, **kwargs):
        self.chromium.context_kwargs_values.append(kwargs)
        return self.context

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, page):
        self.page = page
        self.browser = None
        self.headless_values = []
        self.launch_kwargs_values = []
        self.context_kwargs_values = []

    def launch(self, **kwargs):
        self.headless_values.append(kwargs.get("headless"))
        self.launch_kwargs_values.append(kwargs)
        self.browser = FakeBrowser(self.page, self)
        return self.browser


class FakePlaywright:
    def __init__(self, page):
        self.chromium = FakeChromium(page)


class FakePlaywrightManager:
    def __init__(self, page):
        self.playwright = FakePlaywright(page)

    def __enter__(self):
        return self.playwright

    def __exit__(self, exc_type, exc, tb):
        return False


def install_fake_playwright(monkeypatch, page):
    manager = FakePlaywrightManager(page)
    monkeypatch.setattr(browser_mod, "load_sync_playwright", lambda: (lambda: manager, FakeTimeoutError))
    return manager


def test_browser_automation_returns_install_hint_when_playwright_missing(monkeypatch) -> None:
    monkeypatch.setattr(browser_mod, "load_sync_playwright", lambda: (None, None))

    result = browser_mod.run_speedtest_cn_browser_automation()

    assert result.error is not None
    assert "Playwright is not installed" in result.error
    assert "playwright install chromium" in result.error


def test_browser_automation_parses_mock_body_text(monkeypatch) -> None:
    page = FakePage(
        [
            """
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
        ]
    )
    manager = install_fake_playwright(monkeypatch, page)

    result = browser_mod.run_speedtest_cn_browser_automation(
        BrowserAutomationOptions(headless=True, timeout_seconds=3)
    )

    assert result.error is None
    assert result.download_mbps == 717.68
    assert result.upload_mbps == 64.2
    assert result.ping_ms == 8
    assert result.server_name == "广东移动_Vixtel_1"
    assert manager.playwright.chromium.headless_values == [True]
    assert manager.playwright.chromium.browser.closed is True
    assert manager.playwright.chromium.browser.context.closed is True


def test_browser_automation_emits_event_driven_progress(monkeypatch) -> None:
    page = FakePage(["Download 10 Mbps\nUpload 2 Mbps\nPing 8 ms"])
    install_fake_playwright(monkeypatch, page)
    progress_messages = []

    result = browser_mod.run_speedtest_cn_browser_automation(
        BrowserAutomationOptions(headless=True, timeout_seconds=3),
        progress_callback=progress_messages.append,
    )

    assert result.error is None
    assert progress_messages == [
        "正在启动后台浏览器...",
        "已打开 speedtest.cn",
        "已处理页面提示",
        "已找到测速按钮",
        "已点击测速按钮，正在测速...",
        "已检测到 Ping 结果",
        "已检测到下载结果",
        "已检测到上传结果",
        "测速完成，正在生成结果...",
    ]


def test_browser_automation_emits_result_field_progress_once(monkeypatch) -> None:
    page = FakePage(
        [
            "Ping 8 ms",
            "Ping 8 ms\nDownload 10 Mbps",
            "Ping 8 ms\nDownload 10 Mbps\nUpload 2 Mbps",
        ]
    )
    install_fake_playwright(monkeypatch, page)
    monkeypatch.setattr(browser_mod.time, "sleep", lambda seconds: None)
    progress_messages = []

    result = browser_mod.run_speedtest_cn_browser_automation(
        BrowserAutomationOptions(headless=True, timeout_seconds=3),
        progress_callback=progress_messages.append,
    )

    assert result.error is None
    assert progress_messages.count("已检测到 Ping 结果") == 1
    assert progress_messages.count("已检测到下载结果") == 1
    assert progress_messages.count("已检测到上传结果") == 1
    assert progress_messages.index("已检测到 Ping 结果") < progress_messages.index("已检测到下载结果")
    assert progress_messages.index("已检测到下载结果") < progress_messages.index("已检测到上传结果")
    assert progress_messages[-1] == "测速完成，正在生成结果..."


def test_browser_automation_failure_does_not_emit_complete_progress(monkeypatch) -> None:
    page = FakePage(["下载 1 Mbps"])
    install_fake_playwright(monkeypatch, page)
    progress_messages = []

    result = browser_mod.run_speedtest_cn_browser_automation(
        BrowserAutomationOptions(timeout_seconds=0),
        progress_callback=progress_messages.append,
    )

    assert result.error is not None
    assert "测速完成，正在生成结果..." not in progress_messages


def test_browser_automation_context_uses_desktop_locale_headers(monkeypatch) -> None:
    page = FakePage(["Download 10 Mbps\nUpload 2 Mbps\nPing 8 ms"])
    manager = install_fake_playwright(monkeypatch, page)

    result = browser_mod.run_speedtest_cn_browser_automation(
        BrowserAutomationOptions(headless=True, timeout_seconds=3)
    )

    context_kwargs = manager.playwright.chromium.context_kwargs_values[0]
    assert result.error is None
    assert "Macintosh" in context_kwargs["user_agent"]
    assert context_kwargs["viewport"] == {"width": 1440, "height": 900}
    assert context_kwargs["locale"] == "zh-CN"
    assert context_kwargs["timezone_id"] == "Asia/Shanghai"
    assert context_kwargs["geolocation"] == {"longitude": 113.2644, "latitude": 23.1291}
    assert context_kwargs["permissions"] == ["geolocation"]
    assert context_kwargs["extra_http_headers"] == {"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    grant_calls = manager.playwright.chromium.browser.context.grant_permissions_calls
    assert grant_calls == [(["geolocation"], {"origin": "https://www.speedtest.cn"})]


def test_geolocation_uses_static_default_location_without_user_lookup() -> None:
    assert browser_mod.DEFAULT_CONTEXT_OPTIONS["geolocation"] == {"longitude": 113.2644, "latitude": 23.1291}
    assert browser_mod.DEFAULT_CONTEXT_OPTIONS["permissions"] == ["geolocation"]


def test_dismiss_speedtest_cn_prompts_clicks_do_not_remind() -> None:
    page = FakePage(available_texts={"不再提醒"})

    browser_mod.dismiss_speedtest_cn_prompts(page)

    assert page.clicked_texts == ["不再提醒"]


def test_dismiss_speedtest_cn_prompts_falls_back_to_continue() -> None:
    page = FakePage(available_texts={"继续测速"})

    browser_mod.dismiss_speedtest_cn_prompts(page)

    assert page.clicked_texts == ["继续测速"]


def test_dismiss_speedtest_cn_prompts_missing_buttons_does_not_raise() -> None:
    page = FakePage(available_texts=set())

    browser_mod.dismiss_speedtest_cn_prompts(page)

    assert page.clicked_texts == []


def test_browser_automation_dismisses_prompts_before_and_after_speedtest_click(monkeypatch) -> None:
    page = FakePage(["Download 10 Mbps\nUpload 2 Mbps\nPing 8 ms"])
    install_fake_playwright(monkeypatch, page)
    dismiss_calls = []

    def fake_dismiss(prompt_page):
        dismiss_calls.append(prompt_page)

    monkeypatch.setattr(browser_mod, "dismiss_speedtest_cn_prompts", fake_dismiss)

    result = browser_mod.run_speedtest_cn_browser_automation(
        BrowserAutomationOptions(headless=True, timeout_seconds=3)
    )

    assert result.error is None
    assert dismiss_calls == [page, page]


def test_browser_automation_launches_visible_browser_when_headless_false(monkeypatch) -> None:
    page = FakePage(["Download 10 Mbps\nUpload 2 Mbps\nPing 8 ms"])
    manager = install_fake_playwright(monkeypatch, page)

    result = browser_mod.run_speedtest_cn_browser_automation(
        BrowserAutomationOptions(headless=False, timeout_seconds=3)
    )

    assert result.error is None
    assert manager.playwright.chromium.headless_values == [False]


def test_browser_automation_timeout_returns_friendly_error(monkeypatch) -> None:
    page = FakePage(["下载 1 Mbps"])
    install_fake_playwright(monkeypatch, page)

    result = browser_mod.run_speedtest_cn_browser_automation(
        BrowserAutomationOptions(timeout_seconds=0)
    )

    assert result.error is not None
    assert "测速未完成" in result.error


def test_browser_automation_playwright_timeout_returns_friendly_error(monkeypatch) -> None:
    page = FakePage(goto_error=FakeTimeoutError("goto timeout"))
    install_fake_playwright(monkeypatch, page)

    result = browser_mod.run_speedtest_cn_browser_automation()

    assert result.error is not None
    assert "超时" in result.error
    assert "goto timeout" in result.error


def test_headless_http2_error_retries_once_with_headless_args(monkeypatch) -> None:
    page = FakePage(
        ["Download 10 Mbps\nUpload 2 Mbps\nPing 8 ms"],
        goto_errors=[Exception("Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR"), None],
    )
    manager = install_fake_playwright(monkeypatch, page)

    result = browser_mod.run_speedtest_cn_browser_automation(
        BrowserAutomationOptions(headless=True, timeout_seconds=3)
    )

    assert result.error is None
    assert manager.playwright.chromium.headless_values == [True, True]
    assert manager.playwright.chromium.launch_kwargs_values[1]["args"] == [
        "--disable-http2",
        "--disable-blink-features=AutomationControlled",
    ]


def test_headless_http2_retry_still_fails_returns_friendly_error(monkeypatch) -> None:
    page = FakePage(
        goto_errors=[
            Exception("Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR"),
            Exception("Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR"),
        ]
    )
    manager = install_fake_playwright(monkeypatch, page)

    result = browser_mod.run_speedtest_cn_browser_automation(
        BrowserAutomationOptions(headless=True, timeout_seconds=3)
    )

    assert result.error is not None
    assert "ERR_HTTP2_PROTOCOL_ERROR" in result.error
    assert "speedtest.cn 网页对照测速" in result.error
    assert manager.playwright.chromium.headless_values == [True, True]
    assert False not in manager.playwright.chromium.headless_values


def test_headless_http2_goto_screenshot_failure_keeps_original_error(monkeypatch) -> None:
    page = FakePage(
        goto_errors=[
            Exception("Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR"),
            Exception("Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR"),
        ],
        screenshot_error=Exception("screenshot failed"),
    )
    install_fake_playwright(monkeypatch, page)

    result = browser_mod.run_speedtest_cn_browser_automation(
        BrowserAutomationOptions(headless=True, timeout_seconds=3, debug_screenshot=True)
    )

    assert result.error is not None
    assert "ERR_HTTP2_PROTOCOL_ERROR" in result.error
    assert "screenshot failed" not in result.error


def test_browser_automation_keyboard_interrupt_returns_error(monkeypatch) -> None:
    page = FakePage(goto_error=KeyboardInterrupt())
    install_fake_playwright(monkeypatch, page)

    result = browser_mod.run_speedtest_cn_browser_automation()

    assert result.error == "已取消 speedtest.cn browser automation。"


def test_save_debug_screenshot_uses_netwatch_debug_dir(monkeypatch, tmp_path) -> None:
    page = FakePage()
    monkeypatch.setenv("HOME", str(tmp_path))

    screenshot_path = browser_mod.save_debug_screenshot(page, enabled=True)

    assert screenshot_path is not None
    assert screenshot_path.startswith(str(tmp_path / ".netwatch" / "debug"))
    assert screenshot_path.endswith(".png")
    assert Path(screenshot_path).exists()
    assert page.screenshot_path == screenshot_path
