#!/usr/bin/env python3
"""Clean project build artifacts and cache directories.

Usage:
    python scripts/dev/clean_caches.py          # actual cleanup
    python scripts/dev/clean_caches.py --dry-run  # preview only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories to remove entirely (relative to REPO_ROOT)
REMOVE_DIRS: list[str] = [
    "build",
    "dist",
    "netwatch_cli.egg-info",
]

# Directory names to purge recursively
REMOVE_DIR_NAMES: set[str] = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}

# File extensions to purge recursively
REMOVE_EXTENSIONS: set[str] = {".pyc", ".pyo"}

# Protected paths that must NOT be touched (relative to REPO_ROOT)
PROTECTED_PATHS: list[Path] = [
    REPO_ROOT / ".venv",
    REPO_ROOT / "netwatch" / "location" / "data",
    REPO_ROOT / "tests" / "fixtures",
]

# Protected file extensions that must NOT be deleted
PROTECTED_EXTENSIONS: set[str] = {".geojson", ".csv", ".md", ".py"}


def is_under_protected(path: Path) -> bool:
    """Check if path is inside any protected directory."""
    resolved = path.resolve()
    for protected in PROTECTED_PATHS:
        try:
            resolved.relative_to(protected.resolve())
            return True
        except ValueError:
            continue
    return False


def is_protected_extension(path: Path) -> bool:
    return path.suffix.lower() in PROTECTED_EXTENSIONS


def _rmtree(path: Path, dry_run: bool) -> int:
    """Delete directory tree. Returns file count removed."""
    if dry_run or not path.exists():
        return 0
    count = sum(1 for _ in path.rglob("*")) + 1
    path = Path(str(path))  # resolve symlinks? no, just copy
    import shutil

    shutil.rmtree(path, ignore_errors=True)
    return count


def collect_candidates() -> tuple[list[Path], list[Path], int]:
    """Return (dirs_to_remove, files_to_remove, skipped_count)."""
    dirs: list[Path] = []
    files: list[Path] = []
    skipped = 0

    # Named dirs to purge recursively
    for dir_name in REMOVE_DIR_NAMES:
        for found in REPO_ROOT.rglob(dir_name):
            if found.is_dir():
                if is_under_protected(found):
                    skipped += 1
                else:
                    dirs.append(found)

    # Named paths to remove
    for rel in REMOVE_DIRS:
        p = REPO_ROOT / rel
        if p.exists():
            dirs.append(p)

    # File extensions
    for ext in REMOVE_EXTENSIONS:
        for found in REPO_ROOT.rglob(f"*{ext}"):
            if found.is_file():
                if is_under_protected(found):
                    skipped += 1
                elif is_protected_extension(found):
                    skipped += 1
                else:
                    files.append(found)

    return dirs, files, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean project build artifacts.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without actually deleting.",
    )
    args = parser.parse_args()

    dirs, files, skipped = collect_candidates()

    if args.dry_run:
        print(f"[dry-run] Would remove {len(dirs)} directories and {len(files)} files.")
        print(f"[dry-run] Would skip {skipped} protected paths.")
        if dirs:
            print("\nDirectories:")
            for d in sorted(dirs):
                print(f"  {d.relative_to(REPO_ROOT)}")
        if files:
            print("\nFiles:")
            for f in sorted(files):
                print(f"  {f.relative_to(REPO_ROOT)}")
        return 0

    removed_dirs = 0
    removed_files = 0

    for d in dirs:
        import shutil

        shutil.rmtree(d, ignore_errors=True)
        removed_dirs += 1

    for f in files:
        f.unlink(missing_ok=True)
        removed_files += 1

    print(f"Removed {removed_dirs} directories and {removed_files} files.")
    print(f"Skipped {skipped} protected paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
