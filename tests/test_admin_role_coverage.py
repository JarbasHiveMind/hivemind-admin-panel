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
