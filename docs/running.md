# Running the panel

`hivemind-admin-panel` is the single launcher for a HiveMind deployment. By
default it **starts the hub in-process** and serves the admin UI; you do not run
`hivemind-core` separately. A `--no-core` flag serves the panel only.

## Default: hub + panel together

```bash
hivemind-admin-panel --host 127.0.0.1 --port 8100
```

The panel constructs a `HiveMindService`, keeps a live reference to it, and runs
the hub in a daemon thread (see [Architecture](architecture.md)). You get the full
admin surface plus live introspection:

- clients & access keys, per-client ACLs, plugins, database profiles, personas
- `GET /connections` / `GET /stats` reflect the running hub
- `POST /config/restart` can restart the in-process service

If the hub fails to start, the panel still comes up in a **diagnostics mode** that
surfaces the startup error at `GET /api/startup-error`.

The hub's transports (websocket on `:5678`, etc.) are configured in `server.json`,
independently of the panel's own `--host`/`--port`. See [Configuration](configuration.md).

## Panel only (`--no-core`)

```bash
hivemind-admin-panel --no-core --host 127.0.0.1 --port 8100
```

No in-process hub is started. The panel reads the same on-disk state core uses
(`server.json` + the configured client database), so everything backed by the
database, config files, plugin entry points, and the filesystem still works:
clients, ACLs, plugin install, database profiles/migration, personas, config.

What needs a live hub and therefore degrades in `--no-core`:

- `GET /connections` returns placeholder data — there is no live socket list
- `GET /stats` still reports DB-derived counts but no live connection count
- `POST /config/restart` returns an error (no service handle to restart)

Use `--no-core` to provision clients / edit config without touching a running
service, or on a host where the hub is managed separately.

## Development

```bash
hivemind-admin-panel --no-core --reload
```

`--reload` runs uvicorn in a child process and therefore implies `--no-core`
(the in-process hub thread would not survive a reload).

| Flag | Default | Meaning |
|------|---------|---------|
| `--host` | `127.0.0.1` | bind address for the panel |
| `--port` | `8100` | port for the panel |
| `--no-core` | off | serve the panel only; do not start a hub |
| `--reload` | off | dev auto-reload (implies `--no-core`) |
| `--log-level` | `INFO` | log level for the in-process hub |
