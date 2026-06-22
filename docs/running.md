# Running the panel

The panel runs in one of two modes. They expose the same REST API and UI; they
differ only in whether the panel has an in-process handle to a *running* hub.

## Standalone mode

```bash
hivemind-admin-panel --host 127.0.0.1 --port 8000 [--reload]
```

The panel reads the same on-disk state that `hivemind-core` uses on the host: the
`server.json` config and the configured client database. Everything backed by the
database, config files, plugin entry points, and the filesystem works:

- clients & access keys (create/list/update/delete, credentials)
- per-client ACLs (message types, skills, intents, escalate/propagate, admin)
- plugin discovery and installation, database profiles & migration
- persona management, config editing

**Not available standalone** (these need a live, in-process hub):

- `GET /connections` returns placeholder data — there is no live socket list
- `GET /stats` still reports DB-derived counts but no live connection count
- `POST /config/restart` returns an error (no service handle to restart)

Standalone mode is ideal for provisioning clients and editing config without
touching the running service, or on a host where the hub is managed separately.

## Integrated mode (`--with-admin`)

```bash
hivemind-core --with-admin --admin-host 127.0.0.1 --admin-port 8100
```

Here `hivemind-core` starts the panel in a daemon thread and injects live
references to its `service`, `database`, and `protocol` objects (see
[Architecture](architecture.md)). The panel is started **early** in core's
`run()`, so it stays reachable even if the agent protocol blocks (e.g. waiting for
the OVOS bus). If core fails to start entirely, `--with-admin` still brings the
panel up in a diagnostics mode that surfaces the startup error at
`GET /startup-error`.

| Flag | Default | Meaning |
|------|---------|---------|
| `--with-admin` | off | enable the panel |
| `--admin-host` | `127.0.0.1` | bind address for the panel |
| `--admin-port` | `8100` | port for the panel |

If the panel package is not installed, `--with-admin` logs a warning and core runs
normally — core has no hard dependency on it.

## Which mode should I use?

- Want **live connection/stats** or a **restart button**? Use `--with-admin`.
- Managing config/clients out-of-band, or the hub runs elsewhere? **Standalone**.
