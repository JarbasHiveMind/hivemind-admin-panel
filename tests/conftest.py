# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end test harness.

These tests exercise the real FastAPI app against a real on-disk config and a
real ClientDatabase (SQLite), in an isolated temporary XDG environment — no
mocks for the core admin paths. Only genuinely external boundaries
(``pip install`` subprocess, OVOS bus sockets, plugin discovery) are stubbed in
the individual tests that touch them.
"""
import base64
import os
import tempfile

# Isolate XDG dirs BEFORE anything from hivemind/ovos is imported, so all config
# and database state lands in a throwaway directory instead of the real home.
_TMP = tempfile.mkdtemp(prefix="hmadmin-e2e-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_TMP, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_TMP, "cache")
for _d in ("config", "data", "cache"):
    os.makedirs(os.path.join(_TMP, _d), exist_ok=True)

import pytest
from fastapi.testclient import TestClient

ADMIN_USER = "admin"
ADMIN_PASS = "s3cr3t-test-pass"


@pytest.fixture(scope="session", autouse=True)
def _server_config():
    """Write a server.json with known admin credentials + a JSON client DB."""
    from hivemind_core.config import get_server_config

    cfg = get_server_config()
    cfg["admin_user"] = ADMIN_USER
    cfg["admin_pass"] = ADMIN_PASS
    # use the file-based JSON backend for deterministic, dependency-light tests
    cfg["database"] = {
        "module": "hivemind-json-db-plugin",
        "hivemind-json-db-plugin": {"name": "clients", "subfolder": "hivemind-core"},
    }
    cfg.store()
    return cfg


@pytest.fixture()
def db(_server_config):
    """A real ClientDatabase injected into the admin app's globals."""
    from hivemind_core.database import ClientDatabase
    from hivemind_admin_panel.api import init_injected_objects

    database = ClientDatabase()
    init_injected_objects(service=None, db=database, protocol=None)
    yield database
    # reset injected globals between tests
    init_injected_objects(service=None, db=None, protocol=None)


@pytest.fixture()
def auth():
    token = base64.b64encode(f"{ADMIN_USER}:{ADMIN_PASS}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture()
def client(db):
    """TestClient bound to a freshly-injected real database."""
    from hivemind_admin_panel.api import app

    return TestClient(app)


@pytest.fixture()
def make_client(client, auth):
    """Factory: create a client via the API and return its dict."""
    created = []

    def _make(name="sat", is_admin=False, **kw):
        resp = client.post("/clients", json={"name": name, "is_admin": is_admin, **kw}, headers=auth)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        created.append(data["client_id"])
        return data

    return _make
