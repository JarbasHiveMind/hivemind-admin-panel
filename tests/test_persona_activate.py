# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: pre-activation persona validation."""


def test_activate_blocks_persona_with_missing_handler(client, auth):
    client.post("/personas", json={"name": "qa-broken",
                                    "handlers": ["nonexistent-handler-xyz"]}, headers=auth)
    r = client.post("/personas/qa-broken/activate", headers=auth)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "nonexistent-handler-xyz" in detail["missing_handlers"]


def test_activate_force_overrides_validation(client, auth):
    client.post("/personas", json={"name": "qa-broken2",
                                    "handlers": ["nonexistent-handler-xyz"]}, headers=auth)
    assert client.post("/personas/qa-broken2/activate?force=true", headers=auth).status_code == 200


def test_activate_unknown_persona_404(client, auth):
    assert client.post("/personas/no-such-persona/activate", headers=auth).status_code == 404
