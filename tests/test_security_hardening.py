# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the security hardening pass.

Each test here fails against 0.1.1a2.
"""
import base64
import os

import pytest

from tests.conftest import ADMIN_USER, ADMIN_PASS


DEFAULT_AUTH = {"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()}


@pytest.fixture()
def default_creds():
    """Put the panel back on the shipped default credentials for one test."""
    from hivemind_core.config import get_server_config
    cfg = get_server_config()
    orig_user, orig_pass = cfg.get("admin_user"), cfg.get("admin_pass")
    cfg["admin_user"] = "admin"
    cfg["admin_pass"] = "admin"
    cfg.store()
    yield cfg
    cfg["admin_user"] = orig_user
    cfg["admin_pass"] = orig_pass
    cfg.store()


# --------------------------------------------------------------- S8: non-ASCII creds

def test_non_ascii_username_is_rejected_not_a_500(client):
    """`curl -u 'admín:x'` used to raise TypeError inside hmac.compare_digest."""
    tok = base64.b64encode("admín:x".encode()).decode()
    r = client.get("/clients", headers={"Authorization": f"Basic {tok}"})
    assert r.status_code == 401


def test_non_ascii_password_is_rejected_not_a_500(client):
    tok = base64.b64encode(f"{ADMIN_USER}:pässwörd".encode()).decode()
    r = client.get("/clients", headers={"Authorization": f"Basic {tok}"})
    assert r.status_code == 401


def test_non_ascii_login_body_is_rejected_not_a_500(client):
    r = client.post("/auth/login", json={"username": "admín", "password": "x"})
    assert r.status_code in (401, 429)


# --------------------------------------------------------- S2: server-side setup gate

def test_default_credentials_block_every_route(client, default_creds):
    """The forced password change must not be a client-side modal only."""
    for path in ("/clients", "/config", "/plugins/installed/ovos/stt", "/audit"):
        r = client.get(path, headers=DEFAULT_AUTH)
        assert r.status_code == 403, f"{path} reachable with default credentials"
        assert "default admin credentials" in r.json()["detail"].lower()


def test_default_credentials_still_allow_the_escape_hatch(client, default_creds):
    assert client.get("/setup/status", headers=DEFAULT_AUTH).status_code == 200
    assert client.get("/auth/me", headers=DEFAULT_AUTH).status_code == 200
    assert client.get("/health").status_code == 200
    assert client.post("/auth/login",
                       json={"username": "admin", "password": "admin"}).status_code == 200


def test_setup_gate_clears_after_the_password_changes(client, default_creds):
    from hivemind_core.config import get_server_config
    r = client.post("/auth/password",
                    json={"old_password": "admin", "new_password": "a-strong-one-42"},
                    headers=DEFAULT_AUTH)
    assert r.status_code == 200
    new_auth = {"Authorization": "Basic " + base64.b64encode(
        b"admin:a-strong-one-42").decode()}
    assert client.get("/clients", headers=new_auth).status_code == 200


# ------------------------------------------------------- S3: token rotation on change

def test_password_change_revokes_existing_tokens(client, auth):
    from hivemind_core.config import get_server_config
    cfg = get_server_config()
    token = client.post("/auth/login",
                        json={"username": ADMIN_USER, "password": ADMIN_PASS}).json()["token"]
    bearer = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=bearer).status_code == 200
    try:
        assert client.post("/auth/password",
                           json={"old_password": ADMIN_PASS, "new_password": "rotate-me-99"},
                           headers=auth).status_code == 200
        # the old token was minted under the old password: it must be dead
        assert client.get("/auth/me", headers=bearer).status_code == 401
    finally:
        cfg["admin_pass"] = ADMIN_PASS
        cfg.store()


# ------------------------------------------------------------ S4: server.json is 0600

def test_config_file_is_not_world_readable(client, auth):
    from hivemind_core.config import get_server_config
    client.post("/config", json={"config": {"chmod_probe": 1}}, headers=auth)
    path = get_server_config().path
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"


# ------------------------------------------------------------------ S6: default-deny

@pytest.fixture()
def operator_auth():
    """An `operator`-role account, which must not reach destructive routes."""
    from hivemind_core.config import get_server_config
    cfg = get_server_config()
    orig = cfg.get("users")
    cfg["users"] = [{"username": "ops", "password": "ops-pass-123", "role": "operator"}]
    cfg.store()
    tok = base64.b64encode(b"ops:ops-pass-123").decode()
    yield {"Authorization": f"Basic {tok}"}
    cfg["users"] = orig or []
    cfg.store()


def test_operator_cannot_reach_destructive_client_routes(client, operator_auth, make_client):
    c = make_client(name="guarded")
    cid = c["client_id"]
    assert client.delete(f"/clients/{cid}", headers=operator_auth).status_code == 403
    assert client.put(f"/clients/{cid}", json={"name": "x"},
                      headers=operator_auth).status_code == 403
    assert client.post(f"/clients/{cid}/make-admin", headers=operator_auth).status_code == 403
    assert client.put(f"/clients/{cid}/acl", json={"client_id": cid, "is_admin": True},
                      headers=operator_auth).status_code == 403
    assert client.post("/config", json={"config": {}},
                       headers=operator_auth).status_code == 403


def test_operator_cannot_read_client_secrets(client, operator_auth, make_client):
    cid = make_client(name="secrets")["client_id"]
    assert client.get(f"/clients/{cid}/credentials",
                      headers=operator_auth).status_code == 403


def test_operator_can_still_read(client, operator_auth):
    assert client.get("/clients", headers=operator_auth).status_code == 200


# ------------------------------------------------------------------------ S7: CSRF

def test_form_encoded_mutation_is_refused(client, auth, make_client):
    """A cross-site <form> can only send form content types — block them."""
    cid = make_client(name="csrf")["client_id"]
    r = client.post(f"/clients/{cid}/make-admin",
                    headers={**auth, "Content-Type": "application/x-www-form-urlencoded"},
                    content="")
    assert r.status_code == 415


def test_cross_site_mutation_is_refused(client, auth, make_client):
    cid = make_client(name="csrf2")["client_id"]
    r = client.post(f"/clients/{cid}/make-admin",
                    headers={**auth, "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_foreign_origin_mutation_is_refused(client, auth):
    r = client.post("/config", json={"config": {}},
                    headers={**auth, "Origin": "https://evil.example"})
    assert r.status_code == 403


def test_no_www_authenticate_header_on_401(client):
    """The Basic challenge makes browsers cache and replay the credentials."""
    r = client.get("/clients")
    assert r.status_code == 401
    assert "WWW-Authenticate" not in r.headers


# ------------------------------------------------------- S9: query-string bearer scope

def test_query_token_is_not_accepted_on_arbitrary_routes(client):
    from hivemind_core.config import get_server_config
    from hivemind_admin_panel._auth import create_token
    token = create_token(get_server_config(), ADMIN_USER, "admin")["token"]
    assert client.get(f"/clients?access_token={token}").status_code == 401


def test_query_token_still_works_for_the_sse_feed(client):
    from hivemind_admin_panel.api import _allows_query_token
    assert _allows_query_token("/api/events")
    assert _allows_query_token("/api/clients/1/pairing/qr.svg")
    assert not _allows_query_token("/api/clients")


# ------------------------------------------------------------ S1: fail-closed on bind

def test_non_loopback_bind_with_default_credentials_refuses_to_start(default_creds):
    from hivemind_admin_panel.__main__ import check_bind_safety, InsecureBindError
    with pytest.raises(InsecureBindError):
        check_bind_safety("0.0.0.0")
    with pytest.raises(InsecureBindError):
        check_bind_safety("192.168.1.50")


def test_loopback_bind_with_default_credentials_is_allowed(default_creds):
    from hivemind_admin_panel.__main__ import check_bind_safety
    check_bind_safety("127.0.0.1")
    check_bind_safety("localhost")


def test_explicit_override_allows_an_exposed_bind(default_creds):
    from hivemind_admin_panel.__main__ import check_bind_safety
    check_bind_safety("0.0.0.0", allow_insecure=True)


def test_non_default_credentials_allow_any_bind(client):
    from hivemind_admin_panel.__main__ import check_bind_safety
    check_bind_safety("0.0.0.0")


# --------------------------------------------------------------- S9: login throttling

def test_repeated_failed_logins_are_throttled(client):
    from hivemind_admin_panel.api import _LOGIN_FAILURES
    _LOGIN_FAILURES.pop("bruteforce", None)
    codes = [client.post("/auth/login",
                         json={"username": "bruteforce", "password": f"guess{i}"}).status_code
             for i in range(12)]
    assert 429 in codes, codes
    _LOGIN_FAILURES.pop("bruteforce", None)
