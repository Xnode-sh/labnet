# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""AI node: answer questions from the Ark, optionally via a local model.

No cloud, no API keys. Without a local model the Ark still answers — with
sources, honestly, or "не знаю" when nothing matches.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time

PERSONA = (
    "Ты — ARK, локальный оракул сети судного дня. Отвечай кратко, по-русски, только "
    "по фактам. Если в предоставленных источниках нет ответа — скажи «не знаю» и не "
    "выдумывай. Всегда полезнее честное «не знаю», чем ложная уверенность."
)
DEFAULT_MODEL = os.environ.get("LABNET_MODEL", "qwen2.5:1.5b")
MAX_CONTEXT_CHARS = 4000
PERSONA_CANDIDATES = [
    os.environ.get("LABNET_PERSONA", ""),
    (os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
     + "/share/labnet/install/persona-doomsday.md"),
    os.path.expanduser("~/labnet/install/persona-doomsday.md"),
    os.path.expanduser("~/deploy-kit/persona-doomsday.md"),
]


def persona_text() -> str:
    """Персона узла: из файла, иначе встроенный текст."""
    for path in PERSONA_CANDIDATES:
        if path and os.path.isfile(path):
            try:
                text = open(path, encoding="utf-8").read().strip()
                if text:
                    return text
            except OSError:
                pass
    return PERSONA


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
            scored.append((overlap, {"name": manifest["name"], "by": manifest.get("by", ""),
                                     "snippet": snippet}))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:limit]]


def answer(ark, question: str, model: str | None = None, runner=None, focus: str = "") -> dict:
    model = model or DEFAULT_MODEL
    sources = retrieve(ark, question)
    if not sources:
        return {"text": "не знаю", "sources": [], "model": None}
    context = "\n\n".join(f"[{s['name']}]\n{s['snippet']}" for s in sources)[:MAX_CONTEXT_CHARS]
    persona = persona_text() + (f"\nТвой узел специализируется на: {focus}." if focus else "")
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


def handle_ask(ark, message: dict, model: str | None = None, runner=None, focus: str = "") -> str:
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


def _focus_score(question: str, focus: str) -> int:
    return len(_keywords(question) & _keywords(focus))


def asknet(mesh, question: str, timeout: float = 12.0, interval: float = 0.5, reward: bool = True) -> dict:
    """Ask the whole network; rank answers by focus match + reputation. Reward helpful nodes."""
    peers = [p for p in mesh.peers() if not p["self"]]
    mesh.send("all", question, kind="ask")
    cards = {c["node_id"]: c for c in mesh.contacts.all()}
    answers: dict[str, dict] = {}
    start = time.time()
    while time.time() - start < timeout:
        for message in mesh.recv():
            if message.get("type") == "reply" and message.get("from_id") not in answers:
                answers[message["from_id"]] = message
        if peers and len(answers) >= len(peers):
            break
        time.sleep(interval)
    ranked = []
    for node_id, message in answers.items():
        card = cards.get(node_id, {})
        text = message.get("text", "")
        useful = bool(text) and "не знаю" not in text.lower()
        score = _focus_score(question, card.get("focus", "")) * 3
        score += min(int(card.get("rep", 0)), 8)
        score += 1 if useful else 0
        ranked.append({
            "from": message.get("from"), "from_id": node_id,
            "focus": card.get("focus", ""), "rep": int(card.get("rep", 0)),
            "useful": useful, "score": score, "text": text,
        })
    ranked.sort(key=lambda a: a["score"], reverse=True)
    if reward and ranked:
        for index, answer in enumerate(ranked):
            if not answer["useful"]:
                continue
            mesh.contacts.bump(answer["from_id"], 2 if index == 0 else 1)
    return {"question": question, "asked": len(peers), "answers": ranked}
