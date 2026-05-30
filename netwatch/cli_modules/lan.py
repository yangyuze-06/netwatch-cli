"""LAN discovery CLI display and interaction helpers."""

from __future__ import annotations

from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from netwatch.network_info import NetworkCandidate, get_lan_scan_candidates
from netwatch.router import (
    NetworkDevice,
    RouterDevice,
    merge_devices,
    router_devices_to_network_devices,
    scan_results_to_network_devices,
)
from netwatch.scanner import scan_network
from netwatch.cli_modules.common import console
from netwatch.cli_modules.router import prompt_and_fetch_xiaomi_router_devices

LAST_SCAN_DEVICES: list[NetworkDevice] = []


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



