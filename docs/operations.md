# Operations & monitoring

Beyond configuration, the panel is an operations console. This page covers the
real-time, security, onboarding, and ops features.

## Monitor (real-time)

![Monitor](img/monitor.png)

The **Monitor** page surfaces live state:

- **Metrics**: uptime, active connections, total clients, service status, and
  action counters (`GET /metrics`). Tick **live** to stream updates over
  Server-Sent Events (`GET /events`).
- **Event feed**: recent hivemind-core and admin events from an in-process ring buffer
  (`GET /events/recent`). The SSE stream pushes new ones as they happen.
- **hivemind-core log**: a tail of `core.log` with an optional level filter (`GET /logs`).
- **Audit log**: every mutating admin request, with the acting user
  (`GET /audit`).

> The SSE feed authenticates with a short-lived token passed as `?access_token=`,
> because the browser `EventSource` API cannot set headers.

## Authentication, roles & audit

- **Session tokens**: `POST /auth/login` exchanges credentials for an
  HMAC-signed bearer token. Send it as `Authorization: Bearer <token>`. HTTP
  Basic still works for scripts and back-compat. `GET /auth/me` reports the current
  user and role. `POST /auth/logout` is a client-side token discard.
- **Roles**: `admin` (full) and `operator` (read plus non-destructive writes).
  Extra accounts go in `server.json`:

  ```jsonc
  { "users": [{ "username": "ops", "password": "...", "role": "operator" }] }
  ```

  Destructive actions (plugin install, DB migrate/clear, restore, policy/cert
  writes) require the `admin` role.
- **Audit log**: a middleware records every `POST`, `PUT`, and `DELETE` (user, path,
  status) to `~/.local/share/hivemind-admin/audit.log`.
- **uv installs**: `POST /plugins/install` uses `uv` (pip fallback) and is
  admin-gated.

## Satellite onboarding (pairing)

The **Topology** page draws hivemind-core and its satellites. Click a satellite to open
a **pairing modal** with a scannable **QR code** and the full bundle.

- `GET /clients/{id}/pairing`: credentials, the hivemind-core websocket endpoint, and a QR JSON
  payload. Pass `?host=<LAN-IP>` when hivemind-core binds `0.0.0.0`.
- `GET /clients/{id}/pairing/qr.svg`: the bundle rendered as a QR SVG.
- `POST /clients/bulk`: batch `delete`, `make_admin`, `revoke_admin`, or
  `apply_template` over many clients.

## OVOS servers

The **OVOS Servers** page registers external [persona, STT, TTS, and translate
servers](ovos-servers.md) and health-checks them:

- `GET`/`POST /servers`, `DELETE /servers/{id}`: registry stored under
  `~/.config/hivemind-admin/servers.json`.
- `GET /servers/{id}/health`: reachability and latency probe.

## Personas & agents

- **Multi-turn test chat**: `POST /personas/{name}/chat/sessions` opens a session
  that keeps one live `Persona` (and its memory) across turns. `say`/`messages`
  drive it. `DELETE` (or "New session") resets it. The legacy one-shot
  `POST /personas/{name}/chat` still works.
- **Pre-activation validation**: `POST /personas/{name}/activate` rejects (409) a
  persona with config errors or uninstalled handlers, unless `?force=true`.
- `GET /plugins/agents` lists installed plugins per modern engine type (chat,
  memory, summarizer, reranker, retrieval, QA, yes/no, and coreference, among others).
- `GET /plugins/memory` lists persona memory plugins.

## Plugin lifecycle

Install is no longer one-way. Installed plugins show their **version** and gain
**Update** and **Uninstall** buttons (OVOS Plugins page, per tab):

- `POST /plugins/install`, `POST /plugins/upgrade`: `uv pip install [--upgrade]`
  (pip fallback). Upgrade reports the before-to-after version.
- `POST /plugins/uninstall`: `uv pip uninstall`, **refused** if the package
  provides a currently active module (agent, network, database, or binary). Switch
  modules first.
- `version` is surfaced on `/plugins`, `/plugins/installed/ovos/{type}`, and
  `/plugins/solvers`. All lifecycle writes are admin-gated and prompt a restart.

![Plugin lifecycle](img/plugin-lifecycle.png)

## Backup, policy & TLS (Operations page)

![Operations](img/operations.png)

- **Backup/restore**: `GET /backup` downloads a config, clients, and servers
  bundle. `POST /restore` re-adds missing clients (and optionally config and servers).
- **Config history**: `server.json` is snapshotted automatically before every
  config or plugin change (the last 20 are kept). The **Config history** card lists snapshots
  with **Diff** (`GET /config/backups/diff`) and **Revert**
  (`POST /config/backups/restore`, which snapshots the current state first). Take a manual
  snapshot with `POST /config/backups`.

![Config history](img/config-history.png)

- **Policy chain**: `GET`/`PUT /policy` edits the message admission policy chain.
- **TLS certs**: `GET /certs` shows certificate status for the websocket
  transport. `POST /certs/generate` creates a self-signed cert.

## Mesh topology

`GET /topology` returns graph data (hivemind-core and client nodes, edges, live `online`
flags), rendered as an interactive SVG on the Topology page.

## API docs

FastAPI's interactive Swagger UI is served at **`/api/docs`** (OpenAPI schema at
`/api/openapi.json`).

## Live monitoring & message inspector

When hivemind-core runs **in-process** (the default), the panel taps the listener
protocol, so `/connections`, `/stats`, the topology `online` flags, and the
**message inspector** (`GET /messages/recent`, filter by `msg_type` or `peer`) are
authoritative, with no hivemind-core change required. In `--no-core` mode they degrade
gracefully.

## Security notes

- **Password hashing**: `server.json` passwords may be PBKDF2 hashes
  (`pbkdf2_sha256$...`). Legacy plaintext still works. Change your password with
  `POST /auth/password` (stores a hash).
- **CSRF** is not applicable. The API authenticates through the `Authorization` header
  (Basic/Bearer), not cookies, so it is not exposed to cross-site request forgery.
- **Config dry-run**: `POST /config/diff` previews added, removed, and changed keys
  before you apply a config.

---
[← Plugin presets](presets.md) · [Home](index.md) · [Security →](security.md)
