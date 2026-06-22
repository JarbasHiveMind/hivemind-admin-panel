# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: token login, bearer auth, roles, audit log."""
from tests.conftest import ADMIN_USER, ADMIN_PASS


def _token(client, user=ADMIN_USER, pw=ADMIN_PASS):
    r = client.post("/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_login_success_and_failure(client):
    assert client.post("/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS}).status_code == 200
    assert client.post("/auth/login", json={"username": ADMIN_USER, "password": "nope"}).status_code == 401


def test_bearer_token_authenticates(client):
    tok = _token(client)
    r = client.get("/clients", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200


def test_whoami_reports_role(client):
    tok = _token(client)
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["username"] == ADMIN_USER
    assert me["role"] == "admin"


def test_invalid_token_rejected(client):
    assert client.get("/clients", headers={"Authorization": "Bearer not.a.token"}).status_code == 401


def test_operator_role_blocked_from_admin_actions(client, auth):
    from hivemind_core.config import get_server_config
    cfg = get_server_config()
    cfg["users"] = [{"username": "ops", "password": "ops-pw", "role": "operator"}]
    cfg.store()
    try:
        op_tok = _token(client, "ops", "ops-pw")
        hdr = {"Authorization": f"Bearer {op_tok}"}
        # operator can read
        assert client.get("/clients", headers=hdr).status_code == 200
        # but not install plugins (admin-only)
        assert client.post("/plugins/install", json={"package": "x"}, headers=hdr).status_code == 403
    finally:
        cfg["users"] = []
        cfg.store()


def test_audit_records_mutations(client, auth, make_client):
    make_client(name="audited")
    entries = client.get("/audit", headers=auth).json()
    assert isinstance(entries, list)
    assert any("POST /clients" in e.get("action", "") for e in entries)
