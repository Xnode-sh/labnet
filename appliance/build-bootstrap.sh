#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
# Сборка Termux-bootstrap с предустановленной сетью судного дня (labnet).
# Требуется: Linux + Docker. Запускать на ноутбуке/сервере, НЕ на телефоне.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABNET_DIR="$(cd "$HERE/.." && pwd)"
WORK="${WORK:-$HERE/.work}"
PKG_REPO="${PKG_REPO:-https://github.com/termux/termux-packages.git}"
APP_PACKAGE="${TERMUX_APP_PACKAGE:-sh.xnode.redterm}"
ARCH="${ARCH:-aarch64}"
PREFIX="/data/data/$APP_PACKAGE/files/usr"

say() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

say "проверка окружения"
have docker || { echo "НУЖЕН Docker. Установи docker и повтори."; exit 1; }
have git || { echo "нужен git"; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker не запущен (systemctl start docker)"; exit 1; }
echo "  docker: ok   arch: $ARCH   package: $APP_PACKAGE"

mkdir -p "$WORK"
PKG="$WORK/termux-packages"
if [ ! -d "$PKG/.git" ]; then
  say "клонирую termux-packages"
  git clone --depth 1 "$PKG_REPO" "$PKG"
else
  say "termux-packages уже есть — обновляю"
  git -C "$PKG" pull --ff-only || true
fi

say "сборка bootstrap в Docker (долго — десятки минут)"
export TERMUX_APP_PACKAGE="$APP_PACKAGE"
export TERMUX__PREFIX="$PREFIX"
( cd "$PKG" && ./scripts/run-docker.sh ./scripts/build-bootstraps.sh \
    --architectures "$ARCH" \
    --add "python,python-cryptography,git,termux-api,nano,rsync" )

BOOT="$(ls "$PKG"/bootstrap-"$ARCH".zip "$PKG"/build-tools/bootstrap-"$ARCH".zip 2>/dev/null | head -1)"
[ -n "$BOOT" ] && [ -f "$BOOT" ] || { echo "bootstrap не найден после сборки"; exit 1; }
echo "  собран: $BOOT"

say "вкладываю labnet + набор выживания + промпт"
bash "$HERE/inject-payload.sh" "$BOOT" "$PREFIX" "$LABNET_DIR"

echo
say "готово"
echo "bootstrap: $BOOT"
echo "проверка префикса:"
unzip -p "$BOOT" 2>/dev/null | grep -a "com.termux" | head -1 && echo "  ⚠ найден чужой префикс" || echo "  чужого префикса нет — ок"
echo
echo "Дальше — вложить этот bootstrap в форк termux-app (см. appliance/APK.md)."
