# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: bridge catalog, provisioning preset, and live recognition."""


def test_bridge_catalog_lists_known_bridges(client, auth):
    cat = client.get("/bridges/catalog", headers=auth).json()
    ids = {b["id"] for b in cat}
    assert {"matrix", "twitch", "mattermost", "deltachat", "hackchat"} <= ids
    matrix = next(b for b in cat if b["id"] == "matrix")
    assert matrix["repo"].endswith("HiveMind-matrix-bridge")
    assert matrix["needs"]            # the external inputs the operator must supply
    assert "match" not in matrix      # internal recognition tokens are not exposed


def test_provision_bridge_creates_ready_client(client, auth):
    r = client.post("/bridges/provision", json={"type": "matrix"}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    # a client was created with the utterance ACL and a bridge tag
    cid = body["client_id"]
    full = client.get(f"/clients/{cid}", headers=auth).json()
    assert "recognizer_loop:utterance" in full["allowed_types"]
    assert "bridge:matrix" in full["tags"]
    assert full["is_admin"] is False
    # the response carries a usable connection bundle
    assert body["bundle"]["key"] and body["bundle"]["password"] and body["bundle"]["crypto_key"]
    assert body["bridge"]["id"] == "matrix"


def test_provision_unknown_bridge_404s(client, auth):
    assert client.post("/bridges/provision", json={"type": "nope"}, headers=auth).status_code == 404


def test_provisioned_bridge_shows_in_topology(client, auth):
    client.post("/bridges/provision", json={"type": "twitch", "name": "my-twitch"}, headers=auth)
    nodes = client.get("/topology", headers=auth).json()["nodes"]
    bnode = next((n for n in nodes if n.get("label") == "my-twitch"), None)
    assert bnode is not None
    assert bnode["type"] == "bridge"
    assert bnode["bridge"]["id"] == "twitch"


def test_match_bridge_recognizes_useragent():
    # bridges provisioned outside the panel are recognized by their useragent/peer
    from hivemind_admin_panel.api import _match_bridge
    # matrix bridge announces useragent "HiveMindMatrixBridgeV0.2"
    m = _match_bridge("HiveMindMatrixBridgeV0.2::3::room-bot::matrix", tags=[])
    assert m and m["id"] == "matrix"
    # a plain voice satellite is not a bridge
    assert _match_bridge("HiveMessageBusClientV0.0.1::4::kitchen::default", tags=[]) is None


def test_match_bridge_prefers_tag():
    from hivemind_admin_panel.api import _match_bridge
    # tag wins even when the peer string is generic
    m = _match_bridge("HiveMessageBusClientV0.0.1::5::x::default", tags=["bridge:mattermost"])
    assert m and m["id"] == "mattermost"
