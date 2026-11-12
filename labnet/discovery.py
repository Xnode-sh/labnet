# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""LAN discovery: signed UDP beacons. Names stay private until the handshake."""
from __future__ import annotations

import json
import os
import socket
import time

from . import crypto

DEFAULT_PORT = 47111
MULTICAST = "239.76.108.1"
BEACON_VERSION = 1


def build_beacon(node, tcp_port: int) -> dict:
    beacon = {
        "t": "beacon",
        "v": BEACON_VERSION,
        "net": node.net,
        "node_id": node.node_id,
        "pub": node.identity.to_dict()["pub"],
        "tcp_port": tcp_port,
        "nonce": crypto.b64e(os.urandom(8)),
        "ts": int(time.time()),
    }
    beacon["sig"] = node.identity.sign(crypto.canonical(crypto.signed_view(beacon)))
    return beacon


def verify_beacon(beacon: dict, net: str) -> bool:
    if beacon.get("t") != "beacon" or beacon.get("net") != net:
        return False
    return crypto.NodeIdentity.verify(beacon.get("pub", ""),
                                      crypto.canonical(crypto.signed_view(beacon)),
                                      beacon.get("sig", ""))


def open_socket(port: int = DEFAULT_PORT) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("0.0.0.0", port))
    return sock


class Discovery:
    def __init__(self, mesh, tcp_port: int, port: int = DEFAULT_PORT):
        self.mesh = mesh
        self.tcp_port = tcp_port
        self.port = port
        self._seen: set[str] = set()

    def beacon(self) -> dict:
        return build_beacon(self.mesh.node, self.tcp_port)

    def announce(self, sock: socket.socket) -> None:
        data = json.dumps(self.beacon(), ensure_ascii=False).encode("utf-8")
        for target in (("255.255.255.255", self.port), (MULTICAST, self.port)):
            try:
                sock.sendto(data, target)
            except OSError:
                continue

    def listen_once(self, sock: socket.socket, timeout: float = 1.0) -> list[dict]:
        """Collect verified beacons until timeout; dedupe by (node_id, nonce)."""
        found: list[dict] = []
        sock.settimeout(timeout)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                break
            except OSError:
                break
            try:
                beacon = json.loads(data.decode("utf-8"))
            except ValueError:
                continue
            if not verify_beacon(beacon, self.mesh.node.net):
                continue
            if beacon.get("node_id") == self.mesh.node.node_id:
                continue
            key = f"{beacon['node_id']}:{beacon.get('nonce')}"
            if key in self._seen:
                continue
            self._seen.add(key)
            beacon["addr"] = addr[0]
            found.append(beacon)
        return found
