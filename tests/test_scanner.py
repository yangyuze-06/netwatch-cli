import ipaddress
import unittest

import netwatch.scanner as scanner
from netwatch.scanner import normalize_mac_address, parse_arp_output


class ArpParsingTest(unittest.TestCase):
    def test_parse_regular_macos_mac(self) -> None:
        output = "? (192.168.31.83) at 8c:de:f9:e2:a2:c4 on en0 ifscope [ethernet]"

        entries = parse_arp_output(output)

        self.assertEqual(entries["192.168.31.83"]["hostname"], None)
        self.assertEqual(entries["192.168.31.83"]["mac"], "8c:de:f9:e2:a2:c4")

    def test_parse_permanent_macos_mac(self) -> None:
        output = "? (192.168.31.75) at a0:9a:8e:84:82:f6 on en0 ifscope permanent [ethernet]"

        entries = parse_arp_output(output)

        self.assertEqual(entries["192.168.31.75"]["mac"], "a0:9a:8e:84:82:f6")

    def test_parse_single_digit_mac_segments(self) -> None:
        output = "? (192.168.31.139) at aa:39:b3:b:8b:a on en0 ifscope [ethernet]"

        entries = parse_arp_output(output)

        self.assertEqual(entries["192.168.31.139"]["mac"], "aa:39:b3:0b:8b:0a")

    def test_skip_incomplete_records(self) -> None:
        output = "? (192.168.31.60) at (incomplete) on en0 ifscope [ethernet]"

        entries = parse_arp_output(output)

        self.assertNotIn("192.168.31.60", entries)

    def test_parse_hostname_local(self) -> None:
        output = "hostname.local (192.168.31.83) at 8c:de:f9:e2:a2:c4 on en0 ifscope [ethernet]"

        entries = parse_arp_output(output)

        self.assertEqual(entries["192.168.31.83"]["hostname"], "hostname.local")
        self.assertEqual(entries["192.168.31.83"]["mac"], "8c:de:f9:e2:a2:c4")

    def test_normalize_mac_rejects_invalid_values(self) -> None:
        self.assertIsNone(normalize_mac_address("(incomplete)"))
        self.assertIsNone(normalize_mac_address("not-a-mac"))

    def test_get_arp_table_keeps_numeric_macos_results(self) -> None:
        original_platform = scanner.platform.system
        original_run_arp = scanner.run_arp_command
        calls: list[tuple[str, ...]] = []

        def fake_run_arp(command: list[str], timeout_seconds: int = 3) -> str:
            calls.append(tuple(command))
            if command == ["arp", "-an"]:
                return "? (192.168.31.1) at 50:4f:3b:bf:41:5 on en0 ifscope [ethernet]"
            return ""

        scanner.platform.system = lambda: "Darwin"
        scanner.run_arp_command = fake_run_arp
        try:
            entries = scanner.get_arp_table()
        finally:
            scanner.platform.system = original_platform
            scanner.run_arp_command = original_run_arp

        self.assertEqual(calls, [("arp", "-an"), ("arp", "-a")])
        self.assertEqual(entries["192.168.31.1"]["mac"], "50:4f:3b:bf:41:05")


class ScanNetworkArpRefreshTest(unittest.TestCase):
    def test_scan_reads_arp_table_after_ping(self) -> None:
        events: list[str] = []
        original_ping = scanner.ping_host
        original_arp = scanner.get_arp_table
        original_resolve = scanner.resolve_hostname

        def fake_ping(ip_address: str, timeout_seconds: int = 1) -> bool:
            events.append(f"ping:{ip_address}")
            return ip_address == "192.168.31.83"

        def fake_arp_table() -> dict[str, dict[str, str | None]]:
            events.append("arp")
            return {
                "192.168.31.83": {
                    "hostname": "hostname.local",
                    "mac": "8c:de:f9:e2:a2:c4",
                }
            }

        scanner.ping_host = fake_ping
        scanner.get_arp_table = fake_arp_table
        scanner.resolve_hostname = lambda ip_address: None
        try:
            results = scanner.scan_network(ipaddress.ip_network("192.168.31.82/31"), workers=1)
        finally:
            scanner.ping_host = original_ping
            scanner.get_arp_table = original_arp
            scanner.resolve_hostname = original_resolve

        self.assertEqual(events[-1], "arp")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].ip, "192.168.31.83")
        self.assertEqual(results[0].mac, "8c:de:f9:e2:a2:c4")
        self.assertEqual(results[0].hostname, "hostname.local")


if __name__ == "__main__":
    unittest.main()
