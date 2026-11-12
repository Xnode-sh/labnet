# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Cryptography for labnet: network key, node identity, envelope sealing."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12
KEY_BYTES = 32
MAXMEM = 256 * 1024 * 1024
KDF = {"n": 2 ** 15, "r": 8, "p": 1, "dklen": KEY_BYTES}


class LabnetError(Exception):
    """Ошибка labnet."""


def b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64d(text: str) -> bytes:
    return base64.b64decode(text)


def net_salt(net: str) -> bytes:
    return hashlib.sha256(f"labnet/{net}".encode()).digest()[:16]


def derive_net_key(passphrase: str, net: str) -> bytes:
    return hashlib.scrypt(
        passphrase.encode("utf-8"), salt=net_salt(net),
        n=KDF["n"], r=KDF["r"], p=KDF["p"], dklen=KDF["dklen"], maxmem=MAXMEM,
    )


def encrypt(net_key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(net_key).encrypt(nonce, plaintext, aad)


def decrypt(net_key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    if len(blob) < NONCE_BYTES + 16:
        raise LabnetError("повреждённый конверт")
    try:
        return AESGCM(net_key).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], aad)
    except InvalidTag as exc:
        raise LabnetError("не расшифровано: другой ключ сети или порча") from exc


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def random_id() -> str:
    return os.urandom(16).hex()


ROUTING_FIELDS = ("via", "ttl")


def signed_view(envelope: dict) -> dict:
    """Fields covered by the signature: everything except sig and mutable routing."""
    return {k: v for k, v in envelope.items() if k != "sig" and k not in ROUTING_FIELDS}


def hmac256(key: bytes, message: bytes) -> bytes:
    return hmac.new(key, message, hashlib.sha256).digest()


class NodeIdentity:
    """Долговременная подпись узла (Ed25519)."""

    def __init__(self, private: Ed25519PrivateKey):
        self._priv = private
        self._pub = private.public_key()

    @classmethod
    def generate(cls) -> "NodeIdentity":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_dict(cls, data: dict) -> "NodeIdentity":
        return cls(Ed25519PrivateKey.from_private_bytes(b64d(data["priv"])))

    def to_dict(self) -> dict:
        return {
            "pub": b64e(self.public_bytes()),
            "priv": b64e(self._priv.private_bytes_raw()),
        }

    def public_bytes(self) -> bytes:
        return self._pub.public_bytes_raw()

    @property
    def node_id(self) -> str:
        digest = hashlib.sha256(self.public_bytes()).hexdigest()
        return digest[:12]

    def sign(self, message: bytes) -> str:
        return b64e(self._priv.sign(message))

    @staticmethod
    def verify(public_b64: str, message: bytes, signature_b64: str) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(b64d(public_b64)).verify(b64d(signature_b64), message)
            return True
        except (InvalidSignature, ValueError):
            return False
