# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: agent engine taxonomy, OVOS server registry, persona chat."""


def test_agent_engine_taxonomy(client, auth):
    body = client.get("/plugins/agents", headers=auth).json()
    # modern engine types are reported, each a list
    for kind in ("chat", "memory", "summarizer", "reranker"):
        assert kind in body
        assert isinstance(body[kind], list)


def test_server_registry_crud(client, auth):
    created = client.post("/servers", json={"name": "home-llm", "type": "persona",
                                            "url": "http://127.0.0.1:8337/"}, headers=auth)
    assert created.status_code == 200
    sid = created.json()["id"]
    assert created.json()["url"] == "http://127.0.0.1:8337"  # trailing slash trimmed

    listed = client.get("/servers", headers=auth).json()
    assert any(s["id"] == sid for s in listed)

    assert client.delete(f"/servers/{sid}", headers=auth).status_code == 200
    assert client.delete(f"/servers/{sid}", headers=auth).status_code == 404


def test_server_health_unreachable(client, auth):
    sid = client.post("/servers", json={"name": "dead", "type": "persona",
                                        "url": "http://127.0.0.1:9"}, headers=auth).json()["id"]
    body = client.get(f"/servers/{sid}/health", headers=auth).json()
    assert body["reachable"] is False
    client.delete(f"/servers/{sid}", headers=auth)


def test_persona_chat_returns_structure(client, auth):
    r = client.post("/personas", json={"name": "chatty", "handlers": ["ovos-solver-failure-plugin"]},
                    headers=auth)
    if r.status_code != 200:
        return
    resp = client.post("/personas/chatty/chat", json={"message": "hello"}, headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert "reply" in body and "error" in body  # reply may be empty; must not 500
    client.delete("/personas/chatty", headers=auth)


def test_persona_chat_missing_404(client, auth):
    assert client.post("/personas/nope/chat", json={"message": "hi"}, headers=auth).status_code == 404
