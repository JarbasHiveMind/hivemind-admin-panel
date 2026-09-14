# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""No credential in a URL except a one-time SSE ticket.

A token in a query string reaches the access log, the Referer header and the
browser history. Two endpoints used to read one: the pairing QR, which now
loads with an Authorization header, and the SSE feed, which can not set one
because EventSource does not support it.

The feed therefore reads a ticket instead of the login token. A ticket lives
30 seconds, works once, and authenticates nothing but the stream.
"""
import time

import pytest

import hivemind_admin_panel.api as api
from tests.conftest import ADMIN_USER, ADMIN_PASS


@pytest.fixture
def token(client):
    return client.post("/auth/login",
                       json={"username": ADMIN_USER, "password": ADMIN_PASS}).json()["token"]


@pytest.fixture
def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _ticket(client, bearer):
    resp = client.post("/events/ticket", headers=bearer)
    assert resp.status_code == 200, resp.text
    return resp.json()["ticket"]


def _stream(client, url):
    with client.stream("GET", url) as resp:
        status = resp.status_code
        body = "".join(resp.iter_text()) if status == 200 else ""
    return status, body


class TestTheQrCodeNoLongerReadsTheUrl:
    def test_qr_refuses_a_query_token(self, client, bearer, make_client):
        c = make_client(name="qr-sat")
        url = f"/clients/{c['client_id']}/pairing/qr.svg?host=10.0.0.5"
        token = bearer["Authorization"].split()[1]

        assert client.get(f"{url}&access_token={token}").status_code == 401

    def test_qr_still_works_with_the_header(self, client, bearer, make_client):
        c = make_client(name="qr-sat")

        resp = client.get(f"/clients/{c['client_id']}/pairing/qr.svg?host=10.0.0.5",
                          headers=bearer)

        assert resp.status_code == 200
        assert "image/svg+xml" in resp.headers["content-type"]


class TestTheStreamReadsATicketOnly:
    def test_the_login_token_is_refused_in_the_url(self, client, token):
        status, _ = _stream(client, f"/events?limit=1&interval=0.25&access_token={token}")
        assert status == 401

        status, _ = _stream(client, f"/events?limit=1&interval=0.25&ticket={token}")
        assert status == 401

    def test_a_ticket_opens_the_stream(self, client, bearer):
        ticket = _ticket(client, bearer)

        status, body = _stream(client, f"/events?limit=1&interval=0.25&ticket={ticket}")

        assert status == 200
        assert "event: snapshot" in body

    def test_a_ticket_works_once(self, client, bearer):
        ticket = _ticket(client, bearer)
        first, _ = _stream(client, f"/events?limit=1&interval=0.25&ticket={ticket}")

        second, _ = _stream(client, f"/events?limit=1&interval=0.25&ticket={ticket}")

        assert first == 200
        assert second == 401

    def test_an_expired_ticket_is_refused(self, client, bearer, monkeypatch):
        monkeypatch.setattr(api, "_SSE_TICKET_TTL", -1)
        ticket = _ticket(client, bearer)

        status, _ = _stream(client, f"/events?limit=1&interval=0.25&ticket={ticket}")

        assert status == 401

    def test_a_forged_ticket_is_refused(self, client):
        status, _ = _stream(client, "/events?limit=1&interval=0.25&ticket=not.a.token")
        assert status == 401


class TestATicketIsNotALoginToken:
    def test_a_ticket_is_refused_as_a_bearer_token(self, client, bearer):
        ticket = _ticket(client, bearer)

        assert client.get("/clients",
                          headers={"Authorization": f"Bearer {ticket}"}).status_code == 401

    def test_a_ticket_is_refused_on_another_query_endpoint(self, client, bearer):
        ticket = _ticket(client, bearer)

        assert client.get(f"/events/recent?ticket={ticket}").status_code == 401

    def test_minting_a_ticket_needs_authentication(self, client):
        assert client.post("/events/ticket").status_code == 401


class TestTheTicketStoreStaysSmall:
    def test_unused_tickets_are_dropped_when_they_expire(self, client, bearer, monkeypatch):
        api._SSE_TICKETS.clear()   # tickets minted by earlier tests
        monkeypatch.setattr(api, "_SSE_TICKET_TTL", -1)
        for _ in range(5):
            _ticket(client, bearer)
        monkeypatch.setattr(api, "_SSE_TICKET_TTL", 30)

        _ticket(client, bearer)

        assert len(api._SSE_TICKETS) == 1
        assert all(exp > time.time() for exp in api._SSE_TICKETS.values())
