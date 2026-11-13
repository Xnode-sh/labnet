#!/data/data/com.termux/files/usr/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
# labnet — установщик сети судного дня для Termux (без root).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

say "labnet · сеть судного дня — установка"

# --- 1. зависимости -----------------------------------------------------
have python3 || { say "ставлю python"; pkg install -y python; }
python3 -c 'import cryptography' 2>/dev/null || { say "ставлю python-cryptography"; pkg install -y python-cryptography; }
have git || { say "ставлю git"; pkg install -y git; }
if ! have termux-notification; then
  say "нет Termux:API — уведомления и вибрация будут недоступны (остальное работает)."
  echo "  Приложение Termux:API ставится из F-Droid; затем: pkg install termux-api"
fi

# --- 2. ключ сети и узел -------------------------------------------------
if [ -z "${LABNET_PASSPHRASE:-}" ] && [ ! -f "$HOME/.config/labnet/net.pass" ]; then
  if [ -t 0 ]; then
    printf 'Придумай пароль сети (одинаковый на всех устройствах, не показывается): '
    read -rs LABNET_PASSPHRASE; echo
    python3 "$HERE/labnet.py" key set "$LABNET_PASSPHRASE"
  else
    say "нет ввода — генерирую пароль сети (скопируй net.pass на другие узлы)"
    python3 "$HERE/labnet.py" key set
  fi
  unset LABNET_PASSPHRASE
fi
name="${LABNET_NAME:-$(cat /proc/sys/kernel/hostname 2>/dev/null || echo node)}"
net="${LABNET_NET:-redlab}"
share="${LABNET_SHARE:-$HOME/labnet-share}"

if [ -f "$HOME/.config/labnet/config.json" ]; then
  say "узел уже настроен — обновляю объявление"
else
  say "создаю узел '$name' в сети '$net'"
  python3 "$HERE/labnet.py" --share "$share" init --name "$name" --net "$net"
fi
python3 "$HERE/labnet.py" announce || true

# команда `labnet` в PATH
mkdir -p "$PREFIX/bin"
printf '#!/data/data/com.termux/files/usr/bin/bash\nexec python3 "%s/labnet.py" "$@"\n' "$HERE" > "$PREFIX/bin/labnet"
chmod +x "$PREFIX/bin/labnet"

# --- 3. набор выживания в Ковчег ---------------------------------------
files="$(python3 "$HERE/labnet.py" ark stats 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("files",0))' 2>/dev/null || echo 0)"
if [ "${files:-0}" = "0" ]; then
  say "наполняю Ковчег набором выживания"
  bash "$HERE/install/seed-ark.sh" || true
else
  say "Ковчег уже наполнен ($files записей)"
fi

# --- 4. ИИ-промпт -------------------------------------------------------
say "ИИ-узел: промпт судного дня готов (install/persona-doomsday.md)"
if have ollama; then
  echo "  ollama найден — локальная модель доступна: labnet ask <узел> \"вопрос\""
else
  echo "  ollama не установлен — оракул отвечает по Ковчегу без модели."
  echo "  Хочешь модель: pkg install ollama && ollama pull qwen2.5:1.5b"
fi

# --- 5. автономность ----------------------------------------------------
say "включаю фоновый демон (искать своих, знакомить, синкать)"
bash "$HERE/run/start.sh" || true

# --- 6. финал -----------------------------------------------------------
say "готово"
cat <<EOF
Чат:      python3 $HERE/labnet.py web      (откроется в браузере телефона)
Терминал: python3 $HERE/labnet.py chat
Кто рядом: python3 $HERE/labnet.py discover
Ковчег:   python3 $HERE/labnet.py ark list
Инструкция: docs/RUNBOOK.md
EOF
