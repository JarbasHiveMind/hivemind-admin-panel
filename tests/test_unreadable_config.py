"""An unreadable server.json is never written over, and the operator can repair it."""
import json
import sys

import pytest

from tests.conftest import ADMIN_USER, ADMIN_PASS


@pytest.fixture()
def bearer(client):
    login = client.post("/auth/login", json={"username": ADMIN_USER,
                                             "password": ADMIN_PASS})
    assert login.status_code == 200
    return {"Authorization": "Bearer " + login.json()["token"]}


@pytest.fixture()
def corrupt(client, bearer):
    """server.json made unparseable while a session is open; restored afterwards."""
    from hivemind_admin_panel.api import _server_json_path
    path = _server_json_path()
    good = path.read_bytes()
    bad = b"{ this is not json"
    path.write_bytes(bad)
    yield path, good, bad
    path.write_bytes(good)


def test_restore_snapshot_repairs_a_corrupt_file(client, bearer, corrupt):
    from hivemind_admin_panel.api import _config_backups_dir
    path, good, _ = corrupt
    backups = _config_backups_dir()
    backups.mkdir(parents=True, exist_ok=True)
    (backups / "server-good.json").write_bytes(good)
    r = client.post("/config/backups/restore", json={"file": "server-good.json"},
                    headers=bearer)
    assert r.status_code == 200, r.text
    assert json.loads(path.read_text()) == json.loads(good)
    assert path.stat().st_mode & 0o777 == 0o600


def test_setup_status_leaves_a_corrupt_file_alone(client, bearer, corrupt):
    path, _, bad = corrupt
    r = client.get("/setup/status", headers=bearer)
    assert r.status_code == 200
    assert r.json()["database_error"]
    assert path.read_bytes() == bad


def test_startup_refuses_a_corrupt_file_and_leaves_it_alone(corrupt, monkeypatch, capsys):
    from hivemind_admin_panel.__main__ import main
    path, _, bad = corrupt
    monkeypatch.setattr(sys, "argv", ["hivemind-admin-panel", "--no-core"])
    import uvicorn

    def served(*a, **kw):
        raise AssertionError("the panel started serving")

    monkeypatch.setattr(uvicorn, "run", served)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code not in (0, None)
    assert str(path) in str(exc.value.code)
    assert path.read_bytes() == bad


def test_requests_get_a_503_that_says_why(client, bearer, corrupt):
    path, _, bad = corrupt
    r = client.get("/clients", headers=bearer)
    assert r.status_code == 503
    assert "server.json is unreadable" in r.json()["detail"]
    login = client.post("/auth/login", json={"username": ADMIN_USER,
                                             "password": ADMIN_PASS})
    assert login.status_code == 503
    assert "server.json is unreadable" in login.json()["detail"]
    assert path.read_bytes() == bad


def test_no_request_path_writes_a_corrupt_file(client, bearer, corrupt):
    path, _, bad = corrupt
    for method, url in (("get", "/clients"), ("post", "/clients"), ("get", "/health"),
                        ("get", "/setup/status"), ("get", "/topology")):
        getattr(client, method)(url, headers=bearer)
        assert path.read_bytes() == bad, url


def test_default_credentials_never_authenticate_while_unreadable(client, corrupt):
    from hivemind_admin_panel.api import _config_backups_dir
    path, good, bad = corrupt
    backups = _config_backups_dir()
    backups.mkdir(parents=True, exist_ok=True)
    (backups / "server-good.json").write_bytes(good)
    import base64
    basic = {"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()}
    for method, url, body in (("get", "/config", None), ("get", "/health", None),
                              ("post", "/config/backups/restore",
                               {"file": "server-good.json"})):
        r = getattr(client, method)(url, headers=basic, **({"json": body} if body else {}))
        assert r.status_code == 503, url
        assert "server.json is unreadable" in r.json()["detail"]
    login = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 503
    assert path.read_bytes() == bad


def test_a_commented_server_json_is_readable(client, bearer, monkeypatch):
    from hivemind_admin_panel.api import _server_json_path
    import uvicorn
    path = _server_json_path()
    original = path.read_text()
    path.write_text("// operator note\n" + original)
    try:
        assert client.get("/config", headers=bearer).status_code == 200

        def served(*a, **kw):
            raise RuntimeError("served")

        monkeypatch.setattr(uvicorn, "run", served)
        monkeypatch.setattr(sys, "argv", ["hivemind-admin-panel", "--no-core"])
        from hivemind_admin_panel.__main__ import main
        with pytest.raises(RuntimeError, match="served"):
            main()
    finally:
        path.write_text(original)


def _snapshot(good):
    from hivemind_admin_panel.api import _config_backups_dir
    backups = _config_backups_dir()
    backups.mkdir(parents=True, exist_ok=True)
    (backups / "server-good.json").write_bytes(good)


def test_restore_keeps_a_copy_of_the_broken_file(client, bearer, corrupt):
    path, good, bad = corrupt
    _snapshot(good)
    r = client.post("/config/backups/restore", json={"file": "server-good.json"},
                    headers=bearer)
    assert r.status_code == 200
    kept = path.with_name(r.json()["unreadable_copy"])
    assert kept.name.startswith("server.json.unreadable-")
    assert kept.read_bytes() == bad


def test_restore_replaces_the_file_atomically(client, bearer, corrupt, monkeypatch):
    import os
    path, good, bad = corrupt
    _snapshot(good)
    seen = []
    real_fsync = os.fsync

    def fsync(fd):
        seen.append(path.read_bytes())
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    r = client.post("/config/backups/restore", json={"file": "server-good.json"},
                    headers=bearer)
    assert r.status_code == 200
    assert seen, "the snapshot was not fsynced before it replaced the file"
    assert seen[0] == bad       # until the replace, server.json is the whole old file
    assert not list(path.parent.glob("*.tmp"))
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text()) == json.loads(good)


def test_a_session_opened_on_a_file_without_a_secret_survives_breakage(client):
    from hivemind_admin_panel.api import _server_json_path
    path = _server_json_path()
    good = path.read_bytes()
    cfg = json.loads(good)
    cfg.pop("admin_token_secret", None)
    path.write_text(json.dumps(cfg))
    try:
        login = client.post("/auth/login", json={"username": ADMIN_USER,
                                                 "password": ADMIN_PASS})
        assert login.status_code == 200
        headers = {"Authorization": "Bearer " + login.json()["token"]}
        path.write_bytes(b"{ broken")
        assert client.get("/config", headers=headers).status_code == 500
    finally:
        path.write_bytes(good)


def test_a_failed_restore_leaves_server_json_untouched(client, bearer, corrupt, monkeypatch):
    import base64
    import os
    path, good, bad = corrupt
    _snapshot(good)

    def full(fd):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "fsync", full)
    r = client.post("/config/backups/restore", json={"file": "server-good.json"},
                    headers=bearer)
    assert r.status_code == 500
    assert "No space left" in r.json()["detail"]
    assert path.read_bytes() == bad
    assert not list(path.parent.glob("*.tmp"))
    basic = {"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()}
    assert client.get("/config", headers=basic).status_code == 503
    assert path.read_bytes() == bad


def test_restore_keeps_a_symlinked_server_json_a_symlink(client, bearer, corrupt):
    import os
    path, good, bad = corrupt
    target = path.with_name("real-server.json")
    target.write_bytes(bad)
    path.unlink()
    os.symlink(target, path)
    _snapshot(good)
    r = client.post("/config/backups/restore", json={"file": "server-good.json"},
                    headers=bearer)
    assert r.status_code == 200
    assert path.is_symlink()
    assert json.loads(target.read_text()) == json.loads(good)
    assert (path.parent / r.json()["unreadable_copy"]).read_bytes() == bad
    path.unlink()
    target.unlink()
