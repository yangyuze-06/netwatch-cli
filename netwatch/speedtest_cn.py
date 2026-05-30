"""speedtest.cn browser automation result model and text parser."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SpeedtestCnResult:
    """Structured result parsed from speedtest.cn page text."""

    source: str = "speedtest.cn browser automation"
    download_mbps: float | None = None
    upload_mbps: float | None = None
    ping_ms: float | None = None
    jitter_ms: float | None = None
    server_name: str | None = None
    location: str | None = None
    raw_text: str | None = None
    error: str | None = None
    debug_screenshot_path: str | None = None

    @property
    def download_MBps(self) -> float | None:
        """Return download speed in MB/s for display."""
        return self.download_mbps / 8 if self.download_mbps is not None else None

    @property
    def upload_MBps(self) -> float | None:
        """Return upload speed in MB/s for display."""
        return self.upload_mbps / 8 if self.upload_mbps is not None else None


@dataclass(frozen=True)
class ParsedMetric:
    """Metric value with the line index where it was found."""

    value: float | None
    line_index: int | None


DOWNLOAD_ALIASES = ("下载", "download")
UPLOAD_ALIASES = ("上传", "upload")
PING_ALIASES = ("ping", "时延", "延迟")
JITTER_ALIASES = ("抖动", "jitter")
SERVER_ALIASES = ("测速点", "测试点", "服务器", "server")
LOCATION_ALIASES = ("位置", "地区", "运营商", "isp", "location")
ALL_METRIC_ALIASES = DOWNLOAD_ALIASES + UPLOAD_ALIASES + PING_ALIASES + JITTER_ALIASES
NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")


def parse_speedtest_cn_text(text: str) -> SpeedtestCnResult:
    """Parse speedtest.cn DOM text into a structured result without network access."""
    raw_text = text
    normalized_text = normalize_text(text)
    lines = split_clean_lines(normalized_text)
    if not lines:
        return SpeedtestCnResult(raw_text=raw_text, error="无法解析 speedtest.cn 页面文本：内容为空。")

    download = parse_metric(lines, DOWNLOAD_ALIASES, bandwidth=True)
    upload = parse_metric(lines, UPLOAD_ALIASES, bandwidth=True)
    ping = parse_metric(lines, PING_ALIASES, bandwidth=False)
    jitter = parse_metric(lines, JITTER_ALIASES, bandwidth=False)

    server_name = parse_labeled_value(lines, SERVER_ALIASES)
    location = parse_labeled_value(lines, LOCATION_ALIASES)
    if not server_name or not location:
        fallback_server, fallback_location = parse_unlabeled_server_location(lines, [download, upload, ping, jitter])
        server_name = server_name or fallback_server
        location = location or fallback_location

    result = SpeedtestCnResult(
        download_mbps=download.value,
        upload_mbps=upload.value,
        ping_ms=ping.value,
        jitter_ms=jitter.value,
        server_name=server_name,
        location=location,
        raw_text=raw_text,
    )
    missing = [
        name
        for name, value in (
            ("download", result.download_mbps),
            ("upload", result.upload_mbps),
            ("ping", result.ping_ms),
        )
        if value is None
    ]
    if missing:
        result.error = "无法从 speedtest.cn 页面文本解析必要字段：" + ", ".join(missing)
    return result


def normalize_text(text: str) -> str:
    """Normalize common punctuation and whitespace without losing page text."""
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("：", ":")
        .replace("／", "/")
        .replace("Ｍ", "M")
        .replace("ｍ", "m")
        .replace("Ｂ", "B")
        .replace("ｂ", "b")
        .replace("Ｓ", "S")
        .replace("ｓ", "s")
    )


def split_clean_lines(text: str) -> list[str]:
    """Return non-empty, stripped DOM text lines."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_metric(lines: list[str], aliases: tuple[str, ...], *, bandwidth: bool) -> ParsedMetric:
    """Parse a metric from same-line or label-then-value-line page text."""
    for index, line in enumerate(lines):
        if not contains_alias(line, aliases):
            continue
        value = parse_number_from_line(line)
        if value is not None:
            return ParsedMetric(convert_metric_unit(value, line, bandwidth=bandwidth), index)
        next_index, next_line = find_next_value_line(lines, index + 1)
        if next_line is not None:
            next_value = parse_number_from_line(next_line)
            if next_value is not None:
                unit_context = f"{line} {next_line}"
                return ParsedMetric(convert_metric_unit(next_value, unit_context, bandwidth=bandwidth), next_index)
    return ParsedMetric(None, None)


def find_next_value_line(lines: list[str], start_index: int) -> tuple[int | None, str | None]:
    """Find a nearby numeric line after a metric label."""
    for index in range(start_index, min(start_index + 4, len(lines))):
        line = lines[index]
        if contains_alias(line, ALL_METRIC_ALIASES):
            return None, None
        if parse_number_from_line(line) is not None:
            return index, line
    return None, None


def parse_number_from_line(line: str) -> float | None:
    """Return the first decimal number found in a line."""
    match = NUMBER_RE.search(line.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def convert_metric_unit(value: float, unit_context: str, *, bandwidth: bool) -> float:
    """Convert MB/s bandwidth values to Mbps; keep Mbps and ms values unchanged."""
    if bandwidth and re.search(r"\bMB\s*/\s*s\b", unit_context, flags=re.IGNORECASE):
        return value * 8
    return value


def parse_labeled_value(lines: list[str], aliases: tuple[str, ...]) -> str | None:
    """Parse same-line or next-line text for server/location labels."""
    for index, line in enumerate(lines):
        alias = first_alias_in_line(line, aliases)
        if not alias:
            continue
        same_line = cleanup_labeled_value(line, alias)
        if same_line:
            return same_line
        next_value = next_non_metric_text(lines, index + 1)
        if next_value:
            return next_value
    return None


def cleanup_labeled_value(line: str, alias: str) -> str | None:
    """Remove a label and separators, returning useful text when present."""
    position = line.lower().find(alias.lower())
    if position < 0:
        return None
    value = line[position + len(alias) :].strip(" :：-/|")
    if not value or looks_like_number_only(value) or contains_alias(value, ALL_METRIC_ALIASES):
        return None
    return value


def next_non_metric_text(lines: list[str], start_index: int) -> str | None:
    """Return the next line that looks like descriptive text rather than a metric."""
    for line in lines[start_index : min(start_index + 4, len(lines))]:
        if is_candidate_text_value(line):
            return line
    return None


def parse_unlabeled_server_location(
    lines: list[str],
    metrics: list[ParsedMetric],
) -> tuple[str | None, str | None]:
    """Infer server and location from text after the final parsed metric."""
    metric_indexes = [metric.line_index for metric in metrics if metric.line_index is not None]
    if not metric_indexes:
        return None, None
    start_index = max(metric_indexes) + 1
    candidates = [line for line in lines[start_index:] if is_candidate_text_value(line)]
    server_name = candidates[0] if candidates else None
    location = candidates[1] if len(candidates) > 1 else None
    return server_name, location


def is_candidate_text_value(line: str) -> bool:
    """Return True for likely server/location text lines."""
    if not line or looks_like_number_only(line):
        return False
    if contains_alias(line, ALL_METRIC_ALIASES):
        return False
    if contains_alias(line, SERVER_ALIASES + LOCATION_ALIASES):
        return False
    lowered = line.lower()
    noisy_fragments = ("cookie", "privacy", "广告", "验证码", "登录", "注册", "下载app", "app")
    return not any(fragment in lowered for fragment in noisy_fragments)


def looks_like_number_only(line: str) -> bool:
    """Return True for standalone metric values."""
    return re.fullmatch(r"\d+(?:\.\d+)?\s*(?:mbps|mb/s|ms)?", line.strip(), flags=re.IGNORECASE) is not None


def contains_alias(line: str, aliases: tuple[str, ...]) -> bool:
    """Return True if a line contains any metric or metadata alias."""
    lowered = line.lower()
    return any(alias.lower() in lowered for alias in aliases)


def first_alias_in_line(line: str, aliases: tuple[str, ...]) -> str | None:
    """Return the first configured alias found in a line."""
    lowered = line.lower()
    for alias in aliases:
        if alias.lower() in lowered:
            return alias
    return None
