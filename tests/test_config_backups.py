# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: config snapshots + rollback."""


def test_config_change_creates_snapshot(client, auth):
    before = len(client.get("/config/backups", headers=auth).json())
    # a config write snapshots the PRE-change server.json
    assert client.post("/config", json={"config": {"_qa_marker": "v1"}}, headers=auth).status_code == 200
    after = client.get("/config/backups", headers=auth).json()
    assert len(after) >= before + 1
    assert all({"file", "size", "mtime"} <= set(s) for s in after)


def test_manual_snapshot(client, auth):
    r = client.post("/config/backups", headers=auth)
    assert r.status_code == 200
    name = r.json()["file"]
    assert any(s["file"] == name for s in client.get("/config/backups", headers=auth).json())


def test_restore_reverts_config(client, auth):
    from hivemind_core.config import get_server_config
    client.post("/config", json={"config": {"_qa": "A"}}, headers=auth)
    snap = client.post("/config/backups", headers=auth).json()["file"]   # captured with _qa=A
    client.post("/config", json={"config": {"_qa": "B"}}, headers=auth)
    assert get_server_config().get("_qa") == "B"
    assert client.post("/config/backups/restore", json={"file": snap}, headers=auth).status_code == 200
    assert get_server_config().get("_qa") == "A"
    # admin creds survived the round-trip (the snapshot is a full server.json)
    assert get_server_config().get("admin_user") == "admin"


def test_diff_backup_shows_changes(client, auth):
    client.post("/config", json={"config": {"_qa_diff": "old"}}, headers=auth)
    snap = client.post("/config/backups", headers=auth).json()["file"]   # captured with _qa_diff=old
    client.post("/config", json={"config": {"_qa_diff": "new"}}, headers=auth)
    d = client.get(f"/config/backups/diff?file={snap}", headers=auth).json()
    # reverting to the snapshot would change _qa_diff back from "new" to "old"
    assert "_qa_diff" in d["changed"]
    assert d["changed"]["_qa_diff"]["to"] == "old"


def test_restore_rejects_path_traversal(client, auth):
    assert client.post("/config/backups/restore",
                       json={"file": "../server.json"}, headers=auth).status_code == 400


def test_restore_unknown_404(client, auth):
    assert client.post("/config/backups/restore",
                       json={"file": "server-does-not-exist.json"}, headers=auth).status_code == 404


def test_backup_restore_admin_only(client):
    import base64
    from hivemind_core.config import get_server_config
    cfg = get_server_config()
    cfg["users"] = [{"username": "ops", "password": "opspass", "role": "operator"}]
    cfg.store()
    try:
        op = {"Authorization": "Basic " + base64.b64encode(b"ops:opspass").decode()}
        assert client.post("/config/backups", headers=op).status_code == 403
        assert client.post("/config/backups/restore", json={"file": "x.json"}, headers=op).status_code == 403
        # listing is allowed for any authed user
        assert client.get("/config/backups", headers=op).status_code == 200
    finally:
        cfg2 = get_server_config()
        cfg2["users"] = []
        cfg2.store()
