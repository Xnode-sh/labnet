# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Local web UI (127.0.0.1): chat with the local AI (ARK) + network view."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import ai

PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ковчег · ARK</title><style>
:root{--bg:#0d1119;--fg:#e6edf5;--muted:#8b97ac;--ark:#1f6feb;--me:#2a3550}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.5 system-ui,sans-serif;display:flex;flex-direction:column;height:100vh}
header{padding:12px 14px;border-bottom:1px solid #223;display:flex;gap:10px;align-items:center;background:#111826}
header b{font-size:17px}header .st{font-size:11px;color:var(--muted);margin-left:auto}
.net{padding:8px 12px;display:flex;gap:8px;overflow-x:auto;border-bottom:1px solid #1b2233}
.node{flex:0 0 auto;background:#151d2c;border:1px solid #26314a;border-radius:10px;padding:6px 10px;font-size:12px;min-width:110px}
.node .n{font-weight:700}.node .f{color:var(--muted);font-size:11px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#3b4763;margin-right:6px}
.dot.on{background:#36e2ce}
#log{flex:1;overflow:auto;padding:14px;display:flex;flex-direction:column;gap:10px}
.m{max-width:82%;padding:10px 13px;border-radius:14px;white-space:pre-wrap;word-break:break-word}
.me{align-self:flex-end;background:var(--me)}
.ark{align-self:flex-start;background:var(--me);background:#182238}
.src{font-size:11px;color:var(--muted);margin-top:4px}
footer{padding:10px;border-top:1px solid #223;display:flex;gap:8px;background:#111826}
#inp{flex:1;background:#151d2c;color:var(--fg);border:1px solid #2a3550;border-radius:12px;padding:12px;font:inherit}
#send{padding:12px 18px;border:0;border-radius:12px;background:var(--me);background:#1f6feb;color:#fff;font:inherit}
</style></head><body>
<header><b>🔥 Ковчег</b><span>локальный ИИ · ARK</span><span id="st" class="st"></span></header>
<div id="net" class="net"></div>
<div id="log"></div>
<footer><input id="inp" placeholder="Спроси ARK…" autocomplete="off"><button id="send">→</button></footer>
<script>
const log=document.getElementById('log'),inp=document.getElementById('inp');
function add(cls,txt,sources){const d=document.createElement('div');d.className='m '+cls;
 d.textContent=txt;if(sources&&sources.length){const s=document.createElement('div');s.className='src';
 s.textContent='источники: '+sources.join(', ');d.appendChild(s)}log.appendChild(d);log.scrollTop=log.scrollHeight;}
async function api(u,o){const r=await fetch(u,o);return r.json()}
async function ask(){const t=inp.value.trim();if(!t)return;add('me',t);inp.value='';
 add('ark','…');const wait=log.lastChild;
 try{const d=await api('/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q:t})});
  wait.textContent=d.text||'(нет ответа)';if(d.sources&&d.sources.length){const s=document.createElement('div');
  s.className='src';s.textContent='источники: '+d.sources.join(', ');wait.appendChild(s);}}
 catch(e){wait.textContent='ошибка: '+e}}
document.getElementById('send').onclick=ask;
inp.addEventListener('keydown',e=>{if(e.key==='Enter')ask()});
async function loadNet(){try{const d=await api('/api/network');const el=document.getElementById('net');
 let h='<div class="node"><div class="n"><span class="dot on"></span>'+d.me.name+'</div><div class="f">'+
 d.me.files+' знаний'+(d.me.focus?' · '+d.me.focus:'')+'</div></div>';
 for(const n of d.nodes){h+='<div class="node"><div class="n"><span class="dot'+(n.online?' on':'')+'"></span>'+n.name+
 '</div><div class="f">'+(n.focus||n.level||'—')+'</div></div>'}el.innerHTML=h}catch(e){}
 document.getElementById('st').textContent='сеть '+(d.me?d.me.name:'');}
add('ark','Привет. Я ARK — локальный оракул сети судного дня. Работаю без интернета. Спрашивай.');
loadNet();setInterval(loadNet,3000);
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    chat = None
    mesh = None

    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/api/network"):
            self._json({"me": self._me(), "nodes": self._peers()})
        elif self.path.startswith("/api/peers"):
            self._json({"peers": self._peers()})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            payload = {}
        if self.path.startswith("/api/ai"):
            q = (payload.get("q") or "").strip()
            if not q:
                self._json({"text": "пустой вопрос", "sources": []}, 400)
                return
            try:
                ans = ai.answer(self.mesh.ark, q, focus=self.mesh.node.focus, allow_general=True)
            except Exception as exc:
                ans = {"text": f"ошибка ИИ: {exc}", "sources": []}
            self._json(ans)
        elif self.path.startswith("/api/send"):
            peer, text = payload.get("peer", ""), (payload.get("text") or "").strip()
            if peer and text:
                self.chat.send(peer, text)
                self._json({"ok": True})
            else:
                self._json({"ok": False}, 400)
        else:
            self._json({"error": "not found"}, 404)

    def _me(self):
        stats = self.mesh.ark.stats()
        return {"id": self.mesh.node.node_id, "name": self.mesh.node.name,
                "focus": self.mesh.node.focus, "files": stats["files"], "bytes": stats["bytes"]}

    def _peers(self):
        contacts = {c["node_id"]: c for c in self.mesh.contacts.all()}
        known = {}
        for peer in self.mesh.peers():
            if peer["self"]:
                continue
            card = contacts.get(peer["node_id"], {})
            known[peer["node_id"]] = {"id": peer["node_id"], "name": peer["name"],
                                      "online": peer["age"] < 300, "level": card.get("level", ""),
                                      "focus": card.get("focus", ""), "seen": card.get("seen", 0)}
        return sorted(known.values(), key=lambda p: p["name"])


def serve(chat, mesh, host: str = "127.0.0.1", port: int = 8787):
    _Handler.chat = chat
    _Handler.mesh = mesh
    return ThreadingHTTPServer((host, port), _Handler)
