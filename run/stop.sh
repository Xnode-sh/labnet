#!/data/data/com.termux/files/usr/bin/bash
# labnet — остановить фоновый демон.
set -euo pipefail
LOG="${XDG_STATE_HOME:-$HOME/.local/state}/labnet"
if [ -f "$LOG/daemon.pid" ] && kill "$(cat "$LOG/daemon.pid")" 2>/dev/null; then
  echo "labnet демон остановлен"
  rm -f "$LOG/daemon.pid"
else
  echo "демон не запущен"
fi
command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock || true
