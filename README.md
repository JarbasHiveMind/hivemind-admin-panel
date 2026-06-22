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
# or, starting from core:
pip install hivemind-core[admin]
```

## Quickstart

**Standalone** (manage a host's config/database directly):

```bash
hivemind-admin-panel --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000
```

**Integrated** with a running hub (adds live connection/stats + restart):

```bash
hivemind-core --with-admin --admin-host 127.0.0.1 --admin-port 8100
# open http://127.0.0.1:8100
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
- [Development](docs/development.md) — the end-to-end test suite & contributing

## Relationship to HiveMind-core

The panel was extracted from core so it has its own release cadence and stays an
optional, separately-deployable admin plane. Core keeps only a thin `--with-admin`
launcher that lazily imports the panel and injects live objects — it has no hard
dependency on it. See [docs/architecture.md](docs/architecture.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
