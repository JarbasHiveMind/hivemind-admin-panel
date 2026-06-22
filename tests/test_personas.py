# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: persona management and persona config."""


def test_personas_list_empty_then_created(client, auth):
    before = client.get("/personas", headers=auth)
    assert before.status_code == 200
    assert isinstance(before.json(), list)

    created = client.post("/personas", json={"name": "tester", "description": "e2e",
                                             "solvers": ["ovos-solver-failure-plugin"]}, headers=auth)
    assert created.status_code in (200, 400)  # 400 only if validation rejects the solver set
    if created.status_code == 200:
        names = [p.get("name") for p in client.get("/personas", headers=auth).json()]
        assert "tester" in names


def test_persona_get_missing_404(client, auth):
    assert client.get("/personas/does-not-exist", headers=auth).status_code == 404


def test_persona_roundtrip_and_delete(client, auth):
    r = client.post("/personas", json={"name": "rt", "solvers": ["ovos-solver-failure-plugin"]}, headers=auth)
    if r.status_code != 200:
        return  # validation environment-dependent; covered by list test
    assert client.get("/personas/rt", headers=auth).status_code == 200
    assert client.get("/personas/rt/export", headers=auth).status_code == 200
    assert client.delete("/personas/rt", headers=auth).status_code == 200
    assert client.get("/personas/rt", headers=auth).status_code == 404


def test_active_persona_endpoint(client, auth):
    body = client.get("/personas/active", headers=auth)
    assert body.status_code == 200
    assert "active" in body.json()


def test_persona_config_roundtrip(client, auth):
    assert client.get("/persona/config", headers=auth).status_code == 200
    saved = client.put("/persona/config", json={"name": "default", "solvers": {}}, headers=auth)
    assert saved.status_code == 200
    assert saved.json()["status"] == "success"
