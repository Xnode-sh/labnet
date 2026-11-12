#!/data/data/com.termux/files/usr/bin/bash
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
# Загружает стартовое знание (seed/) в Ковчег узла.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -z "${LABNET_PASSPHRASE:-}" ]; then
  printf 'Пароль сети labnet: '; read -rs LABNET_PASSPHRASE; echo; export LABNET_PASSPHRASE
fi

for file in "$HERE"/seed/*.md; do
  name="survival-$(basename "$file" .md)"
  python3 "$HERE/labnet.py" ark put "$file" -n "$name" >/dev/null
  echo "  + $name"
done
echo "набор выживания загружен в Ковчег"
