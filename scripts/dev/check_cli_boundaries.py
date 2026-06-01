#!/usr/bin/env python3
"""Advisory scan for CLI module boundary drift."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_MODULES_DIR = REPO_ROOT / "netwatch" / "cli_modules"
SUSPICIOUS_IMPORTS = {
    "http.server",
    "requests",
    "shapely",
    "socket",
    "subprocess",
    "psutil",
}
ALLOWED_IMPORTS = {
    ("netwatch/cli_modules/router.py", "webbrowser"),
}


@dataclass(frozen=True)
class BoundaryFinding:
    path: str
    status: str
    notes: str


def scan_cli_boundaries(repo_root: Path = REPO_ROOT) -> list[BoundaryFinding]:
    """Return advisory findings for cli_modules files."""
    findings: list[BoundaryFinding] = []
    for path in sorted((repo_root / "netwatch" / "cli_modules").glob("*.py")):
        rel_path = path.relative_to(repo_root).as_posix()
        notes = inspect_file(path, rel_path)
        status = "ok_adapter" if not notes else "review"
        findings.append(BoundaryFinding(rel_path, status, "; ".join(notes) or "CLI/UI adapter only"))
    return findings


def inspect_file(path: Path, rel_path: str) -> list[str]:
    """Inspect one CLI module for suspicious low-level imports."""
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [f"syntax error: {exc}"]

    notes: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _maybe_note_import(notes, rel_path, alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            _maybe_note_import(notes, rel_path, node.module)

    if len(text.splitlines()) > 900:
        notes.append("large CLI module; periodically review for extractable presentation helpers")
    return sorted(set(notes))


def _maybe_note_import(notes: list[str], rel_path: str, module: str) -> None:
    top_module = module.split(".", 1)[0]
    if (rel_path, module) in ALLOWED_IMPORTS:
        return
    if module in SUSPICIOUS_IMPORTS or top_module in SUSPICIOUS_IMPORTS:
        notes.append(f"suspicious low-level import: {module}")


def print_findings(findings: list[BoundaryFinding]) -> None:
    rows = [("path", "status", "notes")]
    rows.extend((finding.path, finding.status, finding.notes) for finding in findings)
    widths = [max(len(row[i]) for row in rows) for i in range(3)]
    for index, row in enumerate(rows):
        print(" | ".join(value.ljust(widths[i]) for i, value in enumerate(row)))
        if index == 0:
            print("-+-".join("-" * width for width in widths))


def main() -> int:
    findings = scan_cli_boundaries()
    print_findings(findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
