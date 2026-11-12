# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Durable outbox and dedup seen-set for store-and-forward delivery."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

FILE_MODE = 0o600
DIR_MODE = 0o700


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, FILE_MODE)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Outbox:
    """Исходящие, которые ждут подтверждения (ack). Ничего не теряется."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.done = self.path / "done"

    def _file(self, envelope_id: str) -> Path:
        return self.path / f"{envelope_id}.json"

    def add(self, envelope: dict) -> bool:
        path = self._file(envelope["id"])
        if path.exists():
            return False
        _atomic(path, json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
        return True

    def get(self, envelope_id: str) -> dict | None:
        path = self._file(envelope_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def pending(self) -> list[dict]:
        if not self.path.is_dir():
            return []
        out = []
        for path in sorted(self.path.glob("*.json")):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return out

    def mark_done(self, envelope_id: str) -> bool:
        path = self._file(envelope_id)
        if not path.is_file():
            return False
        self.done.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        os.replace(path, self.done / path.name)
        return True

    def size(self) -> int:
        return len(self.pending())


class Seen:
    """Помнит id обработанных конвертов — защита от дублей при пересылке."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._ids: set[str] = set()
        if self.path.is_file():
            self._ids = set(self.path.read_text(encoding="utf-8").split())

    def is_new(self, envelope_id: str) -> bool:
        if not envelope_id or envelope_id in self._ids:
            return False
        self._ids.add(envelope_id)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(envelope_id + "\n")
        os.chmod(self.path, FILE_MODE)
        return True
