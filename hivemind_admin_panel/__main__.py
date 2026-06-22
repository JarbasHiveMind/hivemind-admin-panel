# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Main entry point for the HiveMind Admin Panel.

This module provides the FastAPI application that serves both the REST API and
the static web UI, and is the single launcher for a HiveMind deployment: by
default it starts an in-process ``hivemind-core`` hub and keeps a live reference
to it, so operators run ``hivemind-admin-panel`` only — there is no separate
``hivemind-core`` process to launch.

Example:
    ```bash
    # Launch the hub + admin panel together (default)
    hivemind-admin-panel --host 0.0.0.0 --port 8100

    # Admin panel only, no in-process hub (manage on-disk state, or attach to a
    # hub managed elsewhere on the host)
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


def launch_core():
    """Start an in-process HiveMind hub and inject it into the admin API.

    Constructs a ``HiveMindService``, hands its live ``service``/``db`` objects to
    the admin API via ``init_injected_objects``, and runs the hub in a daemon
    thread so the admin server stays responsive. If the hub fails to start, the
    error is injected for diagnostics (surfaced at ``GET /api/startup-error``)
    and the panel still comes up.

    Returns:
        The ``HiveMindService`` instance, or ``None`` if startup failed.
    """
    from ovos_utils import create_daemon
    from ovos_utils.log import LOG
    from hivemind_admin_panel.api import init_injected_objects

    try:
        from hivemind_core.service import HiveMindService

        service = HiveMindService()
        init_injected_objects(service=service, db=service.db, protocol=None)
        create_daemon(service.run)
        LOG.info("HiveMind hub started in-process")
        return service
    except Exception as error:
        LOG.exception("HiveMind hub failed to start; admin panel running in diagnostics mode")
        init_injected_objects(service=None, db=None, protocol=None, startup_error=error)
        return None


def main() -> None:
    """Launch the HiveMind hub (in-process) and the admin panel.

    By default this starts ``hivemind-core`` inside this process and then serves
    the admin panel. Pass ``--no-core`` to serve the panel only.

    Note:
        Default credentials are admin/admin. Change them in
        ~/.config/hivemind-core/server.json (admin_user, admin_pass).
    """
    parser = argparse.ArgumentParser(description="HiveMind Admin Panel (launches the hub + admin UI)")
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
        help="Do not start an in-process hub; serve the admin panel only.",
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
        help="Log level for the in-process hub (e.g. DEBUG, INFO, ERROR).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show version and exit",
    )

    args = parser.parse_args()

    import uvicorn

    print(f"HiveMind Admin Panel v{__version__}")

    # --reload runs uvicorn in a child process, which would not inherit the hub
    # daemon thread — so reload (a dev affordance) forces panel-only mode.
    run_core = not args.no_core and not args.reload

    if run_core:
        from ovos_utils.log import init_service_logger, LOG
        init_service_logger("core")
        LOG.set_level(args.log_level)
        launch_core()
        print("HiveMind hub: running in-process")
    else:
        print("HiveMind hub: not started (--no-core)")

    print(f"Admin panel: http://{args.host}:{args.port}")
    print("Change admin credentials in server.json: admin_user, admin_pass")

    if run_core:
        # pass the app object directly so the hub daemon thread persists
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        uvicorn.run(
            "hivemind_admin_panel.__main__:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )


if __name__ == "__main__":
    main()
