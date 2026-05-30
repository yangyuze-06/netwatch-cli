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
from netwatch.speedtest.speed import format_speed, sample_network_speed
from netwatch.cli_modules.lan import (
    build_lan_discovery_menu,
    choose_lan_scan_candidate,
    print_network_devices,
    run_lan_scan,
    show_enhanced_lan_discovery,
    show_lan_discovery_menu,
    show_router_only_device_sync,
)
from netwatch.cli_modules.location import print_device_location_result, show_network_info
from netwatch.cli_modules.router import (
    choose_router_admin_url,
    choose_router_sync_method,
    normalize_router_admin_url,
    print_missing_stok_guidance,
    prompt_and_fetch_xiaomi_redmi_stok_devices,
    prompt_and_fetch_xiaomi_router_devices,
    show_generic_luci_sync_notice,
    show_open_router_admin,
)
from netwatch.cli_modules.speedtest import (
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
