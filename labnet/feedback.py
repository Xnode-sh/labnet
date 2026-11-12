# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Haptic / toast / speech feedback. Degrades to no-op when Termux:API is absent."""
from __future__ import annotations

import shutil
import subprocess
import time

from . import profile

GAP_MS = 90

PATTERNS = {
    "new_peer": [120, 80, 120, 80, 120],
    "known_peer": [120, 80, 120],
    "sync_done": [400],
    "alert": [80, 60, 80, 60, 80, 60, 400],
}


def available() -> bool:
    return shutil.which("termux-vibrate") is not None


def _default_runner(argv: list[str]) -> None:
    subprocess.run(argv, capture_output=True, timeout=10)


def pulse(pattern: list[int], runner=None, sleeper=time.sleep) -> int:
    """Play a vibration pattern: each value is a buzz (ms), GAP_MS pause between."""
    run = runner or _default_runner
    for index, duration in enumerate(pattern):
        run(["termux-vibrate", "-d", str(duration)])
        if index < len(pattern) - 1:
            sleeper(GAP_MS / 1000)
    return len(pattern)


def greeting(node_id: str, runner=None, sleeper=time.sleep) -> int:
    """Personal callsign: vibration pattern unique to a node."""
    return pulse(profile.haptic_of(node_id), runner=runner, sleeper=sleeper)


def event(name: str, runner=None, sleeper=time.sleep) -> int:
    return pulse(PATTERNS.get(name, PATTERNS["known_peer"]), runner=runner, sleeper=sleeper)


def toast(text: str, runner=None) -> None:
    run = runner or _default_runner
    run(["termux-toast", text])


def speak(text: str, runner=None) -> None:
    run = runner or _default_runner
    run(["termux-tts-speak", text])
