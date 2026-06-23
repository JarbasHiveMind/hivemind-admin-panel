# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: plugin lifecycle — uninstall (with active-module guard), upgrade, versions."""
import pytest

import hivemind_admin_panel.api as api


class _Proc:
    def __init__(self, returncode=0, stdout="ok", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture()
def stub_pip(monkeypatch):
    """Capture uv/pip invocations instead of really (un)installing."""
    calls = []

    def fake_run(cmd, capture_output=True, text=True, timeout=120):
        calls.append(cmd)
        return _Proc(0)

    monkeypatch.setattr(api.subprocess, "run", fake_run)
    return calls


def test_uninstall_blocked_for_active_module(client, auth, stub_pip):
    # the test harness activates hivemind-json-db-plugin as the database backend
    r = client.post("/plugins/uninstall", json={"package": "hivemind-json-db-plugin"}, headers=auth)
    assert r.status_code == 400
    assert "active" in r.json()["detail"].lower()
    assert stub_pip == []          # must never shell out for a blocked uninstall


def test_uninstall_allowed_for_inactive_package(client, auth, stub_pip):
    r = client.post("/plugins/uninstall", json={"package": "ovos-tts-plugin-mimic3"}, headers=auth)
    assert r.status_code == 200 and r.json()["success"] is True
    assert any("uninstall" in c for c in stub_pip[0])


def test_upgrade_runs_with_upgrade_flag(client, auth, stub_pip):
    r = client.post("/plugins/upgrade", json={"package": "ovos-tts-plugin-mimic3"}, headers=auth)
    assert r.status_code == 200 and r.json()["success"] is True
    assert any("--upgrade" in c for c in stub_pip[0])


def test_lifecycle_endpoints_require_admin(client, make_client):
    # an operator (non-admin) is forbidden from uninstall/upgrade
    import base64
    from hivemind_core.config import get_server_config
    cfg = get_server_config()
    cfg["users"] = [{"username": "ops", "password": "opspass", "role": "operator"}]
    cfg.store()
    try:
        op = {"Authorization": "Basic " + base64.b64encode(b"ops:opspass").decode()}
        assert client.post("/plugins/uninstall", json={"package": "x"}, headers=op).status_code == 403
        assert client.post("/plugins/upgrade", json={"package": "x"}, headers=op).status_code == 403
    finally:
        cfg["users"] = []
        cfg.store()


def test_plugins_list_exposes_version(client, auth):
    items = client.get("/plugins", headers=auth).json()
    assert isinstance(items, list)
    assert all("version" in p for p in items)


def test_pkg_version_helper():
    assert api._pkg_version("hivemind-core") is not None
    assert api._pkg_version("definitely-not-a-real-pkg-xyz123") is None
