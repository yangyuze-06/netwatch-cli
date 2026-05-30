"""Speedtest-related CLI display and interaction helpers."""

from __future__ import annotations

import time
from pathlib import Path

from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from netwatch.analysis import (
    analyze_speedtest_consistency,
    build_network_path_summary,
    detect_vpn_tun,
    get_result_confidence,
)
from netwatch.config import (
    clear_preferred_librespeed,
    clear_preferred_speedtest,
    get_config_path,
    get_preferred_librespeed,
    get_preferred_speedtest,
    save_preferred_speedtest,
    set_preferred_librespeed,
)
from netwatch.network_info import get_preferred_physical_interface as _default_get_preferred_physical_interface
from netwatch.proxy_probe import probe_exit_ip as _default_probe_exit_ip
from netwatch.speedtest_cn import SpeedtestCnResult, is_valid_speedtest_cn_label
from netwatch.speedtest_cn_browser import (
    BrowserAutomationOptions,
    run_speedtest_cn_browser_automation as _default_run_speedtest_cn_browser_automation,
)
from netwatch.speedtest_runner import (
    SpeedtestResult,
    build_isp_preset_keywords,
    filter_servers_by_keyword,
    get_available_backends,
    get_last_successful_speedtest_result,
    get_selection_details,
    get_speedtest_quality_details,
    list_speedtest_servers,
    run_best_speedtest as _default_run_best_speedtest,
    run_configured_speedtest,
    run_librespeed_custom_speedtest as _default_run_librespeed_custom_speedtest,
    run_speedtest_with_backend,
    show_backend_info,
    summarize_speedtest_raw,
)
from netwatch.cli_modules.common import cli_override, console

SPEEDTEST_STATUS_MESSAGES = (
    "正在启动测速后端...",
    "正在连接测速服务器...",
    "正在执行下载测速...",
    "正在执行上传测速...",
    "测速可能需要 10~30 秒...",
)


def get_preferred_physical_interface():
    return cli_override(
        "get_preferred_physical_interface",
        _default_get_preferred_physical_interface,
        current=get_preferred_physical_interface,
    )()


def probe_exit_ip():
    return cli_override("probe_exit_ip", _default_probe_exit_ip, current=probe_exit_ip)()


def run_best_speedtest(*args, **kwargs):
    return cli_override("run_best_speedtest", _default_run_best_speedtest, current=run_best_speedtest)(*args, **kwargs)


def run_librespeed_custom_speedtest(*args, **kwargs):
    return cli_override(
        "run_librespeed_custom_speedtest",
        _default_run_librespeed_custom_speedtest,
        current=run_librespeed_custom_speedtest,
    )(*args, **kwargs)


def run_speedtest_cn_browser_automation(*args, **kwargs):
    return cli_override(
        "run_speedtest_cn_browser_automation",
        _default_run_speedtest_cn_browser_automation,
        current=run_speedtest_cn_browser_automation,
    )(*args, **kwargs)


def _print_speedtest_result(result: SpeedtestResult, detailed: bool = True) -> None:
    printer = cli_override("print_speedtest_result", print_speedtest_result, current=print_speedtest_result)
    if printer is print_speedtest_result:
        printer(result, detailed=detailed)
    elif detailed:
        printer(result)
    else:
        printer(result, detailed=detailed)
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
            result = run_speedtest_with_status(lambda: run_configured_speedtest(preferred, fallback=True))
            if result is None:
                return
            _print_speedtest_result(result)
            return

    preferred_interface = get_preferred_physical_interface()
    if preferred_interface:
        console.print(
            "[green]使用物理网卡测速："
            f"{preferred_interface['name']} ({preferred_interface['ip']})[/green]"
        )
    else:
        console.print("[yellow]未识别到真实物理网卡，将使用当前 CLI 默认出口测速。[/yellow]")
    result = run_speedtest_with_status(lambda: run_best_speedtest(use_interface=True))
    if result is None:
        return
    _print_speedtest_result(result)


def show_speedtest_by_server_id() -> None:
    """Prompt for a Speedtest server id and run a test."""
    server_id = Prompt.ask("请输入 Speedtest server id").strip()
    if not server_id:
        console.print("[yellow]server id 不能为空。[/yellow]")
        return
    use_interface = Confirm.ask("是否使用物理网卡测速？", default=True)
    result, interface = run_speedtest_with_server_id(server_id, use_interface=use_interface)
    if result is None:
        return
    if not result.error and result.server_id and Confirm.ask("是否保存此服务器为默认测速服务器？", default=False):
        save_result_as_preferred(result, interface)


def run_speedtest_with_server_id(server_id: str, use_interface: bool = True) -> tuple[SpeedtestResult | None, str | None]:
    """Run Speedtest against a selected server id."""
    backend = "official-ookla-cli" if "official-ookla-cli" in get_available_backends() else "python-speedtest-cli"
    interface = None
    if backend == "official-ookla-cli" and use_interface:
        preferred_interface = get_preferred_physical_interface()
        if preferred_interface:
            interface = preferred_interface["name"]
            console.print(f"[green]使用物理网卡测速：{interface} ({preferred_interface['ip']})[/green]")
    result = run_speedtest_with_status(lambda: run_speedtest_with_backend(backend, server_id=server_id, interface=interface))
    if result is None:
        return None, interface
    _print_speedtest_result(result)
    return result, interface


def run_speedtest_with_status(task) -> SpeedtestResult | None:
    """Run a speedtest task with user-facing progress and Ctrl+C cancellation."""
    for message in SPEEDTEST_STATUS_MESSAGES:
        console.print(f"[dim]{message}[/dim]")
    try:
        with console.status("[bold green]测速进行中...[/bold green]"):
            return task()
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消当前测速，返回菜单。[/yellow]")
        return None


def print_speedtest_result(result: SpeedtestResult, detailed: bool = True) -> None:
    """Print a unified speedtest result. detailed=True includes quality warnings + path analysis."""
    print_speedtest_result_table(result)
    if detailed:
        print_speedtest_results_extra(result)


def print_speedtest_result_table(result: SpeedtestResult) -> None:
    """Print the basic speedtest result table and minimal extra info."""
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


def print_speedtest_results_extra(result: SpeedtestResult) -> None:
    """Print detailed speedtest diagnostics: quality warnings and path analysis."""
    print_speedtest_quality_warning(result)
    print_speedtest_path_analysis(result)


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


def print_speedtest_path_analysis(result: SpeedtestResult) -> None:
    """Print speedtest confidence and network path analysis."""
    confidence, reasons = get_result_confidence(result)
    console.print(f"[bold]Result confidence:[/bold] {confidence}")
    for reason in reasons:
        console.print(f"[dim]- {reason}[/dim]")

    summary = build_network_path_summary(result)
    console.print("[bold]网络路径分析：[/bold]")
    console.print(f"- 当前出口：{summary['current_exit']}")
    console.print(f"- 测速节点：{summary['speedtest_server']}")
    console.print(f"- VPN/TUN：{summary['vpn_tun']}")
    console.print(f"- 高延迟绕路：{summary['high_latency_route']}")
    console.print(f"- 指标矛盾：{summary['metric_contradiction']}")
    console.print(f"- 当前结果更可能代表：{summary['likely_represents']}")
    if summary["not_necessarily"] != "-":
        console.print(f"- 而不一定代表：{summary['not_necessarily']}")

    messages = analyze_speedtest_consistency(result)
    if messages:
        console.print("[yellow]当前测速结果可能受到服务器池、网络路径、VPN/TUN、国际出口、测速实现差异影响。[/yellow]")
        for message in messages:
            console.print(f"[yellow]→ {message}[/yellow]")


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
    """Show current CLI exit IP and run best speedtest (simplified, optional detailed)."""
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
    console.print("[dim]已检测当前 CLI 公网出口。[/dim]")
    time.sleep(0.4)

    console.print("[dim]本次测速将按当前 CLI 进程实际出口进行，不强制指定物理网卡。[/dim]")
    time.sleep(0.4)
    console.print("[dim]正在准备测速后端...[/dim]")
    time.sleep(0.4)
    console.print("[dim]测速进行中，通常需要 10~30 秒...[/dim]")

    try:
        with console.status("[bold green]等待测速后端返回...[/bold green]"):
            result = run_best_speedtest(use_interface=False)
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消当前测速，返回菜单。[/yellow]")
        return

    if result.error:
        console.print(f"[red]当前出口测速失败：{compact_error(result.error)}[/red]")
        console.print("[yellow]可尝试：关闭/切换代理，或使用高级功能里的通用测速诊断。[/yellow]")
        return

    console.print("[dim]测速后端已返回结果，正在整理...[/dim]")
    time.sleep(0.3)
    console.print("[dim]测速完成。[/dim]")
    print_speedtest_result_table(result)
    print_proxy_exit_judgment(result)

    try:
        show_detailed = Prompt.ask("是否查看详细诊断？", choices=["y", "n"], default="n")
    except KeyboardInterrupt:
        console.print("\n[yellow]已返回主菜单。[/yellow]")
        return

    if show_detailed.lower() == "y":
        print_speedtest_results_extra(result)


def print_proxy_exit_judgment(result: SpeedtestResult) -> None:
    """Print a one-line judgment for the proxy exit speedtest result."""
    if detect_vpn_tun(result):
        console.print("[yellow]检测到当前可能经过代理/TUN，结果更可能代表代理出口质量。[/yellow]")
    else:
        console.print("[yellow]未检测到明显 TUN/VPN，结果更接近当前直连出口质量。[/yellow]")
    console.print("[dim]当前测速代表当前 CLI 出口路径，不一定代表本地宽带裸连质量。[/dim]")


def compact_error(error: str) -> str:
    """Return the first line of an error message without traceback."""
    return error.strip().splitlines()[0] if error.strip() else "未知错误"


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
    result = run_speedtest_with_status(lambda: run_speedtest_with_backend("official-ookla-cli", server_id=selection, interface=interface))
    if result is None:
        return
    _print_speedtest_result(result)
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
        result = run_speedtest_with_status(lambda server_id=server_id: run_speedtest_with_backend("official-ookla-cli", server_id=server_id, interface=interface))
        if result is None:
            return
        if result.error:
            console.print(f"[yellow]server id {server_id} 测试失败：{result.error}[/yellow]")
            continue
        if best_result is None or (result.download_mbps or 0) > (best_result.download_mbps or 0):
            best_result = result

    if best_result is None:
        console.print("[yellow]候选服务器测速均失败，请换关键词或换 interface 后重试。[/yellow]")
        return

    console.print("[green]推荐结果如下：[/green]")
    _print_speedtest_result(best_result)


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


def open_speedtest_cn_reference() -> None:
    """Open speedtest.cn as a browser reference test."""
    url = "https://www.speedtest.cn/"
    import webbrowser

    webbrowser.open(url)
    console.print(f"[green]已打开 speedtest.cn 网页。[/green]")
    console.print("[dim]这是浏览器对照测速，不会自动回传结果到终端。[/dim]")
    console.print("[dim]本项目不调用或逆向 speedtest.cn 私有 API。[/dim]")


def show_speedtest_cn_browser_automation() -> None:
    """Run experimental speedtest.cn browser automation from the advanced menu."""
    console.print("[yellow]这是实验功能，会在后台浏览器中访问 speedtest.cn 并尝试读取测速结果。[/yellow]")
    console.print("[yellow]本功能不调用 speedtest.cn 私有 API，页面结构变化可能导致失败。[/yellow]")
    try:
        continue_choice = Prompt.ask("是否继续？", choices=["y", "n"], default="n")
        if continue_choice.lower() != "y":
            console.print("[yellow]已取消实验测速。[/yellow]")
            return
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消当前实验任务，返回高级菜单。[/yellow]")
        return

    options = BrowserAutomationOptions(
        headless=True,
        timeout_seconds=90,
        debug_screenshot=False,
    )

    def show_progress(message: str) -> None:
        console.print(f"[dim]{message}[/dim]")

    console.print("[dim]正在执行 speedtest.cn 后台测速，请稍候...[/dim]")

    try:
        with console.status("[bold green]speedtest.cn browser automation 进行中...[/bold green]"):
            result = run_speedtest_cn_browser_automation(options, progress_callback=show_progress)
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消当前实验任务，返回高级菜单。[/yellow]")
        return

    print_speedtest_cn_browser_result(result)


def print_speedtest_cn_browser_result(result: SpeedtestCnResult) -> None:
    """Print an experimental speedtest.cn browser automation result."""
    if result.error:
        if result.error.startswith("已取消"):
            console.print("[yellow]已取消当前实验任务，返回高级菜单。[/yellow]")
            return
        short_error = compact_speedtest_cn_error(result.error)
        console.print(f"[red]speedtest.cn 浏览器自动化失败：{short_error}[/red]")
        if "Playwright is not installed" in result.error:
            console.print("[yellow]Playwright 是可选依赖，安装后再运行实验功能：[/yellow]")
            console.print("[bold]pip install playwright[/bold]")
            console.print("[bold]playwright install chromium[/bold]")
        console.print("[yellow]可能原因：页面结构变化、弹窗/验证码、headless 限制或网络问题。[/yellow]")
        console.print("[yellow]可尝试：使用 speedtest.cn 网页对照测速，或使用 Ookla / LibreSpeed 后端。[/yellow]")
        return

    table = Table(title="speedtest.cn Browser Automation 结果")
    table.add_column("Source", style="bold cyan")
    table.add_column("Server")
    table.add_column("Location")
    table.add_column("Ping", justify="right")
    table.add_column("Jitter", justify="right")
    table.add_column("Download", justify="right")
    table.add_column("Upload", justify="right")
    table.add_row(
        result.source,
        format_speedtest_cn_label(result.server_name),
        format_speedtest_cn_label(result.location),
        format_optional_ms(result.ping_ms),
        format_optional_ms(result.jitter_ms),
        format_bandwidth(result.download_mbps, result.download_MBps),
        format_bandwidth(result.upload_mbps, result.upload_MBps),
    )
    console.print(table)
    console.print("[dim]来源：speedtest.cn 浏览器自动化实验结果，非官方 API。[/dim]")


def compact_speedtest_cn_error(error: str) -> str:
    """Return a short CLI-safe error summary without traceback noise."""
    first_line = error.strip().splitlines()[0] if error.strip() else "未知错误"
    if "ERR_HTTP2_PROTOCOL_ERROR" in error:
        return "ERR_HTTP2_PROTOCOL_ERROR"
    return first_line


def show_speedtest_cn_main() -> None:
    """Run speedtest.cn browser automation as the main bandwidth test (simplified output)."""
    console.print("[yellow]宽带测速将使用 speedtest.cn 浏览器自动化实验功能，尽量模拟普通网页测速体验。[/yellow]")
    console.print("[yellow]本功能不调用 speedtest.cn 私有 API，页面结构变化可能导致失败。[/yellow]")
    try:
        continue_choice = Prompt.ask("是否继续？", choices=["y", "n"], default="n")
        if continue_choice.lower() != "y":
            console.print("[yellow]已取消测速。[/yellow]")
            return
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消测速，返回主菜单。[/yellow]")
        return

    options = BrowserAutomationOptions(
        headless=True,
        timeout_seconds=90,
        debug_screenshot=False,
    )

    def show_progress(message: str) -> None:
        console.print(f"[dim]{message}[/dim]")

    console.print("[dim]正在执行 speedtest.cn 后台测速，请稍候...[/dim]")

    try:
        with console.status("[bold green]speedtest.cn browser automation 进行中...[/bold green]"):
            result = run_speedtest_cn_browser_automation(options, progress_callback=show_progress)
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消测速，返回主菜单。[/yellow]")
        return

    print_main_speedtest_cn_result(result)


def print_main_speedtest_cn_result(result: SpeedtestCnResult) -> None:
    """Print a simplified speedtest.cn result for the main menu (no advanced diagnostics)."""
    if result.error:
        short_error = compact_speedtest_cn_error(result.error)
        console.print(f"[red]speedtest.cn 浏览器自动化测速失败：{short_error}[/red]")
        console.print("[yellow]可尝试：重新运行、使用高级功能里的通用测速诊断，或打开 speedtest.cn 网页对照测速。[/yellow]")
        return

    table = Table(title="宽带测速结果")
    table.add_column("Source", style="bold cyan")
    table.add_column("Server")
    table.add_column("Location")
    table.add_column("Ping", justify="right")
    table.add_column("Jitter", justify="right")
    table.add_column("Download", justify="right")
    table.add_column("Upload", justify="right")
    table.add_row(
        result.source,
        format_speedtest_cn_label(result.server_name),
        format_speedtest_cn_label(result.location),
        format_optional_ms(result.ping_ms),
        format_optional_ms(result.jitter_ms),
        format_bandwidth(result.download_mbps, result.download_MBps),
        format_bandwidth(result.upload_mbps, result.upload_MBps),
    )
    console.print(table)
    console.print("[dim]来源：speedtest.cn 浏览器自动化实验结果，非官方 API。[/dim]")


def format_speedtest_cn_label(value: str | None) -> str:
    """Format optional speedtest.cn metadata labels without leaking UI noise."""
    return value if is_valid_speedtest_cn_label(value) else "-"


def build_librespeed_menu() -> Panel:
    """Build LibreSpeed custom server list submenu."""
    menu = "\n".join(
        [
            "[bold cyan]1[/bold cyan]. 使用已保存的 LibreSpeed 配置测速",
            "[bold cyan]2[/bold cyan]. 输入远程 server-json URL 测速",
            "[bold cyan]3[/bold cyan]. 输入本地 local-json 文件测速",
            "[bold cyan]4[/bold cyan]. 保存 LibreSpeed 配置",
            "[bold cyan]5[/bold cyan]. 清除 LibreSpeed 配置",
            "[bold cyan]6[/bold cyan]. 返回",
        ]
    )
    return Panel(menu, title="LibreSpeed 自定义服务器列表测速", border_style="cyan")


def show_librespeed_custom_menu() -> None:
    """Run LibreSpeed custom server list submenu."""
    while True:
        try:
            console.print(build_librespeed_menu())
            console.print("[yellow]公共 LibreSpeed 节点质量不保证。[/yellow]")
            console.print("[dim]测速结果取决于 server list 中的服务器质量，不承诺跑满千兆。[/dim]")
            choice = Prompt.ask("请选择 LibreSpeed 功能", choices=["1", "2", "3", "4", "5", "6"], default="6")
            if choice == "1":
                show_librespeed_preferred_speedtest()
            elif choice == "2":
                show_librespeed_server_json_speedtest()
            elif choice == "3":
                show_librespeed_local_json_speedtest()
            elif choice == "4":
                show_save_librespeed_config()
            elif choice == "5":
                show_clear_librespeed_config()
            elif choice == "6":
                break
        except KeyboardInterrupt:
            console.print("\n[yellow]已返回上一级菜单。[/yellow]")
            break


def show_librespeed_preferred_speedtest() -> None:
    """Run LibreSpeed using saved custom list config."""
    preferred = get_preferred_librespeed()
    if not preferred:
        console.print("[yellow]当前没有保存的 LibreSpeed 配置。[/yellow]")
        return
    print_librespeed_config(preferred)
    result = run_speedtest_with_status(lambda: run_librespeed_custom_speedtest(use_preferred=True))
    if result is None:
        return
    _print_speedtest_result(result)


def show_librespeed_server_json_speedtest() -> None:
    """Run LibreSpeed using a remote server-json URL."""
    server_json_url = Prompt.ask("请输入远程 server-json URL").strip()
    if not validate_server_json_url(server_json_url):
        return
    is_valid_duration, duration = prompt_optional_duration()
    if not is_valid_duration:
        return
    result = run_speedtest_with_status(
        lambda: run_librespeed_custom_speedtest(server_json_url=server_json_url, duration=duration)
    )
    if result is None:
        return
    _print_speedtest_result(result)


def show_librespeed_local_json_speedtest() -> None:
    """Run LibreSpeed using a local server list JSON file."""
    local_json_path = Prompt.ask("请输入本地 local-json 文件路径").strip()
    if not validate_local_json_path(local_json_path):
        return
    is_valid_duration, duration = prompt_optional_duration()
    if not is_valid_duration:
        return
    result = run_speedtest_with_status(
        lambda: run_librespeed_custom_speedtest(local_json_path=local_json_path, duration=duration)
    )
    if result is None:
        return
    _print_speedtest_result(result)


def show_save_librespeed_config() -> None:
    """Save LibreSpeed custom server list config."""
    mode = Prompt.ask("请选择配置类型", choices=["server-json", "local-json"], default="server-json")
    server_json_url = None
    local_json_path = None
    if mode == "server-json":
        server_json_url = Prompt.ask("请输入远程 server-json URL").strip()
        if not validate_server_json_url(server_json_url):
            return
    else:
        local_json_path = Prompt.ask("请输入本地 local-json 文件路径").strip()
        if not validate_local_json_path(local_json_path):
            return

    is_valid_duration, duration = prompt_optional_duration()
    if not is_valid_duration:
        return
    try:
        preferred = set_preferred_librespeed(
            mode=mode,
            server_json_url=server_json_url,
            local_json_path=local_json_path,
            duration=duration,
        )
    except ValueError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return
    console.print("[green]已保存 LibreSpeed 配置。[/green]")
    print_librespeed_config(preferred)


def show_clear_librespeed_config() -> None:
    """Clear saved LibreSpeed custom server list config."""
    existed = clear_preferred_librespeed()
    if existed:
        console.print("[green]已清除 LibreSpeed 配置。[/green]")
    else:
        console.print("[yellow]当前没有保存的 LibreSpeed 配置。[/yellow]")


def prompt_optional_duration() -> tuple[bool, int | None]:
    """Prompt for optional LibreSpeed duration."""
    raw_value = Prompt.ask("测速时长秒数，可留空使用 librespeed-cli 默认值", default="").strip()
    if not raw_value:
        return True, None
    try:
        duration = int(raw_value)
    except ValueError:
        console.print("[yellow]测速时长必须是 1 到 300 之间的整数。[/yellow]")
        return False, None
    if not 1 <= duration <= 300:
        console.print("[yellow]测速时长必须是 1 到 300 之间的整数。[/yellow]")
        return False, None
    return True, duration


def validate_server_json_url(server_json_url: str) -> bool:
    """Validate a LibreSpeed server-json URL."""
    if not server_json_url.startswith(("http://", "https://")):
        console.print("[yellow]无效 URL。[/yellow]")
        return False
    return True


def validate_local_json_path(local_json_path: str) -> bool:
    """Validate a LibreSpeed local-json file path."""
    path = Path(local_json_path).expanduser()
    if not path.exists() or not path.is_file():
        console.print("[yellow]文件不存在。[/yellow]")
        return False
    if path.suffix.lower() != ".json":
        console.print("[yellow]不是 JSON 文件。[/yellow]")
        return False
    return True


def print_librespeed_config(preferred: dict) -> None:
    """Print saved LibreSpeed config."""
    table = Table(title="LibreSpeed 配置")
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")
    for key in ("mode", "server_json_url", "local_json_path", "duration"):
        table.add_row(key, str(preferred.get(key) or "-"))
    console.print(table)
