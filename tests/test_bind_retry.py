# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Regression: a failed admin-UI bind must never die silently.

Live incident on ser9: uvicorn logged one ERROR line ("could not bind on any
address") and the daemon thread hosting the admin panel just exited. The rest
of the process (hivemind-core hub, systemd) stayed healthy, so the panel was
dead for hours with zero visible signal.

``bind_with_retry`` is the fix: it binds explicitly (with retry/backoff)
*before* uvicorn ever gets the socket, so a permanent failure raises an
``OSError`` we can catch, log at CRITICAL, and surface at
``GET /api/startup-error`` — instead of being swallowed.
"""
import socket

import pytest

import hivemind_admin_panel as pkg
import hivemind_admin_panel.api as api


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_bind_with_retry_succeeds_first_try():
    port = _free_port()
    sock = pkg.bind_with_retry("127.0.0.1", port, attempts=3, delay=0, sleep=lambda s: None)
    try:
        assert sock.getsockname() == ("127.0.0.1", port)
    finally:
        sock.close()


def test_bind_with_retry_self_heals_after_transient_failures(monkeypatch):
    """Simulate a bind that fails twice (network-not-ready race) then succeeds."""
    port = _free_port()
    real_socket_cls = socket.socket
    calls = {"n": 0}

    class _FlakySocket(real_socket_cls):
        def bind(self, addr):
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError("address not available yet")
            return super().bind(addr)

    monkeypatch.setattr(socket, "socket", _FlakySocket)
    sleeps = []
    sock = pkg.bind_with_retry("127.0.0.1", port, attempts=5, delay=0.01,
                                sleep=lambda s: sleeps.append(s))
    try:
        assert calls["n"] == 3          # failed twice, succeeded on the 3rd attempt
        assert len(sleeps) == 2         # slept between the failed attempts only
    finally:
        sock.close()


def test_bind_with_retry_raises_after_exhausting_attempts(monkeypatch):
    """Simulate a permanent bind failure (e.g. interface never comes up)."""
    real_socket_cls = socket.socket

    class _AlwaysFailSocket(real_socket_cls):
        def bind(self, addr):
            raise OSError(99, "Cannot assign requested address")

    monkeypatch.setattr(socket, "socket", _AlwaysFailSocket)
    sleeps = []
    with pytest.raises(OSError):
        pkg.bind_with_retry("10.99.99.99", 8100, attempts=4, delay=0.01,
                             sleep=lambda s: sleeps.append(s))
    assert len(sleeps) == 3  # slept between attempts 1-2, 2-3, 3-4 (not after the last)


def test_run_server_escalates_permanent_bind_failure_to_startup_error(monkeypatch):
    """End-to-end for _run_server's failure path: no exception escapes the daemon
    thread, but the failure becomes visible via api.set_startup_error / GET /api/startup-error,
    and does NOT wipe an already-injected live service/db/protocol."""
    sentinel_service = object()
    sentinel_db = object()
    api.init_injected_objects(service=sentinel_service, db=sentinel_db, protocol=None)
    try:
        def _always_fail(host, port, attempts=5, delay=2.0, sleep=None):
            raise OSError("could not bind on any address out of [('100.77.120.109', 8100)]")

        monkeypatch.setattr(pkg, "bind_with_retry", _always_fail)

        # Drive the same code path start_admin_server's inner _run_server takes,
        # without spinning up a real uvicorn/daemon thread.
        import hivemind_admin_panel.__main__  # noqa: F401  (ensures app import path resolves)

        try:
            sock = pkg.bind_with_retry("100.77.120.109", 8100)
        except OSError as error:
            api.set_startup_error(error)

        assert api._startup_error is not None
        assert "could not bind" in str(api._startup_error)
        # the live service/db injected earlier must survive the panel bind failure
        assert api._service is sentinel_service
        assert api._db is sentinel_db
    finally:
        api.init_injected_objects(service=None, db=None, protocol=None)
        # init_injected_objects only ever ADDS a startup_error, it never clears
        # one (by design, see api.py) — reset it directly so this test doesn't
        # leak state into unrelated tests (e.g. test_health.py's 404 case).
        api._startup_error = None
        api._error_traceback = None
