# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Node profile card: nickname, role, knowledge level, haptic callsign."""
from __future__ import annotations

import hashlib
import socket
import time

from . import crypto

CARD_VERSION = 1
LEVELS = [
    (100_000_000, "Архивариус"),
    (10_000_000, "Хранитель"),
    (1_000_000, "Знаток"),
    (0, "Новичок"),
]


def compute_level(holdings: dict) -> str:
    size = int(holdings.get("bytes", 0))
    for threshold, name in LEVELS:
        if size >= threshold:
            return name
    return "Новичок"


def haptic_of(node_id: str) -> list[int]:
    """Deterministic vibration pattern (ms pulses) derived from a node id."""
    digest = hashlib.sha256(node_id.encode("utf-8")).digest()
    return [80 + (digest[i] % 5) * 40 for i in range(3)]


def build_card(node, holdings: dict | None = None, role: str = "node", caps: list[str] | None = None) -> dict:
    holdings = holdings or {"topics": 0, "docs": 0, "chunks": 0, "bytes": 0}
    card = {
        "v": CARD_VERSION,
        "node_id": node.node_id,
        "nick": node.name,
        "pub": node.identity.to_dict()["pub"],
        "role": role,
        "host": socket.gethostname(),
        "holdings": holdings,
        "level": compute_level(holdings),
        "caps": caps or ["labnet"],
        "haptic": haptic_of(node.node_id),
        "ts": int(time.time()),
    }
    card["sig"] = node.identity.sign(crypto.canonical(card))
    return card


def verify_card(card: dict) -> bool:
    return crypto.NodeIdentity.verify(
        card.get("pub", ""),
        crypto.canonical({k: v for k, v in card.items() if k != "sig"}),
        card.get("sig", ""),
    )
