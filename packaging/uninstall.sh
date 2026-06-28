#!/bin/bash
# Stop TinkAgent and remove its LaunchAgent (no more auto-start at login).
# Usage: packaging/uninstall.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
PY="$REPO/.venv/bin/python"

"$PY" - <<'PYEOF'
from tink_agent import launchagent
launchagent.uninstall()
print(f"stopped + removed LaunchAgent: {launchagent.PLIST_PATH}")
PYEOF
