"""Interactive command-line interface for netwatch-cli."""

from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from netwatch.network_info import (
    NetworkCandidate,
    get_display_network_interfaces,
    get_lan_scan_candidates,
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
from netwatch.speedtest_runner import (
    SpeedtestResult,
    SpeedtestRunError,
    SpeedtestUnavailableError,
    list_nearby_servers,
    run_speedtest,
)

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
            "[bold cyan]4[/bold cyan]. 带宽测速",
            "[bold cyan]5[/bold cyan]. 打开路由器管理后台",
            "[bold cyan]6[/bold cyan]. 高级功能",
            "[bold cyan]7[/bold cyan]. 退出",
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
    """Display local network interface information."""
    interfaces = get_display_network_interfaces()
    table = Table(title="本机网络信息")
    table.add_column("网卡名称", style="bold cyan")
    table.add_column("IPv4 地址")
    table.add_column("MAC 地址")

    for interface in interfaces:
        table.add_row(interface.name, interface.ipv4 or "-", interface.mac or "-")

    if not interfaces:
        console.print("[yellow]未找到可显示的网络接口。[/yellow]")
        return

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
        console.print(build_lan_discovery_menu())
        choice = Prompt.ask("请选择局域网设备发现功能", choices=["1", "2", "3", "4"], default="1")
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
            "[bold cyan]3[/bold cyan]. 仅从路由器同步设备列表",
            "[bold cyan]4[/bold cyan]. 返回主菜单",
        ]
    )
    return Panel(menu, title="局域网设备发现", border_style="cyan")


def show_enhanced_lan_discovery() -> None:
    """Run LAN scan and optionally merge Xiaomi router device names."""
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
    """Fetch router devices without ping scanning."""
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


def show_auto_speedtest() -> None:
    """Run an automatic internet bandwidth test using speedtest-cli."""
    console.print("[dim]Speedtest 测速会连接公网测速服务器，可能需要几十秒。[/dim]")
    try:
        result = run_speedtest(lambda message: console.print(f"[cyan]{message}[/cyan]"))
    except SpeedtestUnavailableError:
        console.print("[yellow]未安装 speedtest-cli，请先执行：[/yellow]")
        console.print("[bold]pip install speedtest-cli[/bold]")
        return
    except SpeedtestRunError as exc:
        console.print(f"[red]Speedtest 测速失败：{exc}[/red]")
        console.print("[yellow]自动测速波动较大，建议在“高级功能”中手动指定 Speedtest server id。[/yellow]")
        return
    except KeyboardInterrupt:
        console.print("\n[green]已取消 Speedtest 测速。[/green]")
        return

    print_speedtest_result(result)


def show_manual_speedtest() -> None:
    """List nearby servers and run a speedtest against a chosen server."""
    servers = show_speedtest_servers()
    if not servers:
        return

    server_ids = [server.id for server in servers]
    server_id = Prompt.ask("请输入 server id", choices=server_ids)
    run_speedtest_with_server_id(server_id)


def show_speedtest_servers():
    """List nearby Speedtest servers."""
    console.print("[dim]正在获取附近 Speedtest 服务器...[/dim]")
    try:
        servers = list_nearby_servers(limit=10)
    except SpeedtestUnavailableError:
        console.print("[yellow]未安装 speedtest-cli，请先执行：[/yellow]")
        console.print("[bold]pip install speedtest-cli[/bold]")
        return
    except SpeedtestRunError as exc:
        message = str(exc)
        if "403" in message:
            console.print("[yellow]当前 speedtest-cli 后端无法获取服务器列表。建议使用“带宽测速”自动模式，或后续安装官方 Ookla CLI。[/yellow]")
        else:
            console.print(f"[red]获取测速服务器失败：{message}[/red]")
        return
    except KeyboardInterrupt:
        console.print("\n[green]已取消 Speedtest 测速。[/green]")
        return

    if not servers:
        console.print("[yellow]未找到附近测速服务器。[/yellow]")
        return []

    table = Table(title="附近测速服务器")
    table.add_column("Server ID", style="bold cyan")
    table.add_column("Sponsor")
    table.add_column("Name")
    table.add_column("Country")
    table.add_column("Distance", justify="right")

    server_ids = [server.id for server in servers]
    for server in servers:
        distance = f"{server.distance_km:.2f} km" if server.distance_km is not None else "-"
        table.add_row(server.id, server.sponsor, server.name, server.country, distance)

    console.print(table)
    return servers


def show_speedtest_by_server_id() -> None:
    """Prompt for a Speedtest server id and run a test."""
    server_id = Prompt.ask("请输入 Speedtest server id").strip()
    if not server_id:
        console.print("[yellow]server id 不能为空。[/yellow]")
        return
    run_speedtest_with_server_id(server_id)


def run_speedtest_with_server_id(server_id: str) -> None:
    """Run Speedtest against a selected server id."""
    try:
        result = run_speedtest(lambda message: console.print(f"[cyan]{message}[/cyan]"), server_id=server_id)
    except SpeedtestUnavailableError:
        console.print("[yellow]未安装 speedtest-cli，请先执行：[/yellow]")
        console.print("[bold]pip install speedtest-cli[/bold]")
        return
    except SpeedtestRunError as exc:
        console.print(f"[red]Speedtest 测速失败：{exc}[/red]")
        return
    except KeyboardInterrupt:
        console.print("\n[green]已取消 Speedtest 测速。[/green]")
        return

    print_speedtest_result(result)


def print_speedtest_result(result: SpeedtestResult) -> None:
    """Print a speedtest result with Mbps and MB/s units."""
    table = Table(title="Speedtest 测速结果")
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", justify="right")
    table.add_row("Ping", f"{result.ping_ms:.2f} ms")
    table.add_row("Download", f"{result.download_mbps:.2f} Mbps / {result.download_mbs:.2f} MB/s")
    table.add_row("Upload", f"{result.upload_mbps:.2f} Mbps / {result.upload_mbs:.2f} MB/s")
    table.add_row("Server", f"{result.server_sponsor} ({result.server_name}, ID: {result.server_id})")
    console.print(table)

    if is_speedtest_result_suspicious(result):
        console.print("[yellow]测速结果看起来偏低或异常，可在“高级功能”中手动指定 Speedtest server id。[/yellow]")


def is_speedtest_result_suspicious(result: SpeedtestResult) -> bool:
    """Return True for clearly invalid or suspicious Speedtest results."""
    return result.download_bps <= 0 or result.upload_bps <= 0 or result.ping_ms <= 0


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
    """Prompt for Xiaomi router URL and fetch device list."""
    global LAST_ROUTER_DEVICES
    gateway = get_default_gateway()
    if not gateway:
        gateway = Prompt.ask("请输入路由器地址，例如 192.168.31.1").strip()
    if not gateway:
        console.print("[yellow]未提供路由器地址。[/yellow]")
        return

    console.print(f"[bold]路由器地址：[/bold]{gateway}")
    console.print("[dim]请先在浏览器登录小米路由器后台。[/dim]")
    console.print("[dim]登录后复制浏览器地址栏中的完整 URL，URL 通常包含 ;stok=xxxx。[/dim]")
    pasted_url = Prompt.ask("请粘贴登录后的 URL").strip()
    stok = extract_xiaomi_stok(pasted_url)
    if not stok:
        console.print("[red]未能从输入中提取 ;stok= token。[/red]")
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


def show_speedtest_backend_info() -> None:
    """Display Speedtest backend information."""
    console.print("[bold]测速后端信息[/bold]")
    console.print("后端库：speedtest-cli")
    console.print("自动测速：speedtest.Speedtest().get_best_server()")
    console.print("手动测速：get_servers([server_id]) 后再测速")
    console.print("单位：Mbps = bit/s / 1_000_000；MB/s = bit/s / 8 / 1_000_000")


def build_advanced_menu() -> Panel:
    """Build advanced feature menu."""
    menu = "\n".join(
        [
            "[bold cyan]1[/bold cyan]. 列出 Speedtest 服务器",
            "[bold cyan]2[/bold cyan]. 手动指定 Speedtest server id 测速",
            "[bold cyan]3[/bold cyan]. 显示测速后端信息",
            "[bold cyan]4[/bold cyan]. 返回主菜单",
        ]
    )
    return Panel(menu, title="高级功能", border_style="cyan")


def show_advanced_menu() -> None:
    """Run advanced menu."""
    while True:
        console.print(build_advanced_menu())
        choice = Prompt.ask("请选择高级功能", choices=["1", "2", "3", "4"], default="4")
        if choice == "1":
            show_speedtest_servers()
        elif choice == "2":
            show_speedtest_by_server_id()
        elif choice == "3":
            show_speedtest_backend_info()
        elif choice == "4":
            break


def main() -> None:
    """Run the interactive menu."""
    try:
        while True:
            console.print(build_menu())
            choice = Prompt.ask("请选择功能", choices=["1", "2", "3", "4", "5", "6", "7"], default="1")

            if choice == "1":
                show_realtime_traffic()
            elif choice == "2":
                show_network_info()
            elif choice == "3":
                show_lan_discovery_menu()
            elif choice == "4":
                show_auto_speedtest()
            elif choice == "5":
                show_open_router_admin()
            elif choice == "6":
                show_advanced_menu()
            elif choice == "7":
                console.print("[green]再见。[/green]")
                break
    except (KeyboardInterrupt, EOFError):
        console.print("\n[green]已退出 netwatch-cli。[/green]")


if __name__ == "__main__":
    main()
