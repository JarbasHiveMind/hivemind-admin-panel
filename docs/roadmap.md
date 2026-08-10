# Roadmap & status

Status of the UI/feature roadmap. Most items are **implemented** (backend +
SPA + tests, CI-green). A few require **hivemind-core changes** and are tracked
as gated.

## Implemented

| Theme | Feature | Endpoints / UI |
|-------|---------|----------------|
| Observability | Metrics, event feed, SSE live stream, log tail | `/metrics`, `/events`, `/events/recent`, `/logs` · Monitor page |
| Observability | Audit log of admin actions | `/audit` + mutation middleware |
| Security | Session tokens, Basic+Bearer auth | `/auth/login`, `/auth/logout`, `/auth/me` |
| Security | Roles (admin/operator), admin-gated destructive actions | `require_admin` on install/migrate/clear/restore/policy/certs |
| Security | uv installs | `/plugins/install` (uv, pip fallback) |
| Onboarding | Pairing bundle + QR | `/clients/{id}/pairing`, `/pairing/qr.svg` · Topology pairing modal |
| Onboarding | Bulk client ops | `/clients/bulk` |
| Onboarding | Client tags | `/clients/{id}/tags` |
| Agents | Persona test-chat (one-shot + **multi-turn** memory-aware sessions) | `/personas/{name}/chat`, `/personas/{name}/chat/sessions` · personas page |
| Agents | **Configurable memory module** (config under its entry-point key) + install from editor | persona JSON `memory_module` + keyed config · `/plugins/memory` |
| Agents | Pre-activation persona validation (handlers installed) | `/personas/{name}/activate` 409 / `?force=` |
| Agents | Engine taxonomy + memory plugins | `/plugins/agents`, `/plugins/memory` |
| Plugins | **Lifecycle**: install, **upgrade**, **uninstall** (active-module guarded), version display | `/plugins/install`,`/plugins/upgrade`,`/plugins/uninstall` · plugin cards |
| Ops | **Config snapshots + rollback** (auto before every change, diff/revert) | `/config/backups`,`/config/backups/diff`,`/config/backups/restore` · Operations page |
| Agents | OVOS server registry + health | `/servers`, `/servers/{id}/health` · Servers page |
| Ops | Backup / restore | `/backup`, `/restore` · Operations page |
| Ops | Admission policy editor | `/policy` · Operations page |
| Ops | TLS cert status / self-signed generate | `/certs`, `/certs/generate` |
| Live | **Authoritative** connections + live protocol | `_tracked_protocol` injects the live protocol in `launch_core` |
| Live | **Message inspector** (taps every HiveMessage) | `/messages/recent` (filter by type/peer) |
| Scale | Topology graph | `/topology` · Topology page (SVG) |
| Security | Password hashing + change | PBKDF2 in `_auth.py`, `POST /auth/password` |
| Ops | Config dry-run diff | `/config/diff` |
| Polish | i18n scaffold (en/es/pt) + language selector | `static/js/i18n.js`, `data-i18n` |
| Polish | First-run setup hints | `/setup/status` |
| Polish | OpenAPI / Swagger | `/api/docs`, `/api/openapi.json` (built-in) |

## How "live" works without a core change

`/connections`, `/stats`, `/topology` online flags, and the message inspector are
authoritative when hivemind-core runs **in-process** (the default). `launch_core()`
subclasses hivemind-core's listener protocol (`_tracked_protocol`) to capture the live
instance and tap `handle_message`, connect, disconnect, and invalid-key events, with no change
to hivemind-core. In `--no-core` mode these degrade gracefully (no live hivemind-core to tap).

## Remaining / notes

- **CSRF** is **not applicable** to this API: it authenticates via the
  `Authorization` header (Basic or Bearer), not ambient cookies, so cross-site
  requests cannot carry credentials. A cookie-session mode would need CSRF tokens.
- **i18n** ships a working mechanism (en/es/pt) and a language selector. UI string
  coverage is extended progressively through `data-i18n` tags.
- Passwords now support PBKDF2 hashes (`pbkdf2_sha256$...`) while still accepting
  legacy plaintext for back-compat. Change one through `POST /auth/password`.

---
[← Development](development.md) · [Home](index.md)
