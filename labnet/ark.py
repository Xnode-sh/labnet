# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Ark — content-addressed, encrypted knowledge/file store with replication."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from . import crypto

CHUNK_SIZE = 1 << 20  # 1 MiB
DIR_MODE = 0o700
FILE_MODE = 0o600
AAD = b"labnet-ark"


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


class ArkStore:
    def __init__(self, net_key: bytes, path: Path):
        self.net_key = net_key
        self.path = Path(path)
        self.chunks_dir = self.path / "chunks"
        self.manifests_dir = self.path / "manifests"

    # --- chunks ---------------------------------------------------------
    def _chunk_file(self, sha: str) -> Path:
        return self.chunks_dir / sha[:2] / sha

    def has(self, sha: str) -> bool:
        return self._chunk_file(sha).is_file()

    def add_bytes(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        if not self.has(sha):
            _atomic(self._chunk_file(sha), crypto.encrypt(self.net_key, data, AAD))
        return sha

    def chunk_blob(self, sha: str) -> bytes | None:
        path = self._chunk_file(sha)
        return path.read_bytes() if path.is_file() else None

    def add_chunk(self, sha: str, blob: bytes) -> bool:
        """Store a received encrypted chunk only if it decrypts to the expected hash."""
        try:
            plain = crypto.decrypt(self.net_key, blob, AAD)
        except Exception:
            return False
        if hashlib.sha256(plain).hexdigest() != sha:
            return False
        if not self.has(sha):
            _atomic(self._chunk_file(sha), blob)
        return True

    def get(self, sha: str) -> bytes | None:
        blob = self.chunk_blob(sha)
        if blob is None:
            return None
        return crypto.decrypt(self.net_key, blob, AAD)

    # --- files / manifests ----------------------------------------------
    def put_file(self, source: Path, name: str | None = None, by: str = "", topic: str = "") -> dict:
        data = Path(source).read_bytes()
        chunks = []
        for offset in range(0, len(data), CHUNK_SIZE):
            chunks.append(self.add_bytes(data[offset:offset + CHUNK_SIZE]))
        manifest = {
            "v": 1,
            "name": name or Path(source).name,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "chunk_size": CHUNK_SIZE,
            "chunks": chunks,
            "by": by,
            "topic": topic,
            "ts": int(time.time()),
        }
        self.add_manifest(manifest)
        return manifest

    def put_text(self, text: str, name: str, by: str = "", topic: str = "") -> dict:
        tmp = self.path / "_pending.txt"
        _atomic(tmp, text.encode("utf-8"))
        manifest = self.put_file(tmp, name, by=by, topic=topic)
        tmp.unlink(missing_ok=True)
        return manifest

    def add_manifest(self, manifest: dict) -> None:
        _atomic(self.manifests_dir / f"{manifest['name']}.json",
                json.dumps(manifest, ensure_ascii=False).encode("utf-8"))

    def manifests(self) -> list[dict]:
        if not self.manifests_dir.is_dir():
            return []
        out = []
        for path in sorted(self.manifests_dir.glob("*.json")):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return out

    def has_manifest(self, name: str) -> bool:
        return (self.manifests_dir / f"{name}.json").is_file()

    def manifest(self, name: str) -> dict | None:
        path = self.manifests_dir / f"{name}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def missing(self, manifest: dict) -> list[str]:
        return [sha for sha in manifest.get("chunks", []) if not self.has(sha)]

    def get_file(self, name: str, dest: Path) -> bool:
        manifest = self.manifest(name)
        if not manifest or self.missing(manifest):
            return False
        data = b"".join(self.get(sha) or b"" for sha in manifest["chunks"])
        if hashlib.sha256(data).hexdigest() != manifest["sha256"]:
            return False
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True

    def stats(self) -> dict:
        manifests = self.manifests()
        chunks = sum(len(m["chunks"]) for m in manifests)
        return {
            "files": len(manifests),
            "chunks": chunks,
            "bytes": sum(m["size"] for m in manifests),
        }
