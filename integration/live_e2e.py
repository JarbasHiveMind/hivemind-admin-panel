# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""REAL end-to-end QA: in-process hivemind-core + admin UI + a genuine bus client.

Registers a client through the admin API, connects an actual HiveMessageBusClient
with the minted credentials, and asserts the admin UI's *live* views reflect
reality: /connections, /health, /topology, the message inspector, auth rejection
of bogus keys, and that deleting a client through the UI actually revokes access.

Admin API: http://127.0.0.1:8100   Core websocket: 127.0.0.1:5678
"""
import os, sys, time, threading, requests

ADMIN = os.environ.get("ADMIN_URL", "http://127.0.0.1:8100/api")
AUTH = ("admin", "admin")
CORE_HOST, CORE_PORT = "127.0.0.1", 5678

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  PASS " if cond else "  FAIL ") + name + (f"  [{detail}]" if detail else ""))
    return bool(cond)

def _safe(c):
    from ovos_utils.fakebus import FakeBus
    try: c.connect(FakeBus())
    except Exception: pass

def poll(fn, timeout=20, interval=0.5):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            last = fn()
            if last:
                return last
        except Exception as e:
            last = e
        time.sleep(interval)
    return last

def api(method, path, **kw):
    return requests.request(method, ADMIN + path, auth=AUTH, timeout=10, **kw)

# --- 0. Core is live & in-process --------------------------------------------------
h = api("GET", "/health").json()
check("admin reports in-process core", h.get("run_mode") == "in-process", h.get("run_mode"))
check("core service is RUNNING/STARTED", str(h.get("service_status")) not in ("None", "unknown", ""),
      h.get("service_status"))

# --- 1. Register a client through the admin API ------------------------------------
crypto = os.urandom(16).hex()            # 32-char shared cipher key
r = api("POST", "/clients", json={"name": "qa-satellite", "crypto_key": crypto})
check("POST /clients succeeds", r.status_code == 200, r.status_code)
client_rec = r.json()
KEY = client_rec["api_key"]; PW = client_rec["password"]; CK = client_rec["crypto_key"]; CID = client_rec["client_id"]
check("minted creds returned (key/password/crypto)", all([KEY, PW, CK]), f"id={CID}")

# Grant it permission to speak an utterance (whitelist-only core)
api("POST", f"/clients/{CID}/allow-msg", json={"msg_type": "recognizer_loop:utterance"})

# Baseline: nothing connected yet
check("baseline /connections is empty", api("GET", "/connections").json().get("count", 0) == 0)

# --- 2. Connect a REAL bus client with those credentials ---------------------------
from ovos_utils.fakebus import FakeBus
from hivemind_bus_client import HiveMessageBusClient
from hivemind_bus_client.message import HiveMessage, HiveMessageType
from ovos_bus_client.message import Message

bus = HiveMessageBusClient(key=KEY, password=PW, crypto_key=CK,
                           host=CORE_HOST, port=CORE_PORT, self_signed=True)
err = {}
def _connect():
    try:
        bus.connect(FakeBus())
    except Exception as e:
        err["e"] = e
threading.Thread(target=_connect, daemon=True).start()
connected = bus.handshake_event.wait(25)
check("bus client completes the HiveMind handshake", connected, err.get("e", ""))

# --- 3. The admin UI sees the live connection --------------------------------------
conns = poll(lambda: (lambda d: d if d.get("count", 0) >= 1 else None)(api("GET", "/connections").json()))
check("/connections shows the live satellite", isinstance(conns, dict) and conns.get("count", 0) >= 1,
      conns.get("count") if isinstance(conns, dict) else conns)
if isinstance(conns, dict):
    keys = [c.get("key") for c in conns.get("connections", [])]
    check("connection key matches the minted access key",
          any(KEY.lower() == str(k).lower() for k in keys), keys)

health2 = api("GET", "/health").json()
check("/health active_connections >= 1", health2.get("active_connections", 0) >= 1,
      health2.get("active_connections"))

topo = api("GET", "/topology").json()
nodes = topo.get("nodes", [])
sat_nodes = [n for n in nodes if n.get("type") != "core"]
check("/topology has the core node", any(n.get("type") == "core" for n in nodes))
check("/topology shows a satellite node", len(sat_nodes) >= 1, [n.get("type") for n in nodes])

# --- 4. The message inspector taps real traffic ------------------------------------
before = len(api("GET", "/messages/recent").json())
bus.emit(HiveMessage(HiveMessageType.BUS,
                     Message("recognizer_loop:utterance", {"utterances": ["hello hivemind"]})))
msgs = poll(lambda: (lambda m: m if len(m) > 0 else None)(api("GET", "/messages/recent").json()), timeout=15)
check("message inspector captured live traffic",
      isinstance(msgs, list) and len(msgs) >= 1, f"{before} -> {len(msgs) if isinstance(msgs,list) else msgs}")

events = api("GET", "/events/recent").json()
ev_types = [e.get("event") or e.get("type") or str(e) for e in (events if isinstance(events, list) else [])]
check("a client.connected event was recorded",
      any("connect" in str(t).lower() for t in ev_types), ev_types[:6])

# --- 5. Bogus key is rejected (auth enforcement, observable in the UI) -------------
bogus = HiveMessageBusClient(key="deadbeef" * 4, password="nope", crypto_key=os.urandom(16).hex(),
                             host=CORE_HOST, port=CORE_PORT, self_signed=True)
threading.Thread(target=lambda: _safe(bogus), daemon=True).start()
rejected = not bogus.handshake_event.wait(10)
check("core rejects a bogus key (no handshake)", rejected)
try: bogus.close()
except Exception: pass

# --- 6. Deleting the client through the UI actually revokes access -----------------
bus.close()
time.sleep(2)
delr = api("DELETE", f"/clients/{CID}")
check("DELETE /clients/{id} succeeds", delr.status_code == 200, delr.status_code)
# reconnect with the now-deleted credentials -> must fail
reborn = HiveMessageBusClient(key=KEY, password=PW, crypto_key=CK,
                              host=CORE_HOST, port=CORE_PORT, self_signed=True)
threading.Thread(target=lambda: _safe(reborn), daemon=True).start()
revoked = not reborn.handshake_event.wait(10)
check("revoked credentials can no longer connect", revoked)
try: reborn.close()
except Exception: pass

# disconnect reflected in the UI
gone = poll(lambda: (lambda d: d if d.get("count", 0) == 0 else None)(api("GET", "/connections").json()), timeout=15)
check("/connections returns to 0 after disconnect/revoke",
      isinstance(gone, dict) and gone.get("count", 0) == 0,
      gone.get("count") if isinstance(gone, dict) else gone)

passed = sum(1 for _, ok in results if ok)
print(f"\n{passed}/{len(results)} real-e2e checks passed")
sys.exit(0 if passed == len(results) else 1)
