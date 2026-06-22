# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: topology graph, pairing QR, SSE query-token auth."""
from tests.conftest import ADMIN_USER, ADMIN_PASS


def test_topology_includes_core_and_clients(client, auth, make_client):
    make_client(name="topo-sat")
    g = client.get("/topology", headers=auth).json()
    assert any(n["id"] == "core" for n in g["nodes"])
    assert any(n["label"] == "topo-sat" for n in g["nodes"])
    # every client node is linked to hivemind-core
    client_nodes = [n for n in g["nodes"] if n["type"] != "core"]
    assert len(g["edges"]) == len(client_nodes)


def test_pairing_qr_svg(client, auth, make_client):
    c = make_client(name="qr-sat")
    resp = client.get(f"/clients/{c['client_id']}/pairing/qr.svg?host=10.0.0.5", headers=auth)
    assert resp.status_code == 200
    assert "image/svg+xml" in resp.headers["content-type"]
    assert b"<svg" in resp.content


def test_sse_accepts_query_token(client):
    tok = client.post("/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS}).json()["token"]
    # no Authorization header — auth solely via access_token query param
    with client.stream("GET", f"/events?limit=1&interval=0.25&access_token={tok}") as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
    assert "event: snapshot" in body


def test_sse_rejects_without_token(client):
    assert client.get("/events?limit=1").status_code == 401
