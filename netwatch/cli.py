"""Interactive command-line interface for netwatch-cli."""

from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from netwatch.config import (
    clear_preferred_speedtest,
    get_config_path,
    get_preferred_speedtest,
    save_preferred_speedtest,
)
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
from netwatch.proxy_probe import probe_exit_ip
from netwatch.speedtest_runner import (
    SpeedtestResult,
    filter_servers_by_keyword,
    get_available_backends,
    get_last_successful_speedtest_result,
    get_selection_details,
    get_speedtest_quality_warnings,
    list_speedtest_servers,
    run_best_speedtest,
    run_configured_speedtest,
    run_speedtest_with_backend,
    show_backend_info,
    summarize_speedtest_raw,
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
    """Run the best available bandwidth test backend."""
    console.print("[dim]带宽测速会连接公网测速服务器，可能需要几十秒。[/dim]")
    preferred = get_preferred_speedtest()
    if preferred:
        server_label = " / ".join(
            value
            for value in (
                str(preferred.get("server_name") or preferred.get("server_id") or ""),
                str(preferred.get("location") or ""),
            )
            if value
        )
        console.print(f"[green]检测到常用测速服务器：{server_label or preferred.get('server_id')}[/green]")
        if Confirm.ask("是否使用？", default=True):
            result = run_configured_speedtest(preferred, fallback=True)
            print_speedtest_result(result)
            return

    preferred_interface = get_preferred_physical_interface()
    if preferred_interface:
        console.print(
            "[green]使用物理网卡测速："
            f"{preferred_interface['name']} ({preferred_interface['ip']})[/green]"
        )
    else:
        console.print("[yellow]未识别到真实物理网卡，将使用当前 CLI 默认出口测速。[/yellow]")
    result = run_best_speedtest(use_interface=True)
    print_speedtest_result(result)


def show_manual_speedtest() -> None:
    """List nearby servers and run a speedtest against a chosen server."""
    servers = show_speedtest_servers()
    if not servers:
        return

    server_ids = [str(server.get("id")) for server in servers if server.get("id")]
    if not server_ids:
        console.print("[yellow]服务器列表没有可用 server id。[/yellow]")
        return
    server_id = Prompt.ask("请输入 server id", choices=server_ids)
    run_speedtest_with_server_id(server_id)


def show_speedtest_servers():
    """List nearby Speedtest servers."""
    console.print("[dim]正在获取附近 Speedtest 服务器...[/dim]")
    servers = list_speedtest_servers()

    if not servers:
        console.print("[yellow]未找到附近测速服务器。[/yellow]")
        return []
    if servers and servers[0].get("error"):
        console.print("[yellow]当前后端无法获取服务器列表。建议使用“带宽测速”自动模式，或安装官方 Ookla CLI。[/yellow]")
        console.print(f"[dim]{servers[0]['error']}[/dim]")
        return []

    table = Table(title="附近测速服务器")
    table.add_column("Server ID", style="bold cyan")
    table.add_column("Sponsor")
    table.add_column("Name")
    table.add_column("Country")
    table.add_column("Distance", justify="right")

    server_ids = [str(server.get("id", "-")) for server in servers if server.get("id")]
    for server in servers:
        distance_value = server.get("distance") or server.get("d")
        try:
            distance = f"{float(distance_value):.2f} km" if distance_value is not None else "-"
        except (TypeError, ValueError):
            distance = "-"
        table.add_row(
            str(server.get("id", "-")),
            str(server.get("sponsor", "-")),
            str(server.get("name", "-")),
            str(server.get("country", server.get("location", "-"))),
            distance,
        )

    console.print(table)
    return servers


def show_speedtest_by_server_id() -> None:
    """Prompt for a Speedtest server id and run a test."""
    server_id = Prompt.ask("请输入 Speedtest server id").strip()
    if not server_id:
        console.print("[yellow]server id 不能为空。[/yellow]")
        return
    use_interface = Confirm.ask("是否使用物理网卡测速？", default=True)
    result, interface = run_speedtest_with_server_id(server_id, use_interface=use_interface)
    if not result.error and result.server_id and Confirm.ask("是否保存此服务器为默认测速服务器？", default=False):
        save_result_as_preferred(result, interface)


def run_speedtest_with_server_id(server_id: str, use_interface: bool = True) -> tuple[SpeedtestResult, str | None]:
    """Run Speedtest against a selected server id."""
    backend = "official-ookla-cli" if "official-ookla-cli" in get_available_backends() else "python-speedtest-cli"
    interface = None
    if backend == "official-ookla-cli" and use_interface:
        preferred_interface = get_preferred_physical_interface()
        if preferred_interface:
            interface = preferred_interface["name"]
            console.print(f"[green]使用物理网卡测速：{interface} ({preferred_interface['ip']})[/green]")
    result = run_speedtest_with_backend(backend, server_id=server_id, interface=interface)
    print_speedtest_result(result)
    return result, interface


def print_speedtest_result(result: SpeedtestResult) -> None:
    """Print a unified speedtest result."""
    if result.error:
        console.print(f"[red]{result.error}[/red]")
        if result.backend == "none" or "Official Ookla CLI is not installed" in result.error:
            console.print("[yellow]推荐安装官方 Ookla CLI：[/yellow]")
            console.print("[bold]brew tap teamookla/speedtest[/bold]")
            console.print("[bold]brew install speedtest[/bold]")
        return

    table = Table(title="Speedtest 测速结果")
    table.add_column("Backend", style="bold cyan")
    table.add_column("Server")
    table.add_column("Location")
    table.add_column("Ping", justify="right")
    table.add_column("Download", justify="right")
    table.add_column("Upload", justify="right")
    table.add_row(
        result.backend,
        result.server_sponsor or result.server_name or result.server_id or "-",
        result.server_location or "-",
        format_optional_ms(result.ping_ms),
        format_bandwidth(result.download_mbps, result.download_MBps),
        format_bandwidth(result.upload_mbps, result.upload_MBps),
    )
    console.print(table)

    if result.jitter_ms is not None:
        console.print(f"[dim]Jitter: {result.jitter_ms:.2f} ms[/dim]")
    if result.packet_loss is not None:
        console.print(f"[dim]Packet loss: {result.packet_loss:.2f}%[/dim]")
    if result.backend == "python-speedtest-cli":
        console.print("[yellow]当前使用 Python speedtest-cli fallback，结果可能低于网页测速或官方 Ookla CLI。[/yellow]")
    print_speedtest_quality_warning(result)


def print_speedtest_quality_warning(result: SpeedtestResult) -> None:
    """Print speedtest quality warning with cause-specific actionable advice."""
    details = get_speedtest_quality_details(result)
    if not details:
        return
    console.print("[yellow]当前测速结果可能不代表真实最大带宽。[/yellow]")
    for detail in details:
        console.print(f"\n[yellow]触发条件：{detail['condition']}[/yellow]")
        for line in detail["advice"]:
            console.print(f"[yellow]→ {line}[/yellow]")

def format_optional_ms(value: float | None) -> str:
    """Format optional milliseconds."""
    return f"{value:.2f} ms" if value is not None else "-"


def format_bandwidth(mbps: float | None, MBps: float | None) -> str:
    """Format Mbps and MB/s pair."""
    if mbps is None or MBps is None:
        return "-"
    return f"{mbps:.2f} Mbps / {MBps:.2f} MB/s"


def is_speedtest_result_suspicious(result: SpeedtestResult) -> bool:
    """Return True for clearly invalid or suspicious Speedtest results."""
    return (result.download_mbps or 0) <= 0 or (result.upload_mbps or 0) <= 0 or (result.ping_ms or 0) <= 0


def show_proxy_exit_speedtest() -> None:
    """Show current CLI exit IP and run best speedtest."""
    info = probe_exit_ip()
    table = Table(title="当前 CLI 公网出口")
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    table.add_row("当前出口 IP", info.ip or "-")
    table.add_row("国家/地区", info.country or info.region or "-")
    table.add_row("城市", info.city or "-")
    table.add_row("ISP/组织", info.org or "-")
    if info.error:
        table.add_row("Error", info.error)
    console.print(table)
    console.print("[dim]如果你使用 TUN/VPN 模式，CLI 通常会走代理出口。[/dim]")
    console.print("[dim]如果只是浏览器代理，CLI 可能仍然直连。[/dim]")
    console.print("[dim]本功能只检测当前 CLI 进程实际看到的公网出口。[/dim]")
    console.print("[dim]代理/当前出口测速不会强制指定 en0/en1，会按当前 CLI 进程实际出口测速。[/dim]")
    result = run_best_speedtest(use_interface=False)
    print_speedtest_result(result)


def show_keyword_speedtest() -> None:
    """Filter Ookla servers by keyword and test selected candidates."""
    keyword = Prompt.ask("请输入服务器关键词，例如 Guangzhou / Guangdong / China Mobile / Hong Kong").strip()
    if not keyword:
        console.print("[yellow]关键词不能为空。[/yellow]")
        return
    run_keyword_speedtest(keyword)


def run_keyword_speedtest(keyword: str) -> None:
    """Run a server keyword speedtest flow."""
    servers = list_speedtest_servers()
    if not servers or servers[0].get("error"):
        console.print("[yellow]当前后端无法获取服务器列表。建议使用“带宽测速”自动模式，或安装官方 Ookla CLI。[/yellow]")
        if servers:
            console.print(f"[dim]{servers[0].get('error')}[/dim]")
        return

    matches = filter_servers_by_keyword(servers, keyword, limit=10)
    if not matches:
        console.print(f"[yellow]未找到匹配 “{keyword}” 的服务器。[/yellow]")
        return

    print_server_matches(matches, title=f"关键词匹配服务器：{keyword}")
    selection = Prompt.ask("请输入要测速的 server id，或输入 auto 自动测试前 3 个", default="auto").strip()
    interface = get_speedtest_interface_name()

    if selection.lower() == "auto":
        auto_test_keyword_servers(matches[:3], interface=interface)
        return

    valid_ids = {str(server.get("id")) for server in matches if server.get("id")}
    if selection not in valid_ids:
        console.print("[yellow]输入的 server id 不在当前匹配列表中。[/yellow]")
        return
    result = run_speedtest_with_backend("official-ookla-cli", server_id=selection, interface=interface)
    print_speedtest_result(result)
    if not result.error and result.server_id and Confirm.ask("是否保存此服务器为默认测速服务器？", default=False):
        save_result_as_preferred(result, interface)


def show_isp_city_preset_speedtest() -> None:
    """Try keyword presets based on current ISP and city."""
    info = probe_exit_ip()
    keywords = build_isp_preset_keywords(
        org=info.org or "",
        city=info.city or "",
        region=info.region or "",
    )

    servers = list_speedtest_servers()
    if not servers or servers[0].get("error"):
        console.print("[yellow]当前后端无法获取服务器列表。建议手动带宽测速或安装官方 Ookla CLI。[/yellow]")
        return

    for keyword in keywords:
        if keyword.lower() == "hong kong":
            console.print(
                "[dim]Hong Kong is only a fallback candidate and may not be optimal "
                "for mainland China Mobile lines.[/dim]"
            )
        matches = filter_servers_by_keyword(servers, keyword, limit=10)
        if matches:
            console.print(f"[green]使用关键词预设：{keyword}[/green]")
            print_server_matches(matches, title=f"预设匹配服务器：{keyword}")
            auto_test_keyword_servers(matches[:3], interface=get_speedtest_interface_name())
            return

    console.print("[yellow]未按当前运营商/城市找到候选服务器，请尝试手动输入关键词。[/yellow]")

def print_server_matches(servers: list[dict], *, title: str) -> None:
    """Print keyword-matched server rows."""
    table = Table(title=title)
    table.add_column("ID", style="bold cyan")
    table.add_column("Name")
    table.add_column("Location")
    table.add_column("Country")
    table.add_column("Host")
    for server in servers:
        table.add_row(
            str(server.get("id", "-")),
            str(server.get("name", "-")),
            str(server.get("location", "-")),
            str(server.get("country", "-")),
            str(server.get("host", "-")),
        )
    console.print(table)


def auto_test_keyword_servers(servers: list[dict], *, interface: str | None) -> None:
    """Run selected candidate servers and show the best download result."""
    best_result: SpeedtestResult | None = None
    for server in servers:
        server_id = str(server.get("id", "")).strip()
        if not server_id:
            continue
        console.print(f"[dim]正在测试 server id {server_id}...[/dim]")
        result = run_speedtest_with_backend("official-ookla-cli", server_id=server_id, interface=interface)
        if result.error:
            console.print(f"[yellow]server id {server_id} 测试失败：{result.error}[/yellow]")
            continue
        if best_result is None or (result.download_mbps or 0) > (best_result.download_mbps or 0):
            best_result = result

    if best_result is None:
        console.print("[yellow]候选服务器测速均失败，请换关键词或换 interface 后重试。[/yellow]")
        return

    console.print("[green]推荐结果如下：[/green]")
    print_speedtest_result(best_result)


def get_speedtest_interface_name() -> str | None:
    """Return preferred physical interface name for advanced Ookla tests."""
    preferred_interface = get_preferred_physical_interface()
    if not preferred_interface:
        return None
    console.print(
        "[green]使用物理网卡测速："
        f"{preferred_interface['name']} ({preferred_interface['ip']})[/green]"
    )
    return preferred_interface["name"]


def save_result_as_preferred(result: SpeedtestResult, interface: str | None = None) -> None:
    """Save a speedtest result as preferred config."""
    try:
        preferred = save_preferred_speedtest(result, interface=interface)
    except ValueError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return
    console.print(
        "[green]已保存默认测速服务器："
        f"{preferred.get('server_name') or preferred.get('server_id')} / {preferred.get('location') or '-'}[/green]"
    )


def show_save_last_speedtest_server() -> None:
    """Save latest successful speedtest server as default."""
    result = get_last_successful_speedtest_result()
    if result is None:
        console.print("[yellow]还没有最近一次成功测速结果。[/yellow]")
        return
    if not result.server_id:
        console.print("[yellow]最近一次测速结果没有 server id，无法保存。[/yellow]")
        return
    save_result_as_preferred(result)


def show_clear_preferred_speedtest() -> None:
    """Clear preferred speedtest server config."""
    existed = clear_preferred_speedtest()
    if existed:
        console.print("[green]已清除默认测速服务器。[/green]")
    else:
        console.print("[yellow]当前没有默认测速服务器配置。[/yellow]")


def show_speedtest_config() -> None:
    """Display current speedtest config."""
    preferred = get_preferred_speedtest()
    console.print(f"[dim]配置文件：{get_config_path()}[/dim]")
    if not preferred:
        console.print("[yellow]当前没有默认测速服务器配置。[/yellow]")
        return
    table = Table(title="当前测速配置")
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    for key in ("backend", "server_id", "server_name", "location", "interface"):
        table.add_row(key, str(preferred.get(key) or "-"))
    console.print(table)


def show_last_speedtest_raw_summary() -> None:
    """Display compact raw summary for the latest successful speedtest."""
    result = get_last_successful_speedtest_result()
    if result is None:
        console.print("[yellow]还没有最近一次成功测速结果。[/yellow]")
        return
    summary = summarize_speedtest_raw(result)
    table = Table(title="最近一次测速 raw 摘要")
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    for key, value in summary.items():
        table.add_row(key, value)
    console.print(table)


def show_open_speedtest_cn() -> None:
    """Open speedtest.cn as a browser reference test."""
    url = "https://www.speedtest.cn/"
    console.print(f"[green]正在打开浏览器测速对照：{url}[/green]")
    console.print("[dim]这是网页对照入口，不调用或逆向 speedtest.cn 私有 API。[/dim]")
    import webbrowser

    webbrowser.open(url)


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
    info = show_backend_info()
    console.print("[bold]测速后端信息[/bold]")
    console.print(f"优先级：{', '.join(info['priority'])}")
    console.print(f"当前可用：{', '.join(info['available']) or '-'}")
    table = Table(title="后端详情")
    table.add_column("Backend", style="bold cyan")
    table.add_column("Available")
    table.add_column("Binary Path")
    table.add_column("Version Output")
    for backend_name, backend_info in info["backends"].items():
        table.add_row(
            backend_name,
            "yes" if backend_info["available"] else "no",
            backend_info["binary_path"] or "-",
            (backend_info["version_output"] or "-").splitlines()[0],
        )
    console.print(table)
    console.print("官方 Ookla CLI 安装：brew tap teamookla/speedtest && brew install speedtest")
    console.print("Python speedtest-cli 仅作为 fallback，结果可能偏低。")


def show_ookla_selection_details() -> None:
    """Display Ookla server selection details."""
    details = get_selection_details()
    if details is None:
        console.print("[yellow]未获取到 Ookla selection details。[/yellow]")
    else:
        console.print(details)


def build_advanced_menu() -> Panel:
    """Build advanced feature menu."""
    menu = "\n".join(
        [
            "[bold cyan]1[/bold cyan]. 列出 Speedtest 服务器",
            "[bold cyan]2[/bold cyan]. 手动指定 Speedtest server id 测速",
            "[bold cyan]3[/bold cyan]. 按关键词筛选服务器测速",
            "[bold cyan]4[/bold cyan]. 按当前运营商/城市优选服务器",
            "[bold cyan]5[/bold cyan]. 保存最近一次成功测速服务器为默认",
            "[bold cyan]6[/bold cyan]. 清除默认测速服务器",
            "[bold cyan]7[/bold cyan]. 查看当前测速配置",
            "[bold cyan]8[/bold cyan]. 显示最近一次测速 raw 摘要",
            "[bold cyan]9[/bold cyan]. 打开 speedtest.cn 网页对照测速",
            "[bold cyan]10[/bold cyan]. 显示测速后端信息",
            "[bold cyan]11[/bold cyan]. 显示 Ookla server selection details",
            "[bold cyan]12[/bold cyan]. 返回主菜单",
        ]
    )
    return Panel(menu, title="高级功能", border_style="cyan")


def show_advanced_menu() -> None:
    """Run advanced menu."""
    while True:
        console.print(build_advanced_menu())
        choice = Prompt.ask(
            "请选择高级功能",
            choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
            default="12",
        )
        if choice == "1":
            show_speedtest_servers()
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
            show_open_speedtest_cn()
        elif choice == "10":
            show_speedtest_backend_info()
        elif choice == "11":
            show_ookla_selection_details()
        elif choice == "12":
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
                show_auto_speedtest()
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
