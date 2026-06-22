# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Unit: the in-process hub launcher injects the live hub (no real hub started)."""
import ovos_utils
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
    started = {}
    monkeypatch.setattr(core_service, "HiveMindService", _FakeService)
    monkeypatch.setattr(ovos_utils, "create_daemon", lambda target, *a, **kw: started.setdefault("target", target))

    svc = launch_core()
    assert isinstance(svc, _FakeService)
    assert api._service is svc
    assert api._db is svc.db
    # the hub is handed to a daemon thread rather than run inline
    assert started["target"] == svc.run
    api.init_injected_objects(service=None, db=None, protocol=None)


def test_launch_core_failure_injects_startup_error(monkeypatch):
    def boom():
        raise RuntimeError("no hub for you")

    monkeypatch.setattr(core_service, "HiveMindService", boom)
    svc = launch_core()
    assert svc is None
    assert api._startup_error is not None
    api.init_injected_objects(service=None, db=None, protocol=None)
