"""Compatibility wrapper for netwatch.speedtest.backends."""

from netwatch.speedtest.backends import librespeed_cli, models, ookla_cli, python_speedtest

__all__ = ["librespeed_cli", "models", "ookla_cli", "python_speedtest"]
