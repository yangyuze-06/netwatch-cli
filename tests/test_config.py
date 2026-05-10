from pathlib import Path

from netwatch.config import (
    clear_preferred_speedtest,
    get_preferred_speedtest,
    load_config,
    save_config,
    save_preferred_speedtest,
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
