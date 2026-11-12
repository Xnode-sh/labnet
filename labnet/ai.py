# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""AI node: answer questions from the Ark, optionally via a local model.

No cloud, no API keys. Without a local model the Ark still answers — with
sources, honestly, or "не знаю" when nothing matches.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time

PERSONA = (
    "Ты — ARK, локальный оракул сети судного дня. Отвечай кратко, по-русски, только "
    "по фактам. Если в предоставленных источниках нет ответа — скажи «не знаю» и не "
    "выдумывай. Всегда полезнее честное «не знаю», чем ложная уверенность."
)
DEFAULT_MODEL = "qwen2.5:1.5b"
MAX_CONTEXT_CHARS = 4000


def provider_available() -> bool:
    return shutil.which("ollama") is not None


def _default_runner(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=120)


def run_model(prompt: str, model: str = DEFAULT_MODEL, runner=None) -> str | None:
    run = runner or _default_runner
    try:
        result = run(["ollama", "run", model, prompt])
    except (OSError, subprocess.SubprocessError):
        return None
    if getattr(result, "returncode", 1) != 0:
        return None
    return (getattr(result, "stdout", "") or "").strip() or None


def _keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[\w\-]{3,}", text.lower())}


def retrieve(ark, question: str, limit: int = 3) -> list[dict]:
    """Find Ark entries whose text overlaps the question (simple keyword RAG)."""
    terms = _keywords(question)
    if not terms:
        return []
    scored = []
    for manifest in ark.manifests():
        if manifest.get("size", 0) > 500_000:
            continue
        try:
            text = ""
            for sha in manifest["chunks"]:
                blob = ark.get(sha)
                if blob is None:
                    break
                text += blob.decode("utf-8", errors="ignore")
        except Exception:
            continue
        overlap = len(terms & _keywords(text))
        if overlap:
            snippet = text[:600]
            scored.append((overlap, {"name": manifest["name"], "snippet": snippet}))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:limit]]


def answer(ark, question: str, model: str = DEFAULT_MODEL, runner=None, focus: str = "") -> dict:
    sources = retrieve(ark, question)
    if not sources:
        return {"text": "не знаю", "sources": [], "model": None}
    context = "\n\n".join(f"[{s['name']}]\n{s['snippet']}" for s in sources)[:MAX_CONTEXT_CHARS]
    persona = PERSONA + (f"\nТвой узел специализируется на: {focus}." if focus else "")
    if provider_available():
        prompt = f"{persona}\n\nИсточники:\n{context}\n\nВопрос: {question}\nОтвет:"
        reply = run_model(prompt, model, runner=runner)
        if reply:
            return {"text": reply, "sources": [s["name"] for s in sources], "model": model}
    # no model: return the most relevant source excerpt honestly
    return {
        "text": f"(без модели) источник «{sources[0]['name']}»: {sources[0]['snippet'][:300]}",
        "sources": [s["name"] for s in sources],
        "model": None,
    }


def handle_ask(ark, message: dict, model: str = DEFAULT_MODEL, runner=None, focus: str = "") -> str:
    return answer(ark, message.get("text", ""), model=model, runner=runner, focus=focus)["text"]


def ask(mesh, peer: str, question: str, timeout: float = 10.0, interval: float = 0.5) -> dict | None:
    mesh.send(peer, question, kind="ask")
    start = time.time()
    while time.time() - start < timeout:
        for message in mesh.recv():
            if message.get("type") == "reply":
                return message
        time.sleep(interval)
    return None
