# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Autonomous daemon: beacon, discover, greet, sync, drain queue — unattended."""
from __future__ import annotations

import socket
import time

from . import discovery, feedback, session
from .chat import Chat

DEFAULT_INTERVAL = 20.0
PROBE_TIMEOUT = 1.5


class Daemon:
    def __init__(self, mesh, tcp_port: int = 47112, udp_port: int = 47111,
                 interval: float = DEFAULT_INTERVAL, role: str = "node", quiet: bool = False):
        self.mesh = mesh
        self.role = role
        self.interval = interval
        self.quiet = quiet
        self.chat = Chat(mesh, mesh.net_key)
        self.disc = discovery.Discovery(mesh, tcp_port, udp_port)
        self.udp = discovery.open_socket(udp_port)
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("0.0.0.0", tcp_port))
        self.listener.listen(4)
        self.listener.setblocking(False)

    def _log(self, text: str) -> None:
        if not self.quiet:
            print(text, flush=True)

    def _greet(self, sess) -> None:
        try:
            if sess.meet_status in ("new", "changed"):
                feedback.event("new_peer" if sess.meet_status == "new" else "alert")
            else:
                feedback.greeting(sess.peer_id)
        except Exception:
            pass
        nick = (sess.peer_card or {}).get("nick", sess.peer_id)
        level = (sess.peer_card or {}).get("level", "?")
        self._log(f"🤝 {nick} · {level} · {sess.meet_status or '?'}")

    def _ingest(self, messages: list[dict]) -> int:
        for message in messages:
            if message.get("type") in ("text", "error"):
                self.chat.store.append(message.get("from_id") or message.get("from", "?"),
                                       "in", message.get("text", ""), message.get("ts"))
            self._log(f"   [{message.get('type')}] {message.get('from')}: {message.get('text')}")
        return len(messages)

    def _announce_and_sync(self) -> dict:
        self.mesh.announce()
        self.disc.announce(self.udp)
        summary = {"peers": 0, "messages": 0, "gained": 0}
        for beacon in self.disc.listen_once(self.udp, timeout=PROBE_TIMEOUT):
            try:
                sess = session.connect(beacon["addr"], beacon["tcp_port"], self.mesh,
                                       self.mesh.card(role=self.role), timeout=6.0)
                self._greet(sess)
                before = self.mesh.ark.stats()["chunks"]
                summary["messages"] += self._ingest(sess.sync())
                summary["gained"] += max(0, self.mesh.ark.stats()["chunks"] - before)
                sess.close()
                summary["peers"] += 1
            except Exception:
                continue
        return summary

    def _accept_one(self) -> int:
        try:
            conn, _ = self.listener.accept()
        except BlockingIOError:
            return 0
        conn.settimeout(8.0)
        try:
            sess = session.Session(self.mesh, conn)
            sess.server_handshake(self.mesh.card(role=self.role))
            self._greet(sess)
            self._ingest(sess.sync())
            sess.close()
            return 1
        except Exception:
            try:
                conn.close()
            except OSError:
                pass
            return 0

    def cycle(self) -> dict:
        summary = self._announce_and_sync()
        summary["accepted"] = self._accept_one()
        self.chat.poll()
        self.mesh.outbox.pending()  # touch: pending stays durable
        return summary

    def run(self, cycles: int | None = None, sleeper=time.sleep) -> int:
        count = 0
        try:
            while cycles is None or count < cycles:
                summary = self.cycle()
                self._log(f"цикл {count + 1}: соседей {summary['peers']}, "
                          f"входящих {summary['messages']}, чанков +{summary['gained']}")
                count += 1
                if cycles is None or count < cycles:
                    sleeper(self.interval)
        except KeyboardInterrupt:
            return count
        return count
