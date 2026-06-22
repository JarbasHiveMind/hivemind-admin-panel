# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: authentication on the admin API."""
import base64


def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_protected_endpoint_requires_auth(client):
    assert client.get("/clients").status_code == 401


def test_wrong_credentials_rejected(client):
    bad = base64.b64encode(b"admin:wrong").decode()
    resp = client.get("/clients", headers={"Authorization": f"Basic {bad}"})
    assert resp.status_code == 401


def test_valid_credentials_accepted(client, auth):
    assert client.get("/clients", headers=auth).status_code == 200
