#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
# Вкладывает labnet (код, набор выживания, промпт ИИ, установщик) в bootstrap-zip.
# Layout bootstrap = содержимое префикса (bin/, share/, ...).
# Использует python3 (zipfile) — сохраняет права, правит shebang под префикс.
set -euo pipefail

BOOT="$1"; PREFIX="$2"; SRCDIR="$3"
[ -f "$BOOT" ] || { echo "нет bootstrap: $BOOT"; exit 1; }
command -v python3 >/dev/null || { echo "нужен python3"; exit 1; }

python3 - "$BOOT" "$PREFIX" "$SRCDIR" <<'PY'
import os, stat, sys, zipfile

boot, prefix, srcdir = sys.argv[1:4]
items = ["labnet", "install", "seed", "docs", "run"]


def add_file(zf, arc, data, mode=0o644):
    zi = zipfile.ZipInfo(arc)
    zi.external_attr = (mode & 0xFFFF) << 16
    zi.date_time = (2026, 1, 1, 0, 0, 0)
    zf.writestr(zi, data)


def add_tree(zf, path, arc):
    if os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            if "__pycache__" in root:
                continue
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, path)
                add_file(zf, f"{arc}/{rel}".replace(os.sep, "/"), open(full, "rb").read())
    else:
        add_file(zf, arc, open(path, "rb").read())


src = zipfile.ZipFile(boot)
out = zipfile.ZipFile(boot + ".new", "w", zipfile.ZIP_DEFLATED)
existing = set(src.namelist())
for zi in src.infolist():
    out.writestr(zi, src.read(zi.filename))
src.close()

base = "share/labnet"
for item in items:
    path = os.path.join(srcdir, item)
    if os.path.exists(path):
        add_tree(out, path, f"{base}/{item}")

entry = os.path.join(srcdir, "labnet.py")
data = open(entry, "rb").read().split(b"\n", 1)
add_file(out, f"{base}/labnet.py", f"#!{prefix}/bin/python3\n".encode() + data[1], 0o755)

add_file(out, "bin/labnet-setup",
         f'#!{prefix}/bin/bash\nexec bash "{prefix}/share/labnet/install/install.sh" "$@"\n'.encode(),
         0o755)
add_file(out, "bin/labnet",
         f'#!{prefix}/bin/bash\nexec python3 "{prefix}/share/labnet/labnet.py" "$@"\n'.encode(),
         0o755)

# Автозапуск при первом открытии Termux (через etc/profile.d): настроит сеть,
# поставит локальный ИИ и откроет чат — без единой ручной команды.
firstrun = f'''# labnet первый запуск — один раз
[ -n "$PS1" ] || return 0
[ -f "$HOME/.labnet-ready" ] && return 0
printf '\\n\\033[1m=== ПЕРВЫЙ ЗАПУСК СЕТИ СУДНОГО ДНЯ ===\\033[0m\\n'
printf 'Это один раз. Займёт несколько минут — просто жди, экран будет писать этапы.\\n'
mkdir -p "$HOME"
printf '\\n\\033[1m[1/3] Настраиваю сеть и Ковчег…\\033[0m\\n'
if [ ! -f "$HOME/.config/labnet/net.pass" ]; then
  python3 "{prefix}/share/labnet/labnet.py" key set || true
fi
bash "{prefix}/share/labnet/install/install.sh" || true
printf '\\n\\033[1m[2/3] Ставлю локальный ИИ (обновление пакетов, ollama, модель ~400 МБ)…\\033[0m\\n'
printf 'Загрузка модели может занять несколько минут — это нормально.\\n'
LABNET_NOCHAT=1 bash "{prefix}/share/labnet/install/ai-fix.sh" || true
touch "$HOME/.labnet-ready"
printf '\\n\\033[1m[3/3] Открываю приложение «Ковчег» в браузере…\\033[0m\\n'
nohup python3 "{prefix}/share/labnet/labnet.py" web --no-open >/dev/null 2>&1 &
sleep 3
termux-open-url "http://127.0.0.1:8787/" >/dev/null 2>&1 || true
printf 'Готово. Если окно не открылось — открой в браузере: http://127.0.0.1:8787\\n'
'''
add_file(out, "etc/profile.d/zz-labnet-firstrun.sh", firstrun.encode(), 0o644)
out.close()
os.replace(boot + ".new", boot)

# Если префикс не com.termux, проверим, что чужой префикс не просочился в наш payload.
if "com.termux" not in prefix:
    check = zipfile.ZipFile(boot)
    joined = b"".join(check.read(n) for n in check.namelist() if n.startswith(base))
    if b"com.termux" in joined:
        print("  ⚠ в payload остался префикс com.termux")
print(f"  payload вложен: {base} + bin/labnet-setup (prefix {prefix})")
PY
