# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: client-impersonation chat (with a non-networked fake bus session)."""
import uuid

import pytest

import hivemind_admin_panel._chat as chatmod


class _FakeSession:
    """Stand-in for ImpersonationSession that echoes instead of touching a hub."""
    def __init__(self, client_id, name, key, password, crypto_key, host, port):
        self.id = uuid.uuid4().hex
        self.client_id = client_id
        self.name = name
        self.error = None
        self.last_used = 0.0
        self.creds = (key, password, crypto_key, host, port)
        self._t = []

    def say(self, utterance, lang="en-us"):
        self._t.append({"role": "user", "text": utterance, "ts": 0})
        self._t.append({"role": "assistant", "text": f"echo: {utterance}", "ts": 0})

    def messages(self, since=0):
        return self._t[since:], len(self._t)

    def close(self):
        pass


@pytest.fixture()
def fake_chat(monkeypatch):
    monkeypatch.setattr(chatmod, "ImpersonationSession", _FakeSession)
    reg = chatmod.ChatSessions()
    monkeypatch.setattr(chatmod, "CHAT", reg)
    return reg


def test_impersonation_roundtrip(client, auth, make_client, fake_chat):
    c = make_client(name="kitchen")
    r = client.post("/chat/sessions", json={"client_id": c["client_id"]}, headers=auth)
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    assert r.json()["name"] == "kitchen"

    assert client.post(f"/chat/sessions/{sid}/say",
                       json={"utterance": "hello there"}, headers=auth).status_code == 200
    body = client.get(f"/chat/sessions/{sid}/messages", headers=auth).json()
    roles = [(m["role"], m["text"]) for m in body["messages"]]
    assert ("user", "hello there") in roles
    assert ("assistant", "echo: hello there") in roles
    assert body["total"] == 2

    # incremental polling with ?since
    assert client.get(f"/chat/sessions/{sid}/messages?since=2", headers=auth).json()["messages"] == []
    # session is listed, then removed on delete
    assert any(s["session_id"] == sid for s in client.get("/chat/sessions", headers=auth).json())
    assert client.delete(f"/chat/sessions/{sid}", headers=auth).status_code == 200


def test_impersonation_passes_real_credentials(client, auth, make_client, fake_chat):
    c = make_client(name="creds", crypto_key="0123456789abcdef")
    full = client.get(f"/clients/{c['client_id']}", headers=auth).json()
    client.post("/chat/sessions", json={"client_id": c["client_id"]}, headers=auth)
    sess = next(s for s in fake_chat._sessions.values())
    key, password, crypto_key, host, port = sess.creds
    assert key == full["api_key"]
    assert crypto_key == "0123456789abcdef"
    assert host == "127.0.0.1"          # loopback to the in-process hub


def test_chat_unknown_client_404(client, auth, fake_chat):
    assert client.post("/chat/sessions", json={"client_id": 999999}, headers=auth).status_code == 404


def test_chat_say_empty_400(client, auth, make_client, fake_chat):
    c = make_client(name="x")
    sid = client.post("/chat/sessions", json={"client_id": c["client_id"]}, headers=auth).json()["session_id"]
    assert client.post(f"/chat/sessions/{sid}/say", json={"utterance": "   "}, headers=auth).status_code == 400


def test_chat_unknown_session_404(client, auth, fake_chat):
    assert client.get("/chat/sessions/nope/messages", headers=auth).status_code == 404
    assert client.post("/chat/sessions/nope/say", json={"utterance": "hi"}, headers=auth).status_code == 404


def test_chat_start_surfaces_connect_error(client, auth, make_client, monkeypatch):
    class _ErrSession(_FakeSession):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.error = "handshake timed out"
    monkeypatch.setattr(chatmod, "ImpersonationSession", _ErrSession)
    monkeypatch.setattr(chatmod, "CHAT", chatmod.ChatSessions())
    c = make_client(name="bad")
    r = client.post("/chat/sessions", json={"client_id": c["client_id"]}, headers=auth)
    assert r.status_code == 502
    assert "handshake timed out" in r.json()["detail"]


def test_denial_is_surfaced_in_transcript(monkeypatch):
    """A `hive.policy.denied` bus event must show up as a visible error message,
    not vanish silently (a blocked utterance would otherwise look identical to
    a dead agent)."""
    monkeypatch.setattr(chatmod.ImpersonationSession, "_connect", lambda self, *a, **k: None)
    sess = chatmod.ImpersonationSession(1, "n", "k", "p", "c", "127.0.0.1", 5678)

    class _Msg:
        data = {"denied_type": "recognizer_loop:utterance", "reason": "not in allowed_types"}

    sess._on_denied(_Msg())
    msgs, total = sess.messages()
    assert total == 1
    assert msgs[0]["role"] == "error"
    assert "recognizer_loop:utterance" in msgs[0]["text"]
    assert "not in this client's allowed message types" in msgs[0]["text"]


def test_registry_one_session_per_client(fake_chat):
    a = fake_chat.create(1, "n", "k", "p", "c", "127.0.0.1", 5678)
    b = fake_chat.create(1, "n", "k", "p", "c", "127.0.0.1", 5678)
    # creating a second for the same client replaces the first
    assert fake_chat.get(a.id) is None
    assert fake_chat.get(b.id) is not None
    assert len(fake_chat.list_active()) == 1
