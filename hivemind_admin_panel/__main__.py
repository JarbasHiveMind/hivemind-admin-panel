# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Main entry point for the HiveMind Admin Panel.

This module provides the FastAPI application that serves both the REST API and
the static web UI, and is the single launcher for a HiveMind deployment: by
default it starts an in-process ``hivemind-core`` hivemind-core and keeps a live reference
to it, so operators run ``hivemind-admin-panel`` only — there is no separate
``hivemind-core`` process to launch.

Example:
    ```bash
    # Launch hivemind-core + admin panel together (default)
    hivemind-admin-panel --host 0.0.0.0 --port 8100

    # Admin panel only, no in-process hivemind-core (manage on-disk state, or attach to a
    # hivemind-core managed elsewhere on the host)
    hivemind-admin-panel --no-core
    ```
"""

import argparse
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from hivemind_admin_panel.api import app as api_app
from hivemind_admin_panel.version import __version__

__all__ = ["app", "main"]

#: Directory containing static files (SPA web UI)
static_dir = Path(__file__).parent / "static"

#: Main FastAPI application instance
app = FastAPI(title="HiveMind Admin Panel")

# Mount the API app under /api prefix
app.mount("/api", api_app)

# Mount static files for direct access (CSS, JS, images)
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root() -> FileResponse:
    """Serve the main index.html file for the SPA.

    Returns:
        FileResponse: The index.html file from static directory.

    Raises:
        HTTPException: 404 if index.html is not present (e.g. package installed without static assets).
    """
    from fastapi import HTTPException
    index_path = static_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Admin UI static assets not found. "
                            "Reinstall with: pip install hivemind-admin-panel")
    return FileResponse(index_path)


@app.get("/index.html")
async def index() -> FileResponse:
    """Serve the main index.html file for the SPA.

    Returns:
        FileResponse: The index.html file from static directory.

    Raises:
        HTTPException: 404 if index.html is not present (e.g. package installed without static assets).
    """
    from fastapi import HTTPException
    index_path = static_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Admin UI static assets not found. "
                            "Reinstall with: pip install hivemind-admin-panel")
    return FileResponse(index_path)


def _tracked_protocol(base, service):
    """Subclass hivemind-core's listener protocol to feed the admin panel live state.

    Captures the live protocol instance (so ``/connections``, ``/stats`` and the
    topology become authoritative) and taps connection + message handlers to feed
    the metrics event/message buffers — entirely panel-side, with no core change.
    """
    from hivemind_admin_panel.api import init_injected_objects
    from hivemind_admin_panel._metrics import METRICS

    class _Tracked(base):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            init_injected_objects(service=service, db=service.db, protocol=self)
            METRICS.event("core.ready", "hivemind-core listener protocol online")

        def handle_new_client(self, client):
            METRICS.event("client.connected", f"{getattr(client, 'peer', '?')} connected")
            return super().handle_new_client(client)

        def handle_client_disconnected(self, client):
            METRICS.event("client.disconnected", f"{getattr(client, 'peer', '?')} disconnected")
            return super().handle_client_disconnected(client)

        def handle_message(self, message, client):
            try:
                METRICS.message(str(getattr(message, "msg_type", "?")),
                                str(getattr(client, "peer", "?")))
            except Exception:
                pass
            return super().handle_message(message, client)

        def handle_invalid_key_connected(self, client):
            METRICS.event("auth.rejected", f"invalid key from {getattr(client, 'peer', '?')}")
            return super().handle_invalid_key_connected(client)

    return _Tracked


def launch_core():
    """Construct an in-process hivemind-core and inject it into the admin API.

    Builds a ``HiveMindService`` and hands its live ``service``/``db`` objects to
    the admin API via ``init_injected_objects``. It does **not** run hivemind-core —
    ``HiveMindService.run()`` blocks on signal handlers and must execute on the
    main thread (see :func:`main`). If construction fails, the error is injected
    for diagnostics (surfaced at ``GET /api/startup-error``) and ``None`` is
    returned so the panel can still come up.

    Returns:
        The ``HiveMindService`` instance, or ``None`` if construction failed.
    """
    from ovos_utils.log import LOG
    from hivemind_admin_panel.api import init_injected_objects

    try:
        from hivemind_core.service import HiveMindService

        service = HiveMindService()
        init_injected_objects(service=service, db=service.db, protocol=None)
        # Wrap the listener protocol so the panel gets the LIVE protocol instance
        # (authoritative connections) and a tap on every HiveMessage — no core change.
        service.hm_protocol = _tracked_protocol(service.hm_protocol, service)
        LOG.info("hivemind-core constructed; will run in-process")
        return service
    except Exception as error:
        LOG.exception("hivemind-core failed to start; admin panel running in diagnostics mode")
        init_injected_objects(service=None, db=None, protocol=None, startup_error=error)
        return None


def main() -> None:
    """Launch the hivemind-core (in-process) and the admin panel.

    By default this starts ``hivemind-core`` inside this process and then serves
    the admin panel. Pass ``--no-core`` to serve the panel only.

    Note:
        Default credentials are admin/admin. Change them in
        ~/.config/hivemind-core/server.json (admin_user, admin_pass).
    """
    parser = argparse.ArgumentParser(description="HiveMind Admin Panel (launches hivemind-core + admin UI)")
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Admin panel host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8100,
        help="Admin panel port (default: 8100)",
    )
    parser.add_argument(
        "--no-core",
        action="store_true",
        help="Do not start an in-process hivemind-core; serve the admin panel only.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development (implies --no-core).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Log level for the in-process hivemind-core (e.g. DEBUG, INFO, ERROR).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show version and exit",
    )

    args = parser.parse_args()

    print(f"HiveMind Admin Panel v{__version__}")

    # --reload runs uvicorn in a child process, which would not carry hivemind-core —
    # so reload (a dev affordance) forces panel-only mode.
    run_core = not args.no_core and not args.reload

    if not run_core:
        import uvicorn
        print("hivemind-core: not started (--no-core)")
        print(f"Admin panel: http://{args.host}:{args.port}")
        print("Change admin credentials in server.json: admin_user, admin_pass")
        uvicorn.run(
            "hivemind_admin_panel.__main__:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return

    # Run-core mode. hivemind-core's run() installs SIGINT/SIGTERM handlers, which only
    # work on the main thread — so hivemind-core runs on the main thread and the admin
    # panel (uvicorn, which skips signal handlers off the main thread) runs in a
    # daemon thread.
    from ovos_utils import wait_for_exit_signal
    from ovos_utils.log import init_service_logger, LOG
    from hivemind_admin_panel import start_admin_server

    init_service_logger("core")
    LOG.set_level(args.log_level)

    service = launch_core()
    start_admin_server(host=args.host, port=args.port)  # panel in a daemon thread
    print("hivemind-core: running in-process")
    print(f"Admin panel: http://{args.host}:{args.port}")
    print("Change admin credentials in server.json: admin_user, admin_pass")

    if service is not None:
        service.run()           # main thread; blocks until SIGINT/SIGTERM
    else:
        wait_for_exit_signal()  # diagnostics mode: keep the panel up


if __name__ == "__main__":
    main()
