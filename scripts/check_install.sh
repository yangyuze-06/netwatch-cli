#!/usr/bin/env bash
set -euo pipefail

find_project_root() {
  if [[ -f "pyproject.toml" && -d "netwatch" ]]; then
    pwd
    return 0
  fi

  if [[ "$(basename "$PWD")" == "netwatch" && -f "../pyproject.toml" && -d "../netwatch" ]]; then
    cd ..
    pwd
    return 0
  fi

  echo "Could not find project root. Please run this script from netwatch-cli or netwatch/." >&2
  return 1
}

PROJECT_ROOT="$(find_project_root)"
cd "$PROJECT_ROOT"

if [[ ! -d ".venv" ]]; then
  echo "Please run the Quick Start installation commands first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source ".venv/bin/activate"

python - <<'PY'
import importlib
import sys

modules = [
    ("rich", "rich"),
    ("requests", "requests"),
    ("speedtest", "speedtest-cli"),
    ("playwright.sync_api", "playwright"),
]

missing = []
for module_name, package_name in modules:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        missing.append((module_name, package_name, exc))

if missing:
    print("Python dependency check failed.", file=sys.stderr)
    for module_name, package_name, exc in missing:
        print(f"- {module_name} ({package_name}): {exc}", file=sys.stderr)
    print("Please install dependencies with:", file=sys.stderr)
    print("  python -m pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)
PY

if ! command -v netwatch >/dev/null 2>&1; then
  echo "netwatch command not found." >&2
  echo "Please install the project with:" >&2
  echo "  python -m pip install -e ." >&2
  exit 1
fi

python - <<'PY'
import sys
from playwright.sync_api import sync_playwright

try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser.close()
except Exception as exc:
    print("Playwright Chromium check failed.", file=sys.stderr)
    print(exc, file=sys.stderr)
    print("Please run:", file=sys.stderr)
    print("  python -m playwright install chromium", file=sys.stderr)
    sys.exit(1)
PY

if command -v speedtest >/dev/null 2>&1; then
  echo "speedtest command found: $(command -v speedtest)"
  echo "This command may be provided by Python speedtest-cli; official Ookla CLI is optional."
else
  echo "Optional speedtest command not found."
  echo "This command may be provided by Python speedtest-cli; official Ookla CLI is optional."
fi

echo "✅ netwatch installation looks good."
