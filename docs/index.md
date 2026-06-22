# HiveMind Admin Panel — Documentation

A web-based admin panel for [hivemind-core](https://github.com/JarbasHiveMind/HiveMind-core):
manage the devices on your voice mesh, who's allowed to do what, the AI that
answers, and watch it all live — from a browser.

New here? Read **[Concepts](concepts.md)** first, then follow the
**[Tutorial](tutorial.md)**. Already know HiveMind? Jump to the
**[CLI](cli.md)** or **[API reference](api-reference.md)**.

---

## 🟢 Zero → running (newcomers)

Start here if you've never run HiveMind. No prior knowledge assumed.

1. **[Concepts](concepts.md)** — what hivemind-core, a satellite, an ACL, a
   persona and an agent actually are, in plain language.
2. **[Getting started](getting-started.md)** — install and launch in two commands.
3. **[Tutorial: zero to hero](tutorial.md)** — a full walkthrough: launch, pair
   your first satellite with a QR code, lock it down with an ACL, give it a
   personality, and watch messages flow live.
4. **[Glossary](glossary.md)** — every term, defined.
5. **[Troubleshooting & FAQ](troubleshooting.md)** — when something doesn't work.

## 🔵 Operate it (running a real deployment)

1. **[Running](running.md)** — in-process (default) vs. `--no-core`.
2. **[CLI reference](cli.md)** — every command-line flag.
3. **[Configuration](configuration.md)** — `server.json`, credentials, database
   backends, personas.
4. **[Operations](operations.md)** — monitoring, sessions & roles, pairing,
   backup/restore, policy, TLS.
5. **[Security](security.md)** — the auth model and how to harden it.
6. **[Deployment](deployment.md)** — Docker, Compose, reverse proxy, systemd.
7. **[OVOS servers](ovos-servers.md)** — persona/STT/TTS/translate servers and the
   homelab topology.

## 🟣 Hack on it (advanced developers)

1. **[Architecture](architecture.md)** — components, the injection seam, the live
   protocol tap, the threading model.
2. **[Extending the panel](extending.md)** — add an endpoint, a UI page, or a
   translation; the module map.
3. **[API reference](api-reference.md)** — every REST endpoint with `curl`.
4. **[Development](development.md)** — local setup, the end-to-end test suite, CI.
5. **[Roadmap & status](roadmap.md)** — what's built.

---

## What it manages, at a glance

| Area | What you can do |
|------|-----------------|
| **Clients** | Provision satellites, mint/reveal keys, QR-pair, tag, bulk-edit |
| **ACLs** | Per-client whitelists of message types, skills, intents; admin/escalate/propagate flags |
| **Agents & personas** | Pick the AI that answers; author personas; live test-chat |
| **Monitoring** | Live metrics, event feed, message inspector, log tail, audit log |
| **Databases** | JSON / SQLite / Redis backends, profiles, migration |
| **Plugins** | Discover & install network/agent/database/voice plugins (via uv) |
| **Ops** | Backup/restore, policy chain, TLS certs |
| **Servers** | Register & health-check external OVOS servers |

## Two ways to run it

- **Default** — `hivemind-admin-panel` starts hivemind-core *in-process* and
  serves the UI. You run **one** command; there is no separate `hivemind-core`
  process to manage.
- **`--no-core`** — serve the panel only, against a host's on-disk state or a
  hivemind-core managed elsewhere.

See [Running](running.md).

## License

Apache-2.0.
