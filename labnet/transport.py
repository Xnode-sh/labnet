# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Directory transport: the shared channel that carries labnet envelopes.

Any folder that all nodes can see works as the channel — a Syncthing folder,
an SSH mount, a synced storage dir. labnet never assumes how it is synced.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path

DIR_MODE = 0o700


class DirTransport:
    def __init__(self, channel: Path):
        self.channel = Path(channel)

    def _ensure(self, path: Path) -> Path:
        path.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        return path

    @property
    def roster_dir(self) -> Path:
        return self.channel / "roster"

    def inbox_dir(self, node_id: str) -> Path:
        return self.channel / "inbox" / node_id

    def _atomic(self, path: Path, data: bytes) -> None:
        self._ensure(path.parent)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def publish_roster(self, node_id: str, entry: dict) -> None:
        self._atomic(self.roster_dir / f"{node_id}.json", json.dumps(entry, ensure_ascii=False).encode("utf-8"))

    def roster(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        if not self.roster_dir.is_dir():
            return out
        for path in sorted(self.roster_dir.glob("*.json")):
            try:
                out[path.stem] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        return out

    def deliver(self, to_id: str, envelope: dict) -> Path:
        name = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.json"
        path = self.inbox_dir(to_id) / name
        self._atomic(path, json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
        return path

    def collect(self, node_id: str) -> list[tuple[Path, dict]]:
        inbox = self.inbox_dir(node_id)
        messages: list[tuple[Path, dict]] = []
        if not inbox.is_dir():
            return messages
        for path in sorted(inbox.glob("*.json")):
            try:
                messages.append((path, json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                continue
        return messages

    def ack(self, path: Path) -> None:
        done = self._ensure(path.parent / "done")
        os.replace(path, done / path.name)
