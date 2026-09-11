"""A revoked client is not handed back by a restore.

``GET /backup`` exports ``revoked`` for every client. ``POST /restore`` listed the
field among the ones it knows, so it was not even reported as ignored, and never
applied it. A bundle row for a revoked client therefore came back as a client with a
working api_key and no revocation — an operator's revocation undone by a recovery path,
which is the same widening as a denied permission restored as granted.

The assertions read the restored state back rather than the endpoint's status, because
the endpoint answered ``ok`` throughout.
"""


def _revoked_row(api_key="rk-was-revoked", name="retired-sat"):
    return {
        "name": name,
        "api_key": api_key,
        "is_admin": False,
        "allowed_types": ["recognizer_loop:utterance"],
        "can_escalate": True,
        "can_propagate": True,
        "can_broadcast": True,
        "revoked": True,
    }


def test_restore_does_not_hand_back_a_revoked_client(client, auth):
    row = _revoked_row()

    resp = client.post("/restore", json={"clients": [row]}, headers=auth)
    assert resp.status_code == 200, resp.text

    listed = client.get("/clients", headers=auth).json()
    assert not [c for c in listed if c["name"] == row["name"]], (
        "a revoked client was restored and is listed as active: "
        f"{[c for c in listed if c['name'] == row['name']]}"
    )


def test_restore_reports_the_refusal(client, auth):
    resp = client.post("/restore", json={"clients": [_revoked_row("rk-refusal-note")]},
                       headers=auth)
    body = resp.json()
    assert body["clients_refused_revoked"] == 1
    assert body["clients_added"] == 0
    assert "revoked" in body.get("message", "")


def test_an_active_client_in_the_same_bundle_still_restores(client, auth):
    """The refusal is per row, not per bundle."""
    revoked = _revoked_row("rk-mixed-revoked", "mixed-retired")
    active = _revoked_row("rk-mixed-active", "mixed-live")
    active["revoked"] = False

    resp = client.post("/restore", json={"clients": [revoked, active]}, headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["clients_added"] == 1
    assert resp.json()["clients_refused_revoked"] == 1

    names = {c["name"] for c in client.get("/clients", headers=auth).json()}
    assert "mixed-live" in names
    assert "mixed-retired" not in names
