# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""HiveMind Admin - Web-based management UI for HiveMind-core.

This module provides a web-based administration interface for HiveMind-core,
allowing management of clients, permissions, and server configuration via
a REST API and web UI.

When launched with the in-process hivemind-core (the default), this module gets
direct access to internal HiveMind-core objects for real-time monitoring.
"""

import socket
import time
from typing import TYPE_CHECKING

from ovos_utils import create_daemon
from ovos_utils.log import LOG

if TYPE_CHECKING:
    from hivemind_core.service import HiveMindService
    from hivemind_core.database import ClientDatabase
    from hivemind_core.protocol import HiveMindListenerProtocol

__version__ = "0.2.0"
__all__ = ["start_admin_server", "init_injected_objects", "get_admin_app", "bind_with_retry"]

#: attempts / delay for the admin UI's own bind-with-retry (see bind_with_retry)
BIND_RETRY_ATTEMPTS = 5
BIND_RETRY_DELAY = 2.0


def init_injected_objects(
    service: "HiveMindService" = None,
    db: "ClientDatabase" = None,
    protocol: "HiveMindListenerProtocol" = None,
    startup_error: Exception = None
) -> None:
    """Initialize admin with direct access to core objects.

    Args:
        service: HiveMindService instance.
        db: ClientDatabase instance.
        protocol: HiveMindListenerProtocol instance.
        startup_error: Exception if core failed to start.
    """
    from hivemind_admin_panel.api import init_injected_objects as _init
    _init(service=service, db=db, protocol=protocol, logger=LOG, startup_error=startup_error)


def bind_with_retry(
    host: str,
    port: int,
    attempts: int = BIND_RETRY_ATTEMPTS,
    delay: float = BIND_RETRY_DELAY,
    sleep=time.sleep,
) -> socket.socket:
    """Bind the admin UI's listening socket, retrying on failure.

    ``uvicorn.run()`` swallows bind failures internally: on a bad address it
    logs one ERROR line ("could not bind on any address...") and then returns
    normally instead of raising. When that call is made from a daemon thread
    (as the admin panel is, see ``main()`` in ``__main__.py``), the thread just
    exits — no exception, no crash, no restart — and the panel is silently
    dead while the rest of the process (and systemd) reports healthy.

    Binding here, *before* handing the socket to uvicorn, gives an explicit,
    catchable ``OSError`` instead. This is also what makes a transient bind
    failure (e.g. a Tailscale interface not up yet at boot) self-healing: a
    few retries with a short delay ride out the network-readiness race
    without requiring a process restart.

    Args:
        host: address to bind.
        port: port to bind.
        attempts: number of attempts before giving up.
        delay: seconds to sleep between attempts.
        sleep: sleep function (injected for tests).

    Returns:
        A bound, listening TCP socket ready to hand to uvicorn (``fd=``).

    Raises:
        OSError: if binding still fails after all attempts.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    last_error: OSError = OSError(f"could not bind on {host}:{port}")
    for attempt in range(1, attempts + 1):
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            sock.listen(2048)
            return sock
        except OSError as error:
            last_error = error
            sock.close()
            LOG.warning(f"Admin UI bind attempt {attempt}/{attempts} on "
                        f"{host}:{port} failed: {error}")
            if attempt < attempts:
                sleep(delay)
    raise last_error


def start_admin_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Start the HiveMind Admin web server.

    This function starts a uvicorn server hosting the FastAPI admin interface.
    It should be called after hivemind-core service is running.

    The listening socket is bound up front, with bounded retry/backoff (see
    :func:`bind_with_retry`), before uvicorn is handed the connection. If the
    bind still fails after all retries, the failure is escalated LOUDLY:
    logged at CRITICAL and surfaced at ``GET /api/startup-error`` (the same
    channel other startup failures use), rather than the daemon thread just
    exiting in silence. The hivemind-core hub (ws/http protocol) is
    deliberately NOT taken down by a panel bind failure — it keeps serving
    satellites — so this only ever affects the admin UI's own reachability.

    Args:
        host: Host to bind the server (default: 127.0.0.1).
        port: Port to bind the server (default: 8000).
        reload: Enable auto-reload for development (default: False).

    Note:
        This function runs the server in a daemon thread and returns
        immediately. The server will shut down when the main process exits.
    """
    import uvicorn
    from hivemind_admin_panel.__main__ import app

    def _run_server():
        try:
            sock = bind_with_retry(host, port)
        except OSError as error:
            LOG.critical(
                f"Admin UI could not bind {host}:{port} after "
                f"{BIND_RETRY_ATTEMPTS} attempts — the admin panel is DOWN "
                f"(hivemind-core itself is unaffected and keeps serving "
                f"satellites): {error}"
            )
            from hivemind_admin_panel.api import set_startup_error
            set_startup_error(error)
            return

        LOG.info(f"Starting HiveMind Admin UI at http://{host}:{port}")
        LOG.info("Change admin credentials in ~/.config/hivemind-core/server.json (admin_user, admin_pass)")
        try:
            uvicorn.run(
                app,
                fd=sock.fileno(),
                reload=reload,
                log_level="info",
            )
        finally:
            sock.close()

    # Run server in daemon thread
    create_daemon(_run_server)
    LOG.info("HiveMind Admin server thread started")


def get_admin_app():
    """Get the FastAPI app instance for admin UI.

    Returns:
        FastAPI app configured with all admin routes.
    """
    from hivemind_admin_panel.api import get_admin_app
    return get_admin_app()
