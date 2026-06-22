# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: backup/restore, policy chain, TLS certs."""


def test_backup_includes_clients(client, auth, make_client):
    make_client(name="backup-sat")
    bundle = client.get("/backup", headers=auth).json()
    assert bundle["version"] == 1
    assert "config" in bundle
    assert any(c["name"] == "backup-sat" for c in bundle["clients"])


def test_restore_adds_missing_clients(client, auth):
    bundle = {
        "clients": [
            {"name": "restored-1", "api_key": "rk-aaa", "is_admin": False, "allowed_types": []},
        ]
    }
    resp = client.post("/restore", json=bundle, headers=auth)
    assert resp.status_code == 200
    assert resp.json()["clients_added"] == 1
    # idempotent: second restore skips the existing key
    again = client.post("/restore", json=bundle, headers=auth)
    assert again.json()["clients_skipped"] == 1


def test_policy_roundtrip(client, auth):
    chain = [{"module": "hivemind-ovos-agent-policy"}]
    put = client.put("/policy", json={"chain": chain}, headers=auth)
    assert put.status_code == 200
    assert client.get("/policy", headers=auth).json()["chain"] == chain


def test_certs_status_and_generate(client, auth):
    before = client.get("/certs", headers=auth).json()
    assert "cert_path" in before and "cert_exists" in before
    gen = client.post("/certs/generate", headers=auth)
    assert gen.status_code == 200, gen.text
    after = client.get("/certs", headers=auth).json()
    assert after["cert_exists"] is True
    assert after["key_exists"] is True
