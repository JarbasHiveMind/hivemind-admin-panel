# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Smoke tests: package imports, app construction, static assets, health route."""
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import hivemind_admin_panel
from hivemind_admin_panel.api import app, get_admin_app, init_injected_objects
from hivemind_admin_panel.version import __version__


def test_version_is_pep440():
    assert re.match(r"^\d+\.\d+\.\d+(a\d+)?$", __version__), __version__


def test_public_api_surface():
    for name in ("start_admin_server", "init_injected_objects", "get_admin_app"):
        assert hasattr(hivemind_admin_panel, name), name


def test_get_admin_app_returns_fastapi():
    assert isinstance(get_admin_app(), FastAPI)


def test_static_assets_bundled():
    static = Path(hivemind_admin_panel.__file__).parent / "static"
    assert (static / "index.html").is_file()
    assert (static / "js" / "app.js").is_file()
    assert (static / "css" / "style.css").is_file()


def test_health_endpoint_is_public():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "status" in resp.json()


def test_protected_endpoint_requires_auth():
    client = TestClient(app)
    # /clients is guarded by HTTP Basic; no credentials -> 401
    assert client.get("/clients").status_code == 401


def test_injection_seam_accepts_none():
    # standalone mode: core objects may all be None
    init_injected_objects(service=None, db=None, protocol=None)
