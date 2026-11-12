# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""labnet mesh: sealed, signed envelopes between named nodes over a shared channel.

Store-and-forward: outgoing envelopes live in a durable outbox until the recipient
acks them; envelopes addressed to other nodes are relayed (multi-hop, TTL-bounded).
"""
from __future__ import annotations

import json
import socket
import time

from . import crypto, profile
from .ark import ArkStore
from .contacts import ContactStore
from .crypto import LabnetError
from .queue import Outbox, Seen
from .relay import DEFAULT_TTL, RelayStore, hop
from .store import Labnet
from .transport import DirTransport

PROTOCOL = 1


class Mesh:
    def __init__(self, node: Labnet, net_key: bytes):
        self.node = node
        self.net_key = net_key
        self.transport = DirTransport(node.channel)
        self.outbox = Outbox(node.state / "outbox")
        self.relay = RelayStore(node.state / "relay")
        self.seen = Seen(node.state / "seen.txt")
        self.ark = ArkStore(net_key, node.state / "ark")
        self.contacts = ContactStore(net_key, node.state / "contacts.json")

    def meet(self, card: dict) -> tuple[str, dict]:
        """Register a peer from its card (TOFU pinning). Returns (status, record)."""
        return self.contacts.check(card.get("node_id", ""), card.get("nick", ""),
                                   card.get("pub", ""), card.get("level", ""))

    # --- roster ---------------------------------------------------------
    def card(self, holdings: dict | None = None, role: str = "node", caps: list[str] | None = None) -> dict:
        if holdings is None:
            stats = self.ark.stats()
            holdings = {"topics": stats["files"], "docs": stats["files"],
                        "chunks": stats["chunks"], "bytes": stats["bytes"]}
        return profile.build_card(self.node, holdings, role, caps)

    def holdings(self) -> dict:
        stats = self.ark.stats()
        return {"topics": stats["files"], "docs": stats["files"],
                "chunks": stats["chunks"], "bytes": stats["bytes"]}

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
    def _seal(self, to_id: str, payload: dict, ttl: int = DEFAULT_TTL) -> dict:
        aad = self.node.net.encode("utf-8")
        blob = crypto.encrypt(self.net_key, json.dumps(payload, ensure_ascii=False).encode("utf-8"), aad)
        envelope = {
            "v": PROTOCOL,
            "id": crypto.random_id(),
            "net": self.node.net,
            "from": self.node.name,
            "from_id": self.node.node_id,
            "from_pub": self.node.identity.to_dict()["pub"],
            "to_id": to_id,
            "via": [],
            "ttl": ttl,
            "ts": int(time.time()),
            "ct": crypto.b64e(blob),
        }
        envelope["sig"] = self.node.identity.sign(crypto.canonical(crypto.signed_view(envelope)))
        return envelope

    def _payload(self, kind: str, text: str = "", **extra) -> dict:
        payload = {"type": kind, "text": text, "ts": int(time.time())}
        payload.update(extra)
        return payload

    def send(self, target: str, text: str, kind: str = "text", via: str | None = None) -> list[str]:
        """Queue + deliver to every resolved recipient. `via` routes through a relay node."""
        relay_ids = None
        if via:
            relay_ids = [r["node_id"] for r in self.resolve(via)]
        delivered = []
        for peer in self.resolve(target):
            envelope = self._seal(peer["node_id"], self._payload(kind, text))
            self.outbox.add(envelope)
            if relay_ids:
                for relay_id in relay_ids:
                    self.transport.deliver(relay_id, envelope)
            else:
                self.transport.deliver(peer["node_id"], envelope)
            delivered.append(peer["name"])
        return delivered

    def _open(self, envelope: dict) -> dict:
        if envelope.get("net") != self.node.net:
            raise LabnetError("конверт из другой сети")
        if not crypto.NodeIdentity.verify(envelope.get("from_pub", ""),
                                           crypto.canonical(crypto.signed_view(envelope)),
                                           envelope.get("sig", "")):
            raise LabnetError("подпись не сходится — конверт подделан")
        plain = crypto.decrypt(self.net_key, crypto.b64d(envelope["ct"]), self.node.net.encode("utf-8"))
        payload = json.loads(plain.decode("utf-8"))
        return {
            "from": envelope.get("from", "?"),
            "from_id": envelope.get("from_id", ""),
            "ts": envelope.get("ts", 0),
            "id": envelope.get("id", ""),
            "type": payload.get("type", "text"),
            "text": payload.get("text", ""),
            "ack_id": payload.get("ack_id", ""),
        }

    def _ack(self, to_id: str, ack_id: str) -> None:
        if not ack_id:
            return
        self.transport.deliver(to_id, self._seal(to_id, self._payload("ack", "", ack_id=ack_id), ttl=1))

    def _handle(self, envelope: dict) -> dict:
        """Central inbox logic shared by directory and live-session transports."""
        if not self.seen.is_new(envelope.get("id", "")):
            return {"kind": "skip"}
        if envelope.get("to_id") != self.node.node_id:
            if int(envelope.get("ttl", 0)) > 0:
                return {"kind": "relay", "envelope": hop(envelope, self.node.node_id)}
            return {"kind": "skip"}
        try:
            message = self._open(envelope)
        except LabnetError as exc:
            return {"kind": "message", "message": {
                "from": envelope.get("from", "?"), "type": "error", "text": str(exc),
                "ts": envelope.get("ts", 0)}}
        if message["type"] == "ack":
            self.outbox.mark_done(message["ack_id"])
            return {"kind": "skip"}
        ack = None
        if message["id"]:
            ack = self._seal(message["from_id"], self._payload("ack", "", ack_id=message["id"]), ttl=1)
        return {"kind": "message", "message": message, "ack": ack}

    def recv(self) -> list[dict]:
        """Process everything queued: ack own outbox, relay foreign envelopes, return new messages."""
        messages: list[dict] = []
        for path, envelope in self.transport.collect(self.node.node_id):
            self.transport.ack(path)
            result = self._handle(envelope)
            if result["kind"] == "relay":
                self.relay.accept(result["envelope"])
            elif result["kind"] == "message":
                ack = result.get("ack")
                if ack:
                    try:
                        self.transport.deliver(ack["to_id"], ack)
                    except OSError:
                        pass
                messages.append(result["message"])
        self.forward()
        self.redeliver()
        return messages

    def forward(self) -> int:
        """Deliver relayed envelopes to peers that are now known."""
        known = {p["node_id"] for p in self.peers()}
        count = 0
        for envelope in self.relay.all():
            if envelope.get("to_id") in known:
                self.transport.deliver(envelope["to_id"], envelope)
                self.relay.drop(envelope["id"])
                count += 1
        return count

    def redeliver(self) -> int:
        """Re-send pending outbox envelopes (idempotent thanks to dedup)."""
        count = 0
        for envelope in self.outbox.pending():
            self.transport.deliver(envelope["to_id"], envelope)
            count += 1
        return count

    # --- liveness -------------------------------------------------------
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
        answered = 0
        for message in self.recv():
            if message["type"] == "ping":
                self.send(message["from"], message["text"], kind="pong")
                answered += 1
        return answered
