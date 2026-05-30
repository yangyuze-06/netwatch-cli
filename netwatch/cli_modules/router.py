"""Router-related CLI display and interaction helpers."""

from __future__ import annotations

from rich.prompt import Prompt
from rich.table import Table

from netwatch.router import (
    RouterApiError,
    RouterDevice,
    extract_xiaomi_stok,
    fetch_xiaomi_device_list,
    get_default_gateway as _default_get_default_gateway,
    mask_stok,
)
from netwatch.cli_modules.common import cli_override, console

LAST_ROUTER_DEVICES: list[RouterDevice] = []


def get_default_gateway():
    return cli_override("get_default_gateway", _default_get_default_gateway, current=get_default_gateway)()


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


