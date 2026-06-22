# Architecture

## Components

```
hivemind_admin_panel/
├── api.py          FastAPI app: ~68 REST endpoints (the whole admin API)
├── __main__.py     standalone entrypoint; mounts api under /api + serves the SPA
├── __init__.py     public API: start_admin_server, init_injected_objects, get_admin_app
├── static/         single-page web UI (index.html, js/app.js, css/style.css)
└── *.json          bundled defaults: acl_config, plugins_config, persona
```

The backend is a single FastAPI application. `__main__.py` builds an outer app that
mounts the API under `/api` and serves the SPA from `static/`. So a route documented
as `/clients` is served at `http://host:port/api/clients`, and the UI is at `/`.

## The coupling seam to core

The panel depends on `hivemind-core` (for `ClientDatabase`, config, and the plugin
factories), but its coupling to a *running* hivemind-core is deliberately tiny — a single
function:

```python
init_injected_objects(service=None, db=None, protocol=None, startup_error=None)
```

It stores the live objects in module globals that the endpoints read:

| Global | Source | Used by |
|--------|--------|---------|
| `_db` | `HiveMindService.db` | all `/clients/*`, `/stats`, DB endpoints |
| `_service` | the `HiveMindService` | `/config/restart`, service status |
| `_protocol` | the live listener protocol | `/connections`, live counts |
| `_startup_error` | exception if core failed to boot | `/startup-error` |

By default the panel is the launcher: `launch_core()` (in `__main__.py`)
constructs a `HiveMindService`, calls `init_injected_objects(service, db)`, and
runs hivemind-core in a daemon thread — then uvicorn serves the panel in the main
thread. So the panel holds the live hivemind-core reference directly; there is no separate
`hivemind-core` process and no `--with-admin` flag in core.

In `--no-core` mode none of the globals are injected; endpoints that need a live
hivemind-core degrade gracefully (placeholder connections, restart returns an error) while
everything DB/config/filesystem-backed works by opening the same on-disk state.

If hivemind-core raises during construction, `launch_core()` injects the exception as
`_startup_error` and the panel still serves, surfacing the error at
`GET /api/startup-error`.

## Why a separate package

The panel was extracted from core so that:

- it ships on its **own release cadence** (UI churn doesn't force core releases);
- the **admin plane is optional and separately deployable** — it can `pip install`
  packages, migrate databases, and restart the service, so you may not want it
  present in every deployment;
- core's wheel stays lean (no FastAPI/uvicorn unless you opt into `[admin]`);
- its **JS/frontend toolchain** stays out of the core repo.

## Known limitation & direction

Live objects are injected **once at startup**, and the panel starts *before* the
listener protocol is fully built — so live-connection introspection (`/connections`)
is best-effort. The intended direction is for core to expose a small, stable
read-only status/control seam (a localhost query or a bus message) that the panel
consumes, which would also let the panel run fully **out-of-process or remote**
rather than only in-process. Until then, treat `/connections` live data as
advisory and rely on the database-backed views for authoritative state.
