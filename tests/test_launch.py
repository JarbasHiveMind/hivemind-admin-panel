# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Unit: the in-process hub launcher injects the live hub (no real hub started).

The hub must run on the MAIN thread (its ``run()`` installs signal handlers), so
``launch_core()`` only constructs + injects and returns the service — ``main()``
runs it. These tests assert that contract without starting a real hub.
"""
import hivemind_core.service as core_service

import hivemind_admin_panel.api as api
from hivemind_admin_panel.__main__ import launch_core


class _FakeService:
    def __init__(self):
        self.db = object()
        self.ran = False

    def run(self):
        self.ran = True


def test_launch_core_injects_live_objects(monkeypatch):
    monkeypatch.setattr(core_service, "HiveMindService", _FakeService)

    svc = launch_core()
    assert isinstance(svc, _FakeService)
    assert api._service is svc
    assert api._db is svc.db
    # launch_core must NOT run the hub (run() is main-thread-only, called by main())
    assert svc.ran is False
    api.init_injected_objects(service=None, db=None, protocol=None)


def test_launch_core_failure_injects_startup_error(monkeypatch):
    def boom():
        raise RuntimeError("no hub for you")

    monkeypatch.setattr(core_service, "HiveMindService", boom)
    svc = launch_core()
    assert svc is None
    assert api._startup_error is not None
    api.init_injected_objects(service=None, db=None, protocol=None)
