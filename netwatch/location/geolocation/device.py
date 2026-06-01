"""Experimental browser geolocation via local HTTP server.

Launches a temporary local web server, opens a page requesting
navigator.geolocation.getCurrentPosition, and waits for the user
to manually allow/deny the browser permission prompt.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any


GEOLOCATION_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>netwatch-cli 设备定位</title>
<style>
body { font-family: sans-serif; max-width: 600px; margin: 2em auto; padding: 0 1em; line-height: 1.6; }
button { font-size: 1.2em; padding: 0.6em 1.2em; cursor: pointer; }
.info { color: #555; font-size: 0.9em; }
.error { color: #c00; }
.success { color: #090; }
</style>
</head>
<body>
<h2>netwatch-cli 设备定位</h2>
<p>netwatch-cli 正在请求一次性定位权限。</p>
<p class="info">浏览器会弹出权限请求，请选择“允许”。</p>
<p class="info">坐标只会回传到本机 127.0.0.1 临时服务，不会上传互联网。</p>
<p class="info">本页面仅用于本次定位，netwatch-cli 不会保存或上传你的位置。</p>
<button id="locateBtn">获取当前位置</button>
<p id="status"></p>
<script>
document.getElementById('locateBtn').addEventListener('click', function() {
    var status = document.getElementById('status');
    status.textContent = '\u6b63\u5728\u8bf7\u6c42\u5b9a\u4f4d\u6743\u9650...';
    status.className = 'info';
    navigator.geolocation.getCurrentPosition(
        function(pos) {
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/location', true);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.send(JSON.stringify({
                latitude: pos.coords.latitude,
                longitude: pos.coords.longitude,
                accuracy: pos.coords.accuracy,
                altitude: pos.coords.altitude,
                altitudeAccuracy: pos.coords.altitudeAccuracy,
                heading: pos.coords.heading,
                speed: pos.coords.speed,
                timestamp: pos.timestamp
            }));
            status.textContent = '\u5b9a\u4f4d\u6210\u529f\uff0c\u6b63\u5728\u8fd4\u56de\u7ec8\u7aef...';
            status.className = 'success';
        },
        function(err) {
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/error', true);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.send(JSON.stringify({
                code: err.code,
                message: err.message
            }));
            status.textContent = '\u5b9a\u4f4d\u5931\u8d25: ' + err.message;
            status.className = 'error';
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
});
</script>
</body>
</html>"""


@dataclass
class DeviceLocationResult:
    """Result from browser geolocation."""

    latitude: float | None = None
    longitude: float | None = None
    accuracy_m: float | None = None
    altitude: float | None = None
    altitude_accuracy: float | None = None
    heading: float | None = None
    speed: float | None = None
    timestamp: float | None = None
    source: str = "browser geolocation"
    error: str | None = None
    country: str | None = None
    admin1: str | None = None
    admin2: str | None = None
    nearest_place: str | None = None
    reverse_geocoder_source: str | None = None
    reverse_geocoder_error: str | None = None
    china_province: str | None = None
    china_city: str | None = None
    china_district: str | None = None


def reverse_geocode_offline(latitude: float, longitude: float) -> dict[str, str | None]:
    """Look up country/region/nearest-place from lat/lng using a local database.

    Uses the reverse_geocoder library (optional dependency). No network calls
    are made — coordinates stay local.

    Returns a dict with keys: country, admin1, admin2, nearest_place, source, error.
    """
    try:
        import reverse_geocoder as rg  # type: ignore[import-untyped]
    except ImportError:
        return {
            "country": None,
            "admin1": None,
            "admin2": None,
            "nearest_place": None,
            "source": None,
            "error": "offline reverse geocoder is not installed",
        }

    try:
        # Suppress reverse_geocoder startup log (e.g. "Loading formatted geocoded file...")
        import io
        from contextlib import redirect_stdout, redirect_stderr

        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            results = rg.search((latitude, longitude), mode=1)

        if not results:
            return {
                "country": None,
                "admin1": None,
                "admin2": None,
                "nearest_place": None,
                "source": None,
                "error": "reverse geocoder returned no results",
            }
        entry = results[0]
        return {
            "country": entry.get("cc"),
            "admin1": entry.get("admin1"),
            "admin2": entry.get("admin2"),
            "nearest_place": entry.get("name"),
            "source": "reverse_geocoder",
            "error": None,
        }
    except Exception as exc:
        return {
            "country": None,
            "admin1": None,
            "admin2": None,
            "nearest_place": None,
            "source": None,
            "error": f"reverse geocoder lookup failed: {exc}",
        }


def _fill_reverse_geocode(result: DeviceLocationResult) -> None:
    """Fill country/admin1/admin2/nearest_place + optional China district lookup."""
    geo = reverse_geocode_offline(result.latitude, result.longitude)  # type: ignore[arg-type]
    if geo.get("error"):
        result.reverse_geocoder_error = geo["error"]
    else:
        result.country = geo.get("country")
        result.admin1 = geo.get("admin1")
        result.admin2 = geo.get("admin2")
        result.nearest_place = geo.get("nearest_place")
        result.reverse_geocoder_source = geo.get("source")
        if geo.get("source"):
            result.source = f"{result.source} + {geo['source']}"

    # If coordinates are in China, try offline district center lookup
    if _is_likely_china(result):
        _fill_china_district(result)


def _is_likely_china(result: DeviceLocationResult) -> bool:
    """Return True if the coordinates are likely within China."""
    if result.country == "CN":
        return True
    if result.latitude is not None and result.longitude is not None:
        # Rough China bounding box
        if 3.86 <= result.latitude <= 53.55 and 73.66 <= result.longitude <= 135.05:
            return True
    return False


def _fill_china_district(result: DeviceLocationResult) -> None:
    """Attempt to find the nearest Chinese district center for these coordinates."""
    try:
        from netwatch.location.admin.china_admin_lookup import lookup_nearest_district
    except ImportError:
        return

    if result.longitude is None or result.latitude is None:
        return

    china = lookup_nearest_district(result.longitude, result.latitude, max_km=80.0)
    if china is None:
        return

    result.china_province = china.get("province") or ""
    result.china_city = china.get("city") or ""
    result.china_district = china.get("district") or ""
    if result.china_province or result.china_city or result.china_district:
        result.source = f"{result.source} + offline_china_district_centers"


def _make_handler(shared_state: list) -> type[BaseHTTPRequestHandler]:
    """Create a handler class that shares state with the caller."""

    class _LocationHandler(BaseHTTPRequestHandler):  # type: ignore[misc]
        """HTTP handler for the temporary geolocation server."""

        # Silence default logging
        def log_message(self, _format: str, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            if self.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(GEOLOCATION_HTML.encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self) -> None:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length).decode("utf-8")

            if self.path == "/location":
                payload = json.loads(body)
                shared_state[0] = DeviceLocationResult(
                    latitude=payload["latitude"],
                    longitude=payload["longitude"],
                    accuracy_m=payload["accuracy"],
                    altitude=payload.get("altitude"),
                    altitude_accuracy=payload.get("altitudeAccuracy"),
                    heading=payload.get("heading"),
                    speed=payload.get("speed"),
                    timestamp=payload.get("timestamp"),
                )
                shared_state[1].set()
                self._respond_ok("定位已接收，可以关闭此页面。")
            elif self.path == "/error":
                payload = json.loads(body)
                code = payload.get("code", "unknown")
                message = payload.get("message", "未知错误")
                shared_state[0] = DeviceLocationResult(
                    error=f"浏览器定位失败 (code={code}): {message}"
                )
                shared_state[1].set()
                self._respond_ok("定位失败，可以关闭此页面。")
            else:
                self.send_response(404)
                self.end_headers()

        def _respond_ok(self, text: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(text.encode("utf-8"))

    return _LocationHandler


def run_browser_geolocation(timeout_seconds: int = 60) -> DeviceLocationResult:
    """Start a local HTTP server, open the page, wait for user location.

    The user must manually allow the browser geolocation permission.
    Returns DeviceLocationResult with coordinates or error.
    """
    event = threading.Event()
    shared_state: list = [None, event]  # [result, event]

    handler_class = _make_handler(shared_state)
    server = HTTPServer(("127.0.0.1", 0), handler_class)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        webbrowser.open(url)
        event.wait(timeout=timeout_seconds)

        result = shared_state[0]
        if result is not None:
            if result.error is None and result.latitude is not None and result.longitude is not None:
                _fill_reverse_geocode(result)
            return result

        return DeviceLocationResult(
            error=f"设备授权定位超时（{timeout_seconds} 秒）。请确认浏览器已打开并允许定位。"
        )
    finally:
        server.shutdown()
        server.server_close()


def get_device_location_html_source() -> str:
    """Return the HTML source for testing purposes."""
    return GEOLOCATION_HTML
