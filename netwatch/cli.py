"""Interactive command-line interface for netwatch-cli."""

from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from netwatch.device_location import DeviceLocationResult, run_browser_geolocation
from netwatch.network_info import (
    NetworkCandidate,
    get_display_network_interfaces,
    get_lan_scan_candidates,
    get_preferred_physical_interface,
)
from netwatch.scanner import scan_network
from netwatch.router import (
    NetworkDevice,
    RouterApiError,
    RouterDevice,
    extract_xiaomi_stok,
    fetch_xiaomi_device_list,
    get_default_gateway,
    mask_stok,
    merge_devices,
    router_devices_to_network_devices,
    scan_results_to_network_devices,
)
from netwatch.speed import format_speed, sample_network_speed
from netwatch.cli_speedtest import (
    open_speedtest_cn_reference,
    print_speedtest_result,
    run_best_speedtest,
    run_librespeed_custom_speedtest,
    run_speedtest_with_status,
    run_speedtest_cn_browser_automation,
    show_auto_speedtest,
    show_clear_preferred_speedtest,
    show_isp_city_preset_speedtest,
    show_keyword_speedtest,
    show_last_speedtest_raw_summary,
    show_librespeed_custom_menu,
    show_librespeed_local_json_speedtest,
    show_librespeed_server_json_speedtest,
    show_ookla_selection_details,
    show_proxy_exit_speedtest,
    show_save_last_speedtest_server,
    show_speedtest_backend_info,
    show_speedtest_by_server_id,
    show_speedtest_cn_browser_automation,
    show_speedtest_cn_main,
    show_speedtest_config,
    format_speedtest_cn_label,
)
from netwatch.proxy_probe import probe_exit_ip

console = Console()
LAST_SCAN_DEVICES: list[NetworkDevice] = []
LAST_ROUTER_DEVICES: list[RouterDevice] = []
def build_menu() -> Panel:
    """Build the main menu panel."""
    menu = "\n".join(
        [
            "[bold cyan]1[/bold cyan]. 查看实时网卡流量",
            "[bold cyan]2[/bold cyan]. 查看本机网络信息",
            "[bold cyan]3[/bold cyan]. 局域网设备发现",
            "[bold cyan]4[/bold cyan]. 宽带测速（speedtest.cn）",
            "[bold cyan]5[/bold cyan]. 代理/当前出口测速",
            "[bold cyan]6[/bold cyan]. 打开路由器管理后台",
            "[bold cyan]7[/bold cyan]. 高级功能",
            "[bold cyan]8[/bold cyan]. 退出",
        ]
    )
    return Panel(menu, title="netwatch-cli", subtitle="轻量级网络状态工具", border_style="cyan")


def show_realtime_traffic() -> None:
    """Refresh current network throughput once per second until Ctrl+C."""
    console.print("[yellow]这是当前网卡实时吞吐量，不代表最大带宽。[/yellow]")
    console.print("[dim]按 Ctrl+C 返回菜单[/dim]")
    table = Table(title="实时网卡流量")
    table.add_column("Metric", style="bold")
    table.add_column("Speed", justify="right")

    try:
        with Live(table, console=console, refresh_per_second=4, screen=False) as live:
            while True:
                speed = sample_network_speed(interval=1.0)
                updated = Table(title="实时网卡流量")
                updated.add_column("Metric", style="bold")
                updated.add_column("Speed", justify="right")
                updated.add_row("Upload speed", format_speed(speed.upload_bps))
                updated.add_row("Download speed", format_speed(speed.download_bps))
                live.update(updated)
    except KeyboardInterrupt:
        console.print("\n[green]已返回菜单[/green]")


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


def run_lan_scan() -> list[NetworkDevice] | None:
    """Scan the inferred /24 local network and return unified devices."""
    global LAST_SCAN_DEVICES
    candidate = choose_lan_scan_candidate()
    if candidate is None:
        return None

    network = candidate.network
    console.print(f"[bold]当前选择的网卡名称：[/bold]{candidate.name}")
    console.print(f"[bold]当前 IP：[/bold]{candidate.ipv4}")
    console.print(f"[bold]推测扫描网段：[/bold]{network}")

    if not Confirm.ask("是否继续扫描？", default=False):
        console.print("[yellow]已取消局域网扫描。[/yellow]")
        return None

    with console.status("[bold green]正在 ping 扫描局域网在线设备...[/bold green]"):
        results = scan_network(network)

    LAST_SCAN_DEVICES = scan_results_to_network_devices(results)

    if results:
        print_network_devices(LAST_SCAN_DEVICES, title=f"在线设备 ({network})")
        console.print(f"[green]Found {len(results)} online devices.[/green]")
    else:
        console.print("[yellow]未发现在线主机，或当前环境禁用了 ping 响应。[/yellow]")
        console.print("[yellow]Found 0 online devices.[/yellow]")

    return LAST_SCAN_DEVICES


def show_lan_discovery_menu() -> None:
    """Run LAN device discovery submenu."""
    while True:
        try:
            console.print(build_lan_discovery_menu())
            choice = Prompt.ask("请选择局域网设备发现功能", choices=["1", "2", "3", "4"], default="1")
        except KeyboardInterrupt:
            console.print("\n[yellow]已返回主菜单。[/yellow]")
            break
        if choice == "1":
            run_lan_scan()
        elif choice == "2":
            show_enhanced_lan_discovery()
        elif choice == "3":
            show_router_only_device_sync()
        elif choice == "4":
            break


def build_lan_discovery_menu() -> Panel:
    """Build LAN discovery submenu."""
    menu = "\n".join(
        [
            "[bold cyan]1[/bold cyan]. 快速扫描：Ping + ARP",
            "[bold cyan]2[/bold cyan]. 增强扫描：Ping + ARP + 路由器设备名",
            "[bold cyan]3[/bold cyan]. 路由器设备名同步（实验）",
            "[bold cyan]4[/bold cyan]. 返回主菜单",
        ]
    )
    return Panel(menu, title="局域网设备发现", border_style="cyan")


def show_enhanced_lan_discovery() -> None:
    """Run LAN scan and optionally merge router device names."""
    scan_devices = run_lan_scan()
    if scan_devices is None:
        return

    if not Confirm.ask("是否从路由器同步设备名？", default=True):
        return

    router_devices = prompt_and_fetch_xiaomi_router_devices()
    if router_devices is None:
        console.print("[yellow]已回退到快速扫描结果。[/yellow]")
        print_network_devices(scan_devices, title="快速扫描结果")
        return

    devices = merge_devices(scan_devices, router_devices)
    print_network_devices(devices, title="增强扫描结果")


def show_router_only_device_sync() -> None:
    """Fetch router devices without ping scanning when a supported adapter is selected."""
    router_devices = prompt_and_fetch_xiaomi_router_devices()
    if router_devices is None:
        return

    devices = router_devices_to_network_devices(router_devices)
    print_network_devices(devices, title="路由器设备列表")
    console.print("[yellow]如需确认当前在线连通性，请运行“快速扫描”或“增强扫描”。[/yellow]")


def choose_lan_scan_candidate() -> NetworkCandidate | None:
    """Let the user choose a safe LAN scan candidate when needed."""
    candidates = get_lan_scan_candidates()
    if not candidates:
        console.print("[red]未找到可用于局域网扫描的真实网卡。[/red]")
        console.print("[dim]已排除 loopback、链路本地、198.18.0.0/15 和常见虚拟网卡。[/dim]")
        return None

    if len(candidates) == 1:
        return candidates[0]

    table = Table(title="请选择用于局域网扫描的网卡")
    table.add_column("#", justify="right")
    table.add_column("网卡名称", style="bold cyan")
    table.add_column("IPv4 地址")
    table.add_column("推测网段")

    for index, candidate in enumerate(candidates, start=1):
        table.add_row(str(index), candidate.name, candidate.ipv4, str(candidate.network))

    console.print(table)
    choice = IntPrompt.ask("请输入网卡编号", choices=[str(i) for i in range(1, len(candidates) + 1)])
    return candidates[choice - 1]




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




def show_open_router_admin() -> None:
    """Open a selected router admin page in the default browser."""
    url = choose_router_admin_url()
    if url is None:
        return
    console.print(f"[green]正在打开路由器管理后台：{url}[/green]")
    import webbrowser

    webbrowser.open(url)


def choose_router_admin_url() -> str | None:
    """Let the user choose a common router admin URL."""
    gateway = get_default_gateway()
    options: list[tuple[str, str]] = []
    if gateway:
        options.append((f"http://{gateway}/", "当前默认网关，推荐"))

    options.extend(
        [
            ("http://192.168.31.1/", "小米 / Redmi 常见"),
            ("http://miwifi.com/", "小米 / Redmi"),
            ("http://192.168.0.1/", "TP-Link / Netgear / D-Link 常见"),
            ("http://192.168.1.1/", "TP-Link / ASUS / Linksys 常见"),
            ("http://192.168.50.1/", "ASUS 常见"),
            ("http://tplinkwifi.net/", "TP-Link"),
            ("http://router.asus.com/", "ASUS"),
        ]
    )

    console.print("[bold]检测到当前默认网关：[/bold]" if gateway else "[yellow]未检测到当前默认网关。[/yellow]")
    table = Table(title="路由器管理后台入口")
    table.add_column("#", justify="right")
    table.add_column("URL", style="bold cyan")
    table.add_column("说明")

    for index, (url, description) in enumerate(options, start=1):
        table.add_row(str(index), url, description)
    manual_index = len(options) + 1
    table.add_row(str(manual_index), "手动输入", "输入 IP、域名或完整 URL")
    table.add_row("0", "返回", "返回主菜单")
    console.print(table)

    choices = [str(index) for index in range(1, manual_index + 1)] + ["0"]
    default = "1" if gateway else str(manual_index)
    choice = Prompt.ask("请选择要打开的入口", choices=choices, default=default)

    if choice == "0":
        return None
    if int(choice) == manual_index:
        manual_url = Prompt.ask("请输入路由器地址或 URL").strip()
        return normalize_router_admin_url(manual_url)
    return options[int(choice) - 1][0]


def normalize_router_admin_url(value: str) -> str | None:
    """Normalize user router admin input to a URL."""
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    return f"http://{value}/"


def prompt_and_fetch_xiaomi_router_devices() -> list[RouterDevice] | None:
    """Prompt for router sync method and fetch device list when supported."""
    method = choose_router_sync_method()
    if method == "xiaomi-redmi":
        return prompt_and_fetch_xiaomi_redmi_stok_devices()
    if method == "generic-luci":
        show_generic_luci_sync_notice()
    return None


def choose_router_sync_method() -> str | None:
    """Let the user choose a router device-name sync method."""
    table = Table(title="请选择路由器同步方式")
    table.add_column("#", justify="right")
    table.add_column("方式", style="bold cyan")
    table.add_column("说明")
    table.add_row("1", "小米/Redmi stok API", "登录后 URL 通常包含 ;stok=xxxx")
    table.add_row("2", "通用 LuCI/OpenWrt 后台", "暂不支持自动同步，仅显示说明")
    table.add_row("3", "返回", "返回上一级菜单")
    console.print(table)
    choice = Prompt.ask("请选择路由器同步方式", choices=["1", "2", "3"], default="3")
    if choice == "1":
        return "xiaomi-redmi"
    if choice == "2":
        return "generic-luci"
    return None


def show_generic_luci_sync_notice() -> None:
    """Explain generic LuCI/OpenWrt sync limitations."""
    console.print("[yellow]检测到的后台可能是 LuCI/OpenWrt/厂商定制页面。[/yellow]")
    console.print("[yellow]这类后台通常不一定使用 ;stok=。[/yellow]")
    console.print("[yellow]当前 netwatch-cli 不读取浏览器 Cookie，也不绕过登录。[/yellow]")
    console.print("[yellow]因此暂不支持自动同步设备名。[/yellow]")
    console.print("[yellow]请使用“快速扫描：Ping + ARP”获取 IP/MAC。[/yellow]")
    console.print("[yellow]未来可以为具体品牌/型号增加只读适配器。[/yellow]")


def print_missing_stok_guidance(pasted_url: str) -> None:
    """Print guidance when a Xiaomi/Redmi stok URL was expected but not found."""
    console.print("[red]未检测到 ;stok= token。[/red]")
    console.print("[yellow]该同步方式仅适用于小米/Redmi 路由器登录后的 URL，例如：[/yellow]")
    console.print("[dim]http://192.168.31.1/cgi-bin/luci/;stok=xxxx/web/home[/dim]")
    console.print(f"[dim]你当前粘贴的 URL：{pasted_url or '-'}[/dim]")
    console.print("[yellow]你当前粘贴的 URL 看起来可能是普通 LuCI/OpenWrt/厂商后台。[/yellow]")
    console.print("[yellow]请返回并选择：通用 LuCI/OpenWrt 后台（暂不支持自动同步）[/yellow]")
    console.print("[yellow]或使用：快速扫描：Ping + ARP。[/yellow]")


def prompt_and_fetch_xiaomi_redmi_stok_devices() -> list[RouterDevice] | None:
    """Prompt for Xiaomi/Redmi stok URL and fetch device list."""
    global LAST_ROUTER_DEVICES
    gateway = get_default_gateway()
    if not gateway:
        gateway = Prompt.ask("请输入路由器地址，例如 192.168.31.1").strip()
    if not gateway:
        console.print("[yellow]未提供路由器地址。[/yellow]")
        return

    console.print(f"[bold]路由器地址：[/bold]{gateway}")
    console.print("[dim]当前自动同步仅支持小米/Redmi 路由器的 stok API。[/dim]")
    console.print("[dim]其他 LuCI/OpenWrt/厂商后台可能没有 ;stok=，暂不支持自动同步。[/dim]")
    console.print("[dim]请先在浏览器登录小米/Redmi 路由器后台。[/dim]")
    console.print("[dim]登录后复制浏览器地址栏中的完整 URL，URL 通常包含 ;stok=xxxx。[/dim]")
    pasted_url = Prompt.ask("请粘贴小米/Redmi 登录后的 URL").strip()
    stok = extract_xiaomi_stok(pasted_url)
    if not stok:
        print_missing_stok_guidance(pasted_url)
        return None

    console.print(f"[dim]stok: {mask_stok(stok)}[/dim]")
    try:
        router_devices = fetch_xiaomi_device_list(gateway, stok)
    except RouterApiError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("[yellow]已回退到 ARP / reverse DNS / mDNS 可获得的信息。[/yellow]")
        return None

    LAST_ROUTER_DEVICES = router_devices
    console.print(f"[green]从路由器同步到 {len(router_devices)} 台设备。[/green]")
    return router_devices


def print_network_devices(devices: list[NetworkDevice], *, title: str, debug: bool = False) -> None:
    """Print unified network device table."""
    table = Table(title=title)
    table.add_column("Name", style="bold cyan")
    table.add_column("IP")
    table.add_column("MAC")
    table.add_column("Source")
    table.add_column("Status")
    if debug:
        table.add_column("Hostname")
        table.add_column("Router Name")
        table.add_column("Connect Type")

    for device in devices:
        row = [device.name, device.ip, device.mac, device.source, device.status]
        if debug:
            row.extend([device.hostname, device.router_name, device.connect_type])
        table.add_row(*row)
    console.print(table)



def build_advanced_menu() -> Panel:
    """Build advanced feature menu."""
    menu = "\n".join(
        [
            "[bold cyan]1[/bold cyan]. 通用测速诊断（Ookla / LibreSpeed / Python fallback）",
            "[bold cyan]2[/bold cyan]. 指定 Ookla server id 测速",
            "[bold cyan]3[/bold cyan]. 按关键词筛选 Ookla 服务器测速",
            "[bold cyan]4[/bold cyan]. 按当前运营商/城市优选服务器",
            "[bold cyan]5[/bold cyan]. 保存最近一次成功测速服务器为默认",
            "[bold cyan]6[/bold cyan]. 清除默认测速服务器",
            "[bold cyan]7[/bold cyan]. 查看当前测速配置",
            "[bold cyan]8[/bold cyan]. 显示最近一次测速摘要",
            "[bold cyan]9[/bold cyan]. 显示测速后端信息",
            "[bold cyan]10[/bold cyan]. 显示 Ookla server selection details",
            "[bold cyan]11[/bold cyan]. LibreSpeed 自定义服务器列表测速",
            "[bold cyan]12[/bold cyan]. 打开 speedtest.cn 网页对照测速",
            "[bold cyan]13[/bold cyan]. 返回主菜单",
        ]
    )
    return Panel(menu, title="高级功能", border_style="cyan")


def show_advanced_menu() -> None:
    """Run advanced menu."""
    while True:
        try:
            console.print(build_advanced_menu())
            console.print("[yellow]通用测速诊断会依次尝试 official Ookla CLI、LibreSpeed CLI、Python speedtest-cli fallback。[/yellow]")
            console.print("[yellow]该结果受测速服务器池、网络路径、代理/TUN 和服务器质量影响，不一定代表本地宽带最大值。[/yellow]")
            choice = Prompt.ask(
                "请选择高级功能",
                choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"],
                default="13",
            )
            if choice == "1":
                show_auto_speedtest()
            elif choice == "2":
                show_speedtest_by_server_id()
            elif choice == "3":
                show_keyword_speedtest()
            elif choice == "4":
                show_isp_city_preset_speedtest()
            elif choice == "5":
                show_save_last_speedtest_server()
            elif choice == "6":
                show_clear_preferred_speedtest()
            elif choice == "7":
                show_speedtest_config()
            elif choice == "8":
                show_last_speedtest_raw_summary()
            elif choice == "9":
                show_speedtest_backend_info()
            elif choice == "10":
                show_ookla_selection_details()
            elif choice == "11":
                show_librespeed_custom_menu()
            elif choice == "12":
                open_speedtest_cn_reference()
            elif choice == "13":
                break
        except KeyboardInterrupt:
            console.print("\n[yellow]已返回主菜单。[/yellow]")
            break


def main() -> None:
    """Run the interactive menu."""
    try:
        while True:
            console.print(build_menu())
            choice = Prompt.ask("请选择功能", choices=["1", "2", "3", "4", "5", "6", "7", "8"], default="1")

            if choice == "1":
                show_realtime_traffic()
            elif choice == "2":
                show_network_info()
            elif choice == "3":
                show_lan_discovery_menu()
            elif choice == "4":
                show_speedtest_cn_main()
            elif choice == "5":
                show_proxy_exit_speedtest()
            elif choice == "6":
                show_open_router_admin()
            elif choice == "7":
                show_advanced_menu()
            elif choice == "8":
                console.print("[green]再见。[/green]")
                break
    except (KeyboardInterrupt, EOFError):
        console.print("\n[green]已退出 netwatch-cli。[/green]")


if __name__ == "__main__":
    main()
