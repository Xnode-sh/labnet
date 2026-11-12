# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Local web chat (127.0.0.1 only) — touch-friendly interface for the phone."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>labnet — чат судного дня</title><style>
:root{--bg:#10141f;--fg:#e6edf5;--muted:#8b97ac;--me:#1f6feb;--r:12px}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.45 system-ui,sans-serif;display:flex;flex-direction:column;height:100vh}
header{padding:10px 14px;border-bottom:1px solid #223;display:flex;gap:10px;align-items:center}
select,#inp{background:#171e2d;color:var(--fg);border:1px solid #2a3550;border-radius:10px;padding:10px;font:inherit}
#log{flex:1;overflow:auto;padding:14px;display:flex;flex-direction:column;gap:8px}
.net{padding:8px 14px;display:flex;gap:8px;overflow-x:auto;border-bottom:1px solid #223}
.node{flex:0 0 auto;background:#171e2d;border:1px solid #2a3550;border-radius:10px;padding:7px 11px;font-size:13px;min-width:120px}
.node .n{font-weight:700}.node .f{color:var(--muted);font-size:11px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#3b4763;margin-right:6px}
.dot.on{background:#36e2ce}
.m{max-width:78%;padding:9px 12px;border-radius:var(--r);white-space:pre-wrap;word-break:break-word}
.in{align-self:flex-start;background:#1b2334}.out{align-self:flex-end;background:var(--me)}
.meta{font-size:11px;color:var(--muted);margin-top:3px}
footer{padding:10px;border-top:1px solid #223;display:flex;gap:8px}
#inp{flex:1}#send{padding:10px 16px;border:0;border-radius:10px;background:var(--me);color:#fff;font:inherit}
</style></head><body>
<header><b>🔥 labnet</b><select id="peer"></select><span id="status" class="meta"></span></header>
<div id="net" class="net"></div>
<div id="log"></div>
<footer><input id="inp" placeholder="сообщение…" autocomplete="off"><button id="send">→</button></footer>
<script>
let peer="",timer=null;
async function api(u,o){const r=await fetch(u,o);return r.json()}
async function loadPeers(){const d=await api('/api/peers');const s=document.getElementById('peer');
 s.innerHTML='';for(const p of d.peers){const o=document.createElement('option');o.value=p.id;
 o.textContent=p.name+(p.level?' · '+p.level:'')+(p.online?' 🟢':' ⚪');s.appendChild(o)}
 if(!peer&&d.peers[0]){peer=d.peers[0].id} s.value=peer;}
async function loadNet(){const d=await api('/api/network');const el=document.getElementById('net');
 let h='<div class="node"><div class="n"><span class="dot on"></span>'+d.me.name+'</div>'+
 '<div class="f">'+d.me.files+' знаний'+(d.me.focus?' · '+d.me.focus:'')+'</div></div>';
 for(const n of d.nodes){h+='<div class="node"><div class="n"><span class="dot'+(n.online?' on':'')+'"></span>'+
 n.name+'</div><div class="f">'+(n.focus||n.level||'—')+'</div></div>'}
 el.innerHTML=h;}
async function load(){if(!peer)return;const d=await api('/api/messages?peer='+encodeURIComponent(peer));
 const l=document.getElementById('log');l.innerHTML='';for(const m of d.messages){const e=document.createElement('div');
 e.className='m '+m.dir;e.textContent=m.text;l.appendChild(e)}l.scrollTop=l.scrollHeight;}
async function send(){const i=document.getElementById('inp');const t=i.value.trim();if(!t)return;
 await api('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({peer:peer,text:t})});i.value='';await load();}
document.getElementById('send').onclick=send;
document.getElementById('inp').addEventListener('keydown',e=>{if(e.key==='Enter')send()});
document.getElementById('peer').onchange=e=>{peer=e.target.value;load()};
(async function(){await loadNet();await loadPeers();await load();timer=setInterval(async()=>{await loadNet();await loadPeers();await load()},2000)})();
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    chat = None
    mesh = None

    def log_message(self, *args):  # silence default logging
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
        elif self.path.startswith("/api/peers"):
            self._json({"peers": self._peers()})
        elif self.path.startswith("/api/network"):
            self._json({"me": self._me(), "nodes": self._peers()})
        elif self.path.startswith("/api/messages"):
            peer = self._query("peer")
            self._json({"messages": self.chat.store.history(peer)})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path.startswith("/api/send"):
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                payload = {}
            peer, text = payload.get("peer", ""), payload.get("text", "").strip()
            if peer and text:
                self.chat.send(peer, text)
                self._json({"ok": True})
            else:
                self._json({"ok": False, "error": "peer/text empty"}, 400)
        else:
            self._json({"error": "not found"}, 404)

    def _query(self, key):
        from urllib.parse import parse_qs, urlparse
        values = parse_qs(urlparse(self.path).query)
        return (values.get(key) or [""])[0]

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
        for peer_id in self.chat.store.peers():
            known.setdefault(peer_id, {"id": peer_id, "name": peer_id[:8], "online": False,
                                       "level": "", "focus": "", "seen": 0})
        return sorted(known.values(), key=lambda p: p["name"])


def serve(chat, mesh, host: str = "127.0.0.1", port: int = 8787):
    _Handler.chat = chat
    _Handler.mesh = mesh
    server = ThreadingHTTPServer((host, port), _Handler)
    return server
