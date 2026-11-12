# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Chat: conversation history (encrypted at rest) over the labnet mesh."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from . import crypto

DIR_MODE = 0o700
FILE_MODE = 0o600
AAD = b"labnet-chat"
MAX_HISTORY = 500


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


class ConversationStore:
    """Per-peer message history, encrypted on disk with the network key."""

    def __init__(self, net_key: bytes, path: Path):
        self.net_key = net_key
        self.path = Path(path)

    def _file(self, peer_id: str) -> Path:
        return self.path / f"{peer_id}.json"

    def _load(self, peer_id: str) -> list[dict]:
        path = self._file(peer_id)
        if not path.is_file():
            return []
        try:
            plain = crypto.decrypt(self.net_key, path.read_bytes(), AAD)
            return json.loads(plain.decode("utf-8"))
        except Exception:
            return []

    def append(self, peer_id: str, direction: str, text: str, ts: int | None = None) -> dict:
        messages = self._load(peer_id)
        record = {"dir": direction, "text": text, "ts": ts or int(time.time())}
        messages.append(record)
        messages = messages[-MAX_HISTORY:]
        _atomic(self._file(peer_id), crypto.encrypt(self.net_key,
                json.dumps(messages, ensure_ascii=False).encode("utf-8"), AAD))
        return record

    def history(self, peer_id: str) -> list[dict]:
        return self._load(peer_id)

    def peers(self) -> list[str]:
        if not self.path.is_dir():
            return []
        return sorted(p.stem for p in self.path.glob("*.json"))


class Chat:
    def __init__(self, mesh, net_key: bytes):
        self.mesh = mesh
        self.store = ConversationStore(net_key, mesh.node.state / "chat")

    def send(self, target: str, text: str) -> list[str]:
        delivered = self.mesh.send(target, text)
        for peer in self.mesh.resolve(target):
            self.store.append(peer["node_id"], "out", text)
        return delivered

    def poll(self) -> list[dict]:
        """Pull new inbound messages into history."""
        stored = []
        for message in self.mesh.recv():
            if message.get("type") in ("text", "error"):
                self.store.append(message.get("from_id") or message.get("from", "?"),
                                   "in", message.get("text", ""), message.get("ts"))
                stored.append(message)
        return stored
