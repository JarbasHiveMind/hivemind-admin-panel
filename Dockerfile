# HiveMind Admin Panel — runs hivemind-core with the admin panel enabled.
# The image bundles hivemind-core (a dependency of the panel), so a single
# container serves the hub (websocket/http transports) plus the admin web UI.
FROM python:3.12-slim AS builder

# Build deps for pycryptodomex / wheels that lack manylinux builds
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . /src

# Install the panel (pulls hivemind-core) plus the Redis client-database backend
# used by the bundled docker-compose topology, into an isolated prefix.
RUN pip install --no-cache-dir --prefix=/install . hivemind-redis-database

FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/JarbasHiveMind/hivemind-admin-panel" \
      org.opencontainers.image.description="Web-based admin panel for HiveMind-core" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY --from=builder /install /usr/local

# Non-root runtime user; config/state live under its home
RUN useradd --create-home --uid 1000 hivemind
USER hivemind
WORKDIR /home/hivemind

# websocket transport, http transport, admin panel
EXPOSE 5678 5679 8100

# Run the hub with the admin panel bound on all interfaces inside the container.
CMD ["hivemind-core", "--with-admin", "--admin-host", "0.0.0.0", "--admin-port", "8100"]
