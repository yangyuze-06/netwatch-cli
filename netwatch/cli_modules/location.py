"""Location-related CLI display and interaction helpers."""

from __future__ import annotations

from rich.prompt import Prompt
from rich.table import Table

from netwatch.device_location import DeviceLocationResult, run_browser_geolocation as _default_run_browser_geolocation
from netwatch.network_info import (
    get_display_network_interfaces as _default_get_display_network_interfaces,
    get_preferred_physical_interface as _default_get_preferred_physical_interface,
)
from netwatch.proxy_probe import probe_exit_ip as _default_probe_exit_ip
from netwatch.router import get_default_gateway as _default_get_default_gateway
from netwatch.cli_modules.common import cli_override, console


def get_preferred_physical_interface():
    return cli_override(
        "get_preferred_physical_interface",
        _default_get_preferred_physical_interface,
        current=get_preferred_physical_interface,
    )()


def get_display_network_interfaces():
    return cli_override(
        "get_display_network_interfaces",
        _default_get_display_network_interfaces,
        current=get_display_network_interfaces,
    )()


def get_default_gateway():
    return cli_override("get_default_gateway", _default_get_default_gateway, current=get_default_gateway)()


def probe_exit_ip():
    return cli_override("probe_exit_ip", _default_probe_exit_ip, current=probe_exit_ip)()


def run_browser_geolocation(*args, **kwargs):
    return cli_override(
        "run_browser_geolocation",
        _default_run_browser_geolocation,
        current=run_browser_geolocation,
    )(*args, **kwargs)


def show_network_info() -> None:
    """Display local network info and public exit location, with optional full interface list."""
    # 1. Local network info
    preferred = get_preferred_physical_interface()
    gateway = get_default_gateway()

    preferred_mac: str | None = None
    if preferred:
        all_interfaces = get_display_network_interfaces()
        for iface in all_interfaces:
            if iface.name == preferred["name"]:
                preferred_mac = iface.mac
                break

    lan_table = Table(title="本机局域网信息")
    lan_table.add_column("Field", style="bold cyan")
    lan_table.add_column("Value")
    if preferred:
        lan_table.add_row("主要网卡", preferred["name"])
        lan_table.add_row("IPv4 地址", preferred["ip"])
        lan_table.add_row("MAC 地址", preferred_mac or "-")
    else:
        lan_table.add_row("主要网卡", "-")
        lan_table.add_row("IPv4 地址", "-")
        lan_table.add_row("MAC 地址", "-")
    lan_table.add_row("默认网关", gateway or "-")
    console.print(lan_table)

    # 2. Public exit location
    exit_info = probe_exit_ip()
    exit_table = Table(title="当前公网出口")
    exit_table.add_column("Field", style="bold cyan")
    exit_table.add_column("Value")
    if exit_info.error:
        exit_table.add_row("信息", "未能获取当前公网出口信息。")
    else:
        exit_table.add_row("公网 IP", exit_info.ip or "-")
        exit_table.add_row("国家/地区", exit_info.country or exit_info.region or "-")
        exit_table.add_row("城市", exit_info.city or "-")
        exit_table.add_row("ISP/组织", exit_info.org or "-")
    console.print(exit_table)
    console.print("[dim]该位置来自公网 IP 粗略定位。若使用 VPN/TUN/代理，显示的是代理出口位置，不代表真实所在地。[/dim]")
    console.print("[dim]公网出口位置来自 IP 数据库，城市可能不准确。[/dim]")

    # 3. Optional browser geolocation
    try:
        use_geolocation = Prompt.ask("是否使用浏览器授权定位进行更准确的位置检测？", choices=["y", "n"], default="n")
    except KeyboardInterrupt:
        console.print("\n[yellow]已返回主菜单。[/yellow]")
        return

    if use_geolocation.lower() == "y":
        console.print("[yellow]这是实验功能，会打开本地临时网页请求浏览器定位权限。[/yellow]")
        console.print("[yellow]请在浏览器中手动点击允许。[/yellow]")
        console.print("[yellow]netwatch-cli 不会保存或上传你的位置。[/yellow]")
        with console.status("[bold green]等待浏览器定位...[/bold green]"):
            geo_result = run_browser_geolocation()
        print_device_location_result(geo_result)

    # 4. Ask about full interface details
    try:
        show_all = Prompt.ask("是否查看全部网卡详情？", choices=["y", "n"], default="n")
    except KeyboardInterrupt:
        console.print("\n[yellow]已返回主菜单。[/yellow]")
        return

    if show_all.lower() == "y":
        interfaces = get_display_network_interfaces()
        if not interfaces:
            console.print("[yellow]未找到可显示的网络接口。[/yellow]")
            return
        table = Table(title="全部网卡信息")
        table.add_column("网卡名称", style="bold cyan")
        table.add_column("IPv4 地址")
        table.add_column("MAC 地址")
        for iface in interfaces:
            table.add_row(iface.name, iface.ipv4 or "-", iface.mac or "-")
        console.print(table)




def print_device_location_result(result: DeviceLocationResult) -> None:
    """Print a browser geolocation result."""
    if result.error:
        console.print(f"[red]设备授权定位失败：{result.error}[/red]")
        console.print("[yellow]可能原因：[/yellow]")
        console.print("[yellow]- 用户拒绝浏览器定位权限[/yellow]")
        console.print("[yellow]- 浏览器定位服务不可用[/yellow]")
        console.print("[yellow]- 浏览器无法访问 localhost[/yellow]")
        console.print("[yellow]- 超时[/yellow]")
        return

    table = Table(title="设备授权定位")
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    table.add_row("纬度", f"{result.latitude:.6f}" if result.latitude is not None else "-")
    table.add_row("经度", f"{result.longitude:.6f}" if result.longitude is not None else "-")
    table.add_row("精度", f"约 {result.accuracy_m:.0f} 米" if result.accuracy_m is not None else "-")
    table.add_row("国家/地区", result.country or "-")

    # China district center lookup takes priority for province/city/district
    if result.china_province or result.china_city or result.china_district:
        table.add_row("省份/区域", result.china_province or result.admin1 or "-")
        table.add_row("城市", result.china_city or "未知")
        table.add_row("区县", result.china_district or "未知")
        table.add_row("附近地点", result.nearest_place or "-")
    else:
        table.add_row("省份/区域", result.admin1 or "-")
        table.add_row("城市", result.admin2 or "未知")
        table.add_row("区县", "未知")
        table.add_row("附近地点", result.nearest_place or "-")

    if result.reverse_geocoder_error:
        if "not installed" in (result.reverse_geocoder_error or ""):
            table.add_row("离线反向地理编码", "[dim]未启用[/dim]")
            table.add_row("来源", result.source)
            console.print(table)
            console.print("[dim]离线反向地理编码返回最近地点匹配，不等于完整行政区划或精确地址。[/dim]")
            console.print("[yellow]安装 reverse_geocoder 后可离线显示地点：[/yellow]")
            console.print("[bold]pip install reverse_geocoder[/bold]")
            return
        table.add_row("离线反向地理编码", f"[yellow]错误: {result.reverse_geocoder_error}[/yellow]")
        table.add_row("来源", result.source)
        console.print(table)
        console.print("[dim]离线反向地理编码返回最近地点匹配，不等于完整行政区划或精确地址。[/dim]")
        return

    table.add_row("来源", result.source)
    console.print(table)
    console.print("[dim]区县位置来自离线最近中心点匹配，不是真实行政边界。[/dim]")




