# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: database profiles and direct database management."""

JSON_MODULE = "hivemind-json-db-plugin"


def _profile_cfg():
    return {"name": "clients", "subfolder": "hivemind-core-test"}


def test_profiles_listing_initializes(client, auth):
    body = client.get("/database/profiles", headers=auth).json()
    assert "profiles" in body


def test_profile_crud(client, auth):
    # create
    r = client.post("/database/profiles", json={"name": "p-test", "module": JSON_MODULE,
                                                "config": _profile_cfg()}, headers=auth)
    assert r.status_code == 200, r.text
    # duplicate -> 409
    assert client.post("/database/profiles", json={"name": "p-test", "module": JSON_MODULE,
                                                   "config": _profile_cfg()}, headers=auth).status_code == 409
    # get
    assert client.get("/database/profiles/p-test", headers=auth).json()["module"] == JSON_MODULE
    # update
    assert client.put("/database/profiles/p-test", json={"config": {"name": "c2"}}, headers=auth).status_code == 200
    # delete
    assert client.delete("/database/profiles/p-test", headers=auth).status_code == 200
    assert client.get("/database/profiles/p-test", headers=auth).status_code == 404


def test_profile_invalid_name_rejected(client, auth):
    r = client.post("/database/profiles", json={"name": "bad name!", "module": JSON_MODULE,
                                                "config": _profile_cfg()}, headers=auth)
    assert r.status_code == 422


def test_profile_connectivity_test(client, auth):
    client.post("/database/profiles", json={"name": "p-conn", "module": JSON_MODULE,
                                            "config": _profile_cfg()}, headers=auth)
    body = client.post("/database/profiles/p-conn/test", headers=auth).json()
    assert "success" in body and body["module"] == JSON_MODULE
    client.delete("/database/profiles/p-conn", headers=auth)


def test_direct_db_test(client, auth):
    body = client.post("/database/test", json={"module": JSON_MODULE, "config": _profile_cfg()}, headers=auth).json()
    assert body["module"] == JSON_MODULE


def test_migrate_endpoint_is_deprecated(client, auth):
    resp = client.post("/database/migrate", json={"target_module": JSON_MODULE, "preserve_data": False}, headers=auth)
    assert "X-Deprecated" in resp.headers


def test_list_clients_for_module(client, auth, make_client):
    make_client(name="db-list-sat")
    resp = client.get(f"/database/{JSON_MODULE}/clients", headers=auth)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
