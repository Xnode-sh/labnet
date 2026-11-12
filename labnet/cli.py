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
