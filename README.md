# HiveMind Admin Panel

A web-based administration panel for [HiveMind-core](https://github.com/JarbasHiveMind/HiveMind-core),
a FastAPI backend and single-page web UI for running and managing a HiveMind hub.

It ships as a **standalone, optional package**. It is the single launcher. It starts
`hivemind-core` in-process and serves the admin UI, so you run **one** command and
get a hub plus a place to administer it.

![Dashboard](docs/img/dashboard.png)

## Features

- **Clients & access keys**: create, list, update, and revoke keys. Run bulk
  operations, reveal credentials, and use **QR pairing** for one-tap satellite onboarding.
- **Per-client ACLs**: allow message types, skills, and intents. Toggle
  escalate and propagate flags and admin flags, and apply ACL templates.
- **Test Chat**: an in-browser chat that **impersonates any client**, talking
  through the hub to whatever agent is behind it. It exercises the real path: the
  client's ACL, routing, and the agent's reply.
- **Chat bridges**: provision a ready client for a Matrix, Twitch, Mattermost,
  DeltaChat, or HackChat bridge, and see it labelled in the topology.
- **Security**: a forced first-run password change, a dashboard security
  self-check, session tokens, `admin`/`operator` roles, and an audit trail.
- **Monitor**: live metrics, an SSE event feed, the hub log tail, and the audit log.
- **Topology**: an interactive mesh graph (hub and satellites) with online status.
- **Personas & agents**: manage personas (modern `handlers` schema), run a **multi-turn
  memory-aware** test chat, use **configurable, installable memory modules**, and
  get pre-activation validation. Browse the agent-engine taxonomy.
- **Plugin lifecycle**: install, **upgrade**, and **uninstall** plugins (with an
  active-module guard) and see installed versions.
- **Plugin presets**: named, reusable `{module, config}` sets for STT, TTS, WW, VAD, agent, and
  network plugins (local plugin or OVOS-server pointer). Author a preset once, test it, and select it.
- **Config safety**: the panel snapshots `server.json` before every change. Diff it and
  **revert** with one click from the Operations page.
- **OVOS servers**: register and health-check external persona, STT, TTS, and translate servers.
- **Plugins & databases**: discover and install network, agent, database, and OVOS plugins
  (via uv). Use JSON, SQLite, or Redis backends with profiles, tests, and migration.
- **Ops**: back up and restore, edit the admission policy, and manage self-signed TLS certs.

## Install

```bash
pip install hivemind-admin-panel
```

## Quickstart

`hivemind-admin-panel` is the single launcher. It starts hivemind-core in-process
and serves the admin UI. You do **not** run `hivemind-core` separately.

```bash
hivemind-admin-panel --host 127.0.0.1 --port 8100
# open http://127.0.0.1:8100   (first login: admin / admin — you'll be forced to change it)
```

**Panel only** (manage on-disk config/database without starting a hub):

```bash
hivemind-admin-panel --no-core --host 127.0.0.1 --port 8100
```

**Docker Compose** (hivemind-core + admin panel + Redis):

```bash
docker compose up --build
# open http://127.0.0.1:8100  (edit docker/server.json to set admin_pass first)
```

> The hub bridges to an **agent backend** (an OVOS messagebus by default) for
> answers. Without one reachable, the panel stays up and tells you the satellite
> listener is not ready. See [Troubleshooting](docs/troubleshooting.md).

## Screenshots

| Test Chat (impersonate a client) | Mesh topology |
|---|---|
| [![Test Chat](docs/img/test-chat.png)](docs/img/test-chat.png) | [![Topology](docs/img/topology.png)](docs/img/topology.png) |

| Forced first-run security | Provision a chat bridge |
|---|---|
| [![First-run gate](docs/img/first-run-gate.png)](docs/img/first-run-gate.png) | [![Add bridge](docs/img/add-bridge.png)](docs/img/add-bridge.png) |

## Credentials

The panel uses HTTP Basic or bearer auth, read from `~/.config/hivemind-core/server.json`
(`admin_user` and `admin_pass`, both default to `admin`). On first login with the
default password, the panel **forces** a change and stores it hashed (PBKDF2). The panel
can install packages and migrate databases, so keep it on `127.0.0.1` or behind a
trusted reverse proxy. See [Security](docs/security.md).

## Documentation

Full docs live in [`docs/`](docs/index.md): a path from zero to a working setup for newcomers, and a
reference track for advanced developers.

**Newcomers:** [Concepts](docs/concepts.md) · [Getting started](docs/getting-started.md) ·
[Tutorial](docs/tutorial.md) · [Glossary](docs/glossary.md) ·
[Troubleshooting](docs/troubleshooting.md)

**Operate:** [Running](docs/running.md) · [CLI](docs/cli.md) ·
[Configuration](docs/configuration.md) · [Operations](docs/operations.md) ·
[Security](docs/security.md) · [Deployment](docs/deployment.md) ·
[OVOS servers](docs/ovos-servers.md) · [Chat bridges](docs/bridges.md) ·
[Test Chat](docs/test-chat.md) · [Plugin presets](docs/presets.md)

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
