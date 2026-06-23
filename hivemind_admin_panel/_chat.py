# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Server-side client impersonation: chat through the hub *as* a registered client.

The admin picks a client; the panel opens a real ``HiveMessageBusClient`` with that
client's credentials, connects to the hub like any satellite would, sends typed
utterances, and collects the agent's ``speak`` replies. This exercises the genuine
path — ACL enforcement, routing, the agent backend — not a simulation.
"""
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple


class ImpersonationSession:
    """One live impersonated client connection and its chat transcript."""

    def __init__(self, client_id: int, name: str, key: str, password: str,
                 crypto_key: Optional[str], host: str, port: int):
        self.id = uuid.uuid4().hex
        self.client_id = client_id
        self.name = name
        self.error: Optional[str] = None
        self.created = time.time()
        self.last_used = time.time()
        self._transcript: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self.bus = None
        self._connect(key, password, crypto_key, host, port)

    def _connect(self, key, password, crypto_key, host, port):
        from ovos_utils.fakebus import FakeBus
        from hivemind_bus_client import HiveMessageBusClient

        self.bus = HiveMessageBusClient(
            key=key, password=password, crypto_key=crypto_key,
            host=host, port=port, self_signed=True, useragent="HiveMindAdminChat",
        )
        self.bus.on_mycroft("speak", self._on_speak)
        self.bus.on_mycroft("hive.complete_intent_failure", self._on_fail)

        def _do():
            try:
                self.bus.connect(FakeBus())
            except Exception as e:   # noqa: BLE001 - surfaced to the caller
                self.error = str(e)

        threading.Thread(target=_do, daemon=True).start()
        if not self.bus.handshake_event.wait(15):
            self.error = self.error or (
                "handshake timed out — is the hub running and does this client have "
                "a crypto key?")

    # --- bus callbacks (run on the websocket thread) ---------------------------
    def _on_speak(self, message):
        utt = ""
        try:
            utt = message.data.get("utterance") or message.data.get("text") or ""
        except Exception:
            pass
        if utt:
            self._append("assistant", utt)

    def _on_fail(self, message):
        self._append("system", "the hub reported no skill/agent handled that utterance")

    def _append(self, role: str, text: str):
        with self._lock:
            self._transcript.append({"role": role, "text": text, "ts": time.time()})

    # --- public API ------------------------------------------------------------
    def say(self, utterance: str, lang: str = "en-us"):
        from hivemind_bus_client.message import HiveMessage, HiveMessageType
        from ovos_bus_client.message import Message

        self.last_used = time.time()
        self._append("user", utterance)
        self.bus.emit(HiveMessage(
            HiveMessageType.BUS,
            Message("recognizer_loop:utterance", {"utterances": [utterance], "lang": lang}),
        ))

    def messages(self, since: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        with self._lock:
            self.last_used = time.time()
            return list(self._transcript[since:]), len(self._transcript)

    def close(self):
        try:
            self.bus.close()
        except Exception:
            pass


class ChatSessions:
    """Process-wide registry of impersonation sessions (bounded, idle-reaped)."""

    def __init__(self, max_sessions: int = 12, max_idle: float = 900.0):
        self._sessions: Dict[str, ImpersonationSession] = {}
        self._lock = threading.Lock()
        self._max = max_sessions
        self._max_idle = max_idle

    def _reap(self):
        now = time.time()
        for sid, s in list(self._sessions.items()):
            if now - s.last_used > self._max_idle:
                s.close()
                self._sessions.pop(sid, None)

    def create(self, client_id, name, key, password, crypto_key, host, port
               ) -> ImpersonationSession:
        with self._lock:
            self._reap()
            # one live session per client: replace any existing
            for sid, s in list(self._sessions.items()):
                if s.client_id == client_id:
                    s.close()
                    self._sessions.pop(sid, None)
            if len(self._sessions) >= self._max:
                oldest = min(self._sessions.values(), key=lambda s: s.last_used)
                oldest.close()
                self._sessions.pop(oldest.id, None)
        sess = ImpersonationSession(client_id, name, key, password, crypto_key, host, port)
        with self._lock:
            self._sessions[sess.id] = sess
        return sess

    def get(self, sid: str) -> Optional[ImpersonationSession]:
        return self._sessions.get(sid)

    def close(self, sid: str):
        with self._lock:
            s = self._sessions.pop(sid, None)
        if s:
            s.close()

    def list_active(self) -> List[Dict[str, Any]]:
        return [{"session_id": s.id, "client_id": s.client_id, "name": s.name}
                for s in self._sessions.values()]


# process-wide singleton
CHAT = ChatSessions()
