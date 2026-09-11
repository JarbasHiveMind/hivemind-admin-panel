# Development

> **Paths in this file** omit the `/api` prefix the panel mounts the API under.
> A route written `/clients` is served at `http://<host>:8100/api/clients`.

## Setup

```bash
git clone https://github.com/JarbasHiveMind/hivemind-admin-panel
cd hivemind-admin-panel
pip install -e ".[test]"      # or: uv pip install -e ".[test]"
```

## Layout

| Path | Contents |
|------|----------|
| `hivemind_admin_panel/` | the package (`api.py`, `__main__.py`, `static/`, JSON defaults) |
| `tests/` | Python end-to-end test suite (pytest) |
| `frontend/` | legacy JS/Jest tests for the SPA |
| `docs/` | this documentation |
| `docker/` | `server.json` used by the Compose stack |

## Running the tests

```bash
pytest tests/ -v
```

### How the end-to-end suite works

The suite (`tests/conftest.py`) is genuinely end-to-end, not mock-heavy:

- It points `XDG_CONFIG_HOME` / `XDG_DATA_HOME` at a throwaway temp directory
  **before** any hivemind/ovos import, so all config and database state is isolated.
- It writes a real `server.json` with known admin credentials and a JSON client DB.
- It injects a **real `ClientDatabase`** into the app via `init_injected_objects`
  and drives the app through FastAPI's `TestClient` with real HTTP Basic auth.

So client CRUD, ACL edits, config writes, database profiles, and personas are
exercised against real on-disk state. Only genuinely external boundaries are
stubbed, and only in the tests that touch them:

| Boundary | Stub |
|----------|------|
| `POST /plugins/install` | `subprocess.run` monkeypatched (never runs `pip`) |
| `GET /ovos/test-bus` | `socket` / `create_connection` monkeypatched (no network) |
| `GET /plugins/solvers` | plugin-discovery functions monkeypatched for determinism |

Test modules map to API domains: `test_auth`, `test_health`, `test_clients`,
`test_client_acls`, `test_config`, `test_monitoring`, `test_plugins`,
`test_database`, `test_personas`, `test_ovos_bus`, plus `test_smoke` (package +
asset bundling).

## CI

GitHub Actions wire the repo to the shared OpenVoiceOS `gh-automations` reusable
workflows (always `@dev`):

| Workflow | Role |
|----------|------|
| `build-tests` | install the wheel + `[test]` extra, run `tests/` on a Python matrix |
| `coverage` | run the suite with coverage on `hivemind_admin_panel` |
| `lint` | ruff |
| `license_check`, `pip_audit` | dependency license + vulnerability audit |
| `release-preview`, `release_workflow`, `publish_stable` | alpha/stable PyPI releases |
| `repo-health`, `conventional-label` | repo hygiene + PR labelling |
| `publish-docker` | build + push the container image to GHCR |

The end-to-end suite runs in `build-tests` and `coverage` on every PR.

## Conventions

- Versions bump automatically from conventional-commit prefixes. **Do not edit
  `version.py`** by hand.
- Branch model: work on a feature branch, then PR into `dev`. Releases flow from `dev`
  to `master`. `dev` is the default branch.
- License: Apache-2.0. Keep the SPDX header on new source files.


### What it looks like

**Widescreen**

![Monitor: live message flow, the fastest way to see your change work (widescreen)](img/monitor.png)

**Mobile**

![Monitor: live message flow, the fastest way to see your change work (mobile)](img/monitor-mobile.png)

---
[← API reference](api-reference.md) · [Home](index.md) · [Roadmap →](roadmap.md)
