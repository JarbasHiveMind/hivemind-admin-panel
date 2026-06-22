# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: client CRUD against a real database."""


def test_create_autogenerates_keys(make_client):
    c = make_client(name="sat-a")
    assert c["name"] == "sat-a"
    assert c["api_key"]
    assert c["is_admin"] is False


def test_create_admin_client(make_client):
    c = make_client(name="boss", is_admin=True)
    assert c["is_admin"] is True


def test_create_rejects_bad_crypto_key_length(client, auth):
    resp = client.post("/clients", json={"name": "x", "crypto_key": "tooshort"}, headers=auth)
    assert resp.status_code == 400


def test_list_and_get_roundtrip(client, auth, make_client):
    c = make_client(name="sat-b")
    got = client.get(f"/clients/{c['client_id']}", headers=auth)
    assert got.status_code == 200
    assert got.json()["name"] == "sat-b"


def test_get_missing_client_404(client, auth):
    assert client.get("/clients/999999", headers=auth).status_code == 404


def test_credentials_endpoint_returns_secrets(client, auth, make_client):
    c = make_client(name="sat-c")
    creds = client.get(f"/clients/{c['client_id']}/credentials", headers=auth).json()
    assert creds["api_key"] == c["api_key"]
    assert "crypto_key" in creds


def test_active_excludes_deleted(client, auth, make_client):
    c = make_client(name="sat-d")
    assert client.delete(f"/clients/{c['client_id']}", headers=auth).status_code == 200
    active_ids = [x["client_id"] for x in client.get("/clients/active", headers=auth).json()]
    assert c["client_id"] not in active_ids


def test_rename_requires_name(client, auth, make_client):
    c = make_client(name="sat-e")
    assert client.post(f"/clients/{c['client_id']}/rename", json={}, headers=auth).status_code == 400


def test_rename_updates_name(client, auth, make_client):
    c = make_client(name="sat-f")
    resp = client.post(f"/clients/{c['client_id']}/rename", json={"name": "renamed"}, headers=auth)
    assert resp.status_code == 200
    assert client.get(f"/clients/{c['client_id']}", headers=auth).json()["name"] == "renamed"


def test_update_toggles_admin(client, auth, make_client):
    c = make_client(name="sat-g")
    resp = client.put(f"/clients/{c['client_id']}", json={"is_admin": True}, headers=auth)
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is True


def test_delete_marks_revoked(client, auth, make_client):
    # delete is a soft-delete: the record is retained but marked revoked and
    # dropped from the active list (credentials store is never stranded).
    c = make_client(name="sat-h")
    assert client.delete(f"/clients/{c['client_id']}", headers=auth).status_code == 200
    got = client.get(f"/clients/{c['client_id']}", headers=auth).json()
    assert got["revoked"] is True
    active_ids = [x["client_id"] for x in client.get("/clients/active", headers=auth).json()]
    assert c["client_id"] not in active_ids
