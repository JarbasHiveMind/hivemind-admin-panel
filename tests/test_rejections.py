# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""/connections carries recent rejected connections with their reason."""
from hivemind_admin_panel import api


class _FakeProtocol:
    def __init__(self, rejections=None, raises=False):
        self.clients = {}
        self._rejections = rejections or []
        self._raises = raises
        self.max_age = None

    def get_recent_rejections(self, max_age=None):
        self.max_age = max_age
        if self._raises:
            raise RuntimeError("boom")
        return list(self._rejections)


def _with_protocol(proto):
    api.init_injected_objects(service=None, db=None, protocol=proto)


def test_rejections_listed_with_reason(client, auth):
    entry = {"time": 1.0, "peer": "sat::abc", "code": 1008,
             "reason": "invalid access key or password"}
    proto = _FakeProtocol([entry])
    _with_protocol(proto)
    try:
        body = client.get("/connections", headers=auth).json()
    finally:
        _with_protocol(None)
    assert body["recent_rejections"] == [entry]
    assert proto.max_age == api.REJECTION_WINDOW_SECONDS
    assert body["rejection_window_seconds"] == api.REJECTION_WINDOW_SECONDS


def test_core_without_ring_gives_empty_list(client, auth):
    class _OldCore:
        clients = {}
    _with_protocol(_OldCore())
    try:
        body = client.get("/connections", headers=auth).json()
    finally:
        _with_protocol(None)
    assert body["recent_rejections"] == []


def test_ring_error_does_not_break_connections(client, auth):
    _with_protocol(_FakeProtocol(raises=True))
    try:
        body = client.get("/connections", headers=auth).json()
    finally:
        _with_protocol(None)
    assert body["count"] == 0
    assert body["recent_rejections"] == []


def test_no_core_attached_has_empty_rejections(client, auth):
    body = client.get("/connections", headers=auth).json()
    assert body["recent_rejections"] == []


def test_rejections_need_credentials(client):
    assert client.get("/connections").status_code in (401, 403)
