# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: OVOS message-bus connectivity probe (sockets stubbed).

The endpoint opens a raw TCP socket (``socket.socket().connect_ex``) and, if the
port is open, attempts a websocket handshake (``create_connection``). Both are
stubbed so the test never touches the network.
"""
import types

import hivemind_admin_panel.api as api


class _FakeSocket:
    """Stand-in for socket.socket() used as a context manager."""
    def __init__(self, connect_result):
        self._result = connect_result

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def settimeout(self, _):
        pass

    def connect_ex(self, _addr):
        return self._result  # 0 == open


def _fake_socket_module(connect_result):
    # replace api.socket wholesale so the real stdlib socket (used by asyncio /
    # TestClient) is untouched.
    return types.SimpleNamespace(
        AF_INET=0,
        SOCK_STREAM=0,
        socket=lambda *a, **kw: _FakeSocket(connect_result),
    )


def test_bus_unreachable_reports_failure(client, auth, monkeypatch):
    monkeypatch.setattr(api, "socket", _fake_socket_module(1))  # port closed
    body = client.get("/ovos/test-bus", params={"host": "127.0.0.1", "port": 8181}, headers=auth).json()
    assert body["success"] is False


def test_bus_reachable_reports_success(client, auth, monkeypatch):
    class _WS:
        def close(self):
            pass

    monkeypatch.setattr(api, "socket", _fake_socket_module(0))  # port open
    monkeypatch.setattr(api, "create_connection", lambda *a, **kw: _WS())
    body = client.get("/ovos/test-bus", params={"host": "127.0.0.1", "port": 8181}, headers=auth).json()
    assert body["success"] is True
