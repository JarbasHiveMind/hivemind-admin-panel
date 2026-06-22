# HiveMind Admin Panel — API Reference

REST API for managing HiveMind-core clients, permissions, server
configuration, plugins, databases, ACLs, personas, and OVOS integration.
Implemented as a FastAPI app in `hivemind_admin_panel/api.py`.

## Base URL & mounting

The FastAPI app declares routes at paths like `/clients` and `/health`. When
served by the panel's `__main__` app, the API is mounted under the `/api`
prefix. So a route declared `@app.get("/clients")` is reachable at:

```
http://<host>:8000/api/clients
```

Throughout this document, paths are written **as declared on the app** (without
the `/api` prefix). Prepend `/api` for the served URL. The default host/port
when launched via the panel is `0.0.0.0:8000`.

All endpoints **except `GET /health`** require HTTP Basic authentication.

## Authentication

Authentication is HTTP Basic. Credentials are read at request time from the
HiveMind-core server config (`~/.config/hivemind-core/server.json`):

| Config key   | Purpose        | Default   |
|--------------|----------------|-----------|
| `admin_user` | Basic username | `"admin"` |
| `admin_pass` | Basic password | `"admin"` |

Comparison uses `hmac.compare_digest` (constant-time). On failure the API
returns `401 Unauthorized` with `WWW-Authenticate: Basic` and
`{"detail": "Invalid credentials"}`.

To change credentials, set the keys in `server.json` (e.g. via
`POST /config`) and restart:

```bash
curl -u admin:admin -X POST http://localhost:8000/api/config \
  -H 'Content-Type: application/json' \
  -d '{"config": {"admin_user": "ops", "admin_pass": "s3cret"}}'
```

Every authenticated `curl` example below uses `-u admin:admin`. The dependency
is wired per-route via `Depends(verify_credentials)`.

### Standalone vs `--with-admin` mode

When hivemind-core is started with `--with-admin`, internal objects (service,
DB, listener protocol) are injected via `init_injected_objects()`, so
`/health`, `/connections`, and `/stats` return real-time data and
`/config/restart` works. In standalone admin mode those endpoints fall back to
config-only / mock data, and restart is unavailable.

---

## 1. Health & status

| Method | Path             | Auth | Description |
|--------|------------------|------|-------------|
| GET    | `/health`        | No   | Health check with version, status, and (if injected) live counts |
| GET    | `/startup-error` | Yes  | Full traceback of a core startup failure, if any |

### `GET /health`
No auth. Returns `status` (`"ok"` or `"degraded"`), `version`, `timestamp`,
and — when core objects are injected — `service_status`, `active_connections`,
and `total_clients`. Error details are never exposed here.

```bash
curl http://localhost:8000/api/health
```

### `GET /startup-error`
Returns `error`, `error_type`, `traceback`, `timestamp`. Responds `404` if no
startup error was recorded.

---

## 2. Configuration

| Method | Path               | Auth | Body            | Description |
|--------|--------------------|------|-----------------|-------------|
| GET    | `/config`          | Yes  | —               | Full server config from `server.json` |
| POST   | `/config`          | Yes  | `ConfigUpdate`  | Merge keys into config and persist |
| POST   | `/config/validate` | Yes  | `ConfigUpdate`  | Validate config without applying |
| POST   | `/config/restart`  | Yes  | —               | Trigger async service restart |
| GET    | `/config/defaults` | Yes  | —               | Default config values (`_DEFAULT`) |

### `POST /config`
Merges each key from `config` into the live config and calls `cfg.store()`.
**Side effect: writes `server.json`.** Returns `{"status": "ok"}`.

```bash
curl -u admin:admin -X POST http://localhost:8000/api/config \
  -H 'Content-Type: application/json' \
  -d '{"config": {"binarize": true}}'
```

### `POST /config/validate`
Returns a `ConfigValidationResult` (`valid`, `errors`, `warnings`). Checks for
required keys (`agent_protocol`, `network_protocol`, `database`), attempts to
load referenced plugin classes via the factories (**plugin discovery**), and
warns about missing optional deps (`zeroconf`, `ggwave`).

### `POST /config/restart`
**Side effect: schedules a graceful service restart via a background task** —
sets `HIVEMIND_AUTO_RESTART=1` and signals the service to stop. Only works in
`--with-admin` mode; in standalone mode returns
`RestartResult(status="error", ...)`. Returns `RestartResult`.

```bash
curl -u admin:admin -X POST http://localhost:8000/api/config/restart
```

---

## 3. Clients (CRUD)

| Method | Path                              | Auth | Body           | Description |
|--------|-----------------------------------|------|----------------|-------------|
| GET    | `/clients`                        | Yes  | —              | List all clients (incl. revoked); excludes internal id=-1 |
| GET    | `/clients/active`                 | Yes  | —              | List only non-revoked clients |
| GET    | `/clients/{client_id}`            | Yes  | —              | Get one client |
| GET    | `/clients/{client_id}/credentials`| Yes  | —              | Get api_key, password, crypto_key |
| POST   | `/clients`                        | Yes  | `ClientCreate` | Create a client |
| PUT    | `/clients/{client_id}`            | Yes  | `ClientUpdate` | Update a client |
| DELETE | `/clients/{client_id}`            | Yes  | —              | Delete (revoke) a client |
| POST   | `/clients/{client_id}/rename`     | Yes  | `{"name": ...}`| Rename a client |

Client objects are returned by `_client_to_dict`, which includes: `client_id`,
`name`, `description`, `api_key`, `is_admin`, `allowed_types`,
`message_blacklist`, `skill_blacklist`, `intent_blacklist`, `can_escalate`,
`can_propagate`, `can_broadcast`, `last_seen`, `revoked`. Create/update
responses additionally include `password` and `crypto_key` (secrets).
A revoked client has `api_key == "REVOKED"` (case-insensitive) or `revoked` set.

### `POST /clients`
Auto-generates `password` and `api_key` (16-byte hex) when omitted; name
defaults to `HiveMind-Node-<count>`. `crypto_key`, if provided, must be 16, 24,
or 32 chars (else `400`). **Side effect: writes to the client database.**
Returns the full client dict including secrets.

```bash
curl -u admin:admin -X POST http://localhost:8000/api/clients \
  -H 'Content-Type: application/json' \
  -d '{"name": "satellite-1", "is_admin": false}'
```

### `PUT /clients/{client_id}`
Updates only the fields present in `ClientUpdate`. `crypto_key` length is
validated (`400` if invalid). `404` if client not found. Returns updated client
with secrets.

```bash
curl -u admin:admin -X PUT http://localhost:8000/api/clients/3 \
  -H 'Content-Type: application/json' \
  -d '{"can_escalate": true, "skill_blacklist": ["skill-weather.openvoiceos"]}'
```

### `DELETE /clients/{client_id}`
Calls `db.delete_client(api_key)` (revokes). `404` if not found. Returns
`{"status": "ok"}`.

### `POST /clients/{client_id}/rename`
Body is a raw dict `{"name": "..."}`. `400` if `name` missing, `404` if not
found.

---

## 4. Client ACLs (per-flag grant/revoke)

These mutate a single permission and return the updated client dict (no
secrets). All require auth and respond `404` if the client is not found.
**Side effect: each writes to the client database** via `db.update_item`.

### Message types

| Method | Path                                   | Body             | Effect |
|--------|----------------------------------------|------------------|--------|
| POST   | `/clients/{client_id}/allow-msg`       | `MsgTypeRequest` | Add `msg_type` to `allowed_types` |
| POST   | `/clients/{client_id}/blacklist-msg`   | `MsgTypeRequest` | Remove `msg_type` from `allowed_types` |

```bash
curl -u admin:admin -X POST http://localhost:8000/api/clients/3/allow-msg \
  -H 'Content-Type: application/json' \
  -d '{"msg_type": "recognizer_loop:utterance"}'
```

### Skills

| Method | Path                                    | Body          | Effect |
|--------|-----------------------------------------|---------------|--------|
| POST   | `/clients/{client_id}/allow-skill`      | `SkillRequest`| Remove `skill_id` from `skill_blacklist` |
| POST   | `/clients/{client_id}/blacklist-skill`  | `SkillRequest`| Add `skill_id` to `skill_blacklist` |

### Intents

| Method | Path                                    | Body           | Effect |
|--------|-----------------------------------------|----------------|--------|
| POST   | `/clients/{client_id}/allow-intent`     | `IntentRequest`| Remove `intent_id` from `intent_blacklist` |
| POST   | `/clients/{client_id}/blacklist-intent` | `IntentRequest`| Add `intent_id` to `intent_blacklist` |

### Boolean flags (no body)

| Method | Path                                      | Effect |
|--------|-------------------------------------------|--------|
| POST   | `/clients/{client_id}/allow-escalate`     | `can_escalate = true` |
| POST   | `/clients/{client_id}/blacklist-escalate` | `can_escalate = false` |
| POST   | `/clients/{client_id}/allow-propagate`    | `can_propagate = true` |
| POST   | `/clients/{client_id}/blacklist-propagate`| `can_propagate = false` |
| POST   | `/clients/{client_id}/make-admin`         | `is_admin = true` |
| POST   | `/clients/{client_id}/revoke-admin`       | `is_admin = false` |

```bash
curl -u admin:admin -X POST http://localhost:8000/api/clients/3/make-admin
```

### Structured ACL (whole-block read/update + templates)

| Method | Path                                          | Auth | Body              | Description |
|--------|-----------------------------------------------|------|-------------------|-------------|
| GET    | `/clients/{client_id}/acl`                    | Yes  | —                 | Read core ACL block for a client |
| PUT    | `/clients/{client_id}/acl`                    | Yes  | `ACLUpdateRequest`| Update ACL fields in one call |
| POST   | `/clients/{client_id}/acl/apply-template`     | Yes  | query `template_name` | Apply a named ACL template |

`GET`/`PUT` return: `client_id`, `name`, `is_admin`, `can_escalate`,
`can_propagate`, `allowed_types`, `skill_blacklist`, `intent_blacklist`.
`PUT` updates only the provided `ACLUpdateRequest` fields. **Side effect:
writes to the client DB.** `404` if not found.

`apply-template` takes `template_name` as a **query parameter** (not body),
looks it up in `acl_config.json`, and sets `allowed_types`,
`message_blacklist`, `skill_blacklist`, `intent_blacklist` from the template.
`404` if client or template not found.

```bash
curl -u admin:admin -X POST \
  "http://localhost:8000/api/clients/3/acl/apply-template?template_name=voice-satellite"
```

---

## 5. Monitoring

| Method | Path           | Auth | Description |
|--------|----------------|------|-------------|
| GET    | `/connections` | Yes  | Active connections (real-time with `--with-admin`, else mock) |
| GET    | `/stats`       | Yes  | Server statistics |

### `GET /connections`
With an injected protocol, returns `count` and a `connections` list with
`peer`, `key`, `session_id`, `is_authenticated`. In standalone mode returns
`{"count": 0, "connections": [], "note": "..."}`.

### `GET /stats`
Returns `network_protocols` (count), `agent_protocol` (module), `binarize`,
and — when objects are injected — `client_count`, `total_clients`,
`active_connections`, `service_status`.

---

## 6. Plugins

| Method | Path                                       | Auth | Body                  | Description |
|--------|--------------------------------------------|------|-----------------------|-------------|
| GET    | `/plugins`                                 | Yes  | —                     | All known plugins + installed status (from `plugins_config.json`) |
| POST   | `/plugins/install`                         | Yes  | `PluginInstallRequest`| Install a package via pip |
| POST   | `/plugins/enable`                          | Yes  | `ConfigUpdateRequest` | Enable/disable a plugin in config |
| GET    | `/plugins/solvers`                         | Yes  | —                     | Solver plugins with install status |
| GET    | `/plugins/installed/ovos/{plugin_type}`    | Yes  | —                     | Installed OVOS plugins (`stt`/`tts`/`ww`/`vad`) |
| GET    | `/plugins/installed/hivemind/{plugin_type}`| Yes  | —                     | Installed HiveMind plugins (`network`/`agent`/`database`/`binary`) |

### `POST /plugins/install`
**Side effect: runs `subprocess` `python -m pip install <package>`** (120s
timeout). The package name is lowercased/stripped. Returns
`PluginInstallResult` (`success`, `message`, `config_updated`); failures are
reported in `message`, not raised.

```bash
curl -u admin:admin -X POST http://localhost:8000/api/plugins/install \
  -H 'Content-Type: application/json' \
  -d '{"package": "hivemind-websocket-protocol"}'
```

### `POST /plugins/enable`
Updates `server.json` for the given `plugin_type` (`database`,
`agent_protocol`, `binary_protocol`, `network_protocol`). For
`network_protocol` with `enabled=false` it deletes the entry; default network
config when none given is `{"host": "0.0.0.0", "port": 5678, "ssl": false}`.
For `binary_protocol` with `enabled=false` it sets `module=None`.
**Side effect: writes `server.json`.** Returns `PluginInstallResult`.

```bash
curl -u admin:admin -X POST http://localhost:8000/api/plugins/enable \
  -H 'Content-Type: application/json' \
  -d '{"plugin_type": "database", "module": "hivemind-redis-db-plugin",
       "enabled": true, "config": {"host": "localhost", "port": 6379}}'
```

### `GET /plugins/solvers`
Cross-references `plugins_config.json` `solver_plugins` against installed
entry-points (`find_question_solver_plugins`, `find_chat_solver_plugins`,
`find_chat_plugins`). `install_status` is one of `installed`, `failed`
(package present but entry-point not registered), or `missing`.
**Side effect: OVOS plugin discovery.**

### `GET /plugins/installed/ovos/{plugin_type}`
`plugin_type` ∈ `stt`, `tts`, `ww`, `vad` (else `400`). Returns entry points
with `install_status: "installed"`, `package`, `error`. **Side effect: OVOS
plugin discovery.**

### `GET /plugins/installed/hivemind/{plugin_type}`
`plugin_type` ∈ `network`, `agent`, `database`, `binary` (else `400`). Returns
a flat list of entry-point strings. **Side effect: HiveMind plugin discovery.**

---

## 7. Database profiles

Named, reusable DB backend configs stored as JSON files in
`~/.config/hivemind-core/database_profiles/<name>.json` (schema
`{"module": ..., "config": {...}}`). On first access a `default` profile is
bootstrapped from the current `server.json` `database` section. The "active"
profile is whichever profile's module+config matches `server.json`.

| Method | Path                                  | Auth | Body                    | Description |
|--------|---------------------------------------|------|-------------------------|-------------|
| GET    | `/database/profiles`                  | Yes  | —                       | List profiles + active name |
| POST   | `/database/profiles`                  | Yes  | `DatabaseProfileCreate` | Create a profile (does not activate) |
| GET    | `/database/profiles/{name}`           | Yes  | —                       | Get one profile |
| PUT    | `/database/profiles/{name}`           | Yes  | `DatabaseProfileUpdate` | Update a profile |
| DELETE | `/database/profiles/{name}`           | Yes  | —                       | Delete a profile |
| POST   | `/database/profiles/{name}/test`      | Yes  | —                       | Test connectivity for a profile |
| POST   | `/database/profiles/{name}/activate`  | Yes  | `ActivateProfileRequest`| Activate (optionally migrate) |

### `GET /database/profiles`
Returns `{"profiles": {name: {...}}, "active": <name|null>}`. **Side effect:
may write `default.json` on first call.**

### `POST /database/profiles`
Name must match `^[a-zA-Z0-9_-]+$` (else `422`); `409` if it already exists.
**Side effect: writes a profile file.** Does not change the active DB.

```bash
curl -u admin:admin -X POST http://localhost:8000/api/database/profiles \
  -H 'Content-Type: application/json' \
  -d '{"name": "redis-prod", "module": "hivemind-redis-db-plugin",
       "config": {"host": "10.0.0.5", "port": 6379, "db": 0}}'
```

### `PUT /database/profiles/{name}`
`404` if not found. **`409` if changing `module` of the active profile.**
**Side effect: writes the profile file.**

### `DELETE /database/profiles/{name}`
`404` if not found. **`409` if it is the active profile.** **Side effect:
deletes the profile file.**

### `POST /database/profiles/{name}/test`
Returns `DatabaseTestResult`. **Side effect: for Redis modules opens a TCP
socket + PING; for file-based modules probes parent-directory writability.**

### `POST /database/profiles/{name}/activate`
Validates the plugin loads (`400` if not). With `migrate_data=true`, copies
clients from the current DB into the target (`500` on failure). Then writes the
profile's module+config into `server.json["database"]`. **Side effects: opens
both DBs and copies clients; writes `server.json`.** A restart is required.
Returns `ActivateProfileResult`.

```bash
curl -u admin:admin -X POST \
  http://localhost:8000/api/database/profiles/redis-prod/activate \
  -H 'Content-Type: application/json' \
  -d '{"migrate_data": true}'
```

---

## 8. Database management

| Method | Path                          | Auth | Body                       | Description |
|--------|-------------------------------|------|----------------------------|-------------|
| POST   | `/database/test`              | Yes  | `{module, config}`         | Test a module+config without saving |
| POST   | `/database/migrate`           | Yes  | `DatabaseMigrationRequest` | **Deprecated** legacy migration |
| GET    | `/database/backends`          | Yes  | —                          | Available DB backends + install status |
| GET    | `/database/{module}/clients`  | Yes  | —                          | List clients from a specific DB module |
| POST   | `/database/copy-client`       | Yes  | `CopyClientRequest`        | Copy one client between DBs |
| POST   | `/database/{module}/clear`    | Yes  | —                          | Delete all clients from a DB module |

### `POST /database/test`
Body is a raw dict with `module` (entry-point) and optional `config`. Returns
`DatabaseTestResult`. **Side effect: TCP/PING for Redis or directory write
probe for file backends.**

```bash
curl -u admin:admin -X POST http://localhost:8000/api/database/test \
  -H 'Content-Type: application/json' \
  -d '{"module": "hivemind-redis-db-plugin", "config": {"host": "localhost", "port": 6379}}'
```

### `POST /database/migrate` (deprecated)
Prefer `POST /database/profiles/{name}/activate`. Sets an `X-Deprecated`
response header. Migrates from the current DB to `target_module` when
`preserve_data` is true, then writes `server.json["database"] = {"module":
target_module}`. **Side effects: opens both DBs, copies clients, writes
config.** Returns `DatabaseMigrationResult` (errors returned in the body, not
raised).

### `GET /database/backends`
From `plugins_config.json` `databases`. Each entry: `package`, `entry_point`,
`module`, `name`, `type`, `description`, `installed`.

### `GET /database/{module}/clients`
Instantiates the named DB plugin and lists clients **with secrets**. `500` on
error. **Side effect: opens the target DB (may open network sockets).**

### `POST /database/copy-client`
Copies the client matching `api_key` from `source_module` to `target_module`,
including ACL fields. `404` if not found in source, `500` on error. **Side
effect: writes to the target DB.**

### `POST /database/{module}/clear`
Deletes every non-internal client from the module's DB. `500` on error. **Side
effect: destructive — wipes the target DB's clients.** Returns count cleared.

---

## 9. ACL config (reference data)

Read-only lookups served from `acl_config.json` (bundled with the package).

| Method | Path             | Auth | Description |
|--------|------------------|------|-------------|
| GET    | `/acl/config`    | Yes  | Full ACL config (messages, skills, intents, templates) |
| GET    | `/acl/templates` | Yes  | Predefined ACL templates |
| GET    | `/acl/messages`  | Yes  | Common message types with descriptions |
| GET    | `/acl/skills`    | Yes  | Common skill IDs with descriptions |
| GET    | `/acl/intents`   | Yes  | Common intent IDs with descriptions |

```bash
curl -u admin:admin http://localhost:8000/api/acl/templates
```

(Applying a template to a client is `POST /clients/{client_id}/acl/apply-template`,
documented in §4.)

---

## 10. Persona management

Personas are JSON files in `~/.config/ovos_persona/`. The active persona is
recorded in `server.json` under
`agent_protocol["hivemind-persona-agent-plugin"]["persona"]`.

| Method | Path                       | Auth | Body            | Description |
|--------|----------------------------|------|-----------------|-------------|
| GET    | `/persona/config`          | Yes  | —               | Bundled `persona.json` template |
| PUT    | `/persona/config`          | Yes  | raw dict        | Save persona config to `~/.config/ovos_persona/persona.json` |
| GET    | `/personas`                | Yes  | —               | List all persona files |
| GET    | `/personas/active`         | Yes  | —               | Currently active persona name/path |
| GET    | `/personas/{name}`         | Yes  | —               | Get one persona |
| POST   | `/personas`                | Yes  | `PersonaCreate` | Create a persona |
| PUT    | `/personas/{name}`         | Yes  | raw dict        | Update a persona |
| DELETE | `/personas/{name}`         | Yes  | —               | Delete a persona file |
| POST   | `/personas/{name}/test`    | Yes  | —               | Validate + check models/solvers |
| GET    | `/personas/{name}/export`  | Yes  | —               | Export persona JSON |
| POST   | `/personas/{name}/activate`| Yes  | —               | Set persona as active in config |

### `PUT /persona/config`
**Side effect: writes `~/.config/ovos_persona/persona.json`.** `500` on write
failure.

### `POST /personas`
Validates: must have `name` and a non-empty `solvers`/`handlers` list (`400`
otherwise). Filename is sanitized from the name. **Side effect: writes a
persona JSON file.** Returns the config plus `status` and `path`.

```bash
curl -u admin:admin -X POST http://localhost:8000/api/personas \
  -H 'Content-Type: application/json' \
  -d '{"name": "Assistant", "solvers": ["ovos-solver-openai-plugin"],
       "memory_module": "ovos-agents-short-term-memory-plugin"}'
```

### `PUT /personas/{name}`
`404` if not found, `400` if the new config fails validation. **Side effect:
overwrites the persona file.**

### `DELETE /personas/{name}`
`404` if not found. **Side effect: deletes the persona file.**

### `POST /personas/{name}/test`
Returns `valid`, `errors`, `warnings`, `download_required`, `solvers`, `name`,
`description`. Flags missing GGUF model files and unrecognized/uninstalled
solver plugins. **Side effect: OVOS solver-plugin discovery.**

### `POST /personas/{name}/activate`
Writes the persona's full path into
`agent_protocol["hivemind-persona-agent-plugin"]["persona"]` and sets
`agent_protocol["module"] = "hivemind-persona-agent-plugin"`. **Side effect:
writes `server.json`.** `404` if not found, `500` if the persona has no file.

```bash
curl -u admin:admin -X POST http://localhost:8000/api/personas/Assistant/activate
```

---

## 11. OVOS integration

| Method | Path            | Auth | Query params | Description |
|--------|-----------------|------|--------------|-------------|
| GET    | `/ovos/test-bus`| Yes  | `host` (default `127.0.0.1`), `port` (default `8181`) | Test connection to an OVOS messagebus |

### `GET /ovos/test-bus`
**Side effect: opens a TCP socket and a websocket handshake** to
`ws://{host}:{port}/core` (2s timeouts). Returns
`{"success": bool, "message": str}`; failures are returned in the body, not
raised.

```bash
curl -u admin:admin "http://localhost:8000/api/ovos/test-bus?host=127.0.0.1&port=8181"
```

(OVOS plugin listing is `GET /plugins/installed/ovos/{plugin_type}`, see §6.)

---

## Appendix: Request models

Pydantic models defined in `api.py`. Optional fields default to `None` unless
noted.

### `ClientCreate`
| Field        | Type            | Default |
|--------------|-----------------|---------|
| `name`       | `Optional[str]` | `None` (auto: `HiveMind-Node-<n>`) |
| `api_key`    | `Optional[str]` | `None` (auto: random hex) |
| `password`   | `Optional[str]` | `None` (auto: random hex) |
| `crypto_key` | `Optional[str]` | `None` |
| `is_admin`   | `bool`          | `False` |

### `ClientUpdate`
All optional, default `None`: `name`, `api_key`, `password`, `crypto_key`
(`str`); `is_admin`, `can_escalate`, `can_propagate` (`bool`); `allowed_types`,
`message_blacklist`, `skill_blacklist`, `intent_blacklist` (`List[str]`).

### `ClientResponse`
| Field | Type |
|-------|------|
| `client_id` | `int` |
| `name` | `str` |
| `api_key` | `str` |
| `is_admin` | `bool` |
| `allowed_types` | `List[str]` |
| `message_blacklist` | `List[str]` |
| `skill_blacklist` | `List[str]` |
| `intent_blacklist` | `List[str]` |
| `can_escalate` | `bool` |
| `can_propagate` | `bool` |
| `last_seen` | `float` |

### `MsgTypeRequest`
| Field | Type | Default |
|-------|------|---------|
| `msg_type` | `str` | — |

### `SkillRequest`
| Field | Type | Default |
|-------|------|---------|
| `skill_id` | `str` | — |

### `IntentRequest`
| Field | Type | Default |
|-------|------|---------|
| `intent_id` | `str` | — |

### `ACLUpdateRequest`
| Field | Type | Default |
|-------|------|---------|
| `client_id` | `int` | — |
| `is_admin` | `Optional[bool]` | `None` |
| `can_escalate` | `Optional[bool]` | `None` |
| `can_propagate` | `Optional[bool]` | `None` |
| `allowed_types` | `Optional[List[str]]` | `None` |
| `skill_blacklist` | `Optional[List[str]]` | `None` |
| `intent_blacklist` | `Optional[List[str]]` | `None` |

### `ConfigUpdate`
| Field | Type | Default |
|-------|------|---------|
| `config` | `Dict[str, Any]` | — |

### `ConfigValidationResult` (response)
| Field | Type |
|-------|------|
| `valid` | `bool` |
| `errors` | `List[str]` |
| `warnings` | `List[str]` |

### `RestartResult` (response)
| Field | Type |
|-------|------|
| `status` | `str` |
| `message` | `str` |

### `PluginInfo` (response)
| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `package` | `str` | — |
| `entry_point` | `Optional[str]` | `None` |
| `description` | `str` | — |
| `category` | `str` | — (`agent`/`network`/`database`/`binary`/`stt`/`tts`/`ww`/`vad`/`other`) |
| `installed` | `bool` | — |

### `PluginInstallRequest`
| Field | Type | Default |
|-------|------|---------|
| `package` | `str` | — |

### `PluginInstallResult` (response)
| Field | Type | Default |
|-------|------|---------|
| `success` | `bool` | — |
| `message` | `str` | — |
| `config_updated` | `bool` | `False` |

### `ConfigUpdateRequest`
| Field | Type | Default |
|-------|------|---------|
| `plugin_type` | `str` | — (`agent_protocol`/`network_protocol`/`database`/`binary_protocol`) |
| `module` | `str` | — |
| `enabled` | `bool` | — |
| `config` | `Optional[Dict[str, Any]]` | `None` |

### `DatabaseProfile`
| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `module` | `str` | — |
| `config` | `Dict[str, Any]` | `{}` |

### `DatabaseProfileCreate`
| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `module` | `str` | — |
| `config` | `Dict[str, Any]` | `{}` |

### `DatabaseProfileUpdate`
| Field | Type | Default |
|-------|------|---------|
| `module` | `Optional[str]` | `None` |
| `config` | `Optional[Dict[str, Any]]` | `None` |

### `ActivateProfileRequest`
| Field | Type | Default |
|-------|------|---------|
| `migrate_data` | `bool` | `False` |

### `ActivateProfileResult` (response)
| Field | Type | Default |
|-------|------|---------|
| `success` | `bool` | — |
| `message` | `str` | — |
| `profile_name` | `str` | — |
| `clients_migrated` | `int` | `0` |

### `DatabaseMigrationRequest`
| Field | Type | Default |
|-------|------|---------|
| `target_module` | `str` | — |
| `preserve_data` | `bool` | `True` |

### `DatabaseMigrationResult` (response)
| Field | Type |
|-------|------|
| `success` | `bool` |
| `message` | `str` |
| `source_module` | `str` |
| `target_module` | `str` |
| `clients_migrated` | `int` |

### `DatabaseTestResult` (response)
| Field | Type |
|-------|------|
| `success` | `bool` |
| `message` | `str` |
| `module` | `str` |

### `CopyClientRequest`
| Field | Type | Default |
|-------|------|---------|
| `source_module` | `str` | — |
| `target_module` | `str` | — |
| `api_key` | `str` | — |

### `PersonaCreate`
| Field | Type | Default |
|-------|------|---------|
| `name` | `str` | — |
| `description` | `Optional[str]` | `None` |
| `solvers` | `List[str]` | `[]` |
| `handlers` | `Optional[List[str]]` | `None` |
| `memory_module` | `Optional[str]` | `"ovos-agents-short-term-memory-plugin"` |

> Note: several endpoints accept a raw `Dict` body rather than a typed model:
> `POST /clients/{client_id}/rename` (`{"name": ...}`), `POST /database/test`
> (`{"module": ..., "config": ...}`), `PUT /persona/config`, and
> `PUT /personas/{name}`.
