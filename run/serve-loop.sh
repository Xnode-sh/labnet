#!/data/data/com.termux/files/usr/bin/bash
# labnet — фоновый ответчик: отвечает на ping и принимает сообщения.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
while true; do
  python3 "$DIR/labnet.py" serve >/dev/null 2>&1 || true
  python3 "$DIR/labnet.py" recv >> "$HOME/.local/state/labnet/inbox.log" 2>&1 || true
  sleep 2
done
