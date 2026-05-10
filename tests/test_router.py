from netwatch.router import (
    NetworkDevice,
    RouterDevice,
    deduplicate_router_devices,
    extract_xiaomi_stok,
    merge_devices,
    normalize_xiaomi_device,
    parse_macos_default_gateway,
)


def test_extract_xiaomi_stok() -> None:
    assert extract_xiaomi_stok("http://192.168.31.1/cgi-bin/luci/;stok=abc/web/home") == "abc"
    assert extract_xiaomi_stok("http://192.168.31.1/cgi-bin/luci/;stok=abc/web/home#router") == "abc"
    assert extract_xiaomi_stok("http://192.168.31.1/cgi-bin/luci/;stok=abc/api/misystem/status") == "abc"
    assert extract_xiaomi_stok("http://192.168.31.1/cgi-bin/luci/web/home") is None


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
