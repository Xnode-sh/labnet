#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
# Надёжный путь: берём официальный bootstrap Termux и вкладываем наш payload.
# Без Docker, без сборки пакетов. Требуется лишь curl.
# Примечание: официальный bootstrap — базовый (без python). При первом запуске
# install.sh доустановит python/cryptography (нужен интернет один раз).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABNET_DIR="$(cd "$HERE/.." && pwd)"
ARCH="${ARCH:-aarch64}"
WORK="${WORK:-$HERE/.workout}"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
VER="${BOOTSTRAP_VERSION:-}"
if [ -n "$VER" ]; then
  REL="https://github.com/termux/termux-packages/releases/download/bootstrap-${VER}/bootstrap-$ARCH.zip"
else
  REL="https://github.com/termux/termux-packages/releases/latest/download/bootstrap-$ARCH.zip"
fi

say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

have curl || { echo "нужен curl"; exit 1; }
mkdir -p "$WORK"
BOOT="$WORK/bootstrap-$ARCH.zip"

say "качаю официальный bootstrap ($ARCH)"
curl -fL "$REL" -o "$BOOT"

say "вкладываю labnet + набор выживания + промпт + установщик"
bash "$HERE/inject-payload.sh" "$BOOT" "$PREFIX" "$LABNET_DIR"

say "готово"
ls -la "$BOOT"
echo "префикс: $PREFIX"
echo "Артефакт: $BOOT"
