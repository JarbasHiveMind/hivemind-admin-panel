# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Regression: concurrent config reads must not race on the shared lock file.

The dashboard fires ~9 requests in parallel, each calling ``get_server_config()``.
hivemind-core builds a ``JsonStorageXDG`` whose ``ComboLock`` does a non-atomic
create+chmod on a shared lock path, so concurrent construction raced into
``FileNotFoundError: .../server.json.lock`` and surfaced as a 500. The panel
wraps the call in a process-local lock; this test hammers it from many threads.
"""
import threading


def test_parallel_get_server_config_never_raises(_server_config):
    from hivemind_admin_panel.api import get_server_config

    errors = []

    def worker():
        for _ in range(10):
            try:
                cfg = get_server_config()
                assert cfg.get("admin_user") is not None
            except Exception as e:  # the race used to raise FileNotFoundError here
                errors.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent config reads raised: {errors[:3]}"


def test_parallel_setup_status_requests_no_5xx(client, auth):
    """Drive the endpoint the live failure hit, concurrently, via the real app."""
    statuses = []

    def hit():
        statuses.append(client.get("/setup/status", headers=auth).status_code)

    threads = [threading.Thread(target=hit) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(s == 200 for s in statuses), statuses
