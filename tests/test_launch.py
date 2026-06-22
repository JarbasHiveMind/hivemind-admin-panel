# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Unit: the in-process hivemind-core launcher injects the live hivemind-core (no real hivemind-core started).

hivemind-core must run on the MAIN thread (its ``run()`` installs signal handlers), so
``launch_core()`` only constructs + injects and returns the service — ``main()``
runs it. These tests assert that contract without starting a real hivemind-core.
"""
import hivemind_core.service as core_service

import hivemind_admin_panel.api as api
from hivemind_admin_panel.__main__ import launch_core


class _FakeService:
    hm_protocol = object  # the launcher wraps this; real HiveMindService has it

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
    # launch_core must NOT run hivemind-core (run() is main-thread-only, called by main())
    assert svc.ran is False
    api.init_injected_objects(service=None, db=None, protocol=None)


def test_launch_core_failure_injects_startup_error(monkeypatch):
    def boom():
        raise RuntimeError("no hivemind-core for you")

    monkeypatch.setattr(core_service, "HiveMindService", boom)
    svc = launch_core()
    assert svc is None
    assert api._startup_error is not None
    api.init_injected_objects(service=None, db=None, protocol=None)


def test_main_survives_core_run_failure(monkeypatch):
    """If the in-process core raises during run() (e.g. its agent backend is down
    and now fails fast), main() must stay up in diagnostics mode, not crash."""
    import sys
    import ovos_utils
    import ovos_utils.log as ovlog
    import hivemind_admin_panel as pkg
    import hivemind_admin_panel.__main__ as mainmod

    db_sentinel = object()

    class _BoomService:
        db = db_sentinel

        def run(self):
            raise ConnectionError("OVOS messagebus unreachable")

    waited = {"called": False}
    monkeypatch.setattr(mainmod, "launch_core", lambda: _BoomService())
    monkeypatch.setattr(pkg, "start_admin_server", lambda **kw: None)
    monkeypatch.setattr(ovlog, "init_service_logger", lambda *a, **k: None)
    monkeypatch.setattr(ovos_utils, "wait_for_exit_signal",
                        lambda: waited.__setitem__("called", True))
    monkeypatch.setattr(sys, "argv", ["hivemind-admin-panel", "--port", "0"])

    api.init_injected_objects(service=None, db=None, protocol=None)
    try:
        mainmod.main()                      # must return, not raise
        assert waited["called"] is True     # stayed up in diagnostics mode
        assert isinstance(api._startup_error, ConnectionError)
        assert api._db is db_sentinel       # db kept for panel-only management
    finally:
        api.init_injected_objects(service=None, db=None, protocol=None)
