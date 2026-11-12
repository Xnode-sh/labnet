# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Relay store: hold envelopes addressed to other nodes and forward when possible."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

FILE_MODE = 0o600
DIR_MODE = 0o700
DEFAULT_TTL = 8


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


def hop(envelope: dict, node_id: str) -> dict:
    """Return a copy with one hop consumed: ttl-1, node_id appended to via."""
    forwarded = dict(envelope)
    forwarded["ttl"] = int(envelope.get("ttl", DEFAULT_TTL)) - 1
    forwarded["via"] = list(envelope.get("via", [])) + [node_id]
    return forwarded


class RelayStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _file(self, envelope_id: str) -> Path:
        return self.path / f"{envelope_id}.json"

    def accept(self, envelope: dict) -> bool:
        if int(envelope.get("ttl", 0)) <= 0:
            return False
        path = self._file(envelope["id"])
        if path.exists():
            return False
        _atomic(path, json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
        return True

    def all(self) -> list[dict]:
        if not self.path.is_dir():
            return []
        out = []
        for path in sorted(self.path.glob("*.json")):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return out

    def for_peer(self, node_id: str) -> list[dict]:
        return [e for e in self.all() if e.get("to_id") == node_id]

    def drop(self, envelope_id: str) -> None:
        path = self._file(envelope_id)
        if path.is_file():
            path.unlink()

    def size(self) -> int:
        return len(self.all())
