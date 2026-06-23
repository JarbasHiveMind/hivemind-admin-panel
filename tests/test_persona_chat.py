# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: multi-turn persona chat sessions (fake Persona, no real handlers)."""
import uuid

import pytest

import hivemind_admin_panel._persona_chat as pchat


class _FakePersonaSession:
    """Echoes with a turn counter to prove state carries across turns."""
    def __init__(self, name, config):
        self.id = uuid.uuid4().hex
        self.name = name
        self.config = config
        self.error = None
        self.last_used = 0.0
        self._t = []

    def say(self, message, lang="en-US"):
        self._t.append({"role": "user", "text": message, "ts": 0})
        n = sum(1 for m in self._t if m["role"] == "user")
        self._t.append({"role": "assistant", "text": f"turn {n}: {message}", "ts": 0})

    def messages(self, since=0):
        return self._t[since:], len(self._t)

    def close(self):
        pass


@pytest.fixture()
def fake_persona_chat(monkeypatch):
    monkeypatch.setattr(pchat, "PersonaChatSession", _FakePersonaSession)
    reg = pchat.PersonaChatSessions()
    monkeypatch.setattr(pchat, "PERSONA_CHAT", reg)
    return reg


def _make_persona(client, auth, name):
    client.post("/personas", json={"name": name, "handlers": ["x"]}, headers=auth)


def test_multi_turn_keeps_state(client, auth, fake_persona_chat):
    _make_persona(client, auth, "qa-mem")
    sid = client.post("/personas/qa-mem/chat/sessions", headers=auth).json()["session_id"]
    client.post(f"/personas/chat/sessions/{sid}/say", json={"message": "hi"}, headers=auth)
    client.post(f"/personas/chat/sessions/{sid}/say", json={"message": "again"}, headers=auth)
    texts = [m["text"] for m in
             client.get(f"/personas/chat/sessions/{sid}/messages", headers=auth).json()["messages"]]
    # turn counter proves the session persisted across calls (1, then 2)
    assert "turn 1: hi" in texts
    assert "turn 2: again" in texts


def test_persona_chat_passes_config(client, auth, fake_persona_chat):
    _make_persona(client, auth, "qa-cfg")
    client.post("/personas/qa-cfg/chat/sessions", headers=auth)
    sess = next(iter(fake_persona_chat._sessions.values()))
    assert sess.config.get("name") == "qa-cfg"
    assert "handlers" in sess.config


def test_persona_chat_unknown_persona_404(client, auth, fake_persona_chat):
    assert client.post("/personas/no-such/chat/sessions", headers=auth).status_code == 404


def test_persona_chat_say_validation(client, auth, fake_persona_chat):
    _make_persona(client, auth, "qa-v")
    sid = client.post("/personas/qa-v/chat/sessions", headers=auth).json()["session_id"]
    assert client.post(f"/personas/chat/sessions/{sid}/say",
                       json={"message": "  "}, headers=auth).status_code == 400
    assert client.post("/personas/chat/sessions/nope/say",
                       json={"message": "hi"}, headers=auth).status_code == 404


def test_persona_chat_start_surfaces_load_error(client, auth, monkeypatch):
    class _ErrSession(_FakePersonaSession):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.error = "no handler plugin installed"
    monkeypatch.setattr(pchat, "PersonaChatSession", _ErrSession)
    monkeypatch.setattr(pchat, "PERSONA_CHAT", pchat.PersonaChatSessions())
    _make_persona(client, auth, "qa-err")
    r = client.post("/personas/qa-err/chat/sessions", headers=auth)
    assert r.status_code == 502
    assert "no handler plugin installed" in r.json()["detail"]


def test_one_session_per_persona(fake_persona_chat):
    a = fake_persona_chat.create("p", {})
    b = fake_persona_chat.create("p", {})
    assert fake_persona_chat.get(a.id) is None
    assert fake_persona_chat.get(b.id) is not None
