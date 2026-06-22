# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: connections and stats introspection."""


def test_connections_degrades_without_protocol(client, auth):
    body = client.get("/connections", headers=auth).json()
    assert "count" in body
    assert "connections" in body


def test_stats_shape(client, auth):
    body = client.get("/stats", headers=auth).json()
    assert "network_protocols" in body
    assert "agent_protocol" in body
    assert "binarize" in body


def test_stats_counts_clients(client, auth, make_client):
    make_client(name="stat-sat")
    body = client.get("/stats", headers=auth).json()
    # with an injected DB, stats expose a client count key
    assert any(k in body for k in ("client_count", "total_clients"))
