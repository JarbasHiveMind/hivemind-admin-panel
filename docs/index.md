# HiveMind Admin Panel — Documentation

A web-based administration panel for a [HiveMind-core](https://github.com/JarbasHiveMind/HiveMind-core)
hub: a FastAPI backend and a single-page web UI for managing clients, access keys,
per-client ACLs, plugins, database backends, and personas — plus live introspection
of a running hub.

It ships as a **standalone, optional package**. Install it only where you want an
admin plane; core deployments that don't want one are unaffected.

## Documentation map

| Page | What it covers |
|------|----------------|
| [Getting started](getting-started.md) | Install, first run, opening the UI |
| [Running](running.md) | Standalone vs. integrated (`--with-admin`) modes |
| [Configuration](configuration.md) | `server.json`, admin credentials, database backend |
| [Architecture](architecture.md) | How the panel couples to core; the injection seam |
| [Security](security.md) | Auth model, the privileged admin plane, hardening |
| [API reference](api-reference.md) | Every REST endpoint, request models, `curl` examples |
| [Deployment](deployment.md) | Docker, Docker Compose, reverse proxy, systemd |
| [Development](development.md) | Local setup, the end-to-end test suite, contributing |

## At a glance

- **What it manages:** clients & access keys, per-client message/skill/intent ACLs,
  escalate/propagate and admin flags, network/agent/database plugins, database
  profiles & migration, and OVOS personas.
- **Two ways to run it:** standalone against a host's on-disk config/database, or
  injected into a live hub via `hivemind-core --with-admin` for real-time
  connection/stats introspection. See [Running](running.md).
- **Auth:** HTTP Basic, credentials in `~/.config/hivemind-core/server.json`. The
  admin plane can install packages and migrate databases — treat it as privileged
  and keep it bound to `127.0.0.1` or behind a trusted proxy. See [Security](security.md).
- **License:** Apache-2.0.
