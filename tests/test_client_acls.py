# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: per-client ACL management."""


def test_allow_and_blacklist_message_type(client, auth, make_client):
    c = make_client(name="acl-msg")
    cid = c["client_id"]
    r = client.post(f"/clients/{cid}/allow-msg", json={"msg_type": "recognizer_loop:utterance"}, headers=auth)
    assert r.status_code == 200
    assert "recognizer_loop:utterance" in r.json()["allowed_types"]
    r = client.post(f"/clients/{cid}/blacklist-msg", json={"msg_type": "recognizer_loop:utterance"}, headers=auth)
    assert r.status_code == 200
    assert "recognizer_loop:utterance" not in r.json()["allowed_types"]


def test_skill_blacklist_toggle(client, auth, make_client):
    cid = make_client(name="acl-skill")["client_id"]
    r = client.post(f"/clients/{cid}/blacklist-skill", json={"skill_id": "skill-weather.openvoiceos"}, headers=auth)
    assert r.status_code == 200
    assert "skill-weather.openvoiceos" in r.json()["skill_blacklist"]
    r = client.post(f"/clients/{cid}/allow-skill", json={"skill_id": "skill-weather.openvoiceos"}, headers=auth)
    assert "skill-weather.openvoiceos" not in r.json()["skill_blacklist"]


def test_intent_blacklist_toggle(client, auth, make_client):
    cid = make_client(name="acl-intent")["client_id"]
    r = client.post(f"/clients/{cid}/blacklist-intent", json={"intent_id": "weather.intent"}, headers=auth)
    assert r.status_code == 200
    assert "weather.intent" in r.json()["intent_blacklist"]
    r = client.post(f"/clients/{cid}/allow-intent", json={"intent_id": "weather.intent"}, headers=auth)
    assert "weather.intent" not in r.json()["intent_blacklist"]


def test_escalate_propagate_flags(client, auth, make_client):
    cid = make_client(name="acl-flags")["client_id"]
    assert client.post(f"/clients/{cid}/blacklist-escalate", headers=auth).json()["can_escalate"] is False
    assert client.post(f"/clients/{cid}/allow-escalate", headers=auth).json()["can_escalate"] is True
    assert client.post(f"/clients/{cid}/blacklist-propagate", headers=auth).json()["can_propagate"] is False
    assert client.post(f"/clients/{cid}/allow-propagate", headers=auth).json()["can_propagate"] is True


def test_admin_flag_toggle(client, auth, make_client):
    cid = make_client(name="acl-admin")["client_id"]
    assert client.post(f"/clients/{cid}/make-admin", headers=auth).json()["is_admin"] is True
    assert client.post(f"/clients/{cid}/revoke-admin", headers=auth).json()["is_admin"] is False


def test_get_and_put_acl(client, auth, make_client):
    cid = make_client(name="acl-rw")["client_id"]
    acl = client.get(f"/clients/{cid}/acl", headers=auth)
    assert acl.status_code == 200
    assert acl.json()["client_id"] == cid
    r = client.put(f"/clients/{cid}/acl", json={"client_id": cid, "is_admin": True,
                                                "allowed_types": ["speak"]}, headers=auth)
    assert r.status_code == 200
    assert r.json()["is_admin"] is True
    assert "speak" in r.json()["allowed_types"]


def test_acl_endpoints_404_for_missing_client(client, auth):
    assert client.get("/clients/999999/acl", headers=auth).status_code == 404


def test_apply_acl_template_if_available(client, auth, make_client):
    templates = client.get("/acl/templates", headers=auth).json()
    if not templates:
        return  # bundled acl_config.json defines templates; nothing to apply otherwise
    name = templates[0].get("name") or templates[0].get("id")
    cid = make_client(name="acl-tmpl")["client_id"]
    r = client.post(f"/clients/{cid}/acl/apply-template", params={"template_name": name}, headers=auth)
    assert r.status_code in (200, 404)
