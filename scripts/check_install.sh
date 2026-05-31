#!/usr/bin/env bash
set -euo pipefail

echo "==> Locating project root..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ ! -f "$PROJECT_ROOT/pyproject.toml" ] || [ ! -d "$PROJECT_ROOT/netwatch" ]; then
  echo "❌ Cannot find project root."
  echo "Please run this script from the netwatch-cli repository."
  exit 1
fi

cd "$PROJECT_ROOT"

VENV_DIR="$PROJECT_ROOT/.venv"
VENV_BIN="$VENV_DIR/bin"
PYTHON="$VENV_BIN/python"
NETWATCH="$VENV_BIN/netwatch"

if [ ! -x "$PYTHON" ]; then
  echo "❌ Virtual environment not found: $VENV_DIR"
  echo "Please run the Quick Start installation commands first:"
  echo "  python3 -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  python -m pip install -e \".[browser]\""
  exit 1
fi

export PATH="$VENV_BIN:$PATH"

echo "==> Checking Python dependencies..."

"$PYTHON" - <<'PY'
import rich
import requests
import speedtest
import reverse_geocoder
from playwright.sync_api import sync_playwright

print("✔ Python dependencies OK")
PY

echo "==> Checking netwatch command..."

if [ -x "$NETWATCH" ]; then
  echo "✔ netwatch command OK: $NETWATCH"
else
  echo "❌ netwatch entrypoint not found in .venv/bin"
  echo "Please reinstall the project:"
  echo "  source .venv/bin/activate"
  echo "  python -m pip install -e \".[browser]\""
  exit 1
fi

echo "==> Checking Playwright Chromium..."

"$PYTHON" - <<'PY'
from playwright.sync_api import sync_playwright

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        browser.close()
    print("✔ Playwright Chromium OK")
except Exception:
    print("❌ Playwright Chromium is not ready")
    print("Run:")
    print("  python -m playwright install chromium")
    raise SystemExit(1)
PY

echo "==> Checking speedtest command..."

if [ -x "$VENV_BIN/speedtest" ]; then
  echo "✔ Python speedtest-cli command found: $VENV_BIN/speedtest"
  echo "ℹ This is likely provided by the Python speedtest-cli package."
elif command -v speedtest >/dev/null 2>&1; then
  echo "✔ speedtest command found: $(command -v speedtest)"
  echo "ℹ This may be the official Ookla CLI or another speedtest command."
else
  echo "ℹ speedtest command not found. Official Ookla CLI is optional."
fi

echo "✅ netwatch installation looks good."
