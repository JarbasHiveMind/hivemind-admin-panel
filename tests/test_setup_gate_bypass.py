# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""The default-credentials gate must not be escapable through a path parameter.

The gate used to allow any request whose path *ended with* an allowed suffix.
Many routes end in a free-form path parameter, so naming a resource ``health``
(or ``status``, or ``me``) produced a path such as ``/chat/sessions/health``
that satisfied the suffix test and reached the handler untouched.
"""
import base64

import pytest
from fastapi.testclient import TestClient

DEFAULT_AUTH = {"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()}

#: Real routes whose trailing path parameter can be made to spell an allowed
#: endpoint. Every one of these must still be refused by the gate.
SMUGGLED = [
    ("DELETE", "/chat/sessions/health"),
    ("DELETE", "/personas/health"),
    ("DELETE", "/database/profiles/health"),
    ("DELETE", "/presets/agent/health"),
    ("DELETE", "/servers/health"),
    ("GET", "/servers/1/health"),
    ("POST", "/personas/status/activate"),
]


@pytest.fixture()
def default_creds_client(_server_config):
    """A TestClient whose server.json still holds the shipped admin/admin."""
    from hivemind_core.config import get_server_config
    from hivemind_admin_panel.api import app

    cfg = get_server_config()
    original_user, original_pass = cfg.get("admin_user"), cfg.get("admin_pass")
    cfg["admin_user"], cfg["admin_pass"] = "admin", "admin"
    cfg.store()
    try:
        yield TestClient(app)
    finally:
        cfg["admin_user"], cfg["admin_pass"] = original_user, original_pass
        cfg.store()


def test_gate_blocks_ordinary_routes(default_creds_client):
    """Control: the gate is actually engaged for this fixture."""
    resp = default_creds_client.get("/clients", headers=DEFAULT_AUTH)
    assert resp.status_code == 403, resp.text
    assert "Default admin credentials" in resp.text


@pytest.mark.parametrize("method,path", SMUGGLED)
def test_gate_cannot_be_smuggled_past_via_path_parameter(default_creds_client, method, path):
    resp = default_creds_client.request(method, path, headers=DEFAULT_AUTH,
                                        json={} if method in ("POST", "PUT") else None)
    assert resp.status_code == 403, (
        f"{method} {path} reached the application with default credentials in "
        f"use (got {resp.status_code}: {resp.text[:120]})")
    assert "Default admin credentials" in resp.text


def test_allow_listed_endpoints_still_reachable(default_creds_client):
    """The gate must not lock the operator out of fixing the problem."""
    assert default_creds_client.get("/health").status_code == 200
    assert default_creds_client.get("/auth/me", headers=DEFAULT_AUTH).status_code == 200
    login = default_creds_client.post("/auth/login",
                                      json={"username": "admin", "password": "admin"})
    assert login.status_code == 200, login.text


@pytest.mark.parametrize("path,root,expected", [
    ("/api/health", "/api", "/health"),          # mounted under /api by the launcher
    ("/health", "", "/health"),                  # API app served on its own
    ("/api/health/", "/api", "/health"),         # trailing slash
    ("/api/chat/sessions/health", "/api", "/chat/sessions/health"),
    ("/api", "/api", "/"),
])
def test_gate_path_strips_the_mount_prefix(path, root, expected):
    """The launcher mounts the API under /api; the allow-lists carry no prefix."""
    from starlette.requests import Request
    from hivemind_admin_panel.api import _gate_path

    request = Request({"type": "http", "method": "GET", "path": path,
                       "root_path": root, "headers": [], "query_string": b""})
    assert _gate_path(request) == expected
