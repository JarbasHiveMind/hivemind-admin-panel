# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Thread-safe metrics registry + a bounded event ring buffer.

The hub runs on the main thread while the admin server (uvicorn) runs in a daemon
thread, so all shared state here is guarded by a lock. Counters are incremented
from request handlers (admin actions) and can be polled by the /metrics endpoint
and streamed by the SSE /events endpoint.
"""
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional


class Metrics:
    """In-process counters, gauges and a recent-events ring buffer."""

    def __init__(self, max_events: int = 500, max_messages: int = 1000) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._events: Deque[Dict[str, Any]] = deque(maxlen=max_events)
        self._messages: Deque[Dict[str, Any]] = deque(maxlen=max_messages)
        self._start = time.monotonic()
        self._wall_start = time.time()

    def incr(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def event(self, kind: str, message: str, **data: Any) -> Dict[str, Any]:
        """Record a recent event (also bumps a per-kind counter)."""
        evt = {"ts": time.time(), "kind": kind, "message": message, **data}
        with self._lock:
            self._events.append(evt)
            self._counters[f"event.{kind}"] = self._counters.get(f"event.{kind}", 0) + 1
        return evt

    def recent_events(self, limit: int = 100, since: Optional[float] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._events)
        if since is not None:
            items = [e for e in items if e["ts"] > since]
        return items[-limit:]

    def message(self, msg_type: str, peer: str, **data: Any) -> None:
        """Record a tapped HiveMessage for the message inspector."""
        with self._lock:
            self._messages.append({"ts": time.time(), "msg_type": msg_type, "peer": peer, **data})
            self._counters["messages.total"] = self._counters.get("messages.total", 0) + 1
            self._counters[f"msg.{msg_type}"] = self._counters.get(f"msg.{msg_type}", 0) + 1

    def recent_messages(self, limit: int = 100, msg_type: Optional[str] = None,
                        peer: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._messages)
        if msg_type:
            items = [m for m in items if m["msg_type"] == msg_type]
        if peer:
            items = [m for m in items if m["peer"] == peer]
        return items[-limit:]

    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "uptime_seconds": round(time.monotonic() - self._start, 3),
                "started_at": self._wall_start,
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "recent_event_count": len(self._events),
            }


#: process-wide singleton
METRICS = Metrics()
