#!/data/data/com.termux/files/usr/bin/bash
# Починка/обновление labnet на устройстве (идемпотентно).
set -e
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
DEST="$PREFIX/share/labnet"
TMP="$PREFIX/tmp"
mkdir -p "$TMP" "$DEST"

echo "== 1/3 качаю свежий labnet =="
python3 - "$TMP" <<'PY'
import sys, os, tarfile, urllib.request
tmp = sys.argv[1]
url = "https://github.com/Xnode-sh/labnet/archive/refs/heads/main.tar.gz"
dst = os.path.join(tmp, "labnet-main.tar.gz")
urllib.request.urlretrieve(url, dst)
with tarfile.open(dst) as t:
    t.extractall(tmp, filter="data")
print("  скачано")
PY

echo "== 2/3 обновляю файлы =="
python3 - "$TMP/labnet-main" "$DEST" <<'PY'
import os, shutil, sys
src, dest = sys.argv[1], sys.argv[2]
for item in ("labnet", "labnet.py", "install", "seed", "docs", "run"):
    s = os.path.join(src, item)
    if not os.path.exists(s):
        continue
    d = os.path.join(dest, item)
    if os.path.isdir(s):
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(s, d)
    else:
        shutil.copy2(s, d)
print("  файлы на месте:", dest)
PY

echo "== 3/3 ставлю команду labnet =="
printf '#!/data/data/com.termux/files/usr/bin/bash\nexec python3 "%s/labnet.py" "$@"\n' "$DEST" > "$PREFIX/bin/labnet"
chmod +x "$PREFIX/bin/labnet"
[ -f "$DEST/run/start.sh" ] && chmod +x "$DEST/run/start.sh" || true

echo
echo "ГОТОВО. Проверь:"
echo "  labnet map"
echo "  labnet web"
echo "  labnet ai-up     # если нужен ИИ на этом узле"
