"""Experimental speedtest.cn browser automation."""

from __future__ import annotations

import importlib.util
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from netwatch.speedtest_cn import SpeedtestCnResult, parse_speedtest_cn_text

SPEEDTEST_CN_URL = "https://www.speedtest.cn/"
DESKTOP_CHROME_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_CONTEXT_OPTIONS = {
    "user_agent": DESKTOP_CHROME_USER_AGENT,
    "viewport": {"width": 1440, "height": 900},
    "locale": "zh-CN",
    "timezone_id": "Asia/Shanghai",
    "extra_http_headers": {"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
}
HEADLESS_HTTP2_RETRY_ARGS = [
    "--disable-http2",
    "--disable-blink-features=AutomationControlled",
]
PLAYWRIGHT_INSTALL_HINT = (
    "Playwright is not installed.\n"
    "Install with:\n"
    "pip install playwright\n"
    "playwright install chromium"
)


@dataclass(frozen=True)
class BrowserAutomationOptions:
    """Options for the experimental speedtest.cn browser automation."""

    headless: bool = True
    timeout_seconds: int = 90
    debug_screenshot: bool = False


def is_playwright_available() -> bool:
    """Return True when Playwright can be imported."""
    return importlib.util.find_spec("playwright") is not None


def run_speedtest_cn_browser_automation(
    options: BrowserAutomationOptions | None = None,
) -> SpeedtestCnResult:
    """Run experimental speedtest.cn browser automation and parse DOM text."""
    options = options or BrowserAutomationOptions()
    sync_playwright, playwright_timeout_error = load_sync_playwright()
    if sync_playwright is None or playwright_timeout_error is None:
        return SpeedtestCnResult(error=PLAYWRIGHT_INSTALL_HINT)

    result = run_speedtest_cn_browser_attempt(
        options=options,
        sync_playwright=sync_playwright,
        playwright_timeout_error=playwright_timeout_error,
    )
    if options.headless and is_http2_protocol_error(result.error):
        retry_result = run_speedtest_cn_browser_attempt(
            options=options,
            sync_playwright=sync_playwright,
            playwright_timeout_error=playwright_timeout_error,
            launch_args=HEADLESS_HTTP2_RETRY_ARGS,
        )
        if retry_result.error and (is_http2_protocol_error(retry_result.error) or not retry_result.raw_text):
            retry_result.error = friendly_http2_error(retry_result.error)
        return retry_result
    if result.error and is_http2_protocol_error(result.error):
        result.error = friendly_http2_error(result.error)
    return result


def run_speedtest_cn_browser_attempt(
    *,
    options: BrowserAutomationOptions,
    sync_playwright: Callable[..., Any],
    playwright_timeout_error: type[Exception],
    launch_args: list[str] | None = None,
) -> SpeedtestCnResult:
    """Run one browser automation attempt."""
    browser = None
    context = None
    page = None
    last_text = ""
    last_parse_error = "DOM 文本无法解析。"

    try:
        with sync_playwright() as playwright:
            launch_kwargs: dict[str, Any] = {"headless": options.headless}
            if launch_args:
                launch_kwargs["args"] = launch_args
            browser = playwright.chromium.launch(**launch_kwargs)
            context = browser.new_context(**DEFAULT_CONTEXT_OPTIONS)
            page = context.new_page()
            try:
                page.goto(SPEEDTEST_CN_URL, wait_until="domcontentloaded", timeout=30_000)
            except Exception as exc:
                screenshot_path = save_debug_screenshot(page, options.debug_screenshot)
                if isinstance(exc, playwright_timeout_error):
                    error_message = f"speedtest.cn browser automation 超时：{exc}"
                else:
                    error_message = friendly_goto_error(exc)
                return SpeedtestCnResult(
                    raw_text=last_text,
                    error=append_screenshot_path(error_message, screenshot_path),
                    debug_screenshot_path=screenshot_path,
                )
            dismiss_common_overlays(page)

            if not click_speedtest_button(page):
                screenshot_path = save_debug_screenshot(page, options.debug_screenshot)
                return SpeedtestCnResult(
                    raw_text=get_body_text(page),
                    error=append_screenshot_path("未找到 speedtest.cn 测速按钮。", screenshot_path),
                    debug_screenshot_path=screenshot_path,
                )

            deadline = time.monotonic() + max(0, options.timeout_seconds)
            while time.monotonic() < deadline:
                last_text = get_body_text(page)
                parsed = parse_speedtest_cn_text(last_text)
                last_parse_error = parsed.error or last_parse_error
                if parsed.download_mbps is not None and parsed.upload_mbps is not None and parsed.ping_ms is not None:
                    screenshot_path = save_debug_screenshot(page, options.debug_screenshot)
                    parsed.debug_screenshot_path = screenshot_path
                    return parsed
                time.sleep(2)

            screenshot_path = save_debug_screenshot(page, options.debug_screenshot)
            return SpeedtestCnResult(
                raw_text=last_text,
                error=append_screenshot_path(
                    f"测速未完成或 DOM 文本无法解析：{last_parse_error}",
                    screenshot_path,
                ),
                debug_screenshot_path=screenshot_path,
            )
    except KeyboardInterrupt:
        return SpeedtestCnResult(error="已取消 speedtest.cn browser automation。")
    except playwright_timeout_error as exc:
        screenshot_path = save_debug_screenshot(page, options.debug_screenshot)
        return SpeedtestCnResult(
            raw_text=last_text,
            error=append_screenshot_path(f"speedtest.cn browser automation 超时：{exc}", screenshot_path),
            debug_screenshot_path=screenshot_path,
        )
    except Exception as exc:
        screenshot_path = save_debug_screenshot(page, options.debug_screenshot)
        return SpeedtestCnResult(
            raw_text=last_text,
            error=append_screenshot_path(f"speedtest.cn browser automation 失败：{exc}", screenshot_path),
            debug_screenshot_path=screenshot_path,
        )
    finally:
        close_quietly(context)
        close_quietly(browser)


def is_http2_protocol_error(message: str | None) -> bool:
    """Return True for the known speedtest.cn headless HTTP/2 failure."""
    if not message:
        return False
    return "ERR_HTTP2_PROTOCOL_ERROR" in message or "net::ERR_HTTP2_PROTOCOL_ERROR" in message


def friendly_goto_error(exc: Exception) -> str:
    """Convert a page.goto exception into a user-facing error."""
    message = str(exc)
    if is_http2_protocol_error(message):
        return friendly_http2_error(message)
    return f"后台浏览器访问 speedtest.cn 失败：{message}"


def friendly_http2_error(message: str | None = None) -> str:
    """Return a concise, actionable HTTP/2 headless failure message."""
    return "\n".join(
        [
            "speedtest.cn 在 headless Chromium 下访问失败：ERR_HTTP2_PROTOCOL_ERROR。",
            "这可能是网站/CDN/HTTP2 对 headless 浏览器不兼容或限制。",
            "请尝试：",
            "1. 使用可见浏览器调试模式。",
            "2. 稍后重试。",
            "3. 使用 speedtest.cn 网页对照测速。",
            "4. 使用 Ookla / LibreSpeed 后端。",
        ]
    )


def load_sync_playwright() -> tuple[Callable[..., Any] | None, type[Exception] | None]:
    """Import Playwright lazily so netwatch-cli can start without it."""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, None
    return sync_playwright, PlaywrightTimeoutError


def dismiss_common_overlays(page: Any) -> None:
    """Best-effort close for ordinary popups, without bypassing CAPTCHA or risk controls."""
    for text in ("同意", "接受", "我知道了", "关闭", "跳过", "×"):
        try:
            page.get_by_text(text, exact=True).click(timeout=1_000)
        except Exception:
            continue


def click_speedtest_button(page: Any) -> bool:
    """Click the first visible speedtest button from several DOM locator strategies."""
    locator_factories = (
        lambda: page.get_by_text("测速", exact=True),
        lambda: page.get_by_text("开始测速"),
        lambda: first_locator(page.locator("text=测速")),
        lambda: first_locator(page.locator("button").filter(has_text="测速")),
    )
    for locator_factory in locator_factories:
        try:
            locator = locator_factory()
            locator.click(timeout=5_000)
            return True
        except Exception:
            continue
    return False


def first_locator(locator: Any) -> Any:
    """Return first locator for real Playwright and simple test fakes."""
    first = getattr(locator, "first", None)
    if first is None:
        return locator
    return first() if callable(first) else first


def get_body_text(page: Any) -> str:
    """Read full page body text from DOM."""
    if page is None:
        return ""
    return page.locator("body").inner_text(timeout=5_000)


def save_debug_screenshot(page: Any, enabled: bool) -> str | None:
    """Save a debug screenshot only when explicitly requested."""
    if not enabled or page is None:
        return None
    try:
        debug_dir = Path("~/.netwatch/debug/").expanduser()
        debug_dir.mkdir(parents=True, exist_ok=True)
        path = debug_dir / f"speedtest-cn-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
        page.screenshot(path=str(path))
        return str(path)
    except Exception:
        return None


def append_screenshot_path(message: str, screenshot_path: str | None) -> str:
    """Attach screenshot path to a user-facing message when available."""
    if not screenshot_path:
        return message
    return f"{message}\nDebug screenshot: {screenshot_path}"


def close_quietly(resource: Any) -> None:
    """Close a Playwright resource, ignoring cleanup failures."""
    if resource is None:
        return
    try:
        resource.close()
    except Exception:
        pass
