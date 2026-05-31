import io

from rich.console import Console

from netwatch.cli_modules import banner as banner_mod
from netwatch.cli_modules.banner import (
    LOGO_LINES,
    play_startup_animation,
    print_banner,
    render_banner,
    render_loading_bar,
    should_animate,
)


def test_render_banner_outputs_expected_fragments() -> None:
    output = render_banner(width=100)

    assert "Created By" in output
    assert "__   ___" in output
    assert "\n             netwatch-cli\n" not in output


def test_render_banner_centers_logo_lines_for_fixed_width() -> None:
    width = 80
    output_lines = render_banner(width=width).splitlines()
    rendered_logo_lines = output_lines[2:]

    assert rendered_logo_lines == [line.center(width) for line in LOGO_LINES]


def test_print_banner_uses_rendered_banner(capsys) -> None:
    print_banner()

    output = capsys.readouterr().out

    assert output.startswith("Created By\n\n")
    assert "netwatch-cli" not in output


def test_render_loading_bar_percentages() -> None:
    assert "  0%" in render_loading_bar(0, 10)
    assert " 50%" in render_loading_bar(5, 10)
    assert "100%" in render_loading_bar(10, 10)


def test_should_animate_false_when_disabled_by_env(monkeypatch) -> None:
    monkeypatch.setenv("NETWATCH_NO_ANIMATION", "1")
    monkeypatch.setattr(banner_mod.sys.stdout, "isatty", lambda: True)

    assert should_animate() is False


def test_play_startup_animation_renders_frames_without_sleeping(monkeypatch, capsys) -> None:
    clear_calls = []
    render_calls = []
    sleep_calls = []

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NETWATCH_NO_ANIMATION", raising=False)
    monkeypatch.setattr(banner_mod.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(banner_mod, "terminal_width", lambda: 80)
    monkeypatch.setattr(banner_mod, "clear_screen", lambda: clear_calls.append("clear"))
    monkeypatch.setattr(
        banner_mod,
        "render_banner",
        lambda width=None: render_calls.append(width) or render_banner(width=width),
    )
    monkeypatch.setattr(banner_mod.time, "sleep", lambda delay: sleep_calls.append(delay))

    play_startup_animation(duration=0.5)

    output = capsys.readouterr().out

    assert "Initializing netwatch-core" in output
    assert "100%" in output
    assert render_calls == [80]
    assert len(clear_calls) == 2
    assert len(sleep_calls) == 11


def run_main_menu_exit(monkeypatch, *, interactive: bool) -> list[str]:
    from netwatch import cli as cli_mod

    banner_calls = []
    monkeypatch.setattr(cli_mod, "_is_interactive_session", lambda: interactive)
    monkeypatch.setattr(cli_mod, "print_banner", lambda: banner_calls.append("banner"))
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *args, **kwargs: "8")

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    original_console = cli_mod.console
    cli_mod.console = console
    try:
        cli_mod.main()
    finally:
        cli_mod.console = original_console

    return banner_calls


def test_main_menu_prints_banner_once_for_interactive_session(monkeypatch) -> None:
    banner_calls = run_main_menu_exit(monkeypatch, interactive=True)

    assert banner_calls == ["banner"]


def test_main_menu_skips_banner_for_non_interactive_session(monkeypatch) -> None:
    banner_calls = run_main_menu_exit(monkeypatch, interactive=False)

    assert banner_calls == []
