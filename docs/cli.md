# CLI reference

`hivemind-admin-panel` is the **single launcher** for a HiveMind deployment. By
default, one process starts hivemind-core **in-process** *and* serves the
admin UI. There is no separate `hivemind-core` command to run. Pass `--no-core`
to serve the panel only.

See [Getting started](getting-started.md) for a first run and [Running](running.md)
for what each mode exposes.

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--host` | `127.0.0.1` | Bind address for the admin panel. |
| `--port` | `8100` | Port for the admin panel. |
| `--no-core` | off | Do not start an in-process hivemind-core; serve the panel only. |
| `--reload` | off | Dev auto-reload (implies `--no-core`, see below). |
| `--log-level` | `INFO` | Log level for the in-process hivemind-core (e.g. `DEBUG`, `INFO`, `ERROR`). |
| `--version` | — | Print the version and exit. |

## Common invocations

### hivemind-core + panel (default)

```bash
hivemind-admin-panel
```

Starts hivemind-core in-process and serves the panel on `http://127.0.0.1:8100`. This is
the normal way to run a deployment.

### Expose on the LAN

```bash
hivemind-admin-panel --host 0.0.0.0 --port 8100
```

Binds the panel on all interfaces so other machines on the network can reach it.
The panel ships with default credentials (`admin`/`admin`). **Change them before
binding to `0.0.0.0`**, and put a firewall or reverse proxy with TLS in front.
Admin credentials live in `server.json` (see [Configuration](configuration.md)),
not on the command line.

### Panel only

```bash
hivemind-admin-panel --no-core
```

Serves the admin UI without starting a hivemind-core instance. Use this to manage on-disk state
(clients, ACLs, config, personas) without a running service, or on a host where the
hivemind-core is managed elsewhere. Live-only views (`/connections`, `/stats` connection
count, `/config/restart`) degrade — see [Running](running.md).

### Development auto-reload

```bash
hivemind-admin-panel --no-core --reload
```

Enables uvicorn auto-reload while editing the panel. `--reload` runs uvicorn in a
**child process**, which the in-process hivemind-core thread cannot survive. So `--reload`
implies `--no-core`, and hivemind-core is never started in this mode.

### Version

```bash
hivemind-admin-panel --version
```

## Configuration is not on the CLI

The CLI flags only control the panel's own bind address and process mode. The
hivemind-core's transports (websocket on `:5678`, etc.) and the admin credentials are
configured in `~/.config/hivemind-core/server.json`, **not** via CLI flags. See
[Configuration](configuration.md).

## Stopping

Press `Ctrl-C` (SIGINT) to shut down cleanly. In the default hivemind-core + panel mode the
hivemind-core runs on the main thread and installs the SIGINT/SIGTERM handlers, so the signal
is handled there and both hivemind-core and panel stop together.

---
[← Running](running.md) · [Home](index.md) · [Configuration →](configuration.md)
