#!/bin/zsh
# Double-click this file in Finder to run the end-to-end test in Terminal.
# Sources the user's zsh profile so Homebrew / Android SDK paths are available.
#
# Usage:
#   Double-click in Finder                         — test any connected physical device
#   zsh run_e2e_test.command RFCW70CZWKV           — assert a specific serial is selected

[ -f ~/.zprofile ] && source ~/.zprofile 2>/dev/null
[ -f ~/.zshrc ]   && source ~/.zshrc   2>/dev/null

cd "$(dirname "$0")"

echo "=== Android-MCP end-to-end test ==="
echo ""

# Ensure the ADB daemon is running before the test probes it
ADB=$(which adb 2>/dev/null || echo "")
[ -n "$ADB" ] && "$ADB" start-server 2>/dev/null

/usr/bin/env python3 e2e_test.py "$@"
STATUS=$?

echo ""
echo "=== Test finished (exit $STATUS) — press Return to close ==="
read
