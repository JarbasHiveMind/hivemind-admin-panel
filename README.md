# HiveMind Admin Panel

Web-based administration UI for [HiveMind-core](https://github.com/JarbasHiveMind/HiveMind-core).

A FastAPI backend + single-page web UI for managing a HiveMind hub: clients and
access keys, per-client ACLs (allowed/blacklisted message types, skills, intents,
escalate/propagate, admin flags), live connection/stats introspection, plugin
discovery and installation, database backends/profiles/migration, and persona
management.

This was previously developed inside `hivemind-core`; it now ships as a standalone,
optional package so it has its own release cadence, its own (AGPL-3.0) license
boundary, and is not present in core deployments that don't want an admin plane.

## Install

```bash
pip install hivemind-admin-panel
```

It depends on `hivemind-core`; installing it pulls core in.

## Usage

### Standalone

Run the panel on its own (it reads the same on-disk config and database that
`hivemind-core` uses on the host):

```bash
hivemind-admin-panel --host 127.0.0.1 --port 8000
```

Live connection/stats and service-restart features require an in-process handle
to a running core and are unavailable in standalone mode; everything backed by the
database, config files, and plugin entry points works.

### Integrated with a running core

`hivemind-core` exposes an optional launcher that, when the panel is installed,
hands it direct references to the live service/database/protocol objects for
real-time introspection:

```bash
hivemind-core --with-admin --admin-host 127.0.0.1 --admin-port 8100
```

## Authentication

The panel is guarded by HTTP Basic auth. Credentials live in
`~/.config/hivemind-core/server.json` (`admin_user`, `admin_pass`). Bind to
`127.0.0.1` (the default) unless it sits behind a trusted reverse proxy — the admin
plane can install packages and migrate databases.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
