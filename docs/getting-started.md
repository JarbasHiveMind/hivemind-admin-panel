# Getting started

## Requirements

- Python 3.10+
- A [HiveMind-core](https://github.com/JarbasHiveMind/HiveMind-core) install (pulled
  in automatically as a dependency).

## Install

```bash
pip install hivemind-admin-panel
```

Installing the panel also installs `hivemind-core`. Conversely, if you start from
core you can pull the panel in via the optional extra:

```bash
pip install hivemind-core[admin]
```

## First run (standalone)

```bash
hivemind-admin-panel --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. You will be prompted for HTTP Basic credentials.

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

## First run (integrated with a live hub)

To get real-time connection and stats introspection, launch the panel from a
running hub instead — it then has direct access to the live service:

```bash
hivemind-core --with-admin --admin-host 127.0.0.1 --admin-port 8100
```

See [Running](running.md) for the difference between the two modes.

## Next steps

- [Configuration](configuration.md) — credentials and the database backend.
- [API reference](api-reference.md) — drive everything over REST.
- [Deployment](deployment.md) — Docker / Compose / reverse proxy.
