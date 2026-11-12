# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Configuration, identity persistence and paths for labnet."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from .crypto import LabnetError, NodeIdentity

DIR_MODE = 0o700
FILE_MODE = 0o600


def config_root() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "labnet"


def keyring_path() -> Path:
    """Локальный файл с паролем сети (600) — для автономной работы демона."""
    return config_root() / "net.pass"


def load_passphrase() -> str | None:
    env = os.environ.get("LABNET_PASSPHRASE")
    if env:
        return env
    path = keyring_path()
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    return None


def save_passphrase(passphrase: str) -> Path:
    path = keyring_path()
    _write_private(path, passphrase.encode("utf-8"))
    return path


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    os.chmod(path.parent, DIR_MODE)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, FILE_MODE)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Labnet:
    """Локальное состояние узла: конфиг, идентичность, каталог-канал."""

    def __init__(self, root: Path, share: Path, config: dict, identity: NodeIdentity):
        self.root = root
        self.share = share
        self.config = config
        self.identity = identity

    @property
    def net(self) -> str:
        return self.config["net"]

    @property
    def name(self) -> str:
        return self.config["node"]

    @property
    def focus(self) -> str:
        return self.config.get("focus", "")

    def set_focus(self, text: str) -> None:
        self.config["focus"] = text.strip()
        self.save()

    @property
    def node_id(self) -> str:
        return self.identity.node_id

    @property
    def channel(self) -> Path:
        return self.share / self.net

    @property
    def state(self) -> Path:
        path = self.root / "state"
        path.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        return path

    @classmethod
    def create(cls, name: str, net: str, share: Path, root: Path | None = None) -> "Labnet":
        root = root or config_root()
        if (root / "config.json").is_file():
            raise LabnetError(f"узел уже настроен: {root}")
        identity = NodeIdentity.generate()
        config = {
            "net": net,
            "node": name,
            "node_id": identity.node_id,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        node = cls(root, Path(share), config, identity)
        node.save()
        return node

    @classmethod
    def load(cls, root: Path | None = None, share: Path | None = None) -> "Labnet":
        root = root or config_root()
        config_path = root / "config.json"
        id_path = root / "identity.json"
        if not config_path.is_file() or not id_path.is_file():
            raise LabnetError("узел не настроен: выполни `labnet init`")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if share is not None:
            config["share"] = str(share)
        share_path = Path(config.pop("share", None) or (root / "share"))
        identity = NodeIdentity.from_dict(json.loads(id_path.read_text(encoding="utf-8")))
        return cls(root, share_path, config, identity)

    def save(self) -> None:
        config = dict(self.config)
        config["share"] = str(self.share)
        _write_private(self.root / "config.json", json.dumps(config, ensure_ascii=False, indent=2).encode("utf-8"))
        _write_private(self.root / "identity.json", json.dumps(self.identity.to_dict(), indent=2).encode("utf-8"))
