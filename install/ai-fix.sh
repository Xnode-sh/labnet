#!/data/data/com.termux/files/usr/bin/bash
# labnet AI — установка и запуск локального ИИ (ARK) на Termux. Всё одной командой.
set -u
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
MODEL="${1:-qwen2.5:0.5b}"
say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

say "1/6 обновляю пакеты (чинит libc++ — из-за него падал движок ollama)"
pkg upgrade -y || true

say "2/6 ollama"
command -v ollama >/dev/null 2>&1 || pkg install -y ollama

say "3/6 запускаю сервер модели (Vulkan выключен — на телефоне он падает)"
export OLLAMA_VULKAN=false
pkill -f "ollama serve" 2>/dev/null || true
sleep 1
nohup ollama serve >"$PREFIX/tmp/ollama.log" 2>&1 </dev/null &
sleep 5

say "4/6 качаю модель $MODEL (лёгкая, ~400 МБ; первый раз долго)"
ollama pull "$MODEL"

say "5/6 собираю модель 'ark' с промптом судного дня"
RUNMODEL="$MODEL"
PERSONA=""
for f in "$PREFIX/share/labnet/install/persona-doomsday.md" \
         "$HOME/labnet/install/persona-doomsday.md" \
         "$HOME/deploy-kit/persona-doomsday.md"; do
  [ -f "$f" ] && PERSONA="$f" && break
done
if [ -n "$PERSONA" ]; then
  { echo "FROM $MODEL"; echo 'PARAMETER temperature 0.3'; printf 'SYSTEM """\n'; cat "$PERSONA"; printf '\n"""\n'; } > "$PREFIX/tmp/ark.mf"
  if ollama create ark -f "$PREFIX/tmp/ark.mf"; then
    RUNMODEL="ark"
  fi
fi

say "6/6 открываю чат (выход: /bye)"
exec ollama run "$RUNMODEL"
