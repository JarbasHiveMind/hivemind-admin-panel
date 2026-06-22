# Getting started

## Requirements

- Python 3.10+
- A [HiveMind-core](https://github.com/JarbasHiveMind/HiveMind-core) install (pulled
  in automatically as a dependency).

## Install

```bash
pip install hivemind-admin-panel
```

Installing the panel also installs `hivemind-core`.

## First run

```bash
hivemind-admin-panel --host 127.0.0.1 --port 8100
```

This launches a HiveMind hub **in-process** and serves the admin panel — you do
not run `hivemind-core` separately. Open <http://127.0.0.1:8100>; you will be
prompted for HTTP Basic credentials.

## Set your credentials

Credentials are read from `~/.config/hivemind-core/server.json` (keys `admin_user`
and `admin_pass`, both defaulting to `admin`). **Change them before exposing the
panel.** See [Configuration](configuration.md).

```jsonc
{
  "admin_user": "admin",
  "admin_pass": "a-strong-password"
}
```

## Panel only (no in-process hub)

To manage on-disk state without starting a hub (or when a hub is managed
elsewhere on the host), use `--no-core`:

```bash
hivemind-admin-panel --no-core --host 127.0.0.1 --port 8100
```

See [Running](running.md) for the difference between the two modes.

## Next steps

- [Configuration](configuration.md) — credentials and the database backend.
- [API reference](api-reference.md) — drive everything over REST.
- [Deployment](deployment.md) — Docker / Compose / reverse proxy.
