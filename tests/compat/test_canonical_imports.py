"""Smoke tests for canonical package imports."""

from __future__ import annotations


def test_core_canonical_imports() -> None:
    import netwatch.core.banner as banner
    import netwatch.core.config as config

    assert callable(banner.render_banner)
    assert callable(config.load_config)


def test_network_canonical_imports() -> None:
    import netwatch.network.info as info
    import netwatch.network.proxy_probe as proxy_probe
    import netwatch.network.router as router
    import netwatch.network.scanner as scanner

    assert info.InterfaceInfo
    assert proxy_probe.ExitIPInfo
    assert router.RouterDevice
    assert scanner.HostScanResult


def test_location_canonical_imports() -> None:
    import netwatch.location.admin.offline_boundary as offline_boundary
    import netwatch.location.geolocation.device as device
    import netwatch.location.roads.nearby_roads as nearby_roads

    assert device.DeviceLocationResult
    assert callable(offline_boundary.load_boundary_dataset)
    assert nearby_roads.RoadsDataset


def test_speedtest_canonical_imports() -> None:
    import netwatch.speedtest.analysis as analysis
    import netwatch.speedtest.backends.ookla_cli as ookla_cli
    import netwatch.speedtest.runner as runner
    import netwatch.speedtest.speed as speed
    import netwatch.speedtest.speedtest_cn as speedtest_cn
    import netwatch.speedtest.speedtest_cn_browser as speedtest_cn_browser

    assert callable(analysis.get_result_confidence)
    assert callable(runner.run_best_speedtest)
    assert speed.NetworkSpeed
    assert speedtest_cn.SpeedtestCnResult
    assert speedtest_cn_browser.BrowserAutomationOptions
    assert callable(ookla_cli.run_speedtest)
