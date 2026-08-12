# Running the panel

> **Paths in this file** omit the `/api` prefix the panel mounts the API under.
> A route written `/clients` is served at `http://<host>:8100/api/clients`.

`hivemind-admin-panel` is the single launcher for a HiveMind deployment. By
default it **starts hivemind-core in-process** and serves the admin UI. You do not run
`hivemind-core` separately. A `--no-core` flag serves the panel only.

![Dashboard](img/dashboard.png)

## Default: hivemind-core + panel together

```bash
hivemind-admin-panel --host 127.0.0.1 --port 8100
```

The panel constructs a `HiveMindService`, keeps a live reference to it, and runs
hivemind-core on the main thread; the panel's own HTTP server runs in a daemon
thread (see [Architecture](architecture.md)). You get the full
admin surface plus live introspection:

- clients & access keys, per-client ACLs, plugins, database profiles, personas
- `GET /connections` / `GET /stats` reflect the running hivemind-core
- `POST /config/restart` can restart the in-process service

If hivemind-core fails to start, the panel still comes up in a **diagnostics mode** that
surfaces the startup error at `GET /api/startup-error`.

hivemind-core's transports (websocket on `:5678`, etc.) are configured in `server.json`,
independently of the panel's own `--host`/`--port`. See [Configuration](configuration.md).

## Panel only (`--no-core`)

```bash
hivemind-admin-panel --no-core --host 127.0.0.1 --port 8100
```

No in-process hivemind-core is started. The panel reads the same on-disk state core uses
(`server.json` + the configured client database), so everything backed by the
database, config files, plugin entry points, and the filesystem still works:
clients, ACLs, plugin install, database profiles/migration, personas, config.

What needs a live hivemind-core and therefore degrades in `--no-core`:

- `GET /connections` returns an empty `connections` list, `count: 0`, and a
  `note` saying no live hivemind-core is attached
- `GET /stats` reports the protocol and config fields only. It reports **no**
  client counts, no connection count and no service status — those come from
  the injected objects, which do not exist in this mode.
- `GET /topology` marks the core node's `online` as null and says so in `note`
- `POST /config/restart` returns an error (no service handle to restart)

Use `--no-core` to provision clients or edit config without touching a running
service.

`--no-core` does **not** attach to a hivemind-core running elsewhere. The live
views come from objects injected in-process by this panel's own launcher; there
is no mechanism for reaching another process. A hivemind-core managed separately
keeps running, and this panel simply has no live view of it.

## Development

```bash
hivemind-admin-panel --no-core --reload
```

`--reload` runs uvicorn in a child process and therefore implies `--no-core`
(the in-process hivemind-core thread would not survive a reload).

| Flag | Default | Meaning |
|------|---------|---------|
| `--host` | `127.0.0.1` | bind address for the panel |
| `--port` | `8100` | port for the panel |
| `--no-core` | off | serve the panel only; do not start a hivemind-core instance |
| `--reload` | off | dev auto-reload (implies `--no-core`) |
| `--log-level` | `INFO` | log level for the in-process hivemind-core |

---
[← Troubleshooting](troubleshooting.md) · [Home](index.md) · [CLI →](cli.md)
