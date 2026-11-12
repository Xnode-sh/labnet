# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Live LAN session: TCP handshake (proves the shared network key) + envelope sync.

Friendly handshake: verify membership, exchange signed profile cards, then
store-and-forward everything addressed to the peer.
"""
from __future__ import annotations

import json
import os
import socket
import time

from . import crypto, profile
from .crypto import LabnetError

PROTOCOL = 1
DEFAULT_PORT = 47112


class SessionError(LabnetError):
    """Ошибка сессии."""


def _nonce() -> str:
    return crypto.b64e(os.urandom(16))


class Session:
    def __init__(self, mesh, sock: socket.socket):
        self.mesh = mesh
        self.node = mesh.node
        self.net_key = mesh.net_key
        self.sock = sock
        self.reader = sock.makefile("rb")
        self.peer_id = ""
        self.peer_card: dict | None = None

    def _send(self, frame: dict) -> None:
        self.sock.sendall((json.dumps(frame, ensure_ascii=False) + "\n").encode("utf-8"))

    def _recv(self) -> dict:
        line = self.reader.readline()
        if not line:
            raise SessionError("соединение закрыто")
        return json.loads(line.decode("utf-8"))

    def _transcript(self, a_id: str, b_id: str, na: str, nb: str) -> bytes:
        return crypto.canonical({"net": self.node.net, "a": a_id, "b": b_id, "na": na, "nb": nb})

    # --- handshake ------------------------------------------------------
    def client_handshake(self, my_card: dict) -> dict:
        nonce_a = _nonce()
        self._send({"t": "hello", "v": PROTOCOL, "node_id": self.node.node_id, "net": self.node.net,
                    "pub": self.node.identity.to_dict()["pub"], "nonce": nonce_a})
        hello = self._recv()
        if hello.get("t") != "hello" or hello.get("net") != self.node.net:
            raise SessionError("неверный ответ рукопожатия")
        if hello.get("node_id") == self.node.node_id:
            raise SessionError("сам с собой")
        if not crypto.NodeIdentity.verify(hello.get("pub", ""), nonce_a.encode(), hello.get("proof", "")):
            raise SessionError("peer не доказал владение ключом")
        nonce_b = hello["nonce"]
        transcript = self._transcript(self.node.node_id, hello["node_id"], nonce_a, nonce_b)
        mac = crypto.b64e(crypto.hmac256(self.net_key, transcript))
        self._send({"t": "confirm", "proof": self.node.identity.sign(nonce_b.encode()),
                    "mac": mac, "card": my_card})
        ok = self._recv()
        if ok.get("t") != "ok" or ok.get("mac") != mac:
            raise SessionError("ключ сети не совпал")
        self.peer_id = hello["node_id"]
        self.peer_card = ok.get("card")
        return self.peer_card or {}

    def server_handshake(self, my_card: dict) -> dict:
        hello = self._recv()
        if hello.get("t") != "hello" or hello.get("net") != self.node.net:
            raise SessionError("неверный hello")
        nonce_b = _nonce()
        self._send({"t": "hello", "v": PROTOCOL, "node_id": self.node.node_id, "net": self.node.net,
                    "pub": self.node.identity.to_dict()["pub"], "nonce": nonce_b,
                    "proof": self.node.identity.sign(hello["nonce"].encode())})
        confirm = self._recv()
        if confirm.get("t") != "confirm":
            raise SessionError("нет подтверждения")
        if not crypto.NodeIdentity.verify(hello.get("pub", ""), nonce_b.encode(), confirm.get("proof", "")):
            raise SessionError("client не доказал владение ключом")
        transcript = self._transcript(hello["node_id"], self.node.node_id, hello["nonce"], nonce_b)
        mac = crypto.b64e(crypto.hmac256(self.net_key, transcript))
        if confirm.get("mac") != mac:
            raise SessionError("ключ сети не совпал")
        self.peer_id = hello["node_id"]
        self.peer_card = confirm.get("card")
        self._send({"t": "ok", "mac": mac, "card": my_card})
        return self.peer_card or {}

    # --- sync -----------------------------------------------------------
    def _outgoing(self) -> list[dict]:
        pending = [e for e in self.mesh.outbox.pending() if e.get("to_id") == self.peer_id]
        return pending + self.mesh.relay.for_peer(self.peer_id)

    def sync(self) -> list[dict]:
        for envelope in self._outgoing():
            self._send({"t": "env", "envelope": envelope})
        self._send({"t": "done"})
        messages: list[dict] = []
        acks: list[dict] = []
        while True:
            frame = self._recv()
            if frame.get("t") == "done":
                break
            if frame.get("t") == "env":
                result = self.mesh._handle(frame["envelope"])
                if result["kind"] == "relay":
                    self.mesh.relay.accept(result["envelope"])
                elif result["kind"] == "message":
                    if result.get("ack"):
                        acks.append(result["ack"])
                    messages.append(result["message"])
        for ack in acks:
            self._send({"t": "env", "envelope": ack})
        self._send({"t": "done"})
        while True:
            frame = self._recv()
            if frame.get("t") == "done":
                break
            if frame.get("t") == "env":
                result = self.mesh._handle(frame["envelope"])
                if result["kind"] == "message":
                    messages.append(result["message"])
        self.sync_ark()
        return messages

    def sync_ark(self) -> int:
        """Exchange knowledge: swap manifests, then pull missing chunks. Returns chunks gained."""
        ark = self.mesh.ark
        self._send({"t": "ark_manifests", "manifests": ark.manifests()})
        frame = self._recv()
        peer_manifests = frame.get("manifests", []) if frame.get("t") == "ark_manifests" else []
        want: list[str] = []
        for manifest in peer_manifests:
            if manifest.get("name") and not ark.has_manifest(manifest["name"]):
                ark.add_manifest(manifest)
                want.extend(ark.missing(manifest))

        self._send({"t": "ark_want", "hashes": want})
        frame = self._recv()
        their_want = frame.get("hashes", []) if frame.get("t") == "ark_want" else []

        for sha in their_want:
            blob = ark.chunk_blob(sha)
            if blob is not None:
                self._send({"t": "ark_chunk", "hash": sha, "data": crypto.b64e(blob)})
            else:
                self._send({"t": "ark_none", "hash": sha})

        gained = 0
        received = 0
        while received < len(want):
            frame = self._recv()
            if frame.get("t") == "ark_chunk":
                if ark.add_chunk(frame["hash"], crypto.b64d(frame["data"])):
                    gained += 1
            received += 1
        self._send({"t": "ark_done"})
        while True:
            frame = self._recv()
            if frame.get("t") == "ark_done":
                break
        return gained

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def connect(host: str, port: int, mesh, my_card: dict, timeout: float = 10.0) -> Session:
    sock = socket.create_connection((host, port), timeout)
    session = Session(mesh, sock)
    try:
        session.client_handshake(my_card)
    except Exception:
        session.close()
        raise
    return session


def serve_once(listener: socket.socket, mesh, my_card: dict) -> Session:
    sock, _ = listener.accept()
    session = Session(mesh, sock)
    try:
        session.server_handshake(my_card)
    except Exception:
        session.close()
        raise
    return session


def verify_peer_card(card: dict) -> bool:
    return bool(card) and profile.verify_card(card)
