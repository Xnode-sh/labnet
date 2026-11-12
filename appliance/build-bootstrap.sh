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
docker info >/dev/null 2>&1 || { echo "Docker не запущен (systemctl start docker / открой Docker Desktop)"; exit 1; }
# На Apple Silicon Docker Desktop по умолчанию arm64 — termux-packages ждёт linux/amd64.
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) export DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-linux/amd64}" ;;
esac
echo "  docker: ok   arch: $ARCH   package: $APP_PACKAGE   platform: ${DOCKER_DEFAULT_PLATFORM:-native}"

mkdir -p "$WORK"
PKG="$WORK/termux-packages"
if [ ! -d "$PKG/.git" ]; then
  say "клонирую termux-packages"
  git clone --depth 1 "$PKG_REPO" "$PKG"
else
  say "termux-packages уже есть — обновляю"
  git -C "$PKG" pull --ff-only || true
fi

# Обход бага upstream: build-bootstraps.sh указывает 'bzip2', но теперь это
# подпакет 'libbz2' (issue termux/termux-packages#27093). Патчим идемпотентно.
if grep -q 'PACKAGES+=("bzip2")' "$PKG/scripts/build-bootstraps.sh" 2>/dev/null; then
  say "патч upstream: bzip2 -> libbz2 в build-bootstraps.sh"
  sed -i 's/PACKAGES+=("bzip2")/PACKAGES+=("libbz2")/' "$PKG/scripts/build-bootstraps.sh"
fi

say "сборка bootstrap в Docker (долго — десятки минут)"
export TERMUX_APP_PACKAGE="$APP_PACKAGE"
export TERMUX__PREFIX="$PREFIX"
say "готовлю права и пользователя для контейнера"
chmod -R a+rwX "$PKG" "$WORK" 2>/dev/null || true
# На CI docker-userns не даёт builder(1001) писать в смонтированный каталог ->
# итоговый mv zip падает. Гоним сборку от root, но с HOME builder (там NDK/SDK).
export TERMUX_DOCKER_EXEC_EXTRA_ARGS="${TERMUX_DOCKER_EXEC_EXTRA_ARGS:---user root -e HOME=/home/builder}"

# Набор предустановки. Без git/rsync: их зависимости (apr-util) сейчас не собираются
# из-за 404 на исходнике, а labnet уже вложен в bootstrap — git на устройстве не нужен.
( cd "$PKG" && ./scripts/run-docker.sh ./scripts/build-bootstraps.sh \
    --architectures "$ARCH" \
    --add "python,python-cryptography,termux-api,nano" )

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
