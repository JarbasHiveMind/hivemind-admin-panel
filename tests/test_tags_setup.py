# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: client tags + first-run setup status."""


def test_client_tags_roundtrip(client, auth, make_client):
    c = make_client(name="tagged")
    assert c["tags"] == []
    r = client.put(f"/clients/{c['client_id']}/tags", json={"tags": ["kitchen", "voice"]}, headers=auth)
    assert r.status_code == 200
    assert r.json()["tags"] == ["kitchen", "voice"]
    # persisted
    assert sorted(client.get(f"/clients/{c['client_id']}", headers=auth).json()["tags"]) == ["kitchen", "voice"]


def test_setup_status_flags_default_creds(client, auth):
    # the test harness uses a non-default password, so default_credentials is False
    body = client.get("/setup/status", headers=auth).json()
    assert "default_credentials" in body
    assert "client_count" in body
    assert body["default_credentials"] is False
