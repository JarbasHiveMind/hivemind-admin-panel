# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: health and startup-error endpoints."""
from fastapi.testclient import TestClient

from hivemind_admin_panel.api import app, init_injected_objects


def test_health_keys():
    init_injected_objects(service=None, db=None, protocol=None)
    body = TestClient(app).get("/health").json()
    assert body["status"]
    assert "version" in body
    assert "timestamp" in body


def test_health_reports_clients_with_db(client):
    body = client.get("/health").json()
    # with an injected DB, health surfaces a client count
    assert "total_clients" in body


def test_startup_error_absent_returns_404(client, auth):
    init_injected_objects(service=None, db=None, protocol=None)
    assert client.get("/startup-error", headers=auth).status_code == 404


def test_startup_error_surfaced_when_present(auth):
    init_injected_objects(service=None, db=None, protocol=None,
                          startup_error=RuntimeError("boom"))
    try:
        body = TestClient(app).get("/startup-error", headers=auth).json()
        assert body["error_type"] == "RuntimeError"
        assert "boom" in body["error"]
    finally:
        init_injected_objects(service=None, db=None, protocol=None)
