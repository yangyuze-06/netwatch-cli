from netwatch.platform.windows import (
    WindowsBackend,
    infer_common_home_gateway_from_ipv4,
    is_virtual_gateway_address,
    parse_windows_ipconfig_adapter_gateways,
    parse_windows_ipconfig_gateway,
    parse_windows_route_print_gateway,
)


def test_parse_windows_route_print_gateway_english_output() -> None:
    output = """
IPv4 Route Table
===========================================================================
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0    192.168.31.1  192.168.31.75     25
        127.0.0.0        255.0.0.0         On-link       127.0.0.1    331
"""

    assert parse_windows_route_print_gateway(output) == "192.168.31.1"


def test_parse_windows_route_print_gateway_prefers_lowest_metric() -> None:
    output = """
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0       10.0.0.1      10.0.0.20     50
          0.0.0.0          0.0.0.0    192.168.1.1   192.168.1.20     10
"""

    assert parse_windows_route_print_gateway(output) == "192.168.1.1"


def test_parse_windows_route_print_gateway_without_default_route() -> None:
    output = """
Network Destination        Netmask          Gateway       Interface  Metric
        127.0.0.0        255.0.0.0         On-link       127.0.0.1    331
"""

    assert parse_windows_route_print_gateway(output) is None


def test_parse_windows_ipconfig_gateway_english_inline() -> None:
    output = """
Wireless LAN adapter Wi-Fi:
   IPv4 Address. . . . . . . . . . . : 192.168.1.20
   Default Gateway . . . . . . . . . : 192.168.1.1
"""

    assert parse_windows_ipconfig_gateway(output) == "192.168.1.1"


def test_parse_windows_ipconfig_gateway_chinese_inline() -> None:
    output = """
无线局域网适配器 WLAN:
   IPv4 地址 . . . . . . . . . . . . : 192.168.31.20
   默认网关. . . . . . . . . . . . . : 192.168.31.1
"""

    assert parse_windows_ipconfig_gateway(output) == "192.168.31.1"


def test_parse_windows_ipconfig_gateway_on_next_line() -> None:
    output = """
Ethernet adapter Ethernet:
   Default Gateway . . . . . . . . . :
                                       10.0.0.1
"""

    assert parse_windows_ipconfig_gateway(output) == "10.0.0.1"


def test_windows_build_ping_command() -> None:
    assert WindowsBackend().build_ping_command("192.168.1.1", 1) == [
        "ping",
        "-n",
        "1",
        "-w",
        "1000",
        "192.168.1.1",
    ]


def test_windows_parse_arp_output_normalizes_dash_mac() -> None:
    output = """
Interface: 192.168.1.20 --- 0x12
  Internet Address      Physical Address      Type
  192.168.1.1           aa-bb-cc-dd-ee-ff     dynamic
"""

    assert WindowsBackend().parse_arp_output(output) == [("192.168.1.1", "aa:bb:cc:dd:ee:ff")]


def test_windows_parse_arp_output_ignores_invalid_rows() -> None:
    output = """
  192.168.1.1           incomplete            invalid
  192.168.1.2           not-a-mac             dynamic
"""

    assert WindowsBackend().parse_arp_output(output) == []


def test_windows_classify_physical_interfaces() -> None:
    backend = WindowsBackend()

    assert backend.classify_interface("Wi-Fi") == "physical"
    assert backend.classify_interface("Ethernet") == "physical"
    assert backend.classify_interface("以太网") == "physical"
    assert backend.classify_interface("Intel(R) Wi-Fi 6 AX201") == "physical"


def test_windows_classify_vpn_interfaces() -> None:
    backend = WindowsBackend()

    assert backend.classify_interface("Wintun Userspace Tunnel") == "vpn"
    assert backend.classify_interface("WireGuard Tunnel") == "vpn"
    assert backend.classify_interface("Clash Verge") == "vpn"
    assert backend.classify_interface("Clash Meta TUN") == "vpn"
    assert backend.classify_interface("Tailscale") == "vpn"
    assert backend.classify_interface("Meta Ethernet Adapter") == "physical"


def test_windows_classify_virtual_and_loopback_interfaces() -> None:
    backend = WindowsBackend()

    assert backend.classify_interface("vEthernet (Default Switch)") == "virtual"
    assert backend.classify_interface("Hyper-V Virtual Ethernet Adapter") == "virtual"
    assert backend.classify_interface("VMware Network Adapter VMnet8") == "virtual"
    assert backend.classify_interface("VirtualBox Host-Only Ethernet Adapter") == "virtual"
    assert backend.classify_interface("Loopback Pseudo-Interface 1") == "loopback"


def test_windows_lan_router_gateway_ignores_198_18_default_route(monkeypatch) -> None:
    backend = WindowsBackend()
    monkeypatch.setattr(
        "netwatch.platform.windows.get_windows_interface_ipv4s",
        lambda: [
            ("Clash Wintun", "198.18.0.2"),
            ("Wi-Fi", "192.168.31.83"),
        ],
    )
    monkeypatch.setattr(
        backend,
        "run_command",
        lambda command: (
            "0.0.0.0 0.0.0.0 198.18.0.2 198.18.0.1 1"
            if command == ["route", "print", "-4"]
            else ""
        ),
    )

    assert backend.get_default_route_gateway() == "198.18.0.2"
    assert backend.get_lan_router_gateway() == "192.168.31.1"


def test_windows_lan_router_gateway_prefers_explicit_same_subnet_gateway(monkeypatch) -> None:
    backend = WindowsBackend()
    monkeypatch.setattr(
        "netwatch.platform.windows.get_windows_interface_ipv4s",
        lambda: [
            ("Clash Wintun", "198.19.0.2"),
            ("Wi-Fi", "192.168.31.83"),
        ],
    )

    def fake_run_command(command):
        if command == ["route", "print", "-4"]:
            return """
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0      198.19.0.2      198.19.0.1      1
"""
        if command == ["ipconfig"]:
            return """
Wireless LAN adapter Wi-Fi:
   IPv4 Address. . . . . . . . . . . : 192.168.31.83
   Default Gateway . . . . . . . . . : 192.168.31.254
"""
        return ""

    monkeypatch.setattr(backend, "run_command", fake_run_command)

    assert backend.get_default_route_gateway() == "198.19.0.2"
    assert backend.get_lan_router_gateway() == "192.168.31.254"


def test_windows_lan_router_gateway_falls_back_to_common_home_heuristic(monkeypatch) -> None:
    backend = WindowsBackend()
    monkeypatch.setattr(
        "netwatch.platform.windows.get_windows_interface_ipv4s",
        lambda: [("Wi-Fi", "192.168.31.83")],
    )
    monkeypatch.setattr(backend, "run_command", lambda command: "")

    assert backend.get_lan_router_gateway() == "192.168.31.1"


def test_parse_windows_ipconfig_adapter_gateways() -> None:
    output = """
Wireless LAN adapter Wi-Fi:
   IPv4 Address. . . . . . . . . . . : 192.168.31.83
   Default Gateway . . . . . . . . . : 192.168.31.254

Ethernet adapter Clash Meta TUN:
   IPv4 Address. . . . . . . . . . . : 198.19.0.1
   Default Gateway . . . . . . . . . : 198.19.0.2
"""

    candidates = parse_windows_ipconfig_adapter_gateways(output)

    assert [(item.interface_name, item.interface_ipv4, item.gateway) for item in candidates] == [
        ("Wireless LAN adapter Wi-Fi", "192.168.31.83", "192.168.31.254"),
        ("Ethernet adapter Clash Meta TUN", "198.19.0.1", "198.19.0.2"),
    ]


def test_virtual_gateway_ranges_are_not_router_gateways() -> None:
    assert is_virtual_gateway_address("198.18.0.2") is True
    assert is_virtual_gateway_address("198.19.0.2") is True
    assert is_virtual_gateway_address("100.64.0.1") is True
    assert is_virtual_gateway_address("192.168.31.1") is False


def test_infer_common_home_gateway_from_private_lan_ip_is_heuristic() -> None:
    assert infer_common_home_gateway_from_ipv4("192.168.31.83") == "192.168.31.1"
    assert infer_common_home_gateway_from_ipv4("192.168.1.83") == "192.168.1.1"
    assert infer_common_home_gateway_from_ipv4("192.168.0.83") == "192.168.0.1"
    assert infer_common_home_gateway_from_ipv4("10.8.0.23") == "10.8.0.1"
    assert infer_common_home_gateway_from_ipv4("198.18.0.2") is None
