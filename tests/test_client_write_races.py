# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Concurrent client mutations must not discard each other.

Every client mutation is a read-modify-write over the whole row: the database
contract has no partial update (``update_item`` delegates to ``add_item``,
an ``INSERT OR REPLACE`` on the SQLite backend). Two overlapping requests
against the same client therefore both write a full row, and the later write
silently reverts the earlier one's field.

The ACL editor in the UI sends one request per permission, so this is the
ordinary path, not an exotic one.
"""
import threading

import pytest


def test_the_write_helper_actually_serialises():
    """Guard the mechanism itself: two threads must not be inside it at once."""
    from hivemind_admin_panel.api import client_db_write

    overlapped = []
    inside = []
    barrier_passed = threading.Event()

    def worker():
        with client_db_write():
            inside.append(1)
            if len(inside) > 1:
                overlapped.append(1)
            barrier_passed.wait(0.05)
            inside.pop()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    barrier_passed.set()
    for t in threads:
        t.join()

    assert not overlapped, "client_db_write() allowed concurrent read-modify-write"


@pytest.mark.parametrize("attempt", range(3))
def test_parallel_flag_updates_do_not_lose_each_other(client, auth, make_client, attempt):
    """allow-escalate and allow-propagate on one client must both survive."""
    created = make_client(name=f"race-victim-{attempt}")
    cid = created["client_id"]

    def hit(path):
        client.post(f"/clients/{cid}/{path}", headers=auth)

    threads = [threading.Thread(target=hit, args=(p,))
               for p in ("allow-escalate", "allow-propagate") for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = client.get(f"/clients/{cid}", headers=auth).json()
    assert final["can_escalate"] is True and final["can_propagate"] is True, (
        f"a concurrent whole-row write discarded a flag: {final}")


def test_parallel_msg_type_grants_all_land(client, auth, make_client):
    """Each allow-msg adds one entry; none may be lost to a concurrent write."""
    created = make_client(name="race-acl")
    cid = created["client_id"]
    wanted = [f"msg.type.{i}" for i in range(8)]

    def grant(msg_type):
        client.post(f"/clients/{cid}/allow-msg", json={"msg_type": msg_type},
                    headers=auth)

    threads = [threading.Thread(target=grant, args=(m,)) for m in wanted]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    allowed = set(client.get(f"/clients/{cid}", headers=auth).json()["allowed_types"])
    missing = [m for m in wanted if m not in allowed]
    assert not missing, f"lost updates: {missing} (kept {sorted(allowed)})"
