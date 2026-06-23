# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: per-entry-point config (handlers + memory) persists on CREATE."""


def test_create_persists_memory_config(client, auth):
    body = {
        "name": "qa-memcfg",
        "handlers": ["ovos-solver-failure-plugin"],
        "memory_module": "ovos-agents-short-term-memory-plugin",
        # config under the memory module's entry-point key (how ovos-persona reads it)
        "ovos-agents-short-term-memory-plugin": {"max_history": 7},
    }
    assert client.post("/personas", json=body, headers=auth).status_code == 200
    p = client.get("/personas/qa-memcfg", headers=auth).json()
    assert p["memory_module"] == "ovos-agents-short-term-memory-plugin"
    assert p["ovos-agents-short-term-memory-plugin"] == {"max_history": 7}


def test_create_persists_handler_config(client, auth):
    # regression: create used to drop per-handler config (only edit kept it)
    body = {
        "name": "qa-hcfg",
        "handlers": ["ovos-solver-openai-plugin"],
        "ovos-solver-openai-plugin": {"model": "gpt-4o", "api_url": "http://x"},
    }
    assert client.post("/personas", json=body, headers=auth).status_code == 200
    p = client.get("/personas/qa-hcfg", headers=auth).json()
    assert p["ovos-solver-openai-plugin"] == {"model": "gpt-4o", "api_url": "http://x"}
