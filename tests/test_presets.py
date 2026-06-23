# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: reusable plugin presets (store + CRUD + load-check)."""
import base64


def test_preset_crud_roundtrip(client, auth):
    body = {"name": "whisper-gpu", "module": "ovos-stt-plugin-fasterwhisper",
            "config": {"model": "large-v3", "device": "cuda"}}
    r = client.post("/presets/stt", json=body, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["type"] == "stt" and r.json()["source"] == "plugin"

    got = client.get("/presets/stt/whisper-gpu", headers=auth).json()
    assert got["config"]["device"] == "cuda"

    # appears in the type listing alongside the installed-modules choices
    listing = client.get("/presets/stt", headers=auth).json()
    assert "whisper-gpu" in listing["presets"]
    assert "installed_modules" in listing

    # update
    client.put("/presets/stt/whisper-gpu", json={"config": {"model": "small"}}, headers=auth)
    assert client.get("/presets/stt/whisper-gpu", headers=auth).json()["config"] == {"model": "small"}

    # delete
    assert client.delete("/presets/stt/whisper-gpu", headers=auth).status_code == 200
    assert client.get("/presets/stt/whisper-gpu", headers=auth).status_code == 404


def test_preset_test_loadcheck(client, auth):
    # bogus module -> not installed
    client.post("/presets/stt", json={"name": "bogus", "module": "no-such-stt-xyz"}, headers=auth)
    r = client.post("/presets/stt/bogus/test", headers=auth).json()
    assert r["ok"] is False and "not installed" in r["message"]

    # a really-installed module (agent/network plugins ship with the stack) -> ok
    installed = client.get("/presets/network", headers=auth).json()["installed_modules"]
    assert installed, "expected at least one installed network protocol"
    client.post("/presets/network", json={"name": "ws", "module": installed[0]}, headers=auth)
    assert client.post("/presets/network/ws/test", headers=auth).json()["ok"] is True


def test_preset_validation(client, auth):
    assert client.post("/presets/nope", json={"name": "x", "module": "y"}, headers=auth).status_code == 400
    assert client.post("/presets/stt", json={"name": "bad name!", "module": "y"}, headers=auth).status_code == 400
    client.post("/presets/tts", json={"name": "dup", "module": "m"}, headers=auth)
    assert client.post("/presets/tts", json={"name": "dup", "module": "m"}, headers=auth).status_code == 409


def test_preset_apply_agent_writes_slot(client, auth):
    installed = client.get("/presets/agent", headers=auth).json()["installed_modules"]
    assert installed, "expected an installed agent protocol"
    client.post("/presets/agent", json={"name": "a1", "module": installed[0],
                                         "config": {"host": "127.0.0.1", "port": 8181}}, headers=auth)
    r = client.post("/presets/agent/a1/apply", headers=auth)
    assert r.status_code == 200 and r.json()["module"] == installed[0]
    from hivemind_core.config import get_server_config
    cfg = get_server_config()
    assert cfg["agent_protocol"]["module"] == installed[0]
    assert cfg["agent_protocol"][installed[0]]["port"] == 8181


def test_preset_apply_speech_rejected(client, auth):
    client.post("/presets/stt", json={"name": "s1", "module": "x"}, headers=auth)
    r = client.post("/presets/stt/s1/apply", headers=auth)
    assert r.status_code == 400 and "Binary Protocol" in r.json()["detail"]


def test_preset_writes_are_admin_only(client):
    from hivemind_core.config import get_server_config
    cfg = get_server_config()
    cfg["users"] = [{"username": "ops", "password": "opspass", "role": "operator"}]
    cfg.store()
    try:
        op = {"Authorization": "Basic " + base64.b64encode(b"ops:opspass").decode()}
        assert client.post("/presets/stt", json={"name": "x", "module": "m"}, headers=op).status_code == 403
        assert client.get("/presets/stt", headers=op).status_code == 200   # read allowed
    finally:
        cfg2 = get_server_config(); cfg2["users"] = []; cfg2.store()
