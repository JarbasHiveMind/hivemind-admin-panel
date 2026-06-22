# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Unit: the protocol tap injects the live protocol + records messages.

Uses a fake base protocol so no real hub is started.
"""
import hivemind_admin_panel.api as api
from hivemind_admin_panel._metrics import METRICS
from hivemind_admin_panel.__main__ import _tracked_protocol


class _FakeBaseProtocol:
    def __init__(self, **kw):
        self.clients = {}

    def handle_new_client(self, client):
        self.clients[client.peer] = client

    def handle_client_disconnected(self, client):
        self.clients.pop(client.peer, None)

    def handle_message(self, message, client):
        return "handled"


class _FakeService:
    db = object()


class _Peer:
    def __init__(self, peer):
        self.peer = peer


class _Msg:
    def __init__(self, t):
        self.msg_type = t


def test_tracked_protocol_injects_and_taps():
    Tracked = _tracked_protocol(_FakeBaseProtocol, _FakeService())
    proto = Tracked()
    # live protocol is now injected into the admin globals -> authoritative
    assert api._protocol is proto

    proto.handle_new_client(_Peer("tcp4:1.2.3.4"))
    assert "tcp4:1.2.3.4" in proto.clients

    before = len(METRICS.recent_messages(limit=1000))
    assert proto.handle_message(_Msg("recognizer_loop:utterance"), _Peer("tcp4:1.2.3.4")) == "handled"
    msgs = METRICS.recent_messages(limit=1000)
    assert len(msgs) == before + 1
    assert msgs[-1]["msg_type"] == "recognizer_loop:utterance"

    api.init_injected_objects(service=None, db=None, protocol=None)


def test_messages_endpoint(client, auth):
    METRICS.message("speak", "tcp4:9.9.9.9")
    body = client.get("/messages/recent?limit=10", headers=auth).json()
    assert isinstance(body, list)
    assert any(m["msg_type"] == "speak" for m in body)
    # filter works
    filtered = client.get("/messages/recent?msg_type=speak", headers=auth).json()
    assert all(m["msg_type"] == "speak" for m in filtered)
