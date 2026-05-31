from netwatch.platform.windows import (
    WindowsBackend,
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


def test_windows_classify_vpn_interfaces() -> None:
    backend = WindowsBackend()

    assert backend.classify_interface("Wintun Userspace Tunnel") == "vpn"
    assert backend.classify_interface("WireGuard Tunnel") == "vpn"
    assert backend.classify_interface("Clash Verge") == "vpn"
    assert backend.classify_interface("Tailscale") == "vpn"


def test_windows_classify_virtual_and_loopback_interfaces() -> None:
    backend = WindowsBackend()

    assert backend.classify_interface("vEthernet (Default Switch)") == "virtual"
    assert backend.classify_interface("Hyper-V Virtual Ethernet Adapter") == "virtual"
    assert backend.classify_interface("VMware Network Adapter VMnet8") == "virtual"
    assert backend.classify_interface("VirtualBox Host-Only Ethernet Adapter") == "virtual"
    assert backend.classify_interface("Loopback Pseudo-Interface 1") == "loopback"
