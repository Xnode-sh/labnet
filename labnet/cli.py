# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Command line interface for labnet."""
from __future__ import annotations

import argparse
import getpass
import json
import shutil
import os
import sys
import time
from pathlib import Path

from . import crypto, store
from .crypto import LabnetError
from .node import Mesh
from .store import Labnet, config_root


def read_passphrase(prompt: str = "Пароль сети labnet: ") -> str:
    env = os.environ.get("LABNET_PASSPHRASE")
    if env is not None:
        return env
    stored = store.load_passphrase()
    if stored is not None:
        return stored
    if not sys.stdin.isatty():
        raise LabnetError("нет tty: задай LABNET_PASSPHRASE или `labnet key set`")
    return getpass.getpass(prompt)


def _share(args) -> Path | None:
    return Path(args.share).expanduser() if getattr(args, "share", None) else None


def _mesh(args) -> Mesh:
    node = Labnet.load(share=_share(args))
    return Mesh(node, crypto.derive_net_key(read_passphrase(), node.net))


def cmd_init(args) -> int:
    share = _share(args) or (config_root() / "share")
    node = Labnet.create(args.name, args.net, share)
    print(f"узел создан: {node.name} ({node.node_id})")
    print(f"сеть: {node.net}   канал: {node.channel}")
    print("не забудь `labnet announce` и ту же пару (net, пароль) на других узлах")
    return 0


def cmd_announce(args) -> int:
    entry = _mesh(args).announce()
    print(f"объявлен: {entry['name']} ({entry['node_id']}) @ {entry['host']}")
    return 0


def cmd_peers(args) -> int:
    peers = _mesh(args).peers()
    if args.json:
        print(json.dumps(peers, ensure_ascii=False, indent=2))
        return 0
    if not peers:
        print("(никого: узлы не объявлялись)")
        return 0
    width = max(len(p["name"]) for p in peers)
    for peer in peers:
        mark = "*" if peer["self"] else (" " if peer["verified"] else "!")
        print(f"{mark} {peer['name']:<{width}}  {peer['node_id']}  {peer['age']:>6}s  {peer['host']}")
    print("* ты · ! подпись не подтверждена")
    return 0


def cmd_send(args) -> int:
    delivered = _mesh(args).send(args.target, " ".join(args.text))
    print("доставлено: " + ", ".join(delivered) if delivered else "некому доставлять")
    return 0


def cmd_queue(args) -> int:
    mesh = _mesh(args)
    pending = mesh.outbox.pending()
    relay = mesh.relay.all()
    if args.json:
        print(json.dumps({"pending": pending, "relay": relay}, ensure_ascii=False, indent=2))
        return 0
    print(f"в очереди (ждут ack): {len(pending)}")
    print(f"на пересылку (relay): {len(relay)}")
    return 0


def cmd_flush(args) -> int:
    mesh = _mesh(args)
    sent = mesh.redeliver()
    relayed = mesh.forward()
    print(f"повторно отправлено: {sent}, переслано: {relayed}")
    return 0


def cmd_recv(args) -> int:
    messages = _mesh(args).recv()
    if args.json:
        print(json.dumps(messages, ensure_ascii=False, indent=2))
        return 0
    if not messages:
        print("(пусто)")
        return 0
    for message in messages:
        print(f"[{message['type']}] {message['from']}: {message['text']}")
    return 0


def cmd_ping(args) -> int:
    rtt = _mesh(args).ping(args.peer, timeout=args.timeout)
    if rtt is None:
        print(f"нет ответа от {args.peer} за {args.timeout}s")
        return 1
    print(f"pong от {args.peer}: {rtt}s")
    return 0


def cmd_serve(args) -> int:
    answered = _mesh(args).serve_pings()
    print(f"отвечено на ping: {answered}")
    return 0


def cmd_whoami(args) -> int:
    node = Labnet.load(share=_share(args))
    print(json.dumps({
        "name": node.name, "node_id": node.node_id, "net": node.net,
        "channel": str(node.channel), "config": str(node.root),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_card(args) -> int:
    mesh = _mesh(args)
    card = mesh.card(role=args.role)
    print(json.dumps(card, ensure_ascii=False, indent=2))
    return 0


def cmd_discover(args) -> int:
    from . import discovery
    mesh = _mesh(args)
    sock = discovery.open_socket(args.port)
    disc = discovery.Discovery(mesh, args.tcp_port, args.port)
    try:
        disc.announce(sock)
        found = disc.listen_once(sock, timeout=args.seconds)
    finally:
        sock.close()
    for beacon in found:
        print(f"{beacon['addr']}:{beacon['tcp_port']}  {beacon['node_id']}  ({beacon['nonce'][:8]})")
    if not found:
        print("(никого рядом)")
    return 0


def _greet(mesh, peer_id, peer_card, meet_status=None) -> None:
    from . import feedback
    label = {"new": "новый знакомый", "known": "свой", "changed": "⚠ ключ узла сменился"}.get(meet_status)
    try:
        if meet_status in ("new", "changed"):
            feedback.event("new_peer" if meet_status == "new" else "alert")
        else:
            feedback.greeting(peer_id)
    except Exception:
        pass
    nick = (peer_card or {}).get("nick", peer_id)
    level = (peer_card or {}).get("level", "?")
    focus = (peer_card or {}).get("focus", "")
    suffix = f" · {label}" if label else ""
    skill = f" · спец: {focus}" if focus else ""
    print(f"🤝 знакомство: {nick} · уровень {level}{skill}{suffix}")


def cmd_listen(args) -> int:
    import socket
    from . import session
    mesh = _mesh(args)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("0.0.0.0", args.port))
    listener.listen(4)
    print(f"слушаю сессии на порту {args.port} (Ctrl-C для выхода)")
    try:
        while True:
            sess = session.serve_once(listener, mesh, mesh.card())
            _greet(mesh, sess.peer_id, sess.peer_card, sess.meet_status)
            for message in sess.sync():
                print(f"[{message['type']}] {message['from']}: {message['text']}")
            sess.close()
    except KeyboardInterrupt:
        return 0
    finally:
        listener.close()


def cmd_connect(args) -> int:
    from . import session
    host, _, port = args.target.partition(":")
    mesh = _mesh(args)
    sess = session.connect(host, int(port or 47112), mesh, mesh.card())
    _greet(mesh, sess.peer_id, sess.peer_card, sess.meet_status)
    for message in sess.sync():
        print(f"[{message['type']}] {message['from']}: {message['text']}")
    sess.close()
    return 0


def cmd_ark(args) -> int:
    mesh = _mesh(args)
    ark = mesh.ark
    if args.action == "stats":
        print(json.dumps(ark.stats(), ensure_ascii=False, indent=2))
    elif args.action == "list":
        for manifest in ark.manifests():
            missing = len(ark.missing(manifest))
            flag = "" if missing == 0 else f"  (нет {missing} чанков)"
            by = f"  {manifest.get('by')}" if manifest.get("by") else ""
            topic = f"  #{manifest['topic']}" if manifest.get("topic") else ""
            print(f"{manifest['name']:<32} {manifest['size']:>10} B{by}{topic}{flag}")
    elif args.action == "put":
        if not args.first:
            raise LabnetError("нужен путь: ark put <file> [name]")
        manifest = ark.put_file(Path(args.first), args.name or args.second, by=mesh.node.name,
                                topic=(args.topic or ""))
        print(f"в Ковчег: {manifest['name']}  ({len(manifest['chunks'])} чанков, {manifest['size']} B)")
    elif args.action == "get":
        name = args.name or args.first
        if not name:
            raise LabnetError("нужно имя: ark get <name> [out]")
        ok = ark.get_file(name, Path(args.out or args.second or name))
        print("извлечено" if ok else "нет такого файла или не хватает чанков")
        return 0 if ok else 1
    else:
        raise LabnetError(f"неизвестное действие: {args.action}")
    return 0


def cmd_chat(args) -> int:
    from .chat import Chat
    mesh = _mesh(args)
    chat = Chat(mesh, mesh.net_key)
    peer = args.peer
    print("labnet чат · /peer <имя> — выбрать собеседника · /quit — выход")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("/quit", "/exit"):
            return 0
        if line.startswith("/peer "):
            peer = line[6:].strip()
            print("собеседник:", peer)
            continue
        for message in chat.poll():
            print(f"[{message.get('from')}] {message.get('text')}")
        if not peer:
            print("выбери собеседника: /peer <имя>")
            continue
        try:
            delivered = chat.send(peer, line)
            print("отправлено:", ", ".join(delivered))
        except LabnetError as exc:
            print("ошибка:", exc)


def cmd_web(args) -> int:
    import shutil
    import subprocess
    import threading
    from . import web
    from .chat import Chat
    mesh = _mesh(args)
    chat = Chat(mesh, mesh.net_key)
    server = web.serve(chat, mesh, port=args.port)
    url = f"http://127.0.0.1:{args.port}/"
    print("чат открыт:", url)
    if not args.no_open and shutil.which("termux-open-url"):
        subprocess.run(["termux-open-url", url], capture_output=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        while True:
            chat.poll()
            time.sleep(2)
    except KeyboardInterrupt:
        return 0
    finally:
        server.shutdown()


def cmd_contacts(args) -> int:
    mesh = _mesh(args)
    contacts = mesh.contacts.all()
    if args.json:
        print(json.dumps(contacts, ensure_ascii=False, indent=2))
        return 0
    if not contacts:
        print("(знакомых пока нет)")
        return 0
    width = max(len(c.get("name", "")) for c in contacts)
    for c in contacts:
        changed = "  ⚠ ключ сменился" if c.get("changed_at") else ""
        print(f"{c.get('name', ''):<{width}}  {c['node_id']}  виделись {c.get('seen', 1)}  {c.get('level', '')}{changed}")
    return 0


def cmd_daemon(args) -> int:
    from .daemon import Daemon
    mesh = _mesh(args)
    daemon = Daemon(mesh, tcp_port=args.tcp_port, udp_port=args.udp_port,
                    interval=args.interval, role=args.role, quiet=args.quiet)
    print(f"labnet демон: сеть {mesh.node.net}, порт сессий {args.tcp_port}, интервал {args.interval}s")
    daemon.run()
    return 0


def cmd_pack(args) -> int:
    from . import sneakernet
    mesh = _mesh(args)
    dest = sneakernet.pack(mesh, Path(args.out))
    print(f"носитель собран: {dest}")
    return 0


def cmd_unpack(args) -> int:
    from . import sneakernet
    mesh = _mesh(args)
    count = sneakernet.unpack(mesh, Path(args.path))
    print(f"носитель распакован; принято сообщений: {count}")
    return 0


def cmd_nfc(args) -> int:
    import subprocess
    if shutil.which("termux-nfc") is None:
        raise LabnetError("нет termux-nfc (нужно приложение Termux:API)")
    result = subprocess.run(["termux-nfc", *args.args], capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


def cmd_ask(args) -> int:
    from . import ai
    mesh = _mesh(args)
    question = " ".join(args.text)
    if ai.provider_available():
        print(f"(локальная модель: {ai.DEFAULT_MODEL})", file=sys.stderr)
    reply = ai.ask(mesh, args.peer, question, timeout=args.timeout)
    if reply is None:
        print("ответа нет (узел оффлайн или не отвечает)")
        return 1
    print(f"{reply.get('from')}: {reply.get('text')}")
    return 0


def cmd_serve_ai(args) -> int:
    from . import ai
    from .chat import Chat
    mesh = _mesh(args)
    chat = Chat(mesh, mesh.net_key)
    print(f"AI-узел готов (модель: {'ollama' if ai.provider_available() else 'только Ковчег'})")
    try:
        while True:
            for message in mesh.recv():
                if message.get("type") == "ask":
                    reply = ai.handle_ask(mesh.ark, message, focus=mesh.node.focus)
                    mesh.send(message.get("from"), reply, kind="reply")
                    print(f"→ {message.get('from')}: {reply[:100]}")
                elif message.get("type") in ("text", "reply"):
                    chat.store.append(message.get("from_id") or message.get("from", "?"),
                                      "in", message.get("text", ""), message.get("ts"))
                    print(f"[{message.get('from')}] {message.get('text')}")
            time.sleep(2)
    except KeyboardInterrupt:
        return 0


def cmd_key(args) -> int:
    import secrets
    from .store import keyring_path, save_passphrase
    if args.action == "set":
        passphrase = args.value or secrets.token_urlsafe(24)
        path = save_passphrase(passphrase)
        print(f"пароль сети сохранён (600): {path}")
        if not args.value:
            print("сгенерирован случайный пароль — скопируй net.pass на другие узлы, иначе они не зайдут")
        return 0
    if args.action == "where":
        print(keyring_path())
        return 0
    if args.action == "has":
        print("есть" if store.load_passphrase() else "нет")
        return 0
    raise LabnetError(f"неизвестное действие: {args.action}")


def cmd_focus(args) -> int:
    node = Labnet.load(share=_share(args))
    if args.value:
        node.set_focus(" ".join(args.value))
        print("специализация узла:", node.focus or "(сброшено)")
    else:
        print(node.focus or "(специализация не задана)")
    return 0


def cmd_asknet(args) -> int:
    from . import ai
    mesh = _mesh(args)
    result = ai.asknet(mesh, " ".join(args.text), timeout=args.timeout)
    if not result["answers"]:
        print(f"ответов нет (спросили узлов: {result['asked']})")
        return 1
    print(f"❓ {result['question']}")
    for answer in result["answers"]:
        star = "⭐ знает" if answer["useful"] else "·"
        spec = f" · спец: {answer['focus']}" if answer["focus"] else ""
        rep = f" · доверие {answer['rep']}" if answer["rep"] else ""
        print(f"\n{star}  {answer['from']}{spec}{rep}\n   {answer['text']}")
    return 0


def cmd_map(args) -> int:
    mesh = _mesh(args)
    node = mesh.node
    contacts = {c["node_id"]: c for c in mesh.contacts.all()}
    B = "\033[1m"
    D = "\033[2m"
    C = "\033[36m"
    G = "\033[32m"
    Y = "\033[33m"
    R = "\033[0m"
    stats = mesh.ark.stats()
    print(f"{C}╔═ СЕТЬ · {node.net} {'═' * max(1, 44 - len(node.net))}╗{R}")
    me_focus = node.focus or "—"
    print(f"{C}║{R} {G}● {node.name}{R}  {D}{node.node_id}{R}")
    print(f"{C}║{R}   специализация: {Y}{me_focus}{R}")
    print(f"{C}║{R}   знания: {stats['files']} записей · {stats['chunks']} чанков · {stats['bytes']} Б")
    print(f"{C}║{R}   queue: {mesh.outbox.size()} · relay: {mesh.relay.size()}")
    peers = [p for p in mesh.peers() if not p["self"]]
    print(f"{C}╠═ узлы рядом ({len(peers)}) {'═' * 32}╣{R}")
    if not peers:
        print(f"{C}║{R}   {D}пока никого — запусти демон или поднеси носитель{R}")
    for peer in peers:
        card = contacts.get(peer["node_id"], {})
        focus = card.get("focus", "")
        seen = card.get("seen", 0)
        mark = G + "●" + R if peer["age"] < 300 else Y + "◐" + R
        line = f"{mark} {peer['name']:<14} {D}{peer['node_id']}{R}"
        if focus:
            line += f"  {Y}{focus}{R}"
        rep = int(card.get("rep", 0))
        if rep:
            line += f"  {G}{'★' * min(rep, 5)}{R}"
        if seen:
            line += f"  {D}виделись {seen}{R}"
        print(f"{C}║{R} {line}")
    print(f"{C}╚{'═' * 54}╝{R}")
    return 0


def cmd_rep(args) -> int:
    mesh = _mesh(args)
    rows = mesh.contacts.ranked()
    if not rows:
        print("(знакомых пока нет)")
        return 0
    for record in rows:
        stars = "★" * min(int(record.get("rep", 0)), 5)
        focus = f"  {record.get('focus', '')}" if record.get("focus") else ""
        print(f"{stars:<5} {record.get('name', ''):<16} доверие {int(record.get('rep', 0)):>3}{focus}")
    return 0


def cmd_rate(args) -> int:
    mesh = _mesh(args)
    target = args.node
    node_id = target
    for record in mesh.contacts.all():
        if record.get("name") == target or record["node_id"] == target:
            node_id = record["node_id"]
            break
    new = mesh.contacts.bump(node_id, args.amount)
    if new == 0 and not any(r["node_id"] == node_id for r in mesh.contacts.all()):
        raise LabnetError(f"не знаю такого узла: {target}")
    print(f"доверие {target}: {new}")
    return 0


def cmd_ai_up(args) -> int:
    import subprocess
    import time as _t
    from . import ai
    if shutil.which("ollama") is None:
        print("нет ollama — ставлю…")
        subprocess.run(["pkg", "install", "-y", "ollama"])
    # сервер модели
    need = True
    try:
        if subprocess.run(["ollama", "list"], capture_output=True, timeout=5).returncode == 0:
            need = False
    except Exception:
        need = True
    if need:
        print("запускаю сервер модели (ollama serve) в фоне…")
        subprocess.run(["pkill", "-f", "ollama serve"], capture_output=True)
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        _t.sleep(5)
    print(f"качаю базовую модель {args.model} (первый раз — долго)…")
    subprocess.run(["ollama", "pull", args.model])
    # модель с персоной
    persona = ai.persona_text()
    mf = Path(os.environ.get("TMPDIR", "/data/data/com.termux/files/usr/tmp")) / "labnet-ark.Modelfile"
    mf.write_text(
        f'FROM {args.model}\n'
        'PARAMETER temperature 0.3\n'
        'PARAMETER num_ctx 4096\n'
        f'SYSTEM """{persona}"""\n',
        encoding="utf-8",
    )
    print("собираю модель 'ark' с персоной судного дня…")
    res = subprocess.run(["ollama", "create", "ark", "-f", str(mf)])
    if res.returncode != 0:
        print("не удалось создать модель ark — работаю на базовой:", args.model)
        ai.DEFAULT_MODEL = args.model
    else:
        ai.DEFAULT_MODEL = "ark"
        print("модель 'ark' готова (персона подключена).")
    print("ИИ-узел запущен. Отвечаю на вопросы сети.\n")
    return cmd_serve_ai(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="labnet", description="Приватная сеть поверх своего канала (без root)")
    parser.add_argument("--share", help="каталог-канал (по умолчанию из конфига)")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="создать узел")
    init.add_argument("--name", required=True)
    init.add_argument("--net", default="redlab")
    init.set_defaults(func=cmd_init)

    sub.add_parser("announce", help="опубликовать себя в roster").set_defaults(func=cmd_announce)

    peers = sub.add_parser("peers", help="список узлов сети")
    peers.add_argument("--json", action="store_true")
    peers.set_defaults(func=cmd_peers)

    send = sub.add_parser("send", help="отправить сообщение узлу (имя / id / all)")
    send.add_argument("target")
    send.add_argument("text", nargs="+")
    send.set_defaults(func=cmd_send)

    recv = sub.add_parser("recv", help="принять сообщения")
    recv.add_argument("--json", action="store_true")
    recv.set_defaults(func=cmd_recv)

    ping = sub.add_parser("ping", help="проверить узел")
    ping.add_argument("peer")
    ping.add_argument("--timeout", type=float, default=5.0)
    ping.set_defaults(func=cmd_ping)

    sub.add_parser("serve", help="ответить на входящие ping").set_defaults(func=cmd_serve)

    queue = sub.add_parser("queue", help="показать очередь и relay")
    queue.add_argument("--json", action="store_true")
    queue.set_defaults(func=cmd_queue)

    sub.add_parser("flush", help="повторить отправку и пересылку").set_defaults(func=cmd_flush)

    card = sub.add_parser("card", help="показать свою визитку")
    card.add_argument("--role", default="node")
    card.set_defaults(func=cmd_card)

    discover = sub.add_parser("discover", help="поискать узлы в локальной сети")
    discover.add_argument("--seconds", type=float, default=3.0)
    discover.add_argument("--port", type=int, default=47111)
    discover.add_argument("--tcp-port", type=int, default=47112)
    discover.set_defaults(func=cmd_discover)

    listen = sub.add_parser("listen", help="принимать сессии")
    listen.add_argument("--port", type=int, default=47112)
    listen.set_defaults(func=cmd_listen)

    connect = sub.add_parser("connect", help="подключиться к узлу HOST[:PORT]")
    connect.add_argument("target")
    connect.set_defaults(func=cmd_connect)

    ark = sub.add_parser("ark", help="Ковчег: обмен знаниями и файлами")
    ark.add_argument("action", choices=["list", "stats", "put", "get"])
    ark.add_argument("first", nargs="?")
    ark.add_argument("second", nargs="?")
    ark.add_argument("-n", "--name")
    ark.add_argument("-o", "--out")
    ark.add_argument("-t", "--topic")
    ark.set_defaults(func=cmd_ark)

    chat = sub.add_parser("chat", help="чат в терминале")
    chat.add_argument("--peer")
    chat.set_defaults(func=cmd_chat)

    web = sub.add_parser("web", help="локальный веб-чат (телефон)")
    web.add_argument("--port", type=int, default=8787)
    web.add_argument("--no-open", action="store_true")
    web.set_defaults(func=cmd_web)

    contacts = sub.add_parser("contacts", help="знакомые узлы (TOFU)")
    contacts.add_argument("--json", action="store_true")
    contacts.set_defaults(func=cmd_contacts)

    daemon = sub.add_parser("daemon", help="фоновый режим: искать, знакомить, синкать")
    daemon.add_argument("--tcp-port", type=int, default=47112)
    daemon.add_argument("--udp-port", type=int, default=47111)
    daemon.add_argument("--interval", type=float, default=20.0)
    daemon.add_argument("--role", default="node")
    daemon.add_argument("--quiet", action="store_true")
    daemon.set_defaults(func=cmd_daemon)

    focus = sub.add_parser("focus", help="специализация узла (чему он учит сеть)")
    focus.add_argument("value", nargs="*")
    focus.set_defaults(func=cmd_focus)

    asknet = sub.add_parser("asknet", help="спросить всю сеть (выберет специалиста)")
    asknet.add_argument("text", nargs="+")
    asknet.add_argument("--timeout", type=float, default=12.0)
    asknet.set_defaults(func=cmd_asknet)

    sub.add_parser("map", help="карта сети: узлы, специализации, знания").set_defaults(func=cmd_map)

    sub.add_parser("rep", help="репутация знакомых узлов").set_defaults(func=cmd_rep)

    rate = sub.add_parser("rate", help="оценить узел (доверие)")
    rate.add_argument("node")
    rate.add_argument("amount", type=int, nargs="?", default=1)
    rate.set_defaults(func=cmd_rate)

    pack = sub.add_parser("pack", help="собрать носитель (sneakernet)")
    pack.add_argument("out")
    pack.set_defaults(func=cmd_pack)

    unpack = sub.add_parser("unpack", help="распаковать носитель")
    unpack.add_argument("path")
    unpack.set_defaults(func=cmd_unpack)

    nfc = sub.add_parser("nfc", help="NFC-токен (аргументы идут в termux-nfc)")
    nfc.add_argument("args", nargs=argparse.REMAINDER)
    nfc.set_defaults(func=cmd_nfc)

    ask = sub.add_parser("ask", help="спросить узел (ИИ/Ковчег)")
    ask.add_argument("peer")
    ask.add_argument("text", nargs="+")
    ask.add_argument("--timeout", type=float, default=10.0)
    ask.set_defaults(func=cmd_ask)

    sub.add_parser("serve-ai", help="отвечать на вопросы (ИИ/Ковчег)").set_defaults(func=cmd_serve_ai)

    aiup = sub.add_parser("ai-up", help="поднять ИИ-узел: ollama + модель + ответы")
    aiup.add_argument("--model", default="qwen2.5:0.5b")
    aiup.set_defaults(func=cmd_ai_up)

    key = sub.add_parser("key", help="ключ сети (автономный режим)")
    key.add_argument("action", choices=["set", "where", "has"])
    key.add_argument("value", nargs="?")
    key.set_defaults(func=cmd_key)

    sub.add_parser("whoami", help="кто я").set_defaults(func=cmd_whoami)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except LabnetError as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("", file=sys.stderr)
        return 130
