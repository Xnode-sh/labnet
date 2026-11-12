#!/data/data/com.termux/files/usr/bin/bash
# labnet — запуск фонового демона с удержанием пробуждения.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${XDG_STATE_HOME:-$HOME/.local/state}/labnet"
mkdir -p "$LOG"
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true
nohup python3 "$DIR/labnet.py" daemon --quiet >> "$LOG/daemon.log" 2>&1 &
echo $! > "$LOG/daemon.pid"
echo "labnet демон запущен (pid $(cat "$LOG/daemon.pid")), лог: $LOG/daemon.log"
