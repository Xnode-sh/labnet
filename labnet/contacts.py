# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""TOFU acquaintance book: pin a peer's key on first meeting, alert on change."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from . import crypto

FILE_MODE = 0o600
DIR_MODE = 0o700
AAD = b"labnet-contacts"


class ContactStore:
    def __init__(self, net_key: bytes, path: Path):
        self.net_key = net_key
        self.path = Path(path)

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(crypto.decrypt(self.net_key, self.path.read_bytes(), AAD).decode("utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(crypto.encrypt(self.net_key, json.dumps(data, ensure_ascii=False).encode("utf-8"), AAD))
            os.chmod(tmp, FILE_MODE)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def check(self, node_id: str, name: str, pub: str, level: str = "", focus: str = "") -> tuple[str, dict]:
        """Return ('new' | 'known' | 'changed', record) and update last-seen."""
        data = self._load()
        now = int(time.time())
        record = data.get(node_id)
        if record is None:
            record = {"name": name, "pub": pub, "level": level, "focus": focus,
                      "rep": 0, "first_seen": now, "last_seen": now, "seen": 1}
            data[node_id] = record
            self._save(data)
            return "new", record
        status = "changed" if record.get("pub") != pub else "known"
        record.update({"name": name, "level": level, "focus": focus, "last_seen": now,
                       "seen": record.get("seen", 1) + 1})
        if status == "changed":
            record["prev_pub"] = record.get("pub")
            record["pub"] = pub
            record["changed_at"] = now
        data[node_id] = record
        self._save(data)
        return status, record

    def all(self) -> list[dict]:
        return [{"node_id": k, **v} for k, v in sorted(self._load().items())]

    def reputation(self, node_id: str) -> int:
        return int(self._load().get(node_id, {}).get("rep", 0))

    def bump(self, node_id: str, amount: int = 1) -> int:
        """Reward (or penalize) a node's helpfulness. Returns the new score."""
        data = self._load()
        record = data.get(node_id)
        if record is None:
            return 0
        record["rep"] = int(record.get("rep", 0)) + amount
        data[node_id] = record
        self._save(data)
        return record["rep"]

    def ranked(self) -> list[dict]:
        return sorted(({"node_id": k, **v} for k, v in self._load().items()),
                      key=lambda r: (r.get("rep", 0), r.get("seen", 0)), reverse=True)
