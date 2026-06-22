# Security

The admin panel is a **privileged control plane**. Through it an authenticated
caller can install Python packages, migrate and clear databases, mint client
credentials, and restart the service. Treat access to it as equivalent to shell
access on the host.

## Authentication

- **HTTP Basic** on every endpoint except `GET /health`.
- Credentials come from `server.json` (`admin_user` / `admin_pass`); comparison is
  timing-safe (`hmac.compare_digest`).
- The defaults are `admin` / `admin`. **Change them before exposing the panel.**

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
| `POST /config`, `/config/restart` | rewrite `server.json`, restart the hub |

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
