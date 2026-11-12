# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
"""Command line interface for labnet."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from . import crypto
from .crypto import LabnetError
from .node import Mesh
from .store import Labnet, config_root


def read_passphrase(prompt: str = "Пароль сети labnet: ") -> str:
    env = os.environ.get("LABNET_PASSPHRASE")
    if env is not None:
        return env
    if not sys.stdin.isatty():
        raise LabnetError("нет tty: задай LABNET_PASSPHRASE")
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


def _greet(mesh, peer_id, peer_card) -> None:
    from . import feedback
    try:
        feedback.greeting(peer_id)
    except Exception:
        pass
    nick = (peer_card or {}).get("nick", peer_id)
    level = (peer_card or {}).get("level", "?")
    print(f"🤝 знакомство: {nick} · уровень {level}")


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
            _greet(mesh, sess.peer_id, sess.peer_card)
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
    _greet(mesh, sess.peer_id, sess.peer_card)
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
            print(f"{manifest['name']:<32} {manifest['size']:>10} B{flag}")
    elif args.action == "put":
        if not args.first:
            raise LabnetError("нужен путь: ark put <file> [name]")
        manifest = ark.put_file(Path(args.first), args.name or args.second)
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
    ark.set_defaults(func=cmd_ark)

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
