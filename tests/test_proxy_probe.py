import subprocess

from netwatch.proxy_probe import parse_ipinfo_json, probe_exit_ip
from netwatch import proxy_probe


def test_probe_exit_ip_parses_ipinfo_json() -> None:
    info = parse_ipinfo_json(
        '{"ip":"1.2.3.4","city":"Shanghai","region":"Shanghai","country":"CN","org":"Example ISP"}'
    )

    assert info.ip == "1.2.3.4"
    assert info.city == "Shanghai"
    assert info.region == "Shanghai"
    assert info.country == "CN"
    assert info.org == "Example ISP"


def test_probe_exit_ip_network_failure_returns_error(monkeypatch) -> None:
    monkeypatch.setattr(proxy_probe.shutil, "which", lambda command: "/usr/bin/curl")

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(["curl"], 8)

    monkeypatch.setattr(proxy_probe.subprocess, "run", raise_timeout)

    info = probe_exit_ip()

    assert info.error
    assert info.ip is None
