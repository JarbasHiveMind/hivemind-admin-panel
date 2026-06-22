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
| Agents | Persona test-chat | `/personas/{name}/chat` · personas page widget |
| Agents | Engine taxonomy + memory plugins | `/plugins/agents`, `/plugins/memory` |
| Agents | OVOS server registry + health | `/servers`, `/servers/{id}/health` · Servers page |
| Ops | Backup / restore | `/backup`, `/restore` · Operations page |
| Ops | Admission policy editor | `/policy` · Operations page |
| Ops | TLS cert status / self-signed generate | `/certs`, `/certs/generate` |
| Live | **Authoritative** connections + live protocol | `_tracked_protocol` injects the live protocol in `launch_core` |
| Live | **Message inspector** (taps every HiveMessage) | `/messages/recent` (filter by type/peer) |
| Scale | Topology graph | `/topology` · Topology page (SVG) |
| Scale | Multi-hub fleet | `/fleet`, `/fleet/{id}/status` |
| Security | Password hashing + change | PBKDF2 in `_auth.py`, `POST /auth/password` |
| Ops | Config dry-run diff | `/config/diff` |
| Polish | i18n scaffold (en/es/pt) + language selector | `static/js/i18n.js`, `data-i18n` |
| Polish | First-run setup hints | `/setup/status` |
| Polish | OpenAPI / Swagger | `/api/docs`, `/api/openapi.json` (built-in) |

## How "live" works without a core change

`/connections`, `/stats`, `/topology` online flags, and the message inspector are
authoritative when the hub runs **in-process** (the default). `launch_core()`
subclasses the hub's listener protocol (`_tracked_protocol`) to capture the live
instance and tap `handle_message` / connect / disconnect / invalid-key — no change
to hivemind-core. In `--no-core` mode these degrade gracefully (no live hub to tap).

## Remaining / notes

- **CSRF** is **not applicable** to this API: it authenticates via the
  `Authorization` header (Basic or Bearer), not ambient cookies, so cross-site
  requests cannot carry credentials. A cookie-session mode would need CSRF tokens.
- **i18n** ships a working mechanism (en/es/pt) and a language selector; UI string
  coverage is extended progressively via `data-i18n` tags.
- Passwords now support PBKDF2 hashes (`pbkdf2_sha256$…`) while still accepting
  legacy plaintext for back-compat; change one via `POST /auth/password`.
