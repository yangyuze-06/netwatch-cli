"""Platform backend selector."""

from __future__ import annotations

import platform as stdlib_platform

from netwatch.platform.base import BasePlatformBackend
from netwatch.platform.linux import LinuxBackend
from netwatch.platform.macos import MacOSBackend
from netwatch.platform.windows import WindowsBackend


def get_backend() -> BasePlatformBackend:
    """Return the backend for the current operating system."""
    system = stdlib_platform.system().lower()
    if system == "windows":
        return WindowsBackend()
    if system == "darwin":
        return MacOSBackend()
    if system == "linux":
        return LinuxBackend()
    return LinuxBackend()
