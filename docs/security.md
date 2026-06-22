# Security

The admin panel is a **privileged control plane**. Through it an authenticated
caller can install Python packages, migrate and clear databases, mint client
credentials, and restart the service. Treat access to it as equivalent to shell
access on the host.

## Authentication

- **HTTP Basic** (or a Bearer token from `POST /auth/login`) on every endpoint
  except `GET /health`.
- Credentials come from `server.json` (`admin_user` / `admin_pass`); comparison is
  timing-safe. New passwords are stored **hashed** (PBKDF2) via `POST /auth/password`.
- The defaults are `admin` / `admin`.

## First-run gate & self-check

The panel actively pushes you off the defaults rather than just warning:

- **Forced password change.** When you log in while the default password is still
  in use, a modal blocks the entire UI until you set a new one (minimum 8
  characters, stored hashed). It cannot be dismissed.
- **Dashboard security self-check.** A card at the top of the dashboard runs
  `GET /setup/status` and reports, with red/yellow/green status and a fix hint:
  whether the admin password is still default (critical), whether the panel is
  bound to a non-loopback address (warning), and whether the hivemind-core
  websocket has TLS configured (info). It stays red until criticals clear.
  A *warning* you've handled deliberately (e.g. binding `0.0.0.0` behind a proxy)
  can be **dismissed** from the card — criticals cannot, and the dismissal is
  audit-logged.
- **Run-mode badge.** The top bar shows whether hivemind-core runs **in-process**
  (closing the panel stops the server) or the panel is in **panel-only** mode.

## Network exposure

- Bind to `127.0.0.1` (the default in both modes) unless the panel sits behind a
  trusted reverse proxy that terminates TLS and adds authentication.
- `--host 0.0.0.0` (and the Docker image) expose it on all interfaces — only
  do this behind a proxy / firewall. See [Deployment](deployment.md).
- The panel speaks plain HTTP; put TLS at the proxy.

## Powerful endpoints to be aware of

| Endpoint | Risk |
|----------|------|
| `POST /plugins/install` | runs `pip install <package>` in the server's interpreter |
| `POST /database/migrate`, `/database/{module}/clear` | move or delete client records |
| `POST /clients`, `/clients/{id}/credentials` | mint / reveal access keys and crypto keys |
| `POST /config`, `/config/restart` | rewrite `server.json`, restart hivemind-core |

## Current hardening gaps

These are known and worth accounting for when deploying:

- **No CSRF protection** on state-changing requests — do not host the panel on a
  shared origin with untrusted content; keep it on its own host/port behind a proxy.
- The web UI stores credentials in `sessionStorage` (cleared on tab close) and HTML-
  escapes user-controlled strings, but Basic auth means the browser holds the
  credentials for the session.
- `POST /plugins/install` installs into the live interpreter; the new package is not
  importable until the service restarts, and the endpoint trusts the caller to
  supply a sane package name. Restrict who can reach the panel accordingly.

## Recommended posture

1. Strong `admin_pass`.
2. Bind `127.0.0.1`, or `0.0.0.0` only behind a TLS-terminating, authenticating
   reverse proxy.
3. Network-isolate the host; the panel and the OVOS bus it can reach are trusted
   surfaces.
