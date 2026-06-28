#!/bin/bash
# Install TinkAgent as a LaunchAgent: starts it now (menu-bar icon appears) and
# auto-starts it at every login. launchd runs it in the GUI/Aqua session, which
# a script-launched .app cannot reliably do.
#
# Usage: packaging/install.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
PY="$REPO/.venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "error: venv not found at $PY — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

"$PY" - "$REPO" <<'PYEOF'
import sys
from tink_agent import launchagent
repo = sys.argv[1]
launchagent.install_and_start(launchagent.current_python(), repo)
print(f"installed + started LaunchAgent: {launchagent.PLIST_PATH}")
print(f"logs: {launchagent.LOG_PATH}")
PYEOF

echo "The Tink Agent menu-bar icon should now appear. Grant Microphone + Accessibility"
echo "to 'Python' in System Settings > Privacy & Security if prompted."
