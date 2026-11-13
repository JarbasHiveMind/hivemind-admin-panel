# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: the security self-check that drives the first-run gate + dashboard."""
import pytest


@pytest.fixture()
def runtime_reset():
    """Restore api runtime info (run_mode/host) after a test mutates it."""
    from hivemind_admin_panel import api
    before = (api._run_mode, api._bound_host)
    yield api
    api._run_mode, api._bound_host = before


def test_setup_status_shape(client, auth):
    body = client.get("/setup/status", headers=auth).json()
    for key in ("default_credentials", "has_clients", "client_count",
                "bound_host", "exposed", "run_mode", "checks", "secure", "warnings"):
        assert key in body, key
    assert isinstance(body["checks"], list) and body["checks"]
    for c in body["checks"]:
        assert {"id", "label", "ok", "severity", "hint"} <= set(c)
        assert c["severity"] in ("critical", "warning", "info")


def test_non_default_creds_are_secure(client, auth):
    # the harness uses a strong non-default password
    body = client.get("/setup/status", headers=auth).json()
    assert body["default_credentials"] is False
    pw_check = next(c for c in body["checks"] if c["id"] == "admin_password")
    assert pw_check["ok"] is True
    assert body["secure"] is True


def test_default_creds_block_secure_verdict(client, runtime_reset):
    import base64
    from hivemind_core.config import get_server_config
    cfg = get_server_config()
    orig = cfg.get("admin_pass")
    cfg["admin_pass"] = "admin"
    cfg.store()
    # the auth header must match the (now default) password to stay authenticated
    tok = base64.b64encode(b"admin:admin").decode()
    auth = {"Authorization": f"Basic {tok}"}
    try:
        body = client.get("/setup/status", headers=auth).json()
        assert body["default_credentials"] is True
        assert body["secure"] is False
        pw = next(c for c in body["checks"] if c["id"] == "admin_password")
        assert pw["ok"] is False and pw["severity"] == "critical"
        # the critical hint is surfaced as a warning string too
        assert any("password" in w.lower() for w in body["warnings"])
    finally:
        cfg["admin_pass"] = orig
        cfg.store()


def test_loopback_bind_is_not_exposed(client, auth, runtime_reset):
    runtime_reset.set_runtime_info(run_mode="in-process", host="127.0.0.1")
    body = client.get("/setup/status", headers=auth).json()
    assert body["exposed"] is False
    assert body["run_mode"] == "in-process"
    bind = next(c for c in body["checks"] if c["id"] == "bind_host")
    assert bind["ok"] is True


def test_public_bind_flagged_as_exposed(client, auth, runtime_reset):
    runtime_reset.set_runtime_info(run_mode="in-process", host="0.0.0.0")
    body = client.get("/setup/status", headers=auth).json()
    assert body["exposed"] is True
    assert body["bound_host"] == "0.0.0.0"
    bind = next(c for c in body["checks"] if c["id"] == "bind_host")
    assert bind["ok"] is False and bind["severity"] == "warning"
    assert any("0.0.0.0" in w for w in body["warnings"])


def test_health_reports_run_mode(client, runtime_reset):
    runtime_reset.set_runtime_info(run_mode="panel-only", host="127.0.0.1")
    body = client.get("/health").json()
    assert body["run_mode"] == "panel-only"


def test_acknowledge_warning_clears_it(client, auth, runtime_reset):
    runtime_reset.set_runtime_info(run_mode="in-process", host="0.0.0.0")
    from hivemind_core.config import get_server_config
    cfg = get_server_config()
    cfg["setup_acked"] = []
    cfg.store()
    try:
        # exposed bind starts as an un-acknowledged warning -> not clean
        before = client.get("/setup/status", headers=auth).json()
        assert before["clean"] is False
        assert any("0.0.0.0" in w for w in before["warnings"])

        acked = client.post("/setup/ack", json={"id": "bind_host"}, headers=auth).json()
        bind = next(c for c in acked["checks"] if c["id"] == "bind_host")
        assert bind["acknowledged"] is True
        assert acked["clean"] is True          # warning no longer nags
        assert acked["secure"] is True         # criticals still pass
        assert not any("0.0.0.0" in w for w in acked["warnings"])

        # un-acknowledge restores the nag
        restored = client.delete("/setup/ack/bind_host", headers=auth).json()
        assert restored["clean"] is False
    finally:
        cfg["setup_acked"] = []
        cfg.store()


def test_cannot_acknowledge_a_critical(client, auth):
    from hivemind_core.config import get_server_config
    cfg = get_server_config()
    try:
        r = client.post("/setup/ack", json={"id": "admin_password"}, headers=auth)
        assert r.status_code == 400          # criticals can't be dismissed
    finally:
        cfg["setup_acked"] = []
        cfg.store()


def test_acknowledge_unknown_check_404s(client, auth):
    assert client.post("/setup/ack", json={"id": "nope"}, headers=auth).status_code == 404
