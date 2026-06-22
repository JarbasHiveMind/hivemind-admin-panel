# HiveMind Admin Panel

Web-based administration panel for [HiveMind-core](https://github.com/JarbasHiveMind/HiveMind-core)
— a FastAPI backend and single-page web UI for managing hivemind-core.

It ships as a **standalone, optional package**: install it only where you want an
admin plane. It depends on `hivemind-core`; without it, core runs unchanged.

## Features

- **Clients & access keys** — create, list, update, revoke; bulk ops; reveal
  credentials; **QR pairing** for one-tap satellite onboarding.
- **Per-client ACLs** — allow/blacklist message types, skills, and intents; toggle
  escalate / propagate and admin flags; apply ACL templates.
- **Monitor** — live metrics, an SSE event feed, the hivemind-core log tail, and an audit log.
- **Security** — forced first-run password change, a dashboard security self-check,
  session tokens, `admin`/`operator` roles, audit trail; uv installs.
- **Topology** — interactive mesh graph (hivemind-core ↔ satellites) with online status.
- **Plugins** — discover and install network/agent/database and OVOS plugins (uv).
- **Databases** — JSON / SQLite / Redis backends, profiles, tests, and migration.
- **Personas & agents** — manage personas (modern `handlers` schema), **test-chat**
  a persona live, browse the agent-engine taxonomy and memory plugins.
- **OVOS servers** — register and health-check external persona/STT/TTS/translate
  servers.
- **Chat bridges** — provision a ready client for Matrix/Twitch/Mattermost/DeltaChat/
  HackChat bridges and see them labelled in the topology.
- **Ops** — backup/restore, admission-policy editor, self-signed TLS certs.

## Install

```bash
pip install hivemind-admin-panel
```

## Quickstart

`hivemind-admin-panel` is the single launcher — it starts hivemind-core
in-process and serves the admin UI. You do **not** run `hivemind-core` separately.

```bash
hivemind-admin-panel --host 127.0.0.1 --port 8100
# open http://127.0.0.1:8100
```

**Panel only** (manage on-disk config/database without starting a hivemind-core instance):

```bash
hivemind-admin-panel --no-core --host 127.0.0.1 --port 8100
```

**Docker Compose** (hivemind-core + admin panel + Redis):

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

Full docs in [`docs/`](docs/index.md) — a zero-to-hero path for newcomers and a
reference track for advanced devs.

**Newcomers:** [Concepts](docs/concepts.md) · [Getting started](docs/getting-started.md) ·
[Tutorial](docs/tutorial.md) · [Glossary](docs/glossary.md) ·
[Troubleshooting](docs/troubleshooting.md)

**Operate:** [Running](docs/running.md) · [CLI](docs/cli.md) ·
[Configuration](docs/configuration.md) · [Operations](docs/operations.md) ·
[Security](docs/security.md) · [Deployment](docs/deployment.md) ·
[OVOS servers](docs/ovos-servers.md) · [Chat bridges](docs/bridges.md)

**Develop:** [Architecture](docs/architecture.md) · [Extending](docs/extending.md) ·
[API reference](docs/api-reference.md) · [Development](docs/development.md) ·
[Roadmap](docs/roadmap.md)

## Relationship to HiveMind-core

The panel was extracted from core so it has its own release cadence and stays an
optional, separately-deployable admin plane. It is the launcher: it starts a
`hivemind-core` in-process and keeps a live reference to it, so core needs no
admin-specific code. See [docs/architecture.md](docs/architecture.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
