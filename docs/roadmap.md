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
| Scale | Topology graph | `/topology` · Topology page (SVG) |
| Polish | First-run setup hints | `/setup/status` |
| Polish | OpenAPI / Swagger | `/api/docs`, `/api/openapi.json` (built-in) |

## Gated on hivemind-core changes

These need a small read-only status/control seam in core (objects are injected
once at startup, before the live protocol is built):

- **Authoritative live connections / metrics** — today `/connections`, the
  topology `online` flags, and active-connection counts are best-effort.
- **True per-message inspector** — tapping every `HiveMessage` (with ACL-denial
  events) needs core to publish a message/event stream the panel can subscribe to.
  The current event feed is an approximation.

## Not yet started (future)

- **Multi-hub / fleet** — manage several hubs from one panel (larger architecture).
- **i18n** — the UI is English-only; strings are not externalized yet.
- **Hardening** — hash `server.json` passwords; CSRF tokens for any cookie-based
  clients (bearer-token clients are not CSRF-exposed).
- **Config dry-run/diff UI** — `/config/validate` exists; a visual diff is pending.
