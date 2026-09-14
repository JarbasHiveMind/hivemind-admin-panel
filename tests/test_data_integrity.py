# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the data-integrity / correctness pass.

Each test here fails against 0.1.1a2.
"""
import json

import pytest


# ------------------------------------------------- C1: the phantom ACL field

PHANTOM = "message_blacklist"


def test_client_payloads_do_not_carry_the_removed_field(client, auth, make_client):
    """`message_blacklist` was removed from the data model upstream.

    The panel kept reading and writing it, so it advertised an ACL control that
    hivemind-core does not honour and that the database drops.
    """
    c = make_client(name="phantom")
    cid = c["client_id"]
    assert PHANTOM not in c
    assert PHANTOM not in client.get(f"/clients/{cid}", headers=auth).json()
    assert PHANTOM not in client.get(f"/clients/{cid}/acl", headers=auth).json()
    assert PHANTOM not in client.get("/clients", headers=auth).json()[0]


def test_updating_a_client_does_not_accept_the_removed_field(client, auth, make_client):
    cid = make_client(name="phantom2")["client_id"]
    r = client.put(f"/clients/{cid}", json={PHANTOM: ["speak"]}, headers=auth)
    assert r.status_code == 200
    assert PHANTOM not in r.json()


def test_acl_view_and_editor_agree(client, auth, make_client):
    """The ACL GET, the ACL PUT model and apply-template must expose one field set."""
    from hivemind_admin_panel.api import ACLUpdateRequest
    cid = make_client(name="acl-shape")["client_id"]
    view = set(client.get(f"/clients/{cid}/acl", headers=auth).json())
    editable = set(ACLUpdateRequest.model_fields) - {"client_id"}
    assert editable <= view, editable - view
    for field in ("can_broadcast", "can_escalate", "can_propagate", "allowed_types"):
        assert field in view


def test_can_broadcast_is_editable_through_the_acl_endpoint(client, auth, make_client):
    cid = make_client(name="broadcast")["client_id"]
    r = client.put(f"/clients/{cid}/acl",
                   json={"client_id": cid, "can_broadcast": False}, headers=auth)
    assert r.status_code == 200
    assert r.json()["can_broadcast"] is False


# --------------------------------------- C2: never write defaults over a config

@pytest.fixture()
def broken_auth():
    """With server.json unreadable, hivemind-core falls back to admin/admin."""
    import base64
    return {"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()}


@pytest.fixture()
def corrupt_config(tmp_path):
    """Temporarily make server.json unparseable."""
    from hivemind_admin_panel.api import _server_json_path
    path = _server_json_path()
    original = path.read_bytes()
    path.write_text("{ this is not json")
    yield path
    path.write_bytes(original)


def test_post_config_refuses_to_write_over_an_unreadable_file(client, broken_auth, corrupt_config):
    """The old behaviour wrote hivemind-core defaults over the real config."""
    before = corrupt_config.read_bytes()
    r = client.post("/config", json={"config": {"anything": 1}}, headers=broken_auth)
    assert r.status_code == 409
    assert corrupt_config.read_bytes() == before   # untouched


def test_get_config_does_not_pass_defaults_off_as_the_file(client, broken_auth, corrupt_config):
    r = client.get("/config", headers=broken_auth)
    assert r.status_code == 500
    assert "unreadable" in r.json()["detail"]


# ------------------------------------------------ C5/C6: honest live-state views

def test_topology_does_not_hardcode_the_core_as_online(client, auth, db):
    """`{"id": "core", "online": true}` was a literal, true even with no core."""
    from hivemind_admin_panel import api
    assert api._protocol is None          # the fixture injects no live protocol
    body = client.get("/topology", headers=auth).json()
    core = next(n for n in body["nodes"] if n["type"] == "core")
    assert core["online"] is not True
    assert "error" in body


def test_topology_reports_a_database_error(client, auth, monkeypatch):
    import hivemind_admin_panel.api as api

    def boom(*a, **kw):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(api, "ClientDatabase", boom)
    body = client.get("/topology", headers=auth).json()
    assert body["error"] and "disk on fire" in body["error"]


def test_setup_status_reports_a_database_error_instead_of_zero(client, auth, monkeypatch):
    import hivemind_admin_panel.api as api

    def boom(*a, **kw):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(api, "ClientDatabase", boom)
    body = client.get("/setup/status", headers=auth).json()
    assert body["database_error"] and "disk on fire" in body["database_error"]
    assert body["client_count"] is None      # not a confident 0
    assert body["has_clients"] is None


# ------------------------------------------------------- C7: name matches action

def test_deny_msg_removes_the_type_from_the_whitelist(client, auth, make_client):
    cid = make_client(name="deny")["client_id"]
    client.post(f"/clients/{cid}/allow-msg",
                json={"msg_type": "recognizer_loop:utterance"}, headers=auth)
    r = client.post(f"/clients/{cid}/deny-msg",
                    json={"msg_type": "recognizer_loop:utterance"}, headers=auth)
    assert r.status_code == 200
    assert "recognizer_loop:utterance" not in r.json()["allowed_types"]


def test_blacklist_msg_still_works_as_an_alias(client, auth, make_client):
    cid = make_client(name="deny-alias")["client_id"]
    client.post(f"/clients/{cid}/allow-msg", json={"msg_type": "speak"}, headers=auth)
    r = client.post(f"/clients/{cid}/blacklist-msg",
                    json={"msg_type": "speak"}, headers=auth)
    assert r.status_code == 200
    assert "speak" not in r.json()["allowed_types"]


# ----------------------------------------------- C8: unknown module is a 4xx

def test_unknown_database_module_is_not_a_500(client, auth):
    r = client.get("/database/no-such-plugin/clients", headers=auth)
    assert r.status_code == 404
    # and it must not leak the internal exception text
    assert "Traceback" not in r.text


# ------------------------------------------------- C9: usable pairing address

def test_pairing_bundle_has_no_placeholder_host(client, auth, make_client):
    cid = make_client(name="pairme")["client_id"]
    bundle = client.get(f"/clients/{cid}/pairing", headers=auth).json()
    assert "<CORE-IP>" not in bundle["connect_url"]
    assert "<CORE-IP>" not in bundle["qr"]
    assert bundle["host"]


def test_explicit_host_still_wins(client, auth, make_client):
    cid = make_client(name="pairme2")["client_id"]
    bundle = client.get(f"/clients/{cid}/pairing?host=10.0.0.5", headers=auth).json()
    assert bundle["host"] == "10.0.0.5"
    assert bundle["connect_url"].startswith("ws://10.0.0.5:")
    assert not bundle.get("host_guessed")


# ------------------------------------------------------ C3: bulk is not silent

def test_bulk_rejects_a_bad_request_before_touching_anything(client, auth, make_client):
    a = make_client(name="bulk-a")["client_id"]
    r = client.post("/clients/bulk",
                    json={"action": "apply_template", "client_ids": [a]}, headers=auth)
    assert r.status_code == 400
    assert client.get(f"/clients/{a}", headers=auth).status_code == 200


def test_bulk_reports_partial_application(client, auth, make_client):
    a = make_client(name="bulk-b")["client_id"]
    body = client.post("/clients/bulk",
                       json={"action": "make_admin", "client_ids": [a, 999999]},
                       headers=auth).json()
    assert body["applied"] == 1
    assert body["failed"] == 1
    assert body["partial"] is True
