# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: server configuration endpoints."""


def test_get_config(client, auth):
    cfg = client.get("/config", headers=auth)
    assert cfg.status_code == 200
    assert isinstance(cfg.json(), dict)


def test_get_defaults(client, auth):
    body = client.get("/config/defaults", headers=auth).json()
    assert "allowed_encodings" in body


def test_post_config_persists(client, auth):
    current = client.get("/config", headers=auth).json()
    current["binarize"] = True
    assert client.post("/config", json={"config": current}, headers=auth).status_code == 200
    assert client.get("/config", headers=auth).json()["binarize"] is True


def test_validate_config(client, auth):
    cfg = client.get("/config", headers=auth).json()
    result = client.post("/config/validate", json={"config": cfg}, headers=auth)
    assert result.status_code == 200
    body = result.json()
    assert set(body) >= {"valid", "errors", "warnings"}


def test_restart_without_service_reports_error(client, auth):
    # no _service injected -> restart cannot proceed and reports an error status
    body = client.post("/config/restart", headers=auth).json()
    assert body["status"] == "error"
