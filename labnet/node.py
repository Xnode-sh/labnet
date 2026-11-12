# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""labnet mesh: sealed, signed envelopes between named nodes over a shared channel."""
from __future__ import annotations

import json
import socket
import time

from . import crypto
from .crypto import LabnetError
from .store import Labnet
from .transport import DirTransport

PROTOCOL = 1
MAX_CLOCK_SKEW = 0  # информативно; время проверяется, но не блокирует приём


class Mesh:
    def __init__(self, node: Labnet, net_key: bytes):
        self.node = node
        self.net_key = net_key
        self.transport = DirTransport(node.channel)

    # --- roster ---------------------------------------------------------
    def announce(self) -> dict:
        entry = {
            "v": PROTOCOL,
            "node_id": self.node.node_id,
            "name": self.node.name,
            "pub": self.node.identity.to_dict()["pub"],
            "host": socket.gethostname(),
            "last_seen": int(time.time()),
        }
        entry["sig"] = self.node.identity.sign(crypto.canonical(entry))
        self.transport.publish_roster(self.node.node_id, entry)
        return entry

    def peers(self) -> list[dict]:
        result = []
        for node_id, entry in self.transport.roster().items():
            verified = crypto.NodeIdentity.verify(entry.get("pub", ""), crypto.canonical(
                {k: entry[k] for k in entry if k != "sig"}), entry.get("sig", ""))
            result.append({
                "node_id": node_id,
                "name": entry.get("name", "?"),
                "host": entry.get("host", ""),
                "last_seen": entry.get("last_seen", 0),
                "age": max(0, int(time.time()) - int(entry.get("last_seen", 0))),
                "verified": verified,
                "self": node_id == self.node.node_id,
            })
        return sorted(result, key=lambda p: p["name"])

    def resolve(self, target: str) -> list[dict]:
        """Resolve a peer name / node_id / 'all' to roster entries."""
        peers = [p for p in self.peers() if not p["self"]]
        if target in ("all", "*"):
            return peers
        matched = [p for p in peers if p["name"] == target or p["node_id"] == target]
        if not matched:
            raise LabnetError(f"узел не найден в roster: {target} (сначала `labnet announce` на нём)")
        return matched

    # --- envelopes ------------------------------------------------------
    def _seal(self, to: dict, payload: dict) -> dict:
        aad = self.node.net.encode("utf-8")
        blob = crypto.encrypt(self.net_key, json.dumps(payload, ensure_ascii=False).encode("utf-8"), aad)
        envelope = {
            "v": PROTOCOL,
            "net": self.node.net,
            "from": self.node.name,
            "from_id": self.node.node_id,
            "from_pub": self.node.identity.to_dict()["pub"],
            "to_id": to["node_id"],
            "ts": int(time.time()),
            "ct": crypto.b64e(blob),
        }
        envelope["sig"] = self.node.identity.sign(crypto.canonical(envelope))
        return envelope

    def send(self, target: str, text: str, kind: str = "text") -> list[str]:
        payload = {"type": kind, "text": text, "ts": int(time.time())}
        delivered = []
        for peer in self.resolve(target):
            self.transport.deliver(peer["node_id"], self._seal(peer, payload))
            delivered.append(peer["name"])
        return delivered

    def _open(self, envelope: dict) -> dict:
        if envelope.get("net") != self.node.net:
            raise LabnetError("конверт из другой сети")
        unsigned = {k: envelope[k] for k in envelope if k != "sig"}
        if not crypto.NodeIdentity.verify(envelope.get("from_pub", ""), crypto.canonical(unsigned), envelope.get("sig", "")):
            raise LabnetError("подпись не сходится — конверт подделан")
        plain = crypto.decrypt(self.net_key, crypto.b64d(envelope["ct"]), self.node.net.encode("utf-8"))
        payload = json.loads(plain.decode("utf-8"))
        return {
            "from": envelope.get("from", "?"),
            "from_id": envelope.get("from_id", ""),
            "ts": envelope.get("ts", 0),
            "type": payload.get("type", "text"),
            "text": payload.get("text", ""),
        }

    def recv(self) -> list[dict]:
        messages = []
        for path, envelope in self.transport.collect(self.node.node_id):
            try:
                messages.append(self._open(envelope))
            except LabnetError as exc:
                messages.append({"from": envelope.get("from", "?"), "type": "error", "text": str(exc), "ts": envelope.get("ts", 0)})
            self.transport.ack(path)
        return messages

    def ping(self, peer: str, timeout: float = 5.0, interval: float = 0.5) -> float | None:
        token = f"ping-{int(time.time() * 1000)}"
        self.send(peer, token, kind="ping")
        start = time.time()
        while time.time() - start < timeout:
            for message in self.recv():
                if message["type"] == "pong" and message["text"] == token:
                    return round(time.time() - start, 3)
            time.sleep(interval)
        return None

    def serve_pings(self) -> int:
        """Answer any queued pings; return how many were answered."""
        answered = 0
        for message in self.recv():
            if message["type"] == "ping":
                self.send(message["from"], message["text"], kind="pong")
                answered += 1
        return answered
