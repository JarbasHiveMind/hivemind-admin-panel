# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: password hashing/change, config diff, multi-hub fleet."""
from hivemind_admin_panel._auth import hash_password, verify_password
from tests.conftest import ADMIN_USER, ADMIN_PASS


def test_password_hash_roundtrip():
    h = hash_password("s3cret")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password(h, "s3cret")
    assert not verify_password(h, "wrong")
    assert verify_password("plaintext", "plaintext")  # legacy path


def test_change_password_then_login(client, auth):
    from hivemind_core.config import get_server_config
    cfg = get_server_config()
    try:
        r = client.post("/auth/password",
                        json={"old_password": ADMIN_PASS, "new_password": "newpass123"}, headers=auth)
        assert r.status_code == 200
        # stored hashed, not plaintext
        assert get_server_config().get("admin_pass").startswith("pbkdf2_sha256$")
        # new password logs in; old one fails
        assert client.post("/auth/login", json={"username": ADMIN_USER, "password": "newpass123"}).status_code == 200
        assert client.post("/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS}).status_code == 401
    finally:
        cfg["admin_pass"] = ADMIN_PASS  # restore for the rest of the session
        cfg.store()


def test_config_diff(client, auth):
    current = client.get("/config", headers=auth).json()
    proposed = dict(current)
    proposed["binarize"] = not current.get("binarize", False)
    proposed["a_new_key"] = 123
    diff = client.post("/config/diff", json={"config": proposed}, headers=auth).json()
    assert diff["has_changes"] is True
    assert "a_new_key" in diff["added"]
    assert "binarize" in diff["changed"]


def test_fleet_registry_and_status(client, auth):
    created = client.post("/fleet", json={"name": "remote-hub", "url": "http://127.0.0.1:9/"}, headers=auth)
    assert created.status_code == 200
    hid = created.json()["id"]
    assert "token" not in created.json()  # tokens never returned
    # unreachable remote -> reachable False, no crash
    st = client.get(f"/fleet/{hid}/status", headers=auth).json()
    assert st["reachable"] is False
    assert client.delete(f"/fleet/{hid}", headers=auth).status_code == 200
