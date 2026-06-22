# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: plugin discovery, install (stubbed) and enable."""
import subprocess
import types

import hivemind_admin_panel.api as api


def test_list_plugins(client, auth):
    body = client.get("/plugins", headers=auth).json()
    assert isinstance(body, list)
    if body:
        assert {"name", "package", "category", "installed"} <= set(body[0])


def test_install_success_is_stubbed(client, auth, monkeypatch):
    def fake_run(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(api.subprocess, "run", fake_run)
    body = client.post("/plugins/install", json={"package": "some-ovos-plugin"}, headers=auth).json()
    assert body["success"] is True


def test_install_failure_is_reported(client, auth, monkeypatch):
    def fake_run(cmd, **kw):
        return types.SimpleNamespace(returncode=1, stdout="", stderr="No matching distribution")
    monkeypatch.setattr(api.subprocess, "run", fake_run)
    body = client.post("/plugins/install", json={"package": "does-not-exist"}, headers=auth).json()
    assert body["success"] is False
    assert "No matching distribution" in body["message"]


def test_install_timeout_is_handled(client, auth, monkeypatch):
    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 120)
    monkeypatch.setattr(api.subprocess, "run", fake_run)
    body = client.post("/plugins/install", json={"package": "slow-pkg"}, headers=auth).json()
    assert body["success"] is False


def test_database_backends_listed(client, auth):
    body = client.get("/database/backends", headers=auth).json()
    assert isinstance(body, list)


def test_installed_hivemind_plugins(client, auth):
    for kind in ("agent", "database", "network", "binary"):
        resp = client.get(f"/plugins/installed/hivemind/{kind}", headers=auth)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


def test_solvers_discovery_is_stubbed(client, auth, monkeypatch):
    monkeypatch.setattr(api, "find_question_solver_plugins", lambda: {}, raising=False)
    monkeypatch.setattr(api, "find_chat_solver_plugins", lambda: {}, raising=False)
    monkeypatch.setattr(api, "find_chat_plugins", lambda: {}, raising=False)
    resp = client.get("/plugins/solvers", headers=auth)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
