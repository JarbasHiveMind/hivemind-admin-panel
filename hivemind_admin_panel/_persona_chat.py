# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Multi-turn persona test chat.

The one-shot ``POST /personas/{name}/chat`` builds a fresh ``Persona`` per call, so
memory never accumulates. These sessions keep a single live ``Persona`` + ``Session``
+ conversation history across turns, so the persona's memory module and the running
context are exercised exactly as they would be in production. "Reset" = a new
session = a fresh Persona instance (clears short-term memory).
"""
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple


class PersonaChatSession:
    """One live persona instance and its multi-turn transcript."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.id = uuid.uuid4().hex
        self.name = name
        self.error: Optional[str] = None
        self.created = time.time()
        self.last_used = time.time()
        self._transcript: List[Dict[str, Any]] = []
        self._messages: List[Any] = []   # AgentMessage history
        self._lock = threading.Lock()
        self.persona = None
        self.session = None
        try:
            from ovos_persona import Persona
            from ovos_bus_client.session import Session
            self.persona = Persona(name, config)
            self.session = Session(lang="en-US")
        except Exception as e:  # noqa: BLE001 — surfaced to the caller
            self.error = str(e)

    def _append(self, role: str, text: str):
        with self._lock:
            self._transcript.append({"role": role, "text": text, "ts": time.time()})

    def say(self, message: str, lang: str = "en-US"):
        from ovos_plugin_manager.templates.agents import AgentMessage, MessageRole
        self.last_used = time.time()
        if self.session is not None and lang:
            self.session.lang = lang
        self._append("user", message)
        self._messages.append(AgentMessage(role=MessageRole.USER, content=message))
        try:
            reply = self.persona.chat(list(self._messages), self.session) or ""
        except Exception as e:  # noqa: BLE001
            self._append("system", f"persona error: {e}")
            return
        self._append("assistant", reply)
        self._messages.append(AgentMessage(role=MessageRole.ASSISTANT, content=reply))

    def messages(self, since: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        with self._lock:
            self.last_used = time.time()
            return list(self._transcript[since:]), len(self._transcript)

    def close(self):
        self.persona = None


class PersonaChatSessions:
    """Bounded, idle-reaped registry of persona chat sessions (one per persona)."""

    def __init__(self, max_sessions: int = 12, max_idle: float = 900.0):
        self._sessions: Dict[str, PersonaChatSession] = {}
        self._lock = threading.Lock()
        self._max = max_sessions
        self._max_idle = max_idle

    def _reap(self):
        now = time.time()
        for sid, s in list(self._sessions.items()):
            if now - s.last_used > self._max_idle:
                s.close()
                self._sessions.pop(sid, None)

    def create(self, name: str, config: Dict[str, Any]) -> PersonaChatSession:
        with self._lock:
            self._reap()
            # one live session per persona name: replace any existing
            for sid, s in list(self._sessions.items()):
                if s.name == name:
                    s.close()
                    self._sessions.pop(sid, None)
            if len(self._sessions) >= self._max:
                oldest = min(self._sessions.values(), key=lambda s: s.last_used)
                oldest.close()
                self._sessions.pop(oldest.id, None)
        sess = PersonaChatSession(name, config)
        with self._lock:
            self._sessions[sess.id] = sess
        return sess

    def get(self, sid: str) -> Optional[PersonaChatSession]:
        return self._sessions.get(sid)

    def close(self, sid: str):
        with self._lock:
            s = self._sessions.pop(sid, None)
        if s:
            s.close()


PERSONA_CHAT = PersonaChatSessions()
