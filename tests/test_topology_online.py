# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Unit: /topology marks a live connection online.

`HiveMindListenerProtocol.clients` is keyed by the peer address of the
connection. The access key is the `key` attribute of the connection object,
the same field that /connections reports.
"""
import pytest

import hivemind_admin_panel.api as api


class _Sess:
    session_id = "sess-1"


class _Conn:
    """The shape of a real live connection record."""

    def __init__(self, peer, key):
        self.peer = peer
        self.key = key
        self.sess = _Sess()
        self.is_authenticated = True


class _Protocol:
    def __init__(self, conns):
        # keyed by peer, as hivemind-core does it
        self.clients = {c.peer: c for c in conns}


@pytest.fixture
def live_protocol():
    """Inject a fake live protocol, and remove it after the test."""
    injected = []

    def _inject(*conns):
        proto = _Protocol(conns)
        api.init_injected_objects(protocol=proto)
        injected.append(proto)
        return proto

    yield _inject
    api.init_injected_objects(service=None, db=None, protocol=None)


def test_topology_marks_a_connected_client_online(client, auth, make_client, live_protocol):
    sat = make_client(name="garage")
    other = make_client(name="kitchen")
    live_protocol(_Conn("tcp4:10.0.0.9:41000", sat["api_key"]))

    body = client.get("/topology", headers=auth).json()
    nodes = {n["label"]: n for n in body["nodes"] if n["type"] != "core"}
    assert nodes["garage"]["online"] is True
    assert nodes["kitchen"]["online"] is False
    assert body["online_count"] == 1
    assert other["api_key"] != sat["api_key"]


def test_topology_agrees_with_connections(client, auth, make_client, live_protocol):
    sat = make_client(name="hall")
    live_protocol(_Conn("tcp4:10.0.0.8:41000", sat["api_key"]))

    conns = client.get("/connections", headers=auth).json()["connections"]
    online_labels = {n["label"] for n in client.get("/topology", headers=auth).json()["nodes"]
                     if n["type"] != "core" and n["online"]}
    assert [c["key"] for c in conns] == [sat["api_key"]]
    assert online_labels == {"hall"}


def test_topology_does_not_match_the_peer_address(client, auth, make_client, live_protocol):
    """A peer address must never count as an access key."""
    sat = make_client(name="ghost")
    live_protocol(_Conn(str(sat["api_key"]), "some-other-key"))

    body = client.get("/topology", headers=auth).json()
    node = next(n for n in body["nodes"] if n["label"] == "ghost")
    assert node["online"] is False
    assert body["online_count"] == 0
