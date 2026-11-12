# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Sneakernet: carry the channel and Ark on physical media between nodes."""
from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

from .crypto import LabnetError


def pack(mesh, dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz") as tar:
        if mesh.node.channel.is_dir():
            tar.add(mesh.node.channel, arcname="channel")
        ark = mesh.node.state / "ark"
        if ark.is_dir():
            tar.add(ark, arcname="ark")
    return dest


def unpack(mesh, source: Path) -> int:
    source = Path(source)
    carrier = mesh.node.root / "_carrier"
    with tarfile.open(source, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise LabnetError(f"небезопасный путь в архиве: {member.name}")
        tar.extractall(carrier, filter="data")
    try:
        if (carrier / "channel").is_dir():
            shutil.copytree(carrier / "channel", mesh.node.channel, dirs_exist_ok=True)
        if (carrier / "ark").is_dir():
            shutil.copytree(carrier / "ark", mesh.node.state / "ark", dirs_exist_ok=True)
    finally:
        shutil.rmtree(carrier, ignore_errors=True)
    return len(mesh.recv())
