# Integration harness — live bus-client validation

`live_e2e.py` is a **manual** end-to-end check that a real
[`HiveMessageBusClient`](https://github.com/JarbasHiveMind/hivemind-websocket-client)
can connect to an in-process hivemind-core launched by this panel, and that the
admin UI's live views (`/connections`, `/health`, `/topology`, the message
inspector, `/events`) reflect reality — including auth rejection of bogus keys
and that **deleting a client through the UI actually revokes access**.

It is not part of the CI unit suite (it needs a live core + an OVOS messagebus).
The CI guards are the unit regressions in `tests/` (`test_health.py::core_ready`,
`test_concurrency.py`, `test_setup_security.py`).

## Prerequisites

hivemind-core's default agent protocol bridges to an **OVOS messagebus**. Its
constructor blocks until that bus is reachable, so the satellite listener only
binds once a messagebus is up. Without one, `/health` reports
`service_status: STARTED` with `core_ready: false` and **no satellite can
connect** (the dashboard now warns about exactly this).

```bash
uv pip install ovos-messagebus            # an agent backend for the core
ovos-messagebus &                          # binds 127.0.0.1:8181

# launch the panel + in-process core (default admin/admin)
hivemind-admin-panel --host 127.0.0.1 --port 8100 &

# run the harness
ADMIN_URL=http://127.0.0.1:8100/api python integration/live_e2e.py
```

Exits non-zero on the first failed assertion; prints a PASS/FAIL line per check.
