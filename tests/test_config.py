from pathlib import Path

from netwatch.config import (
    clear_preferred_librespeed,
    clear_preferred_speedtest,
    get_preferred_librespeed,
    get_preferred_speedtest,
    load_config,
    save_config,
    save_preferred_speedtest,
    set_preferred_librespeed,
)
from netwatch.speedtest_backends.models import SpeedtestResult


def test_config_read_write(tmp_path: Path) -> None:
    path = tmp_path / "config.json"

    save_config({"hello": "world"}, path)

    assert load_config(path) == {"hello": "world"}


def test_save_preferred_server(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    result = SpeedtestResult(
        backend="official-ookla-cli",
        server_id="12345",
        server_name="Guangdong Mobile",
        server_location="Guangzhou",
    )

    preferred = save_preferred_speedtest(result, interface="en0", path=path)

    assert preferred == {
        "backend": "official-ookla-cli",
        "server_id": "12345",
        "server_name": "Guangdong Mobile",
        "location": "Guangzhou",
        "interface": "en0",
    }
    assert get_preferred_speedtest(path) == preferred


def test_clear_preferred_server_preserves_other_config(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    save_config({"preferred_speedtest": {"server_id": "1"}, "other": True}, path)

    existed = clear_preferred_speedtest(path)

    assert existed is True
    assert load_config(path) == {"other": True}


def test_preferred_librespeed_read_write_clear(tmp_path: Path) -> None:
    path = tmp_path / "config.json"

    preferred = set_preferred_librespeed(
        mode="server-json",
        server_json_url="https://example.com/servers.json",
        duration=15,
        path=path,
    )

    assert preferred == {
        "mode": "server-json",
        "server_json_url": "https://example.com/servers.json",
        "local_json_path": None,
        "duration": 15,
    }
    assert get_preferred_librespeed(path) == preferred

    existed = clear_preferred_librespeed(path)

    assert existed is True
    assert get_preferred_librespeed(path) is None


def test_preferred_librespeed_local_json(tmp_path: Path) -> None:
    path = tmp_path / "config.json"

    preferred = set_preferred_librespeed(
        mode="local-json",
        local_json_path="/tmp/servers.json",
        duration=None,
        path=path,
    )

    assert preferred["mode"] == "local-json"
    assert preferred["server_json_url"] is None
    assert preferred["local_json_path"] == "/tmp/servers.json"


def test_preferred_librespeed_rejects_mixed_sources(tmp_path: Path) -> None:
    path = tmp_path / "config.json"

    try:
        set_preferred_librespeed(
            mode="server-json",
            server_json_url="https://example.com/servers.json",
            local_json_path="/tmp/servers.json",
            path=path,
        )
    except ValueError as exc:
        assert "只能二选一" in str(exc)
    else:
        raise AssertionError("expected ValueError")
