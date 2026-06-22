# Deployment

## Docker (single container)

The image runs `hivemind-admin-panel`, which starts the hub in-process, so one
container serves the hub (websocket transport) and the admin panel.

```bash
docker build -t hivemind-admin-panel .
docker run --rm \
  -p 5678:5678 -p 8100:8100 \
  -v hivemind-config:/home/hivemind/.config/hivemind-core \
  hivemind-admin-panel
```

Open <http://127.0.0.1:8100>. The image is published to GHCR by CI:

```bash
docker pull ghcr.io/jarbashivemind/hivemind-admin-panel:latest
```

Exposed ports: `5678` (websocket transport), `5679` (http transport), `8100`
(admin panel).

## Docker Compose (full stack)

The bundled `docker-compose.yml` brings up the hub + admin panel backed by Redis:

```bash
docker compose up --build
```

It defines two services:

- **redis** — the client-database backend (persisted to a named volume);
- **hivemind** — the hub + admin panel, configured by `docker/server.json` (which
  selects the Redis backend and the admin credentials).

Before exposing anything, edit `docker/server.json` and change `admin_pass`. The
panel is published on `127.0.0.1:8100` and the websocket transport on `:5678`.

Volumes:

| Volume | Holds |
|--------|-------|
| `redis-data` | the Redis client database |
| `hivemind-config` | identity keys + `server.json` |
| `hivemind-data` | hub runtime state |

## Behind a reverse proxy (TLS)

Run the panel on `127.0.0.1` and terminate TLS + add access control at the proxy.
Example nginx:

```nginx
server {
    listen 443 ssl;
    server_name hivemind.example.org;
    # ssl_certificate / ssl_certificate_key ...

    location / {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

The panel still enforces its own Basic auth; the proxy can add a second factor.

## systemd (standalone panel)

```ini
# /etc/systemd/system/hivemind-admin-panel.service
[Unit]
Description=HiveMind Admin Panel
After=network-online.target

[Service]
ExecStart=/usr/local/bin/hivemind-admin-panel --host 127.0.0.1 --port 8100
Restart=on-failure
User=hivemind

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now hivemind-admin-panel
```

This single unit runs the hub and the panel together. Add `--no-core` to the
`ExecStart` line if the hub is managed by a separate service on the host.
