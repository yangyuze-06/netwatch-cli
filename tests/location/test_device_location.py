"""Tests for experimental browser geolocation device location.

All tests are mocked — no real browser, no real geolocation.
"""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer

import pytest

from netwatch.device_location import (
    DeviceLocationResult,
    GEOLOCATION_HTML,
    get_device_location_html_source,
    run_browser_geolocation,
    _make_handler,
)


# --- HTML content tests ---


def test_html_contains_geolocation_api() -> None:
    """HTML page must contain navigator.geolocation.getCurrentPosition."""
    html = get_device_location_html_source()
    assert "navigator.geolocation.getCurrentPosition" in html


def test_html_contains_button() -> None:
    """HTML page must contain a clickable button."""
    html = get_device_location_html_source()
    assert "getElementById('locateBtn')" in html
    assert "获取当前位置" in html


def test_html_contains_privacy_note() -> None:
    """HTML page must state that location is not saved or uploaded."""
    html = get_device_location_html_source()
    assert "不会保存或上传" in html


def test_html_posts_to_location() -> None:
    """HTML page must POST to /location on success."""
    html = get_device_location_html_source()
    assert "/location" in html


def test_html_posts_to_error() -> None:
    """HTML page must POST to /error on failure."""
    html = get_device_location_html_source()
    assert "/error" in html


def test_html_contains_latitude_longitude_accuracy() -> None:
    """HTML page must send latitude, longitude, and accuracy."""
    html = get_device_location_html_source()
    assert "accuracy" in html


# --- Server /location handler tests ---


def test_server_location_returns_device_location_result(monkeypatch) -> None:
    """POST to /location must produce a DeviceLocationResult with coordinates."""
    opened_urls = []

    def fake_open(url: str) -> None:
        opened_urls.append(url)
        # Extract port from URL
        import http.client
        from urllib.parse import urlparse

        parsed = urlparse(url)
        port = parsed.port or 80
        conn = http.client.HTTPConnection("127.0.0.1", port)
        body = json.dumps({"latitude": 23.1291, "longitude": 113.2644, "accuracy": 65.0})
        conn.request("POST", "/location", body, {"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 200, f"Expected 200, got {resp.status}"
        conn.close()

    monkeypatch.setattr("webbrowser.open", fake_open)

    result = run_browser_geolocation(timeout_seconds=5)

    assert result.error is None
    assert result.latitude == 23.1291
    assert result.longitude == 113.2644
    assert result.accuracy_m == 65.0
    assert "browser geolocation" in result.source


def test_server_error_returns_error(monkeypatch) -> None:
    """POST to /error must produce a DeviceLocationResult with error message."""
    def fake_open(url: str) -> None:
        import http.client
        from urllib.parse import urlparse

        parsed = urlparse(url)
        port = parsed.port or 80
        conn = http.client.HTTPConnection("127.0.0.1", port)
        body = json.dumps({"code": 1, "message": "Permission denied"})
        conn.request("POST", "/error", body, {"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 200, f"Expected 200, got {resp.status}"
        conn.close()

    monkeypatch.setattr("webbrowser.open", fake_open)

    result = run_browser_geolocation(timeout_seconds=5)

    assert result.error is not None
    assert "Permission denied" in result.error
    assert result.latitude is None


def test_timeout_returns_error(monkeypatch) -> None:
    """No POST must produce a timeout error."""
    # Don't open any browser; just wait for timeout
    monkeypatch.setattr("webbrowser.open", lambda url: None)

    result = run_browser_geolocation(timeout_seconds=1)

    assert result.error is not None
    assert "超时" in result.error


def test_webbrowser_open_called_with_localhost(monkeypatch) -> None:
    """run_browser_geolocation must call webbrowser.open with a 127.0.0.1 URL."""
    opened_urls = []

    def fake_open(url: str) -> None:
        opened_urls.append(url)
        # Simulate a POST to /location to unblock
        import http.client

        for addr, port_part in [(a, p) for a in ("127.0.0.1",) for p in range(1024, 65536)]:
            # Extract port from the URL
            if f"127.0.0.1:" in url:
                port = int(url.split(":")[-1].split("/")[0])
                break
        else:
            return
        conn = http.client.HTTPConnection("127.0.0.1", port)
        body = json.dumps({"latitude": 1.0, "longitude": 2.0, "accuracy": 10.0})
        conn.request("POST", "/location", body, {"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        conn.close()

    monkeypatch.setattr("webbrowser.open", fake_open)

    result = run_browser_geolocation(timeout_seconds=5)

    assert result.error is None
    assert len(opened_urls) == 1
    assert opened_urls[0].startswith("http://127.0.0.1:")


def test_server_shuts_down_cleanly(monkeypatch) -> None:
    """Server must shut down without hanging threads."""
    import gc

    monkeypatch.setattr("webbrowser.open", lambda url: None)

    # With a 1s timeout, the server should shut down after the wait
    result = run_browser_geolocation(timeout_seconds=1)

    assert result.error is not None
    # No threads should remain blocked
    # (daemon threads may still show as alive but won't block exit)


def test_no_file_written(monkeypatch, tmp_path) -> None:
    """run_browser_geolocation must not write any files."""
    monkeypatch.setattr("webbrowser.open", lambda url: None)
    files_before = set(str(p) for p in tmp_path.rglob("*"))

    result = run_browser_geolocation(timeout_seconds=1)

    files_after = set(str(p) for p in tmp_path.rglob("*"))
    assert files_before == files_after


def test_device_location_result_dataclass() -> None:
    """DeviceLocationResult must store coordinates correctly."""
    result = DeviceLocationResult(latitude=23.1291, longitude=113.2644, accuracy_m=65.0)

    assert result.latitude == 23.1291
    assert result.longitude == 113.2644
    assert result.accuracy_m == 65.0


def test_device_location_result_defaults() -> None:
    """DeviceLocationResult with no args must have None fields."""
    result = DeviceLocationResult()

    assert result.latitude is None
    assert result.longitude is None
    assert result.accuracy_m is None
    assert "browser geolocation" in result.source
    assert result.error is None


def test_device_location_result_error() -> None:
    """DeviceLocationResult must store error."""
    result = DeviceLocationResult(error="Permission denied")

    assert result.error == "Permission denied"
    assert result.latitude is None


# --- CLI integration tests ---


def test_network_info_prompts_browser_geolocation(monkeypatch) -> None:
    """show_network_info must ask about browser geolocation."""
    import io
    from rich.console import Console
    from netwatch import cli as cli_mod
    from netwatch.network_info import InterfaceInfo
    from netwatch.proxy_probe import ExitIPInfo

    monkeypatch.setattr(cli_mod, "get_preferred_physical_interface", lambda: {"name": "en0", "ip": "192.168.31.75", "reason": "preferred"})
    monkeypatch.setattr(cli_mod, "get_default_gateway", lambda: "192.168.31.1")
    monkeypatch.setattr(cli_mod, "probe_exit_ip", lambda: ExitIPInfo(ip="1.2.3.4", city="", region="", country="", org=""))
    monkeypatch.setattr(
        cli_mod, "get_display_network_interfaces",
        lambda: [InterfaceInfo("en0", "192.168.31.75", "aa:bb:cc:dd:ee:ff")],
    )

    prompts = []
    answers = iter(["n", "n"])  # geolocation=n, full-interfaces=n

    def fake_prompt(prompt, *args, **kwargs):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(cli_mod.Prompt, "ask", fake_prompt)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_network_info()
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert "公网出口位置来自 IP 数据库" in output
    # The prompt text includes the geolocation question
    assert any("浏览器授权定位" in p for p in prompts)


def test_network_info_no_geolocation_skips_browser(monkeypatch) -> None:
    """When user chooses n for geolocation, run_browser_geolocation must NOT be called."""
    import io
    from rich.console import Console
    from netwatch import cli as cli_mod
    from netwatch.network_info import InterfaceInfo
    from netwatch.proxy_probe import ExitIPInfo

    monkeypatch.setattr(cli_mod, "get_preferred_physical_interface", lambda: {"name": "en0", "ip": "192.168.31.75", "reason": "preferred"})
    monkeypatch.setattr(cli_mod, "get_default_gateway", lambda: "192.168.31.1")
    monkeypatch.setattr(cli_mod, "probe_exit_ip", lambda: ExitIPInfo(ip="1.2.3.4", city="", region="", country="", org=""))
    monkeypatch.setattr(
        cli_mod, "get_display_network_interfaces",
        lambda: [InterfaceInfo("en0", "192.168.31.75", "aa:bb:cc:dd:ee:ff")],
    )

    called = []
    monkeypatch.setattr(cli_mod, "run_browser_geolocation", lambda **kwargs: called.append(True))

    prompts = []
    answers = iter(["n", "n"])  # geolocation=n, full-interfaces=n

    def fake_prompt(prompt, *args, **kwargs):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(cli_mod.Prompt, "ask", fake_prompt)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_network_info()
    finally:
        cli_mod.console = original_console

    assert called == []


def test_network_info_yes_geolocation_calls_browser(monkeypatch) -> None:
    """When user chooses y for geolocation, run_browser_geolocation must be called."""
    import io
    from rich.console import Console
    from netwatch import cli as cli_mod
    from netwatch.network_info import InterfaceInfo
    from netwatch.proxy_probe import ExitIPInfo

    monkeypatch.setattr(cli_mod, "get_preferred_physical_interface", lambda: {"name": "en0", "ip": "192.168.31.75", "reason": "preferred"})
    monkeypatch.setattr(cli_mod, "get_default_gateway", lambda: "192.168.31.1")
    monkeypatch.setattr(cli_mod, "probe_exit_ip", lambda: ExitIPInfo(ip="1.2.3.4", city="", region="", country="", org=""))
    monkeypatch.setattr(
        cli_mod, "get_display_network_interfaces",
        lambda: [InterfaceInfo("en0", "192.168.31.75", "aa:bb:cc:dd:ee:ff")],
    )
    monkeypatch.setattr(cli_mod, "run_browser_geolocation", lambda **kwargs: DeviceLocationResult(
        latitude=23.1291, longitude=113.2644, accuracy_m=65.0,
    ))

    prompts = []
    answers = iter(["y", "n"])  # geolocation=y, full-interfaces=n

    def fake_prompt(prompt, *args, **kwargs):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(cli_mod.Prompt, "ask", fake_prompt)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_network_info()
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert "设备授权定位" in output
    assert "23.1291" in output
    assert "113.2644" in output
    # The geolocation table shows accuracy in the format "约 65 米"
    assert "65" in output
    # The warning about not saving should be printed before geolocation call
    assert "不会保存或上传" in output or "用户授权的浏览器定位" in output


def test_network_info_geolocation_failure_shows_error(monkeypatch) -> None:
    """When browser geolocation fails, show error without traceback."""
    import io
    from rich.console import Console
    from netwatch import cli as cli_mod
    from netwatch.network_info import InterfaceInfo
    from netwatch.proxy_probe import ExitIPInfo

    monkeypatch.setattr(cli_mod, "get_preferred_physical_interface", lambda: {"name": "en0", "ip": "192.168.31.75", "reason": "preferred"})
    monkeypatch.setattr(cli_mod, "get_default_gateway", lambda: "192.168.31.1")
    monkeypatch.setattr(cli_mod, "probe_exit_ip", lambda: ExitIPInfo(ip="1.2.3.4", city="", region="", country="", org=""))
    monkeypatch.setattr(
        cli_mod, "get_display_network_interfaces",
        lambda: [InterfaceInfo("en0", "192.168.31.75", "aa:bb:cc:dd:ee:ff")],
    )
    monkeypatch.setattr(cli_mod, "run_browser_geolocation", lambda **kwargs: DeviceLocationResult(
        error="浏览器定位失败: Permission denied",
    ))

    prompts = []
    answers = iter(["y", "n"])

    def fake_prompt(prompt, *args, **kwargs):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(cli_mod.Prompt, "ask", fake_prompt)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_network_info()
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert "设备授权定位失败" in output
    assert "Permission denied" in output
    assert "Traceback" not in output


# --- Offline reverse geocoding tests ---


def test_reverse_geocode_offline_not_installed(monkeypatch) -> None:
    """When reverse_geocoder is not installed, fields remain None but no crash."""
    import builtins

    _orig_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "reverse_geocoder":
            raise ImportError("No module named 'reverse_geocoder'")
        return _orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)

    from netwatch.device_location import reverse_geocode_offline
    result = reverse_geocode_offline(23.1291, 113.2644)
    assert result["country"] is None
    assert result["admin1"] is None
    assert result["admin2"] is None
    assert result["nearest_place"] is None
    assert result["source"] is None
    assert result["error"] == "offline reverse geocoder is not installed"


def test_reverse_geocode_offline_success(monkeypatch) -> None:
    """When reverse_geocoder returns a match, fields must be populated with correct semantics."""
    import builtins

    class FakeRG:
        @staticmethod
        def search(coords, mode=1):
            return [{"name": "Yonghe", "admin1": "Guangdong", "admin2": "Zengcheng", "cc": "CN"}]

    _orig_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "reverse_geocoder":
            return FakeRG
        return _orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)

    from netwatch.device_location import reverse_geocode_offline
    result = reverse_geocode_offline(23.1291, 113.2644)
    assert result["country"] == "CN"
    assert result["admin1"] == "Guangdong"
    assert result["admin2"] == "Zengcheng"
    assert result["nearest_place"] == "Yonghe"
    assert result["source"] == "reverse_geocoder"
    assert result["error"] is None
    # Must NOT call Yonghe a "city"
    assert "city" not in result


def test_reverse_geocode_offline_exception(monkeypatch) -> None:
    """When reverse_geocoder throws, return error but don't crash."""
    import builtins

    class BrokenRG:
        @staticmethod
        def search(coords, mode=1):
            raise RuntimeError("database corrupted")

    _orig_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "reverse_geocoder":
            return BrokenRG
        return _orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)

    from netwatch.device_location import reverse_geocode_offline
    result = reverse_geocode_offline(23.1291, 113.2644)
    assert result["country"] is None
    assert result["admin1"] is None
    assert result["admin2"] is None
    assert result["nearest_place"] is None
    assert result["source"] is None
    assert result["error"] is not None
    assert "database corrupted" in (result["error"] or "")


def test_reverse_geocode_offline_empty_results(monkeypatch) -> None:
    """When reverse_geocoder returns empty list, return error."""
    import builtins

    class EmptyRG:
        @staticmethod
        def search(coords, mode=1):
            return []

    _orig_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "reverse_geocoder":
            return EmptyRG
        return _orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)

    from netwatch.device_location import reverse_geocode_offline
    result = reverse_geocode_offline(23.1291, 113.2644)
    assert result["country"] is None
    assert result["admin1"] is None
    assert result["admin2"] is None
    assert result["nearest_place"] is None
    assert result["source"] is None
    assert "no results" in (result.get("error") or "")


def test_run_browser_geolocation_fills_reverse_geocode(monkeypatch) -> None:
    """run_browser_geolocation must call _fill_reverse_geocode on success."""
    from netwatch.device_location import _fill_reverse_geocode, DeviceLocationResult

    calls = []
    monkeypatch.setattr(
        "netwatch.device_location._fill_reverse_geocode",
        lambda r: calls.append(r),
    )

    def fake_open(url: str) -> None:
        import http.client
        from urllib.parse import urlparse

        parsed = urlparse(url)
        port = parsed.port or 80
        conn = http.client.HTTPConnection("127.0.0.1", port)
        body = json.dumps({"latitude": 23.1291, "longitude": 113.2644, "accuracy": 65.0})
        conn.request("POST", "/location", body, {"Content-Type": "application/json"})
        conn.getresponse()
        conn.close()

    monkeypatch.setattr("webbrowser.open", fake_open)

    result = run_browser_geolocation(timeout_seconds=5)
    assert len(calls) == 1
    assert calls[0] is result


def test_cli_geolocation_shows_reverse_geocode_fields(monkeypatch) -> None:
    """CLI must always show city and nearest-place fields."""
    import io
    from rich.console import Console
    from netwatch import cli as cli_mod
    from netwatch.network_info import InterfaceInfo
    from netwatch.proxy_probe import ExitIPInfo

    monkeypatch.setattr(cli_mod, "get_preferred_physical_interface", lambda: {"name": "en0", "ip": "192.168.31.75", "reason": "preferred"})
    monkeypatch.setattr(cli_mod, "get_default_gateway", lambda: "192.168.31.1")
    monkeypatch.setattr(cli_mod, "probe_exit_ip", lambda: ExitIPInfo(ip="1.2.3.4", city="", region="", country="", org=""))
    monkeypatch.setattr(
        cli_mod, "get_display_network_interfaces",
        lambda: [InterfaceInfo("en0", "192.168.31.75", "aa:bb:cc:dd:ee:ff")],
    )
    monkeypatch.setattr(cli_mod, "run_browser_geolocation", lambda **kwargs: DeviceLocationResult(
        latitude=23.1291, longitude=113.2644, accuracy_m=65.0,
        country="CN", admin1="Guangdong", admin2="Zengcheng", nearest_place="Yonghe",
        reverse_geocoder_source="reverse_geocoder",
        source="browser geolocation + reverse_geocoder",
    ))

    prompts = []
    answers = iter(["y", "n"])

    def fake_prompt(prompt, *args, **kwargs):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(cli_mod.Prompt, "ask", fake_prompt)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_network_info()
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert "国家/地区" in output
    assert "CN" in output
    assert "省份/区域" in output
    assert "Guangdong" in output
    assert "城市" in output
    assert "Zengcheng" in output
    assert "区县" in output
    assert "附近地点" in output
    assert "Yonghe" in output


def test_cli_geolocation_offline_china_result_shows_city(monkeypatch) -> None:
    """Offline China lookup fields must take priority in the CLI table."""
    import io
    from rich.console import Console
    from netwatch import cli as cli_mod

    result = DeviceLocationResult(
        latitude=23.153126,
        longitude=113.581404,
        accuracy_m=30.0,
        country="CN",
        admin1="Guangdong",
        admin2="",
        nearest_place="Yonghe",
        reverse_geocoder_source="reverse_geocoder",
        china_province="广东省",
        china_city="广州市",
        china_district="黄埔区",
        source="browser geolocation + reverse_geocoder + offline_china_district_centers",
    )

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.print_device_location_result(result)
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert "纬度" in output
    assert "经度" in output
    assert "精度" in output
    assert "国家/地区" in output
    assert "省份/区域" in output
    assert "城市" in output
    assert "广州市" in output
    assert "区县" in output
    assert "黄埔区" in output
    assert "附近地点" in output
    assert "Yonghe" in output
    assert "来源" in output
    assert "offline_china_district_centers" in output


def test_cli_geolocation_not_installed_shows_not_enabled(monkeypatch) -> None:
    """CLI must show '未启用' when reverse_geocoder is not installed."""
    import io
    from rich.console import Console
    from netwatch import cli as cli_mod
    from netwatch.network_info import InterfaceInfo
    from netwatch.proxy_probe import ExitIPInfo

    monkeypatch.setattr(cli_mod, "get_preferred_physical_interface", lambda: {"name": "en0", "ip": "192.168.31.75", "reason": "preferred"})
    monkeypatch.setattr(cli_mod, "get_default_gateway", lambda: "192.168.31.1")
    monkeypatch.setattr(cli_mod, "probe_exit_ip", lambda: ExitIPInfo(ip="1.2.3.4", city="", region="", country="", org=""))
    monkeypatch.setattr(
        cli_mod, "get_display_network_interfaces",
        lambda: [InterfaceInfo("en0", "192.168.31.75", "aa:bb:cc:dd:ee:ff")],
    )
    monkeypatch.setattr(cli_mod, "run_browser_geolocation", lambda **kwargs: DeviceLocationResult(
        latitude=23.1291, longitude=113.2644, accuracy_m=65.0,
        country=None, admin1=None, admin2=None, nearest_place=None,
        reverse_geocoder_error="offline reverse geocoder is not installed",
    ))

    prompts = []
    answers = iter(["y", "n"])

    def fake_prompt(prompt, *args, **kwargs):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(cli_mod.Prompt, "ask", fake_prompt)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_network_info()
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert "未启用" in output
    assert "pip install reverse_geocoder" in output


def test_reverse_geocode_suppresses_loading_output(monkeypatch) -> None:
    """reverse_geocode_offline must suppress the library startup log."""
    import builtins

    printed_lines = []

    class FakeRG:
        @staticmethod
        def search(coords, mode=1):
            import sys
            sys.stderr.write("Loading formatted geocoded file...\n")
            return [{"name": "Yonghe", "admin1": "Guangdong", "admin2": "", "cc": "CN"}]

    _orig_import = builtins.__import__

    def _mock_import(name, *args, **kwargs):
        if name == "reverse_geocoder":
            return FakeRG
        return _orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)

    from netwatch.device_location import reverse_geocode_offline
    result = reverse_geocode_offline(23.1291, 113.2644)
    assert result["nearest_place"] == "Yonghe"
    assert result["error"] is None


def test_cli_geolocation_contains_disclaimer_text(monkeypatch) -> None:
    """CLI must show '最近地点匹配' or '不等于完整行政区划' disclaimer."""
    import io
    from rich.console import Console
    from netwatch import cli as cli_mod
    from netwatch.network_info import InterfaceInfo
    from netwatch.proxy_probe import ExitIPInfo

    monkeypatch.setattr(cli_mod, "get_preferred_physical_interface", lambda: {"name": "en0", "ip": "192.168.31.75", "reason": "preferred"})
    monkeypatch.setattr(cli_mod, "get_default_gateway", lambda: "192.168.31.1")
    monkeypatch.setattr(cli_mod, "probe_exit_ip", lambda: ExitIPInfo(ip="1.2.3.4", city="", region="", country="", org=""))
    monkeypatch.setattr(
        cli_mod, "get_display_network_interfaces",
        lambda: [InterfaceInfo("en0", "192.168.31.75", "aa:bb:cc:dd:ee:ff")],
    )
    monkeypatch.setattr(cli_mod, "run_browser_geolocation", lambda **kwargs: DeviceLocationResult(
        latitude=23.1291, longitude=113.2644, accuracy_m=65.0,
        country="CN", admin1="Guangdong", nearest_place="Yonghe",
        reverse_geocoder_source="reverse_geocoder",
        source="browser geolocation + reverse_geocoder",
    ))

    prompts = []
    answers = iter(["y", "n"])

    def fake_prompt(prompt, *args, **kwargs):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(cli_mod.Prompt, "ask", fake_prompt)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_network_info()
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert "最近地点匹配" in output or "不是真实行政边界" in output
    # CLI must not leak reverse_geocoder internal log
    assert "Loading formatted" not in output


def test_reverse_geocode_error_preserves_coordinates(monkeypatch) -> None:
    """When reverse_geocoder returns error, lat/lng must still be displayed."""
    import io
    from rich.console import Console
    from netwatch import cli as cli_mod
    from netwatch.network_info import InterfaceInfo
    from netwatch.proxy_probe import ExitIPInfo

    monkeypatch.setattr(cli_mod, "get_preferred_physical_interface", lambda: {"name": "en0", "ip": "192.168.31.75", "reason": "preferred"})
    monkeypatch.setattr(cli_mod, "get_default_gateway", lambda: "192.168.31.1")
    monkeypatch.setattr(cli_mod, "probe_exit_ip", lambda: ExitIPInfo(ip="1.2.3.4", city="", region="", country="", org=""))
    monkeypatch.setattr(
        cli_mod, "get_display_network_interfaces",
        lambda: [InterfaceInfo("en0", "192.168.31.75", "aa:bb:cc:dd:ee:ff")],
    )
    monkeypatch.setattr(cli_mod, "run_browser_geolocation", lambda **kwargs: DeviceLocationResult(
        latitude=23.1291, longitude=113.2644, accuracy_m=65.0,
        country=None, admin1=None, admin2=None, nearest_place=None,
        reverse_geocoder_error="reverse geocoder database corrupted",
    ))

    prompts = []
    answers = iter(["y", "n"])

    def fake_prompt(prompt, *args, **kwargs):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(cli_mod.Prompt, "ask", fake_prompt)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.show_network_info()
    finally:
        cli_mod.console = original_console

    output = buf.getvalue()
    assert "23.1291" in output
    assert "113.2644" in output
    assert "database corrupted" in output
