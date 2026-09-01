# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Every mutating route is admin-gated unless it is deliberately not.

``operator`` is documented as "read + non-destructive writes". A route that
widens a satellite's ACL, rewrites server.json or deletes a resource is neither
read nor non-destructive, so it must sit behind :func:`require_admin`.

The allow-list below is the deliberate exception list. Adding a route to it is a
decision; forgetting a ``Depends(require_admin)`` is not.
"""
import base64

import pytest
from fastapi.testclient import TestClient

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

#: Mutating routes an operator may call, with the reason.
OPERATOR_ALLOWED = {
    "/auth/login": "issues a token; authenticates by itself",
    "/auth/logout": "stateless, self-service",
    "/auth/password": "changes the caller's own password",
    "/config/validate": "dry run, writes nothing",
    "/config/diff": "dry run, writes nothing",
    "/database/test": "connection probe, writes nothing",
    "/personas/{name}/test": "dry run, writes nothing",
    "/personas/{name}/chat": "test chat, writes nothing",
    "/presets/{ptype}/{name}/test": "dry run, writes nothing",
}


def _mutating_routes():
    from hivemind_admin_panel.api import app

    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        if not (methods & MUTATING):
            continue
        yield route


def _guards(route):
    return {getattr(d.dependency, "__name__", "") for d in (route.dependencies or [])}


def test_every_mutating_route_is_admin_gated_or_allow_listed():
    from hivemind_admin_panel.api import require_admin  # noqa: F401  (import guard)

    ungated = []
    for route in _mutating_routes():
        if route.path in OPERATOR_ALLOWED:
            continue
        if "require_admin" not in _guards(route):
            ungated.append(f"{sorted(route.methods & MUTATING)} {route.path} "
                           f"-> {sorted(_guards(route)) or 'NO GUARD'}")
    assert not ungated, (
        "these mutating routes are reachable by the operator role; add "
        "Depends(require_admin) or justify them in OPERATOR_ALLOWED:\n  "
        + "\n  ".join(ungated))


def test_allow_list_has_no_stale_entries():
    paths = {r.path for r in _mutating_routes()}
    stale = sorted(set(OPERATOR_ALLOWED) - paths)
    assert not stale, f"OPERATOR_ALLOWED names routes that no longer exist: {stale}"


def test_no_mutating_route_is_completely_unguarded():
    """A route with no dependency at all authenticates nobody."""
    unguarded = [f"{sorted(r.methods & MUTATING)} {r.path}"
                 for r in _mutating_routes()
                 if not _guards(r) and r.path != "/auth/login"]
    assert not unguarded, unguarded


# --------------------------------------------------------------- functional


@pytest.fixture()
def operator_auth(_server_config):
    """Add an ``operator`` account to server.json and return its Basic header."""
    from hivemind_core.config import get_server_config

    cfg = get_server_config()
    previous = cfg.get("users")
    cfg["users"] = [{"username": "ops", "password": "ops-pass", "role": "operator"}]
    cfg.store()
    try:
        token = base64.b64encode(b"ops:ops-pass").decode()
        yield {"Authorization": f"Basic {token}"}
    finally:
        cfg["users"] = previous or []
        cfg.store()


def test_operator_cannot_widen_a_client_acl(client, operator_auth, make_client):
    """The privilege-widening routes were operator-writable; they must not be."""
    created = make_client(name="acl-victim")
    cid = created["client_id"]
    for path in (f"/clients/{cid}/allow-escalate",
                 f"/clients/{cid}/allow-propagate",
                 f"/clients/{cid}/blacklist-skill",
                 f"/clients/{cid}/blacklist-intent"):
        resp = client.post(path, json={"skill_id": "x", "intent_id": "x"},
                           headers=operator_auth)
        assert resp.status_code == 403, f"{path} -> {resp.status_code} {resp.text[:100]}"


def test_operator_cannot_rewrite_server_config_via_plugins(client, operator_auth):
    resp = client.post("/plugins/enable",
                       json={"plugin_type": "database", "module": "evil", "enabled": True},
                       headers=operator_auth)
    assert resp.status_code == 403, resp.text


def test_operator_can_still_read_and_dry_run(client, operator_auth):
    assert client.get("/clients", headers=operator_auth).status_code == 200
    assert client.post("/config/validate", json={"config": {}},
                       headers=operator_auth).status_code == 200


# --------------------------------------------------- secret exfiltration (authz)

TOKEN_SECRET = "deadbeef" * 8  # a known signing secret to look for on the wire
OP_USER = "authz-ops"
OP_PASS = "authz-ops-pass"


@pytest.fixture()
def authz_env(_server_config):
    """Write admin creds, a known token secret and one operator user in a single
    ``store()``, and yield both auth headers.

    server.json is disk-backed and every fixture that reads-modifies-stores it
    holds its own snapshot, so composing separate operator/token fixtures races
    on teardown. Doing it all in one place keeps these tests order-independent.
    """
    from hivemind_core.config import get_server_config
    from tests.conftest import ADMIN_USER, ADMIN_PASS

    cfg = get_server_config()
    previous = {k: cfg.get(k) for k in ("admin_token_secret", "users")}
    cfg["admin_user"] = ADMIN_USER
    cfg["admin_pass"] = ADMIN_PASS
    cfg["admin_token_secret"] = TOKEN_SECRET
    cfg["users"] = [{"username": OP_USER, "password": OP_PASS, "role": "operator"}]
    cfg.store()
    admin = base64.b64encode(f"{ADMIN_USER}:{ADMIN_PASS}".encode()).decode()
    op = base64.b64encode(f"{OP_USER}:{OP_PASS}".encode()).decode()
    try:
        yield {"admin": {"Authorization": f"Basic {admin}"},
               "operator": {"Authorization": f"Basic {op}"}}
    finally:
        for k, v in previous.items():
            if v is None:
                cfg.pop(k, None)
            else:
                cfg[k] = v
        cfg.store()


def test_operator_config_hides_token_secret_and_password(client, authz_env):
    """An operator reading /config must not receive the token-signing secret or
    admin password: leaking the secret lets them forge an admin bearer token."""
    resp = client.get("/config", headers=authz_env["operator"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    from tests.conftest import ADMIN_PASS
    assert body.get("admin_token_secret") != TOKEN_SECRET
    assert body.get("admin_pass") != ADMIN_PASS
    assert TOKEN_SECRET not in resp.text
    assert ADMIN_PASS not in resp.text


def test_admin_config_hides_token_secret(client, authz_env):
    """Even an admin browser session has no need for the raw signing secret."""
    resp = client.get("/config", headers=authz_env["admin"])
    assert resp.status_code == 200, resp.text
    assert TOKEN_SECRET not in resp.text


def test_admin_config_roundtrip_preserves_token_secret(client, authz_env):
    """GET /config then POST it back (as the SPA does) must not clobber the real
    signing secret with the redaction placeholder."""
    cfg = client.get("/config", headers=authz_env["admin"]).json()
    cfg["description"] = "roundtrip"
    assert client.post("/config", json={"config": cfg},
                       headers=authz_env["admin"]).status_code == 200
    from hivemind_core.config import get_server_config
    assert get_server_config().get("admin_token_secret") == TOKEN_SECRET


def test_operator_backup_forbidden(client, authz_env):
    """A full secret-bearing backup is an admin action."""
    assert client.get("/backup", headers=authz_env["operator"]).status_code == 403


def test_admin_backup_omits_token_secret_but_keeps_client_secrets(
        client, authz_env, make_client):
    """The backup drops the token-signing secret and admin password from config,
    but still carries client password/crypto_key so a restore works."""
    make_client(name="backup-sat")
    resp = client.get("/backup", headers=authz_env["admin"])
    assert resp.status_code == 200, resp.text
    bundle = resp.json()
    assert "admin_token_secret" not in bundle["config"]
    assert "admin_pass" not in bundle["config"]
    assert TOKEN_SECRET not in resp.text
    assert bundle["clients"], "backup should include clients"
    assert any("password" in c and "crypto_key" in c for c in bundle["clients"])


def test_operator_clients_list_hides_api_key(client, authz_env, make_client):
    """Operators may list clients but must not read the connection api_key."""
    make_client(name="apikey-sat")
    resp = client.get("/clients", headers=authz_env["operator"])
    assert resp.status_code == 200, resp.text
    clients = resp.json()
    assert clients, "operator should still see the client list"
    assert all("api_key" not in c for c in clients)


def test_admin_clients_list_keeps_api_key(client, authz_env, make_client):
    """Admins still get the api_key in the client list."""
    make_client(name="apikey-admin-sat")
    clients = client.get("/clients", headers=authz_env["admin"]).json()
    assert any(c.get("api_key") for c in clients)


# ------------------------------------------ wave-3 sibling secret-leak sweep

JSON_MODULE = "hivemind-json-db-plugin"


def test_operator_config_diff_hides_secrets(client, authz_env):
    """POST /config/diff must not leak the token secret or admin password to an
    operator diffing an empty proposal against the current server.json."""
    from hivemind_admin_panel.api import REDACTED
    from tests.conftest import ADMIN_PASS

    resp = client.post("/config/diff", json={"config": {}},
                       headers=authz_env["operator"])
    assert resp.status_code == 200, resp.text
    assert TOKEN_SECRET not in resp.text
    assert ADMIN_PASS not in resp.text
    removed = resp.json().get("removed", {})
    assert removed.get("admin_token_secret", REDACTED) == REDACTED
    assert removed.get("admin_pass", REDACTED) == REDACTED


def test_operator_config_backups_diff_hides_secrets(client, authz_env):
    """GET /config/backups/diff must redact the token secret and admin password
    on both sides of the snapshot-vs-current comparison."""
    from hivemind_core.config import get_server_config
    from tests.conftest import ADMIN_PASS

    snap = client.post("/config/backups",
                       headers=authz_env["admin"]).json()["file"]
    cfg = get_server_config()
    cfg["admin_token_secret"] = "live-" + TOKEN_SECRET
    cfg.store()
    try:
        resp = client.get(f"/config/backups/diff?file={snap}",
                          headers=authz_env["operator"])
        assert resp.status_code == 200, resp.text
        assert TOKEN_SECRET not in resp.text
        assert "live-" + TOKEN_SECRET not in resp.text
        assert ADMIN_PASS not in resp.text
    finally:
        cfg["admin_token_secret"] = TOKEN_SECRET
        cfg.store()


def _active_db_module():
    """The database module ``make_client`` (and the injected ClientDatabase)
    actually writes to, so this file does not depend on cross-test DB state."""
    from hivemind_core.config import get_server_config
    return get_server_config().get("database", {}).get(
        "module", "hivemind-sqlite-db-plugin")


def test_operator_db_clients_hides_client_secrets(client, authz_env, make_client):
    """GET /database/{module}/clients must hide client password/crypto_key and
    strip the api_key for operators, mirroring GET /clients."""
    make_client(name="db-secret-sat", password="op-visible-pw",
                crypto_key="0123456789abcdef")
    resp = client.get(f"/database/{_active_db_module()}/clients",
                      headers=authz_env["operator"])
    assert resp.status_code == 200, resp.text
    clients = resp.json()
    assert clients, "operator should still see the client list"
    assert all("password" not in c for c in clients)
    assert all("crypto_key" not in c for c in clients)
    assert all("api_key" not in c for c in clients)
    assert "op-visible-pw" not in resp.text
    assert "0123456789abcdef" not in resp.text


def test_admin_db_clients_keeps_client_secrets(client, authz_env, make_client):
    """Admins still get client password/crypto_key from the per-module list."""
    make_client(name="db-secret-admin-sat", password="adm-pw",
                crypto_key="0123456789abcdef")
    clients = client.get(f"/database/{_active_db_module()}/clients",
                         headers=authz_env["admin"]).json()
    assert any(c.get("crypto_key") for c in clients)


def test_operator_database_profiles_hides_backend_secrets(client, authz_env):
    """GET /database/profiles* must redact backend connection secrets (SQL DSN,
    Redis URL, plain password) baked into a profile config."""
    secret = "s3cr3t-db-pw"
    dsn = "postgresql://user:p4ss@db.internal/hive"
    resp = client.post(
        "/database/profiles",
        json={"name": "leaky", "module": JSON_MODULE,
              "config": {"name": "clients", "password": secret, "dsn": dsn}},
        headers=authz_env["admin"],
    )
    assert resp.status_code == 200, resp.text
    try:
        listed = client.get("/database/profiles", headers=authz_env["operator"])
        assert listed.status_code == 200, listed.text
        assert secret not in listed.text
        assert dsn not in listed.text
        one = client.get("/database/profiles/leaky", headers=authz_env["operator"])
        assert one.status_code == 200, one.text
        assert secret not in one.text
        assert dsn not in one.text
    finally:
        client.delete("/database/profiles/leaky", headers=authz_env["admin"])


def test_operator_startup_error_omits_traceback(client, authz_env):
    """GET /startup-error must not hand an operator the full traceback (which
    carries filesystem paths and config internals); admins may see it."""
    import hivemind_admin_panel.api as api

    prev_err = api._startup_error
    prev_tb = api._error_traceback
    api._startup_error = RuntimeError("boom")
    api._error_traceback = 'File "/home/secret/path/api.py", line 1, in <module>'
    try:
        op = client.get("/startup-error", headers=authz_env["operator"])
        assert op.status_code == 200, op.text
        assert op.json().get("traceback") is None
        assert "/home/secret/path" not in op.text
        adm = client.get("/startup-error", headers=authz_env["admin"])
        assert adm.status_code == 200, adm.text
        assert adm.json().get("traceback")
    finally:
        api._startup_error = prev_err
        api._error_traceback = prev_tb


# ------------------------------------- wave-3 operator-reachable secret leaks

def test_operator_client_detail_hides_api_key(client, authz_env, make_client):
    """GET /clients/{id} must strip the connection api_key for operators,
    mirroring GET /clients."""
    created = make_client(name="detail-sat")
    cid = created["client_id"]
    resp = client.get(f"/clients/{cid}", headers=authz_env["operator"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "api_key" not in body
    assert created["api_key"] not in resp.text


def test_admin_client_detail_keeps_api_key(client, authz_env, make_client):
    """Admins still get the api_key from the single-client detail route."""
    created = make_client(name="detail-admin-sat")
    cid = created["client_id"]
    body = client.get(f"/clients/{cid}", headers=authz_env["admin"]).json()
    assert body.get("api_key") == created["api_key"]


def test_operator_pairing_forbidden(client, authz_env, make_client):
    """GET /clients/{id}/pairing hands out the full connection creds
    (api_key + password + crypto_key), so it is admin-only."""
    created = make_client(name="pairing-sat", password="pair-pw",
                          crypto_key="0123456789abcdef")
    cid = created["client_id"]
    resp = client.get(f"/clients/{cid}/pairing", headers=authz_env["operator"])
    assert resp.status_code == 403, resp.text
    assert "pair-pw" not in resp.text
    assert "0123456789abcdef" not in resp.text


def test_operator_pairing_qr_forbidden(client, authz_env, make_client):
    """The QR variant renders the same creds into a scannable image, so it is
    admin-only too."""
    created = make_client(name="pairing-qr-sat")
    cid = created["client_id"]
    resp = client.get(f"/clients/{cid}/pairing/qr.svg",
                      headers=authz_env["operator"])
    assert resp.status_code == 403, resp.text


def test_admin_pairing_returns_full_credentials(client, authz_env, make_client):
    """Admins still get the full pairing bundle."""
    created = make_client(name="pairing-admin-sat", password="adm-pair-pw",
                          crypto_key="0123456789abcdef")
    cid = created["client_id"]
    resp = client.get(f"/clients/{cid}/pairing", headers=authz_env["admin"])
    assert resp.status_code == 200, resp.text
    bundle = resp.json()
    assert bundle["key"] == created["api_key"]
    assert bundle["password"] == "adm-pair-pw"
    assert bundle["crypto_key"] == "0123456789abcdef"


LLM_KEY = "sk-operator-must-not-see-this"


def _write_persona(name, provider="ovos-solver-openai-plugin"):
    from hivemind_admin_panel.api import _get_personas_path
    import json as _json
    path = _get_personas_path()
    path.mkdir(parents=True, exist_ok=True)
    persona = {
        "name": name,
        "handlers": [provider],
        provider: {"api_url": "https://llm.example/v1", "key": LLM_KEY,
                   "persona": "helpful"},
        "memory_module": "ovos-agents-short-term-memory-plugin",
    }
    file = path / f"{name}.json"
    file.write_text(_json.dumps(persona, indent=2))
    return file


def test_operator_persona_config_hides_llm_key(client, authz_env):
    """GET /persona/config must redact the bundled LLM-provider key for
    operators (the sample persona.json embeds a `key`)."""
    resp = client.get("/persona/config", headers=authz_env["operator"])
    assert resp.status_code == 200, resp.text
    from hivemind_admin_panel.api import _load_persona_config
    raw_key = _load_persona_config().get("ovos-solver-openai-plugin", {}).get("key")
    if raw_key:  # only meaningful if the sample carries a key
        assert raw_key not in resp.text


def test_admin_persona_config_keeps_llm_key(client, authz_env):
    """Admins still get the raw persona config."""
    resp = client.get("/persona/config", headers=authz_env["admin"])
    assert resp.status_code == 200, resp.text
    from hivemind_admin_panel.api import _load_persona_config, REDACTED
    raw = _load_persona_config().get("ovos-solver-openai-plugin", {})
    if raw.get("key"):
        assert resp.json().get("ovos-solver-openai-plugin", {}).get("key") == raw["key"]
        assert REDACTED not in resp.text or raw["key"] in resp.text


def test_operator_persona_get_and_export_hide_llm_key(client, authz_env):
    """GET /personas, /personas/{name} and /personas/{name}/export must redact
    the nested LLM-provider key for operators."""
    from hivemind_admin_panel.api import REDACTED
    f = _write_persona("leaky-persona")
    try:
        listed = client.get("/personas", headers=authz_env["operator"])
        assert listed.status_code == 200, listed.text
        assert LLM_KEY not in listed.text

        one = client.get("/personas/leaky-persona", headers=authz_env["operator"])
        assert one.status_code == 200, one.text
        assert LLM_KEY not in one.text
        assert one.json()["ovos-solver-openai-plugin"]["key"] == REDACTED

        exp = client.get("/personas/leaky-persona/export",
                         headers=authz_env["operator"])
        assert exp.status_code == 200, exp.text
        assert LLM_KEY not in exp.text
    finally:
        f.unlink(missing_ok=True)


def test_admin_persona_get_keeps_llm_key(client, authz_env):
    """Admins still get the raw persona key."""
    f = _write_persona("admin-persona")
    try:
        one = client.get("/personas/admin-persona", headers=authz_env["admin"])
        assert one.status_code == 200, one.text
        assert one.json()["ovos-solver-openai-plugin"]["key"] == LLM_KEY
    finally:
        f.unlink(missing_ok=True)


def test_operator_preset_hides_provider_key(client, authz_env):
    """A preset config can embed a plugin provider key; GET /presets* must
    redact it for operators."""
    from hivemind_admin_panel.api import REDACTED
    resp = client.post(
        "/presets/agent",
        json={"name": "leakypreset", "module": "ovos-solver-openai-plugin",
              "config": {"api_url": "https://llm.example/v1", "key": LLM_KEY}},
        headers=authz_env["admin"],
    )
    assert resp.status_code == 200, resp.text
    try:
        one = client.get("/presets/agent/leakypreset",
                         headers=authz_env["operator"])
        assert one.status_code == 200, one.text
        assert LLM_KEY not in one.text
        assert one.json()["config"]["key"] == REDACTED

        allp = client.get("/presets", headers=authz_env["operator"])
        assert allp.status_code == 200, allp.text
        assert LLM_KEY not in allp.text

        typ = client.get("/presets/agent", headers=authz_env["operator"])
        assert typ.status_code == 200, typ.text
        assert LLM_KEY not in typ.text

        # admin still sees the real key
        adm = client.get("/presets/agent/leakypreset",
                         headers=authz_env["admin"])
        assert adm.json()["config"]["key"] == LLM_KEY
    finally:
        client.delete("/presets/agent/leakypreset", headers=authz_env["admin"])


def test_admin_profile_put_roundtrip_preserves_secret(client, authz_env):
    """PUT /database/profiles/{name} must not clobber the real backend secret
    with the REDACTED sentinel the redacted GET hands back (Item B)."""
    secret = "real-db-password"
    resp = client.post(
        "/database/profiles",
        json={"name": "rtprofile", "module": JSON_MODULE,
              "config": {"name": "clients", "password": secret}},
        headers=authz_env["admin"],
    )
    assert resp.status_code == 200, resp.text
    try:
        # admin reads (redacted) then posts the whole object back, as the SPA does
        got = client.get("/database/profiles/rtprofile",
                         headers=authz_env["admin"]).json()
        got["config"]["extra"] = "touched"
        put = client.put("/database/profiles/rtprofile",
                         json={"config": got["config"]},
                         headers=authz_env["admin"])
        assert put.status_code == 200, put.text
        from hivemind_admin_panel.api import _load_profile
        assert _load_profile("rtprofile")["config"]["password"] == secret
    finally:
        client.delete("/database/profiles/rtprofile", headers=authz_env["admin"])


# ---------------------------------- wave-4 nested config secret-leak sweep

DB_PASSWORD = "nested-db-pw-w4"
DB_DSN = "postgresql://user:nested-db-pw-w4@db.internal/hive"
PROVIDER_KEY = "sk-nested-provider-key-w4"


@pytest.fixture()
def nested_secret_env(authz_env):
    """On top of ``authz_env``, nest a non-sqlite ``database`` backend carrying a
    password + DSN and a provider ``key`` under ``agent_protocol`` in server.json,
    mirroring what activate/persona plugins write. Yields the auth headers."""
    from hivemind_core.config import get_server_config

    cfg = get_server_config()
    previous = {k: cfg.get(k) for k in ("database", "agent_protocol")}
    cfg["database"] = {
        "module": "hivemind-redis-db-plugin",
        "hivemind-redis-db-plugin": {
            "host": "db.internal",
            "port": 6379,
            "password": DB_PASSWORD,
            "dsn": DB_DSN,
        },
    }
    cfg["agent_protocol"] = {
        "module": "hivemind-persona-agent-plugin",
        "hivemind-persona-agent-plugin": {
            "persona": {"solvers": [{"module": "ovos-llm", "key": PROVIDER_KEY}]},
        },
    }
    cfg.store()
    try:
        yield authz_env
    finally:
        for k, v in previous.items():
            if v is None:
                cfg.pop(k, None)
            else:
                cfg[k] = v
        cfg.store()


def _assert_no_nested_secrets(text):
    assert DB_PASSWORD not in text
    assert DB_DSN not in text
    assert PROVIDER_KEY not in text


def test_operator_config_hides_nested_database_and_provider_secrets(
        client, nested_secret_env):
    """GET /config must mask the nested DB password/DSN and the provider key
    buried under agent_protocol for an operator, not just top-level secrets."""
    resp = client.get("/config", headers=nested_secret_env["operator"])
    assert resp.status_code == 200, resp.text
    _assert_no_nested_secrets(resp.text)
    body = resp.json()
    db = body["database"]["hivemind-redis-db-plugin"]
    from hivemind_admin_panel.api import REDACTED
    assert db["password"] == REDACTED
    assert db["dsn"] == REDACTED
    # benign non-secret keys survive
    assert db["host"] == "db.internal"
    assert db["port"] == 6379


def test_operator_config_diff_hides_nested_secrets(client, nested_secret_env):
    """POST /config/diff must not leak the nested DB password/DSN or provider
    key to an operator diffing an empty proposal against the current config."""
    resp = client.post("/config/diff", json={"config": {}},
                       headers=nested_secret_env["operator"])
    assert resp.status_code == 200, resp.text
    _assert_no_nested_secrets(resp.text)


def test_operator_config_backups_diff_hides_nested_secrets(
        client, nested_secret_env):
    """GET /config/backups/diff must redact nested backend/provider secrets on
    both sides of the snapshot-vs-current comparison for an operator."""
    snap = client.post("/config/backups",
                       headers=nested_secret_env["admin"]).json()["file"]
    resp = client.get(f"/config/backups/diff?file={snap}",
                      headers=nested_secret_env["operator"])
    assert resp.status_code == 200, resp.text
    _assert_no_nested_secrets(resp.text)


def test_admin_config_roundtrip_preserves_nested_db_password(
        client, nested_secret_env):
    """GET /config (redacted) then POST it back must not clobber the real nested
    DB password with the placeholder: _restore_redacted recurses to restore it."""
    cfg = client.get("/config", headers=nested_secret_env["admin"]).json()
    cfg["description"] = "nested-roundtrip"
    assert client.post("/config", json={"config": cfg},
                       headers=nested_secret_env["admin"]).status_code == 200
    from hivemind_core.config import get_server_config
    db = get_server_config()["database"]["hivemind-redis-db-plugin"]
    assert db["password"] == DB_PASSWORD
    assert db["dsn"] == DB_DSN
