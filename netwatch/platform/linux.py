"""Linux platform backend."""

from __future__ import annotations

import re

from netwatch.platform.base import BasePlatformBackend


class LinuxBackend(BasePlatformBackend):
    """Linux implementation preserving existing route parsing semantics."""

    def get_default_gateway(self) -> str | None:
        """Return default gateway from `ip route`, falling back to `route -n`."""
        gateway = parse_linux_ip_route_gateway(self.run_command(["ip", "route", "show", "default"]))
        if gateway:
            return gateway
        return parse_linux_route_n_gateway(self.run_command(["route", "-n"]))

    def build_ping_command(self, host: str, timeout_seconds: float) -> list[str]:
        """Build a Linux one-shot ping command."""
        return ["ping", "-c", "1", "-W", str(int(timeout_seconds)), host]

    def get_arp_commands(self) -> list[list[str]]:
        """Return numeric ARP first, then hostname enrichment."""
        return [["arp", "-an"], ["arp", "-a"]]

    def get_ookla_install_hint(self) -> str:
        """Return Linux official Ookla CLI install hint."""
        return (
            "Official Ookla CLI is not installed.\n"
            "Linux 推荐按发行版从 Ookla 官方渠道安装 speedtest。\n"
            "Debian / Ubuntu 常见方式：\n"
            "curl -s https://packagecloud.io/install/repositories/ookla/speedtest-cli/script.deb.sh | sudo bash\n"
            "sudo apt install speedtest"
        )


def parse_linux_ip_route_gateway(output: str) -> str | None:
    """Parse `ip route show default` output."""
    match = re.search(r"\bdefault\s+via\s+(?P<gateway>\d{1,3}(?:\.\d{1,3}){3})\b", output)
    return match.group("gateway") if match else None


def parse_linux_route_n_gateway(output: str) -> str | None:
    """Parse `route -n` output."""
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "0.0.0.0":
            return fields[1]
    return None
