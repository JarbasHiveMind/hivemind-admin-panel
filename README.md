# HiveMind Admin Panel

Web-based administration panel for [HiveMind-core](https://github.com/JarbasHiveMind/HiveMind-core)
— a FastAPI backend and single-page web UI for managing a HiveMind hub.

It ships as a **standalone, optional package**: install it only where you want an
admin plane. It depends on `hivemind-core`; without it, core runs unchanged.

## Features

- **Clients & access keys** — create, list, update, revoke; reveal credentials.
- **Per-client ACLs** — allow/blacklist message types, skills, and intents; toggle
  escalate / propagate and admin flags; apply ACL templates.
- **Live introspection** — connection list and stats when attached to a running hub.
- **Plugins** — discover and install network/agent/database and OVOS plugins.
- **Databases** — JSON / SQLite / Redis backends, profiles, connectivity tests, and
  client migration between backends.
- **Personas** — manage OVOS personas (create, edit, activate, export, validate).

## Install

```bash
pip install hivemind-admin-panel
```

## Quickstart

`hivemind-admin-panel` is the single launcher — it starts a HiveMind hub
in-process and serves the admin UI. You do **not** run `hivemind-core` separately.

```bash
hivemind-admin-panel --host 127.0.0.1 --port 8100
# open http://127.0.0.1:8100
```

**Panel only** (manage on-disk config/database without starting a hub):

```bash
hivemind-admin-panel --no-core --host 127.0.0.1 --port 8100
```

**Docker Compose** (hub + admin panel + Redis):

```bash
docker compose up --build
# open http://127.0.0.1:8100  (edit docker/server.json to set admin_pass first)
```

## Credentials

HTTP Basic auth, read from `~/.config/hivemind-core/server.json`
(`admin_user` / `admin_pass`, both default `admin`). **Change them before exposing
the panel** — it can install packages and migrate databases. Keep it on
`127.0.0.1` or behind a trusted reverse proxy. See [docs/security.md](docs/security.md).

## Documentation

Full docs in [`docs/`](docs/index.md):

- [Getting started](docs/getting-started.md) · [Running](docs/running.md) ·
  [Configuration](docs/configuration.md)
- [Architecture](docs/architecture.md) · [Security](docs/security.md)
- [API reference](docs/api-reference.md) — every REST endpoint with `curl` examples
- [Deployment](docs/deployment.md) — Docker / Compose / reverse proxy / systemd
- [OVOS servers](docs/ovos-servers.md) — persona-server + STT/TTS/translate servers; homelab synergy
- [Development](docs/development.md) — the end-to-end test suite & contributing

## Relationship to HiveMind-core

The panel was extracted from core so it has its own release cadence and stays an
optional, separately-deployable admin plane. It is the launcher: it starts a
`hivemind-core` hub in-process and keeps a live reference to it, so core needs no
admin-specific code. See [docs/architecture.md](docs/architecture.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
