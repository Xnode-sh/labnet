# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from labnet import crypto, discovery, feedback, profile, session
from labnet.crypto import LabnetError
from labnet.node import Mesh
from labnet.session import SessionError
from labnet.store import Labnet

PASSPHRASE = "сеть-лабы"


class MeshTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.share = base / "share"
        self.a = Labnet.create("freya", "redlab", self.share, root=base / "a")
        self.b = Labnet.create("acer", "redlab", self.share, root=base / "b")
        key = crypto.derive_net_key(PASSPHRASE, "redlab")
        self.ma = Mesh(self.a, key)
        self.mb = Mesh(self.b, key)

    def tearDown(self):
        self.tmp.cleanup()

    def test_identity_persist(self):
        reloaded = Labnet.load(root=self.a.root)
        self.assertEqual(reloaded.node_id, self.a.node_id)
        self.assertEqual(reloaded.name, "freya")

    def test_distinct_ids(self):
        self.assertNotEqual(self.a.node_id, self.b.node_id)

    def test_announce_and_peers(self):
        self.ma.announce()
        self.mb.announce()
        names = {p["name"] for p in self.ma.peers()}
        self.assertEqual(names, {"freya", "acer"})
        self.assertTrue(all(p["verified"] for p in self.ma.peers()))
        mine = [p for p in self.ma.peers() if p["self"]]
        self.assertEqual(len(mine), 1)

    def test_send_recv_roundtrip(self):
        self.ma.announce()
        self.mb.announce()
        delivered = self.ma.send("acer", "привет из лаборатории")
        self.assertEqual(delivered, ["acer"])
        messages = self.mb.recv()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["from"], "freya")
        self.assertEqual(messages[0]["text"], "привет из лаборатории")

    def test_broadcast(self):
        self.a_third = Labnet.create("lira", "redlab", self.share, root=Path(self.tmp.name) / "c")
        mc = Mesh(self.a_third, crypto.derive_net_key(PASSPHRASE, "redlab"))
        for m in (self.ma, self.mb, mc):
            m.announce()
        delivered = self.ma.send("all", "всем привет")
        self.assertEqual(set(delivered), {"acer", "lira"})
        self.assertEqual(self.mb.recv()[0]["text"], "всем привет")

    def test_recv_is_consumed_once(self):
        self.mb.announce()
        self.ma.send("acer", "один раз")
        self.assertEqual(len(self.mb.recv()), 1)
        self.assertEqual(self.mb.recv(), [])

    def test_forged_signature_rejected(self):
        self.ma.announce()
        self.mb.announce()
        self.ma.send("acer", "секрет")
        inbox = self.share / "redlab" / "inbox" / self.b.node_id
        envelope_path = next(inbox.glob("*.json"))
        envelope = json.loads(envelope_path.read_text())
        envelope["ct"] = crypto.b64e(bytes(40))
        envelope_path.write_text(json.dumps(envelope))
        messages = self.mb.recv()
        self.assertEqual(messages[0]["type"], "error")

    def test_wrong_net_key_cannot_open(self):
        other = Labnet.create("intruder", "redlab", self.share, root=Path(self.tmp.name) / "x")
        mi = Mesh(other, crypto.derive_net_key("другой-пароль", "redlab"))
        self.mb.announce()
        mi.announce()
        mi.send("acer", "чужой")
        messages = self.mb.recv()
        self.assertEqual(messages[0]["type"], "error")
        self.assertIn("не расшифровано", messages[0]["text"])

    def test_unknown_peer(self):
        with self.assertRaises(LabnetError):
            self.ma.send("призрак", "ау")

    def test_ping_pong_flow(self):
        self.ma.announce()
        self.mb.announce()
        token = "ping-token"
        self.ma.send("acer", token, kind="ping")
        self.assertEqual(self.mb.serve_pings(), 1)
        pongs = [m for m in self.ma.recv() if m["type"] == "pong"]
        self.assertEqual(len(pongs), 1)
        self.assertEqual(pongs[0]["text"], token)


class StoreForwardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.share = base / "share"
        key = crypto.derive_net_key(PASSPHRASE, "redlab")
        self.a = Mesh(Labnet.create("freya", "redlab", self.share, root=base / "a"), key)
        self.b = Mesh(Labnet.create("acer", "redlab", self.share, root=base / "b"), key)

    def tearDown(self):
        self.tmp.cleanup()

    def test_outbox_pending_until_ack(self):
        self.a.announce()
        self.b.announce()
        self.a.send("acer", "на связи?")
        self.assertEqual(self.a.outbox.size(), 1)
        self.b.recv()
        self.a.recv()
        self.assertEqual(self.a.outbox.size(), 0)

    def test_dedup_same_envelope(self):
        self.a.announce()
        self.b.announce()
        self.a.send("acer", "один")
        env = self.a.outbox.pending()[0]
        self.a.transport.deliver(self.b.node.node_id, env)
        messages = self.b.recv()
        self.assertEqual(len(messages), 1)

    def test_relay_multi_hop(self):
        self.a.announce()
        self.b.announce()
        c = Mesh(Labnet.create("lira", "redlab", self.share, root=Path(self.tmp.name) / "c"),
                 crypto.derive_net_key(PASSPHRASE, "redlab"))
        envelope = self.a._seal(c.node.node_id, self.a._payload("text", "для LIRA через ACER"))
        self.a.transport.deliver(self.b.node.node_id, envelope)
        self.b.recv()
        self.assertEqual(self.b.relay.size(), 1)
        c.announce()
        self.assertEqual(self.b.forward(), 1)
        messages = c.recv()
        self.assertEqual(messages[0]["text"], "для LIRA через ACER")
        self.assertEqual(messages[0]["from"], "freya")

    def test_relay_respects_ttl(self):
        self.a.announce()
        self.b.announce()
        c = Mesh(Labnet.create("lira", "redlab", self.share, root=Path(self.tmp.name) / "d"),
                 crypto.derive_net_key(PASSPHRASE, "redlab"))
        envelope = self.a._seal(c.node.node_id, self.a._payload("text", "умрёт в пути"), ttl=1)
        self.a.transport.deliver(self.b.node.node_id, envelope)
        self.b.recv()
        self.assertEqual(self.b.relay.size(), 0)

    def test_send_via_delivers_to_relay(self):
        self.a.announce()
        self.b.announce()
        c = Mesh(Labnet.create("lira", "redlab", self.share, root=Path(self.tmp.name) / "e"),
                 crypto.derive_net_key(PASSPHRASE, "redlab"))
        c.announce()
        self.a.send("lira", "через посредника", via="acer")
        self.b.recv()
        self.assertEqual(c.recv()[0]["text"], "через посредника")


class ProfileTest(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(profile.compute_level({"bytes": 0}), "Новичок")
        self.assertEqual(profile.compute_level({"bytes": 2_000_000}), "Знаток")
        self.assertEqual(profile.compute_level({"bytes": 50_000_000}), "Хранитель")
        self.assertEqual(profile.compute_level({"bytes": 500_000_000}), "Архивариус")

    def test_haptic_deterministic_and_unique(self):
        self.assertEqual(profile.haptic_of("abc"), profile.haptic_of("abc"))
        self.assertNotEqual(profile.haptic_of("abc"), profile.haptic_of("abd"))
        self.assertEqual(len(profile.haptic_of("abc")), 3)
        self.assertTrue(all(80 <= v <= 240 for v in profile.haptic_of("abc")))

    def test_card_roundtrip(self):
        tmp = tempfile.TemporaryDirectory()
        node = Labnet.create("freya", "redlab", Path(tmp.name) / "share", root=Path(tmp.name) / "n")
        card = profile.build_card(node, role="engineering")
        self.assertEqual(card["nick"], "freya")
        self.assertEqual(card["role"], "engineering")
        self.assertTrue(profile.verify_card(card))
        tampered = dict(card, role="hacked")
        self.assertFalse(profile.verify_card(tampered))
        tmp.cleanup()


class FeedbackTest(unittest.TestCase):
    def test_pulse_sequence(self):
        calls = []
        count = feedback.pulse([100, 200], runner=lambda argv: calls.append(argv), sleeper=lambda _s: None)
        self.assertEqual(count, 2)
        self.assertEqual(calls, [["termux-vibrate", "-d", "100"], ["termux-vibrate", "-d", "200"]])

    def test_greeting_uses_node_pattern(self):
        calls = []
        feedback.greeting("node-x", runner=lambda argv: calls.append(argv), sleeper=lambda _s: None)
        self.assertEqual([c[2] for c in calls], [str(v) for v in profile.haptic_of("node-x")])


class DiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.a = Labnet.create("freya", "redlab", base / "s", root=base / "a")
        self.b = Labnet.create("acer", "redlab", base / "s", root=base / "b")

    def tearDown(self):
        self.tmp.cleanup()

    def test_beacon_verify_and_tamper(self):
        beacon = discovery.build_beacon(self.a, 47112)
        self.assertTrue(discovery.verify_beacon(beacon, "redlab"))
        self.assertFalse(discovery.verify_beacon(beacon, "other"))
        self.assertFalse(discovery.verify_beacon(dict(beacon, tcp_port=1), "redlab"))

    def test_unattended_discovery(self):
        port = 47311
        disc = discovery.Discovery(Mesh(self.b, crypto.derive_net_key(PASSPHRASE, "redlab")), 5000, port=port)
        recv_sock = discovery.open_socket(port)
        try:
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            beacon = discovery.build_beacon(self.a, 47112)
            send_sock.sendto(json.dumps(beacon).encode(), ("127.0.0.1", port))
            found = disc.listen_once(recv_sock, timeout=1.0)
            send_sock.close()
        finally:
            recv_sock.close()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["node_id"], self.a.node_id)


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.share = base / "share"
        self.a = Mesh(Labnet.create("freya", "redlab", self.share, root=base / "a"),
                      crypto.derive_net_key(PASSPHRASE, "redlab"))
        self.b = Mesh(Labnet.create("acer", "redlab", self.share, root=base / "b"),
                      crypto.derive_net_key(PASSPHRASE, "redlab"))

    def tearDown(self):
        self.tmp.cleanup()

    def _listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return sock, sock.getsockname()[1]

    def test_handshake_and_socket_sync(self):
        self.a.announce()
        self.b.announce()
        self.a.send("acer", "привет по сессии")
        listener, port = self._listener()
        captured = {}

        def server():
            sess = session.serve_once(listener, self.b, self.b.card())
            captured["card"] = sess.peer_card
            captured["messages"] = sess.sync()
            sess.close()

        thread = threading.Thread(target=server)
        thread.start()
        sess = session.connect("127.0.0.1", port, self.a, self.a.card())
        self.assertTrue(session.verify_peer_card(sess.peer_card))
        self.assertEqual(sess.peer_card["nick"], "acer")
        sess.sync()
        sess.close()
        thread.join(timeout=5)
        listener.close()
        self.assertEqual(captured["messages"][0]["text"], "привет по сессии")

    def test_wrong_network_key_rejected(self):
        self.a.announce()
        self.b.announce()
        listener, port = self._listener()
        errors = {}

        def server():
            try:
                sess = session.serve_once(listener, self.b, self.b.card())
                sess.sync()
                sess.close()
            except (SessionError, OSError) as exc:
                errors["server"] = str(exc)

        thread = threading.Thread(target=server)
        thread.start()
        intruder = Mesh(self.a.node, crypto.derive_net_key("другой-пароль", "redlab"))
        with self.assertRaises(SessionError):
            session.connect("127.0.0.1", port, intruder, self.a.card())
        thread.join(timeout=5)
        listener.close()
        self.assertIn("server", errors)


class CryptoTest(unittest.TestCase):
    def test_net_key_deterministic(self):
        self.assertEqual(
            crypto.derive_net_key(PASSPHRASE, "redlab"),
            crypto.derive_net_key(PASSPHRASE, "redlab"),
        )

    def test_net_key_differs_by_net(self):
        self.assertNotEqual(
            crypto.derive_net_key(PASSPHRASE, "redlab"),
            crypto.derive_net_key(PASSPHRASE, "other"),
        )

    def test_encrypt_decrypt(self):
        key = crypto.derive_net_key(PASSPHRASE, "redlab")
        secret = "секрет".encode("utf-8")
        blob = crypto.encrypt(key, secret, b"aad")
        self.assertNotIn(secret, blob)
        self.assertEqual(crypto.decrypt(key, blob, b"aad"), secret)

    def test_sign_verify(self):
        identity = crypto.NodeIdentity.generate()
        data = crypto.canonical({"a": 1, "b": "текст"})
        self.assertTrue(crypto.NodeIdentity.verify(identity.to_dict()["pub"], data, identity.sign(data)))
        self.assertFalse(crypto.NodeIdentity.verify(identity.to_dict()["pub"], data + b"x", identity.sign(data)))


if __name__ == "__main__":
    unittest.main()
