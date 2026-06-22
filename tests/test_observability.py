# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: metrics, event feed, SSE stream, log tail."""
import json


def test_metrics_shape(client, auth):
    body = client.get("/metrics", headers=auth).json()
    assert "uptime_seconds" in body
    assert "counters" in body
    assert "total_clients" in body  # injected db -> real count


def test_events_recorded_on_client_actions(client, auth, make_client):
    make_client(name="evt-sat")
    events = client.get("/events/recent", headers=auth).json()
    assert any(e["kind"] == "client.created" for e in events)


def test_sse_stream_emits_snapshot(client, auth):
    # bounded stream: limit=1 yields exactly the initial snapshot then closes
    with client.stream("GET", "/events?limit=1&interval=0.25", headers=auth) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        chunks = "".join(resp.iter_text())
    assert "event: snapshot" in chunks
    payload = chunks.split("data:", 1)[1].strip().splitlines()[0]
    assert "uptime_seconds" in json.loads(payload)


def test_logs_endpoint(client, auth):
    body = client.get("/logs?lines=10", headers=auth).json()
    assert "lines" in body
    assert isinstance(body["lines"], list)
