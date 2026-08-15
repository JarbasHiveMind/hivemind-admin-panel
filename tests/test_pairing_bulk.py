# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: satellite pairing bundle + bulk client operations."""
import json


def test_pairing_bundle(client, auth, make_client):
    c = make_client(name="pair-sat")
    body = client.get(f"/clients/{c['client_id']}/pairing?host=192.168.1.50", headers=auth).json()
    assert body["key"] == c["api_key"]
    assert body["host"] == "192.168.1.50"
    assert body["connect_url"].startswith("ws://192.168.1.50:")
    qr = json.loads(body["qr"])
    assert qr["key"] == c["api_key"]
    assert qr["port"] == body["port"]


def test_pairing_missing_client_404(client, auth):
    assert client.get("/clients/999999/pairing", headers=auth).status_code == 404


def test_bulk_make_admin(client, auth, make_client):
    a = make_client(name="bulk-a")
    b = make_client(name="bulk-b")
    resp = client.post("/clients/bulk", json={"action": "make_admin",
                                              "client_ids": [a["client_id"], b["client_id"]]}, headers=auth)
    assert resp.status_code == 200
    assert all(r["ok"] for r in resp.json()["results"])
    assert client.get(f"/clients/{a['client_id']}", headers=auth).json()["is_admin"] is True


def test_bulk_delete_reports_per_client(client, auth, make_client):
    a = make_client(name="bulk-del")
    resp = client.post("/clients/bulk", json={"action": "delete",
                                              "client_ids": [a["client_id"], 999999]}, headers=auth)
    results = {r["client_id"]: r["ok"] for r in resp.json()["results"]}
    assert results[a["client_id"]] is True
    assert results[999999] is False


def test_bulk_unknown_action(client, auth, make_client):
    a = make_client(name="bulk-x")
    resp = client.post("/clients/bulk", json={"action": "nope", "client_ids": [a["client_id"]]}, headers=auth)
    # rejected up front, so nothing is half-applied
    assert resp.status_code == 400
