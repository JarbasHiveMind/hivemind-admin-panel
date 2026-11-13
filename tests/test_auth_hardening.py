# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Brute-force throttling and the password floor.

Two gaps the earlier security pass left open:

* the login throttle only guarded ``POST /auth/login``, while the API accepts
  HTTP Basic on every route — so an attacker guessed against ``GET /clients``;
* ``POST /auth/password`` accepted a one-character password, after which the
  panel reported itself as no longer using default credentials.
"""
import base64

import pytest

from conftest import ADMIN_PASS, ADMIN_USER


@pytest.fixture(autouse=True)
def _clean_throttle():
    from hivemind_admin_panel.api import _LOGIN_FAILURES

    _LOGIN_FAILURES.clear()
    yield
    _LOGIN_FAILURES.clear()


def _basic(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


# ------------------------------------------------------------------ throttle

def test_basic_auth_guessing_is_throttled(client):
    """Guessing against an ordinary route must hit the same throttle as /auth/login."""
    wrong = _basic(ADMIN_USER, "not-the-password")
    codes = [client.get("/clients", headers=wrong).status_code for _ in range(12)]
    assert codes[0] == 401, codes
    assert 429 in codes, (
        f"HTTP Basic guessing was never throttled: {codes}")


def test_throttle_is_shared_between_basic_and_login(client):
    """Failures on one entry point count towards the other."""
    wrong = _basic(ADMIN_USER, "not-the-password")
    for _ in range(12):
        client.get("/clients", headers=wrong)
    resp = client.post("/auth/login",
                       json={"username": ADMIN_USER, "password": "not-the-password"})
    assert resp.status_code == 429, resp.text


def test_successful_basic_auth_clears_the_counter(client, auth):
    from hivemind_admin_panel.api import _LOGIN_FAILURES

    wrong = _basic(ADMIN_USER, "not-the-password")
    for _ in range(3):
        client.get("/clients", headers=wrong)
    assert _LOGIN_FAILURES.get(ADMIN_USER)
    assert client.get("/clients", headers=auth).status_code == 200
    assert not _LOGIN_FAILURES.get(ADMIN_USER)


def test_failure_map_does_not_grow_without_bound(client):
    """A username sprayer must not be able to grow the map forever."""
    from hivemind_admin_panel.api import (_LOGIN_FAILURES, _prune_login_failures,
                                          _LOGIN_WINDOW)
    import time

    for i in range(50):
        client.get("/clients", headers=_basic(f"sprayed-{i}", "x"))
    assert len(_LOGIN_FAILURES) >= 50
    # age every entry past the window, then let the next check prune them
    for name in _LOGIN_FAILURES:
        _LOGIN_FAILURES[name] = [time.time() - _LOGIN_WINDOW - 1]
    _prune_login_failures(time.time())
    assert _LOGIN_FAILURES == {}


def test_audit_middleware_does_not_count_a_second_failure(client):
    """_identify runs again on the way out; it must not double-count."""
    from hivemind_admin_panel.api import _LOGIN_FAILURES

    client.post("/clients", json={"name": "x"}, headers=_basic(ADMIN_USER, "wrong"))
    assert len(_LOGIN_FAILURES.get(ADMIN_USER, [])) == 1, _LOGIN_FAILURES


# ------------------------------------------------------------- password floor

@pytest.mark.parametrize("weak", ["a", "short", "admin", "password", "hivemind",
                                  "change-me-before-exposing", "elevenchars"])
def test_weak_new_passwords_are_refused(client, auth, weak):
    resp = client.post("/auth/password",
                       json={"old_password": ADMIN_PASS, "new_password": weak},
                       headers=auth)
    assert resp.status_code == 422, f"{weak!r} was accepted: {resp.status_code}"


def test_a_strong_password_is_still_accepted(client, auth):
    from hivemind_core.config import get_server_config

    cfg = get_server_config()
    try:
        resp = client.post("/auth/password",
                           json={"old_password": ADMIN_PASS,
                                 "new_password": "a-perfectly-fine-password"},
                           headers=auth)
        assert resp.status_code == 200, resp.text
    finally:
        cfg["admin_pass"] = ADMIN_PASS
        cfg.store()
