from netwatch.network.router import (
    NetworkDevice,
    RouterDevice,
    deduplicate_router_devices,
    extract_xiaomi_stok,
    get_default_gateway,
    merge_devices,
    normalize_xiaomi_device,
    parse_macos_default_gateway,
)
import netwatch.network.router as router


def test_xiaomi_redmi_stok_missing_guidance_for_generic_luci_url(monkeypatch, capsys) -> None:
    from netwatch import cli

    monkeypatch.setattr(cli, "get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr(
        cli.Prompt,
        "ask",
        lambda *args, **kwargs: "http://192.168.1.1/cgi-bin/luci/admin/bandwidth",
    )
    monkeypatch.setattr(
        cli,
        "fetch_xiaomi_device_list",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("API must not be called")),
    )

    result = cli.prompt_and_fetch_xiaomi_redmi_stok_devices()

    output = capsys.readouterr().out
    assert result is None
    assert "未检测到 ;stok=" in output
    assert "仅适用于小米/Redmi" in output
    assert "普通 LuCI/OpenWrt/厂商后台" in output
    assert "快速扫描：Ping + ARP" in output


def test_generic_luci_option_only_shows_notice(monkeypatch, capsys) -> None:
    from netwatch import cli

    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "2")
    monkeypatch.setattr(
        cli,
        "fetch_xiaomi_device_list",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("API must not be called")),
    )

    result = cli.prompt_and_fetch_xiaomi_router_devices()

    output = capsys.readouterr().out
    assert result is None
    assert "LuCI/OpenWrt/厂商定制页面" in output
    assert "不读取浏览器 Cookie" in output
    assert "暂不支持自动同步设备名" in output


def test_router_sync_prompt_no_generic_misleading_xiaomi_copy(capsys) -> None:
    from netwatch import cli

    cli.show_generic_luci_sync_notice()

    output = capsys.readouterr().out
    assert "请先在浏览器登录小米路由器后台" not in output
    assert "通用 LuCI/OpenWrt" not in output or "暂不支持自动同步" in output


def test_extract_xiaomi_stok() -> None:
    assert extract_xiaomi_stok("http://192.168.31.1/cgi-bin/luci/;stok=abc/web/home") == "abc"
    assert extract_xiaomi_stok("http://192.168.31.1/cgi-bin/luci/;stok=abc/web/home#router") == "abc"
    assert extract_xiaomi_stok("http://192.168.31.1/cgi-bin/luci/;stok=abc/api/misystem/status") == "abc"
    assert extract_xiaomi_stok("http://192.168.31.1/cgi-bin/luci/web/home") is None


def test_extract_xiaomi_redmi_stok_url_still_works() -> None:
    assert extract_xiaomi_stok("http://192.168.31.1/cgi-bin/luci/;stok=abc123/web/home") == "abc123"


def test_normalize_xiaomi_device_ip_string_and_name() -> None:
    device = normalize_xiaomi_device(
        {
            "name": "MacBook-Air",
            "ip": "192.168.31.75",
            "mac": "A0:9A:8E:84:82:F6",
            "online": 1,
        }
    )

    assert device is not None
    assert device.name == "MacBook-Air"
    assert device.ip == "192.168.31.75"
    assert device.mac == "a0:9a:8e:84:82:f6"
    assert device.online is True


def test_normalize_xiaomi_device_ip_array_and_name_variants() -> None:
    for key in ("devname", "hostname", "nickname"):
        device = normalize_xiaomi_device(
            {
                key: f"name-from-{key}",
                "ip": [{"ip": "192.168.31.83"}],
                "mac": "8C:DE:F9:E2:A2:C4",
            }
        )

        assert device is not None
        assert device.name == f"name-from-{key}"
        assert device.ip == "192.168.31.83"
        assert device.mac == "8c:de:f9:e2:a2:c4"


def test_merge_devices_by_mac_prefers_router_name() -> None:
    scan = [
        NetworkDevice(
            name="phone.local",
            ip="192.168.31.83",
            mac="8c:de:f9:e2:a2:c4",
            hostname="phone.local",
            router_name="-",
            status="online",
            source="reverse-dns",
            connect_type="-",
        )
    ]
    router = [
        RouterDevice(
            name="iPhone",
            ip="192.168.31.200",
            mac="8c:de:f9:e2:a2:c4",
            online=True,
            connect_type="wifi",
            source="xiaomi-router-api",
            raw={},
        )
    ]

    merged = merge_devices(scan, router)

    assert len(merged) == 1
    assert merged[0].name == "iPhone"
    assert merged[0].hostname == "phone.local"
    assert merged[0].router_name == "iPhone"
    assert merged[0].source == "mixed"
    assert merged[0].status == "online"


def test_merge_devices_by_ip_when_mac_missing() -> None:
    scan = [
        NetworkDevice(
            name="-",
            ip="192.168.31.103",
            mac="-",
            hostname="-",
            router_name="-",
            status="online",
            source="scanner",
            connect_type="-",
        )
    ]
    router = [
        RouterDevice(
            name="Yang",
            ip="192.168.31.103",
            mac="d4:f3:2d:42:43:a7",
            online=True,
            connect_type="wifi",
            source="xiaomi-router-api",
            raw={},
        )
    ]

    merged = merge_devices(scan, router)

    assert len(merged) == 1
    assert merged[0].name == "Yang"
    assert merged[0].mac == "d4:f3:2d:42:43:a7"
    assert merged[0].source == "mixed"


def test_merge_devices_router_only_status() -> None:
    merged = merge_devices(
        [],
        [
            RouterDevice(
                name="iPad",
                ip="192.168.31.61",
                mac="1e:1b:a7:4b:dd:b0",
                online=True,
                connect_type="wifi",
                source="xiaomi-router-api",
                raw={},
            )
        ],
    )

    assert len(merged) == 1
    assert merged[0].status == "router-only"
    assert merged[0].source == "router-api"


def test_parse_macos_default_gateway() -> None:
    output = """
   route to: default
destination: default
       mask: default
    gateway: 192.168.31.1
  interface: en0
"""

    assert parse_macos_default_gateway(output) == "192.168.31.1"


def test_get_default_gateway_delegates_to_backend(monkeypatch) -> None:
    class FakeBackend:
        def get_lan_router_gateway(self) -> str:
            return "192.168.50.1"

        def get_default_route_gateway(self) -> str:
            return "198.18.0.2"

    monkeypatch.setattr(router, "get_backend", lambda: FakeBackend())

    assert get_default_gateway() == "192.168.50.1"


def test_get_default_gateway_falls_back_to_backend_default_route(monkeypatch) -> None:
    class FakeBackend:
        def get_lan_router_gateway(self) -> None:
            return None

        def get_default_route_gateway(self) -> str:
            return "192.168.50.1"

    monkeypatch.setattr(router, "get_backend", lambda: FakeBackend())

    assert get_default_gateway() == "192.168.50.1"


def test_router_admin_menu_prefers_lan_gateway_over_virtual_default(monkeypatch, capsys) -> None:
    from netwatch.cli_modules import router as cli_router

    monkeypatch.setattr(cli_router, "get_lan_router_gateway", lambda: "192.168.31.1")
    monkeypatch.setattr(cli_router, "get_default_route_gateway", lambda: "198.18.0.2")
    monkeypatch.setattr(cli_router.Prompt, "ask", lambda *args, **kwargs: "1")

    url = cli_router.choose_router_admin_url()

    output = capsys.readouterr().out
    assert url == "http://192.168.31.1/"
    assert "识别/推测的 LAN 路由器入口，推荐" in output
    assert "当前系统默认出口网关：198.18.0.2" in output
    assert "可能来自 VPN/TUN/代理" in output
    assert "http://198.18.0.2/" not in output
    assert "http://192.168.31.1/" in output
    assert "http://miwifi.com/" in output


def test_router_admin_menu_does_not_offer_198_19_virtual_default(monkeypatch, capsys) -> None:
    from netwatch.cli_modules import router as cli_router

    monkeypatch.setattr(cli_router, "get_lan_router_gateway", lambda: None)
    monkeypatch.setattr(cli_router, "get_default_route_gateway", lambda: "198.19.0.2")
    monkeypatch.setattr(cli_router.Prompt, "ask", lambda *args, **kwargs: "0")

    url = cli_router.choose_router_admin_url()

    output = capsys.readouterr().out
    assert url is None
    assert "当前系统默认出口网关：198.19.0.2" in output
    assert "http://198.19.0.2/" not in output
    assert "http://192.168.31.1/" in output


def test_router_admin_menu_does_not_offer_100_64_virtual_default(monkeypatch, capsys) -> None:
    from netwatch.cli_modules import router as cli_router

    monkeypatch.setattr(cli_router, "get_lan_router_gateway", lambda: None)
    monkeypatch.setattr(cli_router, "get_default_route_gateway", lambda: "100.64.0.1")
    monkeypatch.setattr(cli_router.Prompt, "ask", lambda *args, **kwargs: "0")

    url = cli_router.choose_router_admin_url()

    output = capsys.readouterr().out
    assert url is None
    assert "当前系统默认出口网关：100.64.0.1" in output
    assert "http://100.64.0.1/" not in output
    assert "http://192.168.31.1/" in output


def test_xiaomi_sync_uses_lan_gateway_not_virtual_default(monkeypatch) -> None:
    from netwatch.cli_modules import router as cli_router

    calls: list[tuple[str, str]] = []
    answers = iter(["http://192.168.31.1/cgi-bin/luci/;stok=abc/web/home"])

    monkeypatch.setattr(cli_router, "get_lan_router_gateway", lambda: "192.168.31.1")
    monkeypatch.setattr(cli_router, "get_default_gateway", lambda: "198.18.0.2")
    monkeypatch.setattr(cli_router.Prompt, "ask", lambda *args, **kwargs: next(answers))

    def fake_fetch(router_ip: str, stok: str) -> list[RouterDevice]:
        calls.append((router_ip, stok))
        return []

    monkeypatch.setattr(cli_router, "fetch_xiaomi_device_list", fake_fetch)

    result = cli_router.prompt_and_fetch_xiaomi_redmi_stok_devices()

    assert result == []
    assert calls == [("192.168.31.1", "abc")]


def test_deduplicate_same_ip_complete_and_empty_record() -> None:
    devices = deduplicate_router_devices(
        [
            RouterDevice("MacBook-Air", "192.168.31.75", "a0:9a:8e:84:82:f6", True, "wifi", "xiaomi-router-api", {}),
            RouterDevice(None, "192.168.31.75", None, True, None, "xiaomi-router-api", {}),
        ]
    )

    assert len(devices) == 1
    assert devices[0].name == "MacBook-Air"
    assert devices[0].ip == "192.168.31.75"
    assert devices[0].mac == "a0:9a:8e:84:82:f6"


def test_deduplicate_same_mac_multiple_records() -> None:
    devices = deduplicate_router_devices(
        [
            RouterDevice(None, "192.168.31.10", "aa:bb:cc:dd:ee:ff", False, None, "xiaomi-router-api", {}),
            RouterDevice("Phone", None, "aa:bb:cc:dd:ee:ff", True, "5GHz", "xiaomi-router-api", {}),
        ]
    )

    assert len(devices) == 1
    assert devices[0].name == "Phone"
    assert devices[0].ip == "192.168.31.10"
    assert devices[0].mac == "aa:bb:cc:dd:ee:ff"
    assert devices[0].online is True
    assert devices[0].connect_type == "5GHz"


def test_deduplicate_same_ip_without_mac() -> None:
    devices = deduplicate_router_devices(
        [
            RouterDevice(None, "192.168.31.20", None, False, None, "xiaomi-router-api", {}),
            RouterDevice("Camera", "192.168.31.20", None, True, "2.4GHz", "xiaomi-router-api", {}),
        ]
    )

    assert len(devices) == 1
    assert devices[0].name == "Camera"
    assert devices[0].ip == "192.168.31.20"
    assert devices[0].mac is None
    assert devices[0].online is True


def test_deduplicate_keeps_meaningful_name() -> None:
    devices = deduplicate_router_devices(
        [
            RouterDevice("-", "192.168.31.30", "11:22:33:44:55:66", False, None, "xiaomi-router-api", {}),
            RouterDevice("NOMI-IPC", "192.168.31.30", None, True, None, "xiaomi-router-api", {}),
        ]
    )

    assert len(devices) == 1
    assert devices[0].name == "NOMI-IPC"
