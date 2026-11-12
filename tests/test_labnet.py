# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Xnode-sh — RED └•TEAM•┐ lab™
import json
import tempfile
import unittest
from pathlib import Path

from labnet import crypto
from labnet.crypto import LabnetError
from labnet.node import Mesh
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
