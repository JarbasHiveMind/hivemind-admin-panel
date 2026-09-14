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


def test_restore_preserves_permissions_and_blacklists(client, auth, make_client):
    """A restored client must keep the permissions it was backed up with.

    Restore must not fall back to the model defaults (can_escalate,
    can_propagate and can_broadcast all True, blacklists empty) for fields
    a bundle actually carries — that would silently upgrade a restricted
    satellite's privileges on every restore.
    """
    created = make_client(name="locked-down-sat")
    client_id = created["client_id"]
    upd = client.put(
        f"/clients/{client_id}",
        json={
            "can_escalate": False,
            "can_propagate": False,
            "can_broadcast": False,
            "skill_blacklist": ["skill-a"],
            "intent_blacklist": ["intent-b"],
        },
        headers=auth,
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["can_escalate"] is False
    assert upd.json()["can_propagate"] is False

    bundle = client.get("/backup", headers=auth).json()
    row = next(c for c in bundle["clients"] if c["client_id"] == client_id)
    assert row["can_escalate"] is False
    assert row["can_propagate"] is False
    assert row["can_broadcast"] is False
    assert row["skill_blacklist"] == ["skill-a"]
    assert row["intent_blacklist"] == ["intent-b"]

    # restore that same row under a fresh api_key, into what is otherwise a
    # clean database as far as this client is concerned
    row = dict(row)
    row["api_key"] = "rk-restored-locked-down"
    resp = client.post("/restore", json={"clients": [row]}, headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["clients_added"] == 1

    restored = next(
        c for c in client.get("/clients", headers=auth).json()
        if c["name"] == "locked-down-sat" and c["client_id"] != client_id
    )
    assert restored["can_escalate"] is False
    assert restored["can_propagate"] is False
    assert restored["can_broadcast"] is False
    assert restored["skill_blacklist"] == ["skill-a"]
    assert restored["intent_blacklist"] == ["intent-b"]


def test_restore_reports_retired_fields(client, auth):
    bundle = {
        "clients": [
            {
                "name": "old-bundle-sat",
                "api_key": "rk-old-bundle",
                "is_admin": False,
                "allowed_types": [],
                "crypto_key": "0123456789abcdef",
            },
        ]
    }
    resp = client.post("/restore", json=bundle, headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["clients_added"] == 1
    assert "crypto_key" in resp.json().get("message", "")


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
