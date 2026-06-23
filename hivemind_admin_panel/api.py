# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""FastAPI for HiveMind-core management.

This module provides REST API endpoints for managing HiveMind-core clients,
permissions, and server configuration. All endpoints except /api/health
require HTTP Basic Authentication.

When the in-process hivemind-core is running (the default launcher), this module has
direct access to internal HiveMind-core objects for real-time data.

Endpoints:
    - /api/health — Health check (no auth required)
    - /api/config — Get/update server configuration
    - /api/config/validate — Validate configuration without applying
    - /api/config/restart — Restart HiveMind service with current config
    - /api/clients — List/create clients
    - /api/clients/{id} — Get/update/delete specific client
    - /api/clients/{id}/credentials — Get client credentials
    - /api/clients/{id}/allow-* — Grant permissions
    - /api/clients/{id}/blacklist-* — Revoke permissions
    - /api/connections — Get active connections (real-time when injected)
    - /api/stats — Get server statistics (real-time when injected)
"""

import hmac
import importlib.metadata
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks, Response, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from hivemind_admin_panel._auth import authenticate, verify_token, create_token, audit, read_audit
from hivemind_admin_panel.version import __version__ as admin_version
from hivemind_core.config import get_server_config as _get_server_config_raw, _DEFAULT

# hivemind-core's get_server_config() builds a JsonStorageXDG whose ComboLock
# does a non-atomic create+chmod on a *shared* lock file. Concurrent calls — e.g.
# the dashboard firing ~9 requests in parallel — race into
# `FileNotFoundError: .../server.json.lock` and surface as a 500. Serialize
# construction with a process-local lock; semantics are unchanged (each caller
# still gets a fresh config object), the races just can't overlap.
_config_lock = threading.Lock()


def get_server_config():
    """Thread-safe wrapper around hivemind-core's ``get_server_config``."""
    with _config_lock:
        return _get_server_config_raw()
from hivemind_core.database import ClientDatabase
from hivemind_plugin_manager import AgentProtocolFactory
from hivemind_plugin_manager import BinaryDataHandlerProtocolFactory
from hivemind_plugin_manager import DatabaseFactory
from hivemind_plugin_manager import NetworkProtocolFactory
from hivemind_plugin_manager import find_plugins, HiveMindPluginTypes
from hivemind_plugin_manager.database import Client
# Modern OVOS agent stack. Solver plugins (ovos_plugin_manager.solvers /
# templates.solvers) are deprecated in favour of AbstractAgentEngine
# (ovos_plugin_manager.templates.agents); legacy solver discovery is imported
# lazily in _discover_chat_engines() only for back-compat.
from ovos_plugin_manager.agents import find_chat_plugins, find_memory_plugins
from ovos_plugin_manager.stt import find_stt_plugins
from ovos_plugin_manager.tts import find_tts_plugins
from ovos_plugin_manager.vad import find_vad_plugins
from ovos_plugin_manager.wakewords import find_wake_word_plugins
from ovos_utils.log import LOG
from ovos_utils.xdg_utils import xdg_config_home
from pydantic import BaseModel, ConfigDict
from websocket import create_connection

if TYPE_CHECKING:
    from hivemind_core.service import HiveMindService
    from hivemind_core.protocol import HiveMindListenerProtocol

__all__ = ["app", "init_injected_objects", "get_admin_app"]

#: HTTP Basic security scheme for authentication
security = HTTPBasic()

#: Global references to injected core objects (set at startup)
_service: Optional["HiveMindService"] = None
_db: Optional[ClientDatabase] = None
_protocol: Optional["HiveMindListenerProtocol"] = None
_logger: Optional[logging.Logger] = None
_startup_error: Optional[Exception] = None
_error_traceback: Optional[str] = None
# How the panel was launched (set by __main__.main via set_runtime_info).
_run_mode: str = "unknown"          # "in-process" | "panel-only" | "unknown"
_bound_host: Optional[str] = None    # the host the panel's HTTP server bound to


def set_runtime_info(run_mode: str = "unknown", host: Optional[str] = None) -> None:
    """Record how the panel was launched, for the security self-check.

    Args:
        run_mode: ``"in-process"`` (the panel runs hivemind-core itself),
            ``"panel-only"`` (``--no-core``), or ``"unknown"``.
        host: the host the panel's HTTP server bound to (e.g. ``127.0.0.1``).
    """
    global _run_mode, _bound_host
    _run_mode = run_mode or "unknown"
    _bound_host = host


def init_injected_objects(
        service: "HiveMindService" = None,
        db: ClientDatabase = None,
        protocol: "HiveMindListenerProtocol" = None,
        logger: logging.Logger = None,
        startup_error: Exception = None
) -> None:
    """Initialize admin with direct access to core objects.

    Called by the panel launcher (launch_core) with the live hivemind-core objects.

    Args:
        service: HiveMindService instance for direct access.
        db: ClientDatabase instance (optional, uses global if not provided).
        protocol: HiveMindListenerProtocol for real-time connection data.
        logger: Logger instance for consistent logging.
        startup_error: Exception if core failed to start.
    """
    global _service, _db, _protocol, _logger, _startup_error, _error_traceback
    _service = service
    _db = db
    _protocol = protocol
    _logger = logger or logging.getLogger("hivemind.admin")

    if startup_error:
        _startup_error = startup_error
        _error_traceback = traceback.format_exc()


def get_admin_app() -> FastAPI:
    """Get the FastAPI app instance for admin UI.

    Returns:
        FastAPI app configured with all admin routes.
    """
    return app


def _identify(request: Request) -> Optional[tuple]:
    """Return (username, role) for a valid Basic or Bearer request, else None.

    Also accepts a bearer token via the ``access_token`` query parameter, since
    the browser EventSource API (used by the SSE /events feed) cannot set headers.
    """
    cfg = get_server_config()
    header = request.headers.get("Authorization", "")
    qtoken = request.query_params.get("access_token")
    if qtoken:
        payload = verify_token(cfg, qtoken)
        if payload:
            return payload.get("sub", "?"), payload.get("role", "admin")
    if header.startswith("Bearer "):
        payload = verify_token(cfg, header[7:].strip())
        if payload:
            return payload.get("sub", "?"), payload.get("role", "admin")
        return None
    if header.startswith("Basic "):
        import base64 as _b64
        try:
            user, _, pw = _b64.b64decode(header[6:]).decode().partition(":")
        except Exception:
            return None
        role = authenticate(cfg, user, pw)
        if role:
            return user, role
    return None


def verify_credentials(request: Request) -> bool:
    """Authenticate via HTTP Basic *or* ``Authorization: Bearer <token>``.

    Basic credentials are checked against ``server.json`` (admin_user/admin_pass
    plus any ``users``); bearer tokens are issued by ``POST /auth/login``.
    """
    if _identify(request) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


def require_admin(request: Request) -> bool:
    """Like :func:`verify_credentials` but requires the ``admin`` role."""
    ident = _identify(request)
    if ident is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    if ident[1] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Admin role required for this action")
    return True


def _current_user(request: Request) -> str:
    ident = _identify(request)
    return ident[0] if ident else "anonymous"


class ClientResponse(BaseModel):
    """Response model for client data."""

    client_id: int
    name: str
    api_key: str
    is_admin: bool
    allowed_types: List[str]
    message_blacklist: List[str]
    skill_blacklist: List[str]
    intent_blacklist: List[str]
    can_escalate: bool
    can_propagate: bool
    last_seen: float


class ClientCreate(BaseModel):
    """Request model for creating a new client.

    Attributes:
        name: Optional client name. Auto-generated if not provided.
        api_key: Optional API key. Auto-generated if not provided.
        password: Optional password. Auto-generated if not provided.
        crypto_key: Optional crypto key for encryption.
        is_admin: Whether client has admin privileges.
    """

    name: Optional[str] = None
    api_key: Optional[str] = None
    password: Optional[str] = None
    crypto_key: Optional[str] = None
    is_admin: bool = False


class ClientUpdate(BaseModel):
    """Request model for updating client data.

    Attributes:
        name: New client name.
        api_key: New API key.
        password: New password.
        crypto_key: New crypto key.
        is_admin: Admin privilege flag.
        can_escalate: Permission to send messages upstream.
        can_propagate: Permission to forward messages to siblings.
        allowed_types: List of allowed message types.
        message_blacklist: List of blacklisted message types.
        skill_blacklist: List of blacklisted skills.
        intent_blacklist: List of blacklisted intents.
    """

    name: Optional[str] = None
    api_key: Optional[str] = None
    password: Optional[str] = None
    crypto_key: Optional[str] = None
    is_admin: Optional[bool] = None
    can_escalate: Optional[bool] = None
    can_propagate: Optional[bool] = None
    allowed_types: Optional[List[str]] = None
    message_blacklist: Optional[List[str]] = None
    skill_blacklist: Optional[List[str]] = None
    intent_blacklist: Optional[List[str]] = None


class MsgTypeRequest(BaseModel):
    """Request model for message type permission changes."""

    msg_type: str


class SkillRequest(BaseModel):
    """Request model for skill permission changes."""

    skill_id: str


class IntentRequest(BaseModel):
    """Request model for intent permission changes."""

    intent_id: str


class ConfigUpdate(BaseModel):
    """Request model for server configuration updates.

    Attributes:
        config: Dictionary containing configuration key-value pairs.
    """

    config: Dict[str, Any]


class ConfigValidationResult(BaseModel):
    """Response model for configuration validation.

    Attributes:
        valid: Whether the configuration is valid.
        errors: List of validation error messages.
        warnings: List of validation warnings.
    """

    valid: bool
    errors: List[str]
    warnings: List[str]


class RestartResult(BaseModel):
    """Response model for service restart request.

    Attributes:
        status: Status of the restart request.
        message: Detailed message about the restart.
    """

    status: str
    message: str


class PluginInfo(BaseModel):
    """Information about an installable plugin."""

    name: str
    package: str
    entry_point: Optional[str] = None
    description: str
    category: str  # 'agent', 'network', 'database', 'binary', 'other'
    installed: bool
    version: Optional[str] = None


class PluginInstallRequest(BaseModel):
    """Request to install a plugin."""

    package: str


class PluginInstallResult(BaseModel):
    """Result of plugin installation."""

    success: bool
    message: str
    config_updated: bool = False


class DatabaseMigrationRequest(BaseModel):
    """Request to migrate database from one backend to another."""

    target_module: str
    preserve_data: bool = True


class DatabaseMigrationResult(BaseModel):
    """Result of database migration."""

    success: bool
    message: str
    source_module: str
    target_module: str
    clients_migrated: int


class DatabaseTestResult(BaseModel):
    """Result of database connection test."""

    success: bool
    message: str
    module: str


class DatabaseProfile(BaseModel):
    """A named, pre-configured database profile.

    Profiles allow users to configure multiple database backends and switch
    between them. The active profile's settings are written into the top-level
    ``database`` key of server.json for backwards compatibility with
    ``ClientDatabase``.

    Attributes:
        name: Unique profile identifier (alphanumeric, hyphens, underscores).
        module: Database plugin entry-point string (e.g. ``hivemind-redis-db-plugin``).
        config: Keyword arguments passed to the database plugin constructor.
    """

    name: str
    module: str
    config: Dict[str, Any] = {}


class DatabaseProfileCreate(BaseModel):
    """Request body for creating a new database profile.

    Attributes:
        name: Unique profile name.
        module: Database plugin entry-point string.
        config: Plugin constructor kwargs.
    """

    name: str
    module: str
    config: Dict[str, Any] = {}


class DatabaseProfileUpdate(BaseModel):
    """Request body for updating an existing database profile.

    Attributes:
        module: New plugin entry-point (optional; changing this on the active
            profile is not allowed).
        config: Replacement plugin constructor kwargs.
    """

    module: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class ActivateProfileRequest(BaseModel):
    """Request body for activating a database profile.

    Attributes:
        migrate_data: When True, copy all clients from the current active
            database into the new profile before switching.
    """

    migrate_data: bool = False


class ActivateProfileResult(BaseModel):
    """Result of activating a database profile.

    Attributes:
        success: Whether activation succeeded.
        message: Human-readable status message.
        profile_name: Name of the newly activated profile.
        clients_migrated: Number of clients copied (0 when migrate_data=False).
    """

    success: bool
    message: str
    profile_name: str
    clients_migrated: int = 0


class ConfigUpdateRequest(BaseModel):
    """Request to update config for a plugin."""

    plugin_type: str  # 'agent_protocol', 'network_protocol', 'database', 'binary_protocol'
    module: str
    enabled: bool
    config: Optional[Dict[str, Any]] = None


def _load_plugins_config() -> Dict[str, Any]:
    """Load plugins configuration from JSON file.

    Returns:
        Dict with plugin lists by category.
    """

    config_path = Path(__file__).parent / "plugins_config.json"
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        LOG.warning(f"Failed to load plugins config: {e}")
        return {
            "agent_protocols": [],
            "network_protocols": [],
            "databases": [],
            "binary_protocols": [],
            "ovos_plugins": []
        }


def _get_plugins_from_config() -> List[PluginInfo]:
    """Get plugin list from config file.

    Returns:
        List of PluginInfo objects.
    """
    config = _load_plugins_config()
    plugins = []

    category_map = {
        "agent_protocols": "agent",
        "network_protocols": "network",
        "databases": "database",
        "binary_protocols": "binary",
        "ovos_plugins_stt": "stt",
        "ovos_plugins_tts": "tts",
        "ovos_plugins_ww": "ww",
        "ovos_plugins_vad": "vad"
    }

    for config_key, category in category_map.items():
        for item in config.get(config_key, []):
            pkg = item.get("package", "")
            plugins.append(PluginInfo(
                name=item.get("name", pkg),
                package=pkg,
                entry_point=item.get("entry_point"),
                description=item.get("description", ""),
                category=category,
                installed=_check_plugin_installed(pkg),
                version=_pkg_version(pkg),
            ))

    return plugins


#: Main FastAPI application instance
app = FastAPI(title="HiveMind Admin API", version="0.1.0")


def validate_config(config: Dict[str, Any]) -> ConfigValidationResult:
    """Validate a HiveMind configuration.

    Args:
        config: Configuration dictionary to validate.

    Returns:
        ConfigValidationResult with validation status, errors, and warnings.
    """
    errors = []
    warnings = []

    # Check required top-level keys
    required_keys = ["agent_protocol", "network_protocol", "database"]
    for key in required_keys:
        if key not in config:
            errors.append(f"Missing required configuration key: '{key}'")

    # Validate agent_protocol
    if "agent_protocol" in config:
        agent_cfg = config["agent_protocol"]
        if not isinstance(agent_cfg, dict):
            errors.append("'agent_protocol' must be a dictionary")
        elif "module" not in agent_cfg:
            errors.append("'agent_protocol.module' is required")
        else:
            # Try to validate plugin can be loaded
            try:
                AgentProtocolFactory.get_class(agent_cfg["module"])
            except Exception as e:
                errors.append(f"Failed to load agent protocol '{agent_cfg['module']}': {e}")

    # Validate binary_protocol (optional)
    if "binary_protocol" in config and config["binary_protocol"]:
        binary_cfg = config["binary_protocol"]
        if isinstance(binary_cfg, dict) and binary_cfg.get("module"):
            try:
                BinaryDataHandlerProtocolFactory.get_class(binary_cfg["module"])
            except Exception as e:
                warnings.append(f"Binary protocol '{binary_cfg['module']}' failed to load: {e}")

    # Validate network_protocol
    if "network_protocol" in config:
        net_cfg = config["network_protocol"]
        if not isinstance(net_cfg, dict):
            errors.append("'network_protocol' must be a dictionary")
        elif not net_cfg:
            errors.append("At least one network protocol must be configured")
        else:
            for name, proto_cfg in net_cfg.items():
                if not isinstance(proto_cfg, dict):
                    errors.append(f"Network protocol '{name}' configuration must be a dictionary")
                    continue
                try:
                    NetworkProtocolFactory.get_class(name)
                except Exception as e:
                    errors.append(f"Failed to load network protocol '{name}': {e}")

    # Validate database
    if "database" in config:
        db_cfg = config["database"]
        if not isinstance(db_cfg, dict):
            errors.append("'database' must be a dictionary")
        elif "module" not in db_cfg:
            errors.append("'database.module' is required")
        else:
            try:
                DatabaseFactory.get_class(db_cfg["module"])
            except Exception as e:
                errors.append(f"Failed to load database plugin '{db_cfg['module']}': {e}")

    # Validate allowed_encodings if present
    if "allowed_encodings" in config:
        encodings = config["allowed_encodings"]
        if not isinstance(encodings, list):
            errors.append("'allowed_encodings' must be a list")
        elif not encodings:
            warnings.append("'allowed_encodings' is empty - no encodings will be allowed")

    # Validate allowed_ciphers if present
    if "allowed_ciphers" in config:
        ciphers = config["allowed_ciphers"]
        if not isinstance(ciphers, list):
            errors.append("'allowed_ciphers' must be a list")

    # Validate presence config if present
    if "presence" in config:
        presence_cfg = config["presence"]
        if not isinstance(presence_cfg, dict):
            errors.append("'presence' must be a dictionary")
        else:
            # Check for optional dependencies if features are enabled
            if presence_cfg.get("zeroconf"):
                try:
                    import zeroconf  # noqa: F401
                except ImportError:
                    warnings.append("zeroconf is enabled but not installed (pip install zeroconf)")
            if presence_cfg.get("ggwave"):
                try:
                    import ggwave  # noqa: F401
                except ImportError:
                    warnings.append("ggwave is enabled but not installed (pip install ggwave)")

    return ConfigValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


@app.get("/health")
def health() -> Dict[str, Any]:
    """Health check endpoint with detailed status information.

    Returns:
        Dict with status, version, timestamp, and service info.
        Does not require authentication.
    """

    response = {
        "status": "ok" if not _startup_error else "degraded",
        "version": admin_version,
        "timestamp": time.time(),
        "run_mode": _run_mode,
    }

    # Add service info if objects are injected
    if _service and hasattr(_service, "_status"):
        status = _service._status
        # report the readable state value, not the ProcessStatus object's repr
        state_name = status.state.name if status else "unknown"
        response["service_status"] = state_name
        # READY is set only AFTER the satellite listeners bind; STARTED-but-not-READY
        # means hivemind-core is hung before opening its network protocols (typically
        # blocked waiting on its agent backend / OVOS messagebus). Surface it so the
        # panel can warn that satellites cannot connect yet.
        response["core_ready"] = state_name == "READY"

    if _protocol and hasattr(_protocol, "clients"):
        response["active_connections"] = len(_protocol.clients)

    if _db:
        try:
            response["total_clients"] = sum(1 for c in _db if c.client_id != -1)
        except Exception:
            # Fallback to creating a new database instance if _db is not iterable
            with ClientDatabase() as db:
                response["total_clients"] = sum(1 for c in db if c.client_id != -1)

    # Signal degraded state without exposing error details on the unauthenticated endpoint
    if _startup_error:
        response["status"] = "degraded"

    return response


@app.get("/startup-error", dependencies=[Depends(verify_credentials)])
def get_startup_error() -> Dict[str, Any]:
    """Get detailed startup error information if core failed to start.

    Returns:
        Dict with error message, type, and full traceback.
        Returns 404 if no startup error occurred.

    Raises:
        HTTPException: 404 if no startup error is stored.
    """
    if not _startup_error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No startup error recorded"
        )

    return {
        "error": str(_startup_error),
        "error_type": type(_startup_error).__name__,
        "traceback": _error_traceback,
        "timestamp": time.time() if _error_traceback else None,
    }


@app.get("/config", dependencies=[Depends(verify_credentials)])
def get_config() -> Dict[str, Any]:
    """Get server configuration.

    Returns:
        Dict containing full server configuration from server.json.
    """
    cfg = get_server_config()
    return dict(cfg)


@app.post("/config", dependencies=[Depends(verify_credentials)])
def set_config(data: ConfigUpdate) -> Dict[str, Any]:
    """Update server configuration.

    Args:
        data: ConfigUpdate with new configuration values.

    Returns:
        Dict with status field on success.
    """
    _snapshot_config()
    cfg = get_server_config()
    for key, value in data.config.items():
        cfg[key] = value
    cfg.store()
    return {"status": "ok"}


# ===================== Config snapshots / rollback =====================

def _server_json_path() -> Path:
    """Path to hivemind-core's server.json."""
    return Path(xdg_config_home()) / "hivemind-core" / "server.json"


def _config_backups_dir() -> Path:
    return _server_json_path().parent / "config_backups"


def _snapshot_config(keep: int = 20) -> Optional[str]:
    """Copy the current server.json into config_backups/ before a mutation.

    Returns the snapshot filename, or None if there was nothing to snapshot.
    Best-effort: never raises into the caller.
    """
    try:
        src = _server_json_path()
        if not src.exists():
            return None
        backups = _config_backups_dir()
        backups.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        dst = backups / f"server-{ts}.json"
        i = 1
        while dst.exists():
            dst = backups / f"server-{ts}-{i}.json"
            i += 1
        dst.write_bytes(src.read_bytes())
        snaps = sorted(backups.glob("server-*.json"), key=lambda p: p.stat().st_mtime)
        for old in snaps[:-keep]:
            try:
                old.unlink()
            except OSError:
                pass
        return dst.name
    except Exception as e:  # noqa: BLE001
        LOG.warning(f"config snapshot failed: {e}")
        return None


class ConfigRestoreRequest(BaseModel):
    """Restore server.json from a named snapshot."""
    file: str


@app.get("/config/backups", dependencies=[Depends(verify_credentials)])
def list_config_backups() -> List[Dict[str, Any]]:
    """List server.json snapshots (newest first)."""
    backups = _config_backups_dir()
    out: List[Dict[str, Any]] = []
    if backups.exists():
        for p in sorted(backups.glob("server-*.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True):
            st = p.stat()
            out.append({"file": p.name, "size": st.st_size, "mtime": st.st_mtime})
    return out


@app.post("/config/backups", dependencies=[Depends(require_admin)])
def create_config_backup(request: Request) -> Dict[str, str]:
    """Take a manual snapshot of the current config."""
    name = _snapshot_config()
    if not name:
        raise HTTPException(status_code=500, detail="Nothing to snapshot")
    audit(_current_user(request), "config.snapshot", file=name)
    return {"status": "ok", "file": name}


@app.post("/config/backups/restore", dependencies=[Depends(require_admin)])
def restore_config_backup(data: ConfigRestoreRequest, request: Request) -> Dict[str, Any]:
    """Revert server.json to a snapshot (snapshots the current state first)."""
    # path-traversal guard: only a bare filename inside the backups dir
    if data.file != Path(data.file).name:
        raise HTTPException(status_code=400, detail="Invalid backup name")
    src = _config_backups_dir() / data.file
    if not src.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        restored = json.loads(src.read_text())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Corrupt backup: {e}")
    _snapshot_config()   # so a revert is itself reversible
    cfg = get_server_config()
    try:
        cfg.clear()
    except Exception:
        for k in list(cfg.keys()):
            cfg.pop(k, None)
    cfg.update(restored)
    cfg.store()
    audit(_current_user(request), "config.restore", file=data.file)
    return {"status": "ok", "restored": data.file}


@app.get("/config/backups/diff", dependencies=[Depends(verify_credentials)])
def diff_config_backup(file: str) -> Dict[str, Any]:
    """Preview what reverting to a snapshot would change vs the current config."""
    if file != Path(file).name:
        raise HTTPException(status_code=400, detail="Invalid backup name")
    src = _config_backups_dir() / file
    if not src.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        snapshot = json.loads(src.read_text())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Corrupt backup: {e}")
    current = dict(get_server_config())
    added = {k: snapshot[k] for k in snapshot if k not in current}
    removed = {k: current[k] for k in current if k not in snapshot}
    changed = {k: {"from": current[k], "to": snapshot[k]}
               for k in snapshot if k in current and current[k] != snapshot[k]}
    return {"file": file, "added": added, "removed": removed, "changed": changed}


@app.post("/config/validate", dependencies=[Depends(verify_credentials)])
def validate_config_endpoint(data: ConfigUpdate) -> ConfigValidationResult:
    """Validate configuration without applying it.

    Args:
        data: ConfigUpdate with configuration to validate.

    Returns:
        ConfigValidationResult with validation status, errors, and warnings.
    """
    return validate_config(data.config)


@app.post("/config/restart", dependencies=[Depends(verify_credentials)])
def restart_service(background_tasks: BackgroundTasks) -> RestartResult:
    """Restart the HiveMind service.

    This endpoint triggers a service restart. The restart happens
    asynchronously in the background.

    Returns:
        RestartResult with status and message.

    Note:
        This will only work when the admin UI is running integrated
        with the in-process hivemind-core. In --no-core
        mode, this returns an error.
    """
    global _service

    if _service is None:
        return RestartResult(
            status="error",
            message="Service restart not available in standalone admin mode. "
                    "Restart hivemind-core manually."
        )

    def do_restart():
        """Perform the actual restart after a short delay."""
        LOG.info("Service restart requested via Admin UI")
        time.sleep(1)  # Give the API response time to be sent

        # Set restart flag for parent process
        os.environ["HIVEMIND_AUTO_RESTART"] = "1"

        # Trigger graceful shutdown
        if _service and hasattr(_service, '_status'):
            _service._status.set_stopping()

        LOG.info("Initiating service restart...")

    background_tasks.add_task(do_restart)

    return RestartResult(
        status="restarting",
        message="Service restart initiated. The service will restart shortly. "
                "Please refresh the page in a few seconds."
    )


@app.get("/config/defaults", dependencies=[Depends(verify_credentials)])
def get_config_defaults() -> Dict[str, Any]:
    """Get default configuration values.

    Returns:
        Dict containing default configuration values.
    """
    return dict(_DEFAULT)


def _client_to_dict(client: Client, include_secrets: bool = False) -> Dict[str, Any]:
    """Convert Client object to dictionary.

    Args:
        client: Client object from database.
        include_secrets: Whether to include password and crypto_key.

    Returns:
        Dict with client data.
    """
    # Check if API key is already marked as revoked in the database
    # Case-insensitive check to handle "REVOKED", "revoked", etc.
    api_key_str = str(client.api_key or "").upper()
    is_revoked = api_key_str == "REVOKED" or (hasattr(client, 'revoked') and client.revoked)
    result = {
        "client_id": client.client_id,
        "name": client.name,
        "description": getattr(client, 'description', ''),
        "api_key": client.api_key,
        "is_admin": bool(client.is_admin),
        "allowed_types": client.allowed_types or [],
        "message_blacklist": client.message_blacklist or [],
        "skill_blacklist": client.skill_blacklist or [],
        "intent_blacklist": client.intent_blacklist or [],
        "can_escalate": bool(client.can_escalate),
        "can_propagate": bool(client.can_propagate),
        "can_broadcast": bool(getattr(client, 'can_broadcast', True)),
        "last_seen": client.last_seen or 0.0,
        "revoked": is_revoked,
        "tags": (getattr(client, "metadata", None) or {}).get("tags", []),
    }
    if include_secrets:
        result["password"] = client.password or ""
        result["crypto_key"] = client.crypto_key or ""
    return result


@app.get("/clients", dependencies=[Depends(verify_credentials)])
def list_clients() -> List[Dict[str, Any]]:
    """List all clients including deleted ones.

    Returns:
        List of client dictionaries (excludes internal client with id=-1).
        Deleted clients are marked with deleted=True.
    """
    with ClientDatabase() as db:
        return [_client_to_dict(c) for c in db if c.client_id != -1]


@app.get("/clients/active", dependencies=[Depends(verify_credentials)])
def list_active_clients() -> List[Dict[str, Any]]:
    """List only active (non-revoked) clients.
    
    Revoked clients are those with api_key="REVOKED" or revoked=True.
    """
    with ClientDatabase() as db:
        result = []
        for c in db:
            if c.client_id == -1:
                continue  # Skip internal client
            # Check if revoked (same as "deleted")
            api_key_str = str(c.api_key or "").upper()
            is_revoked = api_key_str == "REVOKED" or (hasattr(c, 'revoked') and c.revoked)
            if not is_revoked:
                result.append(_client_to_dict(c))
        return result


@app.get("/clients/{client_id}", dependencies=[Depends(verify_credentials)])
def get_client(client_id: int) -> Dict[str, Any]:
    """Get client details by ID.

    Args:
        client_id: The client ID to look up.

    Returns:
        Dict with client data.

    Raises:
        HTTPException: 404 if client not found.
    """
    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                return _client_to_dict(client)
    raise HTTPException(status_code=404, detail="Client not found")


@app.get(
    "/clients/{client_id}/credentials", dependencies=[Depends(verify_credentials)]
)
def get_client_credentials(client_id: int) -> Dict[str, Any]:
    """Get client credentials including password and crypto key.

    Args:
        client_id: The client ID to look up.

    Returns:
        Dict with client_id, name, api_key, password, and crypto_key.

    Raises:
        HTTPException: 404 if client not found.
    """
    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                return {
                    "client_id": client.client_id,
                    "name": client.name,
                    "api_key": client.api_key,
                    "password": client.password or "",
                    "crypto_key": client.crypto_key or "",
                }
    raise HTTPException(status_code=404, detail="Client not found")


@app.post("/clients", dependencies=[Depends(verify_credentials)])
def add_client(data: ClientCreate) -> Dict[str, Any]:
    """Add a new client.

    Args:
        data: ClientCreate with optional name, api_key, password, crypto_key, is_admin.

    Returns:
        Dict with full client data including secrets.

    Raises:
        HTTPException: 400 if crypto_key has invalid length.
    """
    password = data.password or os.urandom(16).hex()
    crypto_key = data.crypto_key
    admin = data.is_admin
    access_key = data.api_key or os.urandom(16).hex()

    if crypto_key and len(crypto_key) not in (16, 24, 32):
        raise HTTPException(
            status_code=400, detail="crypto_key must be 16, 24, or 32 characters"
        )

    with ClientDatabase() as db:
        name = data.name or f"HiveMind-Node-{db.total_clients()}"
        db.add_client(
            name, access_key, crypto_key=crypto_key, password=password, admin=admin
        )
        client = db.get_client_by_api_key(access_key)
        from hivemind_admin_panel._metrics import METRICS
        METRICS.event("client.created", f"Client '{client.name}' created",
                      client_id=client.client_id)
        return _client_to_dict(client, include_secrets=True)


@app.put("/clients/{client_id}", dependencies=[Depends(verify_credentials)])
def update_client(client_id: int, data: ClientUpdate) -> Dict[str, Any]:
    """Update client data.

    Args:
        client_id: The client ID to update.
        data: ClientUpdate with fields to update.

    Returns:
        Dict with updated client data.

    Raises:
        HTTPException: 404 if client not found.
        HTTPException: 400 if crypto_key has invalid length.
    """
    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                if data.name is not None:
                    client.name = data.name
                if data.api_key is not None:
                    client.api_key = data.api_key
                if data.password is not None:
                    client.password = data.password
                if data.crypto_key is not None:
                    if len(data.crypto_key) not in (16, 24, 32):
                        raise HTTPException(
                            status_code=400, detail="crypto_key must be 16, 24, or 32 characters"
                        )
                    client.crypto_key = data.crypto_key
                if data.is_admin is not None:
                    client.is_admin = data.is_admin
                if data.can_escalate is not None:
                    client.can_escalate = data.can_escalate
                if data.can_propagate is not None:
                    client.can_propagate = data.can_propagate
                if data.allowed_types is not None:
                    client.allowed_types = data.allowed_types
                if data.message_blacklist is not None:
                    client.message_blacklist = data.message_blacklist
                if data.skill_blacklist is not None:
                    client.skill_blacklist = data.skill_blacklist
                if data.intent_blacklist is not None:
                    client.intent_blacklist = data.intent_blacklist
                db.update_item(client)
                return _client_to_dict(client, include_secrets=True)
    raise HTTPException(status_code=404, detail="Client not found")


@app.delete("/clients/{client_id}", dependencies=[Depends(verify_credentials)])
def delete_client(client_id: int) -> Dict[str, Any]:
    """Delete a client.

    Args:
        client_id: The client ID to delete.

    Returns:
        Dict with status field on success.

    Raises:
        HTTPException: 404 if client not found.
    """
    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                db.delete_client(client.api_key)
                from hivemind_admin_panel._metrics import METRICS
                METRICS.event("client.deleted", f"Client {client_id} revoked",
                              client_id=client_id)
                return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Client not found")


@app.post("/clients/{client_id}/rename", dependencies=[Depends(verify_credentials)])
def rename_client(client_id: int, data: Dict[str, str]) -> Dict[str, Any]:
    """Rename a client.

    Args:
        client_id: The client ID to rename.
        data: Dict with 'name' key containing new name.

    Returns:
        Dict with updated client data.

    Raises:
        HTTPException: 400 if name is missing, 404 if client not found.
    """
    name = data.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name required")

    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                client.name = name
                db.update_item(client)
                return _client_to_dict(client)
    raise HTTPException(status_code=404, detail="Client not found")


@app.post(
    "/clients/{client_id}/allow-msg", dependencies=[Depends(verify_credentials)]
)
def allow_msg(client_id: int, data: MsgTypeRequest) -> Dict[str, Any]:
    """Allow a message type for a client.

    Args:
        client_id: The client ID.
        data: MsgTypeRequest with msg_type to allow.

    Returns:
        Dict with updated client data.
    """
    return _modify_msg_type(client_id, data.msg_type, "allow")


@app.post(
    "/clients/{client_id}/blacklist-msg", dependencies=[Depends(verify_credentials)]
)
def blacklist_msg(client_id: int, data: MsgTypeRequest) -> Dict[str, Any]:
    """Blacklist a message type for a client.

    Args:
        client_id: The client ID.
        data: MsgTypeRequest with msg_type to blacklist.

    Returns:
        Dict with updated client data.
    """
    return _modify_msg_type(client_id, data.msg_type, "blacklist")


def _modify_msg_type(client_id: int, msg_type: str, action: str) -> Dict[str, Any]:
    """Modify message type permissions for a client.

    Args:
        client_id: The client ID.
        msg_type: Message type to allow or blacklist.
        action: 'allow' or 'blacklist'.

    Returns:
        Dict with updated client data.

    Raises:
        HTTPException: 404 if client not found.
    """
    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                allowed = client.allowed_types or []
                if action == "allow" and msg_type not in allowed:
                    allowed.append(msg_type)
                elif action == "blacklist" and msg_type in allowed:
                    allowed.remove(msg_type)
                client.allowed_types = allowed
                db.update_item(client)
                return _client_to_dict(client)
    raise HTTPException(status_code=404, detail="Client not found")


@app.post(
    "/clients/{client_id}/allow-skill", dependencies=[Depends(verify_credentials)]
)
def allow_skill(client_id: int, data: SkillRequest) -> Dict[str, Any]:
    """Allow a skill for a client.

    Args:
        client_id: The client ID.
        data: SkillRequest with skill_id to allow.

    Returns:
        Dict with updated client data.
    """
    return _modify_skill(client_id, data.skill_id, "allow")


@app.post(
    "/clients/{client_id}/blacklist-skill",
    dependencies=[Depends(verify_credentials)],
)
def blacklist_skill(client_id: int, data: SkillRequest) -> Dict[str, Any]:
    """Blacklist a skill for a client.

    Args:
        client_id: The client ID.
        data: SkillRequest with skill_id to blacklist.

    Returns:
        Dict with updated client data.
    """
    return _modify_skill(client_id, data.skill_id, "blacklist")


def _modify_skill(client_id: int, skill_id: str, action: str) -> Dict[str, Any]:
    """Modify skill blacklist for a client.

    Args:
        client_id: The client ID.
        skill_id: Skill ID to allow or blacklist.
        action: 'allow' or 'blacklist'.

    Returns:
        Dict with updated client data.

    Raises:
        HTTPException: 404 if client not found.
    """
    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                blacklist = client.skill_blacklist or []
                if action == "allow" and skill_id in blacklist:
                    blacklist.remove(skill_id)
                elif action == "blacklist" and skill_id not in blacklist:
                    blacklist.append(skill_id)
                client.skill_blacklist = blacklist
                db.update_item(client)
                return _client_to_dict(client)
    raise HTTPException(status_code=404, detail="Client not found")


@app.post(
    "/clients/{client_id}/allow-intent", dependencies=[Depends(verify_credentials)]
)
def allow_intent(client_id: int, data: IntentRequest) -> Dict[str, Any]:
    """Allow an intent for a client.

    Args:
        client_id: The client ID.
        data: IntentRequest with intent_id to allow.

    Returns:
        Dict with updated client data.
    """
    return _modify_intent(client_id, data.intent_id, "allow")


@app.post(
    "/clients/{client_id}/blacklist-intent",
    dependencies=[Depends(verify_credentials)],
)
def blacklist_intent(client_id: int, data: IntentRequest) -> Dict[str, Any]:
    """Blacklist an intent for a client.

    Args:
        client_id: The client ID.
        data: IntentRequest with intent_id to blacklist.

    Returns:
        Dict with updated client data.
    """
    return _modify_intent(client_id, data.intent_id, "blacklist")


def _modify_intent(client_id: int, intent_id: str, action: str) -> Dict[str, Any]:
    """Modify intent blacklist for a client.

    Args:
        client_id: The client ID.
        intent_id: Intent ID to allow or blacklist.
        action: 'allow' or 'blacklist'.

    Returns:
        Dict with updated client data.

    Raises:
        HTTPException: 404 if client not found.
    """
    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                blacklist = client.intent_blacklist or []
                if action == "allow" and intent_id in blacklist:
                    blacklist.remove(intent_id)
                elif action == "blacklist" and intent_id not in blacklist:
                    blacklist.append(intent_id)
                client.intent_blacklist = blacklist
                db.update_item(client)
                return _client_to_dict(client)
    raise HTTPException(status_code=404, detail="Client not found")


@app.post(
    "/clients/{client_id}/allow-escalate",
    dependencies=[Depends(verify_credentials)],
)
def allow_escalate(client_id: int) -> Dict[str, Any]:
    """Allow client to escalate messages upstream.

    Args:
        client_id: The client ID.

    Returns:
        Dict with updated client data.
    """
    return _modify_flag(client_id, "can_escalate", True)


@app.post(
    "/clients/{client_id}/blacklist-escalate",
    dependencies=[Depends(verify_credentials)],
)
def blacklist_escalate(client_id: int) -> Dict[str, Any]:
    """Block client from escalating messages upstream.

    Args:
        client_id: The client ID.

    Returns:
        Dict with updated client data.
    """
    return _modify_flag(client_id, "can_escalate", False)


@app.post(
    "/clients/{client_id}/allow-propagate",
    dependencies=[Depends(verify_credentials)],
)
def allow_propagate(client_id: int) -> Dict[str, Any]:
    """Allow client to propagate messages to siblings.

    Args:
        client_id: The client ID.

    Returns:
        Dict with updated client data.
    """
    return _modify_flag(client_id, "can_propagate", True)


@app.post(
    "/clients/{client_id}/blacklist-propagate",
    dependencies=[Depends(verify_credentials)],
)
def blacklist_propagate(client_id: int) -> Dict[str, Any]:
    """Block client from propagating messages to siblings.

    Args:
        client_id: The client ID.

    Returns:
        Dict with updated client data.
    """
    return _modify_flag(client_id, "can_propagate", False)


@app.post(
    "/clients/{client_id}/make-admin", dependencies=[Depends(verify_credentials)]
)
def make_admin(client_id: int) -> Dict[str, Any]:
    """Grant admin privileges to a client.

    Args:
        client_id: The client ID.

    Returns:
        Dict with updated client data.
    """
    return _modify_flag(client_id, "is_admin", True)


@app.post(
    "/clients/{client_id}/revoke-admin", dependencies=[Depends(verify_credentials)]
)
def revoke_admin(client_id: int) -> Dict[str, Any]:
    """Revoke admin privileges from a client.

    Args:
        client_id: The client ID.

    Returns:
        Dict with updated client data.
    """
    return _modify_flag(client_id, "is_admin", False)


def _modify_flag(client_id: int, flag: str, value: bool) -> Dict[str, Any]:
    """Modify boolean flag for a client.

    Args:
        client_id: The client ID.
        flag: Flag name (is_admin, can_escalate, can_propagate).
        value: New flag value.

    Returns:
        Dict with updated client data.

    Raises:
        HTTPException: 404 if client not found.
    """
    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                setattr(client, flag, value)
                db.update_item(client)
                return _client_to_dict(client)
    raise HTTPException(status_code=404, detail="Client not found")


# Monitoring endpoints


@app.get("/connections", dependencies=[Depends(verify_credentials)])
def get_connections() -> Dict[str, Any]:
    """Get active connections from HiveMind protocol.

    When the in-process hivemind-core is running, returns real-time data from
    HiveMindListenerProtocol.clients. Otherwise returns mock data.

    Returns:
        Dict with connection count and list of active connections.
    """
    if _protocol and hasattr(_protocol, "clients"):
        clients = _protocol.clients
        # map api_key -> tags so connections can be recognized as bridges
        tags_by_key: Dict[str, List[str]] = {}
        try:
            with ClientDatabase() as db:
                for c in db:
                    if getattr(c, "client_id", -1) != -1:
                        tags_by_key[str(c.api_key)] = (
                            getattr(c, "metadata", None) or {}).get("tags", [])
        except Exception:
            pass
        return {
            "count": len(clients),
            "connections": [
                {
                    "peer": c.peer,
                    "key": c.key,
                    "session_id": c.sess.session_id if hasattr(c, "sess") else None,
                    "is_authenticated": c.is_authenticated if hasattr(c, "is_authenticated") else None,
                    "bridge": _match_bridge(c.peer, tags_by_key.get(str(c.key))),
                }
                for c in clients.values()
            ],
        }
    return {
        "count": 0,
        "connections": [],
        "note": "Live hivemind-core not attached; run hivemind-admin-panel (in-process hivemind-core on by default) for real-time data",
    }


@app.get("/stats", dependencies=[Depends(verify_credentials)])
def get_stats() -> Dict[str, Any]:
    """Get server statistics.

    When the in-process hivemind-core is running, returns real-time stats from
    the running HiveMindService. Otherwise returns basic config info.

    Returns:
        Dict with server statistics including client count,
        uptime, protocol information, and connection stats.
    """
    cfg = get_server_config()

    # Get protocol info
    network_protocols = cfg.get("network_protocol", {})
    agent_protocol = cfg.get("agent_protocol", {})

    stats = {
        "network_protocols": len(network_protocols),
        "agent_protocol": agent_protocol.get("module", "N/A"),
        "binarize": cfg.get("binarize", False),
    }

    # Add real-time data if objects are injected
    if _db:
        try:
            stats["client_count"] = sum(1 for c in _db if c.client_id != -1)
            stats["total_clients"] = _db.total_clients() if hasattr(_db, "total_clients") else stats["client_count"]
        except Exception:
            # Fallback to creating a new database instance if _db is not iterable
            with ClientDatabase() as db:
                stats["client_count"] = sum(1 for c in db if c.client_id != -1)
                stats["total_clients"] = db.total_clients() if hasattr(db, "total_clients") else stats["client_count"]

    if _protocol and hasattr(_protocol, "clients"):
        stats["active_connections"] = len(_protocol.clients)

    if _service and hasattr(_service, "_status"):
        stats["service_status"] = _service._status.state.name if _service._status else "unknown"

    return stats


# Plugin management endpoints


def _check_plugin_installed(package_name: str) -> bool:
    """Check if a plugin package is installed.

    Args:
        package_name: The package name to check.

    Returns:
        True if the package is installed, False otherwise.
    """
    try:
        importlib.metadata.version(package_name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def _pkg_version(package_name: str) -> Optional[str]:
    """Installed version of a package, or None if not installed."""
    try:
        return importlib.metadata.version(package_name)
    except Exception:
        return None


@app.get("/plugins", dependencies=[Depends(verify_credentials)])
def list_plugins() -> List[PluginInfo]:
    """List all known plugins and their installation status.

    Returns:
        List of PluginInfo with installed status.
    """
    return _get_plugins_from_config()


def _install_command(package: str) -> list:
    """Prefer `uv pip install` (org policy); fall back to pip if uv is absent."""
    import shutil
    if shutil.which("uv"):
        return ["uv", "pip", "install", "--python", sys.executable, package]
    return [sys.executable, "-m", "pip", "install", package]


@app.post("/plugins/install", dependencies=[Depends(require_admin)])
def install_plugin(data: PluginInstallRequest) -> PluginInstallResult:
    """Install a plugin package using uv (or pip fallback). Requires admin role.

    Args:
        data: PluginInstallRequest with package name.

    Returns:
        PluginInstallResult with success status and message.

    Raises:
        HTTPException: 400 if package name is invalid.
    """
    package = data.package.strip().lower()

    LOG.info(f"Installing plugin package: {package}")

    try:
        cmd = _install_command(package)
        LOG.debug(f"Running: {' '.join(cmd)}")

        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        elapsed_time = time.time() - start_time

        LOG.info(f"pip install completed in {elapsed_time:.2f}s, return code: {result.returncode}")

        if result.stdout:
            for line in result.stdout.splitlines():
                LOG.debug(f"pip: {line}")

        if result.stderr:
            for line in result.stderr.splitlines():
                LOG.warning(f"pip stderr: {line}")

        if result.returncode == 0:
            LOG.info(f"Successfully installed {package}")
            return PluginInstallResult(
                success=True,
                message=f"Successfully installed {package}"
            )
        else:
            error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            LOG.error(f"Installation failed for {package}: {error_msg}")
            return PluginInstallResult(
                success=False,
                message=f"Installation failed: {error_msg}"
            )
    except subprocess.TimeoutExpired:
        LOG.error(f"Installation timed out for {package}")
        return PluginInstallResult(
            success=False,
            message="Installation timed out after 120 seconds"
        )
    except Exception as e:
        LOG.error(f"Installation error for {package}: {e}", exc_info=True)
        return PluginInstallResult(
            success=False,
            message=f"Installation error: {str(e)}"
        )


def _uninstall_command(package: str) -> list:
    """Prefer `uv pip uninstall`; fall back to pip."""
    import shutil
    if shutil.which("uv"):
        return ["uv", "pip", "uninstall", "--python", sys.executable, package]
    return [sys.executable, "-m", "pip", "uninstall", "-y", package]


def _upgrade_command(package: str) -> list:
    """Prefer `uv pip install --upgrade`; fall back to pip."""
    import shutil
    if shutil.which("uv"):
        return ["uv", "pip", "install", "--upgrade", "--python", sys.executable, package]
    return [sys.executable, "-m", "pip", "install", "--upgrade", package]


def _run_pip(cmd: list, action: str, package: str, timeout: int = 120) -> PluginInstallResult:
    """Run a uv/pip subprocess and map the result to PluginInstallResult."""
    try:
        LOG.info(f"{action} {package}: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return PluginInstallResult(success=True, message=f"Successfully {action} {package}")
        err = (result.stderr or "").strip() or (result.stdout or "").strip() or "Unknown error"
        return PluginInstallResult(success=False, message=f"{action.capitalize()} failed: {err}")
    except subprocess.TimeoutExpired:
        return PluginInstallResult(success=False, message=f"{action.capitalize()} timed out after {timeout}s")
    except Exception as e:  # noqa: BLE001
        return PluginInstallResult(success=False, message=f"{action.capitalize()} error: {e}")


def _entrypoints_provided_by(package: str) -> set:
    """Entry-point names a distribution declares (used to protect active modules)."""
    try:
        dist = importlib.metadata.distribution(package)
    except importlib.metadata.PackageNotFoundError:
        return set()
    return {ep.name for ep in dist.entry_points}


def _active_module_names() -> set:
    """Module entry-point names currently active in server.json."""
    cfg = get_server_config()
    active = set()
    for slot in ("agent_protocol", "database", "binary_protocol"):
        module = (cfg.get(slot) or {}).get("module")
        if module:
            active.add(module)
    active.update((cfg.get("network_protocol") or {}).keys())
    return active


@app.post("/plugins/uninstall", dependencies=[Depends(require_admin)])
def uninstall_plugin(data: PluginInstallRequest, request: Request) -> PluginInstallResult:
    """Uninstall a plugin package (admin). Refuses if it provides an active module."""
    package = data.package.strip().lower()
    conflict = _active_module_names() & _entrypoints_provided_by(package)
    if conflict:
        raise HTTPException(
            status_code=400,
            detail=(f"'{package}' provides a module that is currently active "
                    f"({', '.join(sorted(conflict))}). Switch to another module first."))
    res = _run_pip(_uninstall_command(package), "uninstalled", package)
    if res.success:
        audit(_current_user(request), "plugin.uninstall", package=package)
    return res


@app.post("/plugins/upgrade", dependencies=[Depends(require_admin)])
def upgrade_plugin(data: PluginInstallRequest, request: Request) -> PluginInstallResult:
    """Upgrade a plugin package to the latest version (admin)."""
    package = data.package.strip().lower()
    before = _pkg_version(package)
    res = _run_pip(_upgrade_command(package), "upgraded", package)
    if not res.success:
        return res
    after = _pkg_version(package)
    audit(_current_user(request), "plugin.upgrade", package=package, before=before, after=after)
    msg = (f"{package}: {before or '?'} → {after}" if after and after != before
           else f"{package} already at the latest version ({after or '?'})")
    return PluginInstallResult(success=True, message=msg)


@app.post("/plugins/enable", dependencies=[Depends(verify_credentials)])
def enable_plugin(data: ConfigUpdateRequest) -> PluginInstallResult:
    """Enable a plugin by updating the configuration.

    Args:
        data: ConfigUpdateRequest with plugin type and module.

    Returns:
        PluginInstallResult with success status and config update info.
    """

    LOG.info(f"Plugin enable/disable: type={data.plugin_type} module={data.module} enabled={data.enabled}")

    _snapshot_config()
    cfg = get_server_config()
    config_updated = False

    if data.plugin_type == "database":
        LOG.info(f"Updating database configuration to: {data.module}")
        db_config = data.config or {}
        if "database" not in cfg:
            cfg["database"] = {}
        cfg["database"]["module"] = data.module
        if db_config:
            cfg["database"][data.module] = db_config
        config_updated = True

    elif data.plugin_type == "agent_protocol":
        LOG.info(f"Updating agent protocol to: {data.module}")
        if "agent_protocol" not in cfg:
            cfg["agent_protocol"] = {}
        cfg["agent_protocol"]["module"] = data.module
        if data.config:
            if data.module not in cfg["agent_protocol"]:
                cfg["agent_protocol"][data.module] = {}
            cfg["agent_protocol"][data.module].update(data.config)
            LOG.info(f"Agent protocol config updated: {data.config}")
        config_updated = True

    elif data.plugin_type == "binary_protocol":
        if data.enabled:
            LOG.info(f"Enabling binary protocol: {data.module}")
            if "binary_protocol" not in cfg:
                cfg["binary_protocol"] = {}
            cfg["binary_protocol"]["module"] = data.module
            if data.config:
                # Merge nested config
                for k, v in data.config.items():
                    if k not in cfg["binary_protocol"]:
                        cfg["binary_protocol"][k] = {}
                    if isinstance(v, dict) and isinstance(cfg["binary_protocol"].get(k), dict):
                        cfg["binary_protocol"][k].update(v)
                    else:
                        cfg["binary_protocol"][k] = v
        else:
            LOG.info("Disabling binary protocol")
            if "binary_protocol" not in cfg:
                cfg["binary_protocol"] = {}
            cfg["binary_protocol"]["module"] = None
        config_updated = True

    elif data.plugin_type == "network_protocol":
        if "network_protocol" not in cfg:
            cfg["network_protocol"] = {}
        if data.enabled:
            LOG.info(f"Enabling network protocol: {data.module} with config: {data.config}")
            cfg["network_protocol"][data.module] = data.config or {"host": "0.0.0.0", "port": 5678, "ssl": False}
        else:
            LOG.info(f"Disabling network protocol: {data.module}")
            if data.module in cfg["network_protocol"]:
                del cfg["network_protocol"][data.module]
        config_updated = True
    else:
        LOG.error(f"Unknown plugin type: {data.plugin_type}")

    if config_updated:
        LOG.info(f"Saving configuration to: {cfg.config_path if hasattr(cfg, 'config_path') else 'server.json'}")
        cfg.store()
        LOG.info(f"Plugin {data.module} {'enabled' if data.enabled else 'disabled'} and configuration updated")
        return PluginInstallResult(
            success=True,
            message=f"Plugin {data.module} {'enabled' if data.enabled else 'disabled'} and configuration updated",
            config_updated=True
        )

    LOG.error(f"❌ Failed to enable plugin: Unknown plugin type {data.plugin_type}")
    LOG.info("=" * 60)
    return PluginInstallResult(
        success=False,
        message=f"Unknown plugin type: {data.plugin_type}",
        config_updated=False
    )


# ============================================================================
# Database profile helpers
# ============================================================================

_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _get_profiles_dir() -> Path:
    """Return the directory that stores database profile JSON files.

    Each profile is a separate file: ``<dir>/<name>.json`` with the schema
    ``{"module": "<entry-point>", "config": {<plugin kwargs>}}``.

    Returns:
        Path to ``~/.config/hivemind-core/database_profiles/``.
    """
    return Path(xdg_config_home()) / "hivemind-core" / "database_profiles"


def _load_profile(name: str) -> Optional[Dict[str, Any]]:
    """Load a profile by name from disk.

    Args:
        name: Profile name (filename without ``.json``).

    Returns:
        Profile dict or ``None`` if not found.
    """
    profile_file = _get_profiles_dir() / f"{name}.json"
    if not profile_file.exists():
        return None
    try:
        with open(profile_file) as f:
            return json.load(f)
    except Exception as exc:
        LOG.warning(f"Failed to load profile '{name}': {exc}")
        return None


def _save_profile(name: str, profile: Dict[str, Any]) -> None:
    """Write a profile to disk.

    Args:
        name: Profile name (used as the filename).
        profile: Dict with ``module`` and ``config`` keys.
    """
    profiles_dir = _get_profiles_dir()
    profiles_dir.mkdir(parents=True, exist_ok=True)
    profile_file = profiles_dir / f"{name}.json"
    with open(profile_file, "w") as f:
        json.dump(profile, f, indent=2)


def _list_profiles() -> Dict[str, Dict[str, Any]]:
    """List all saved database profiles from disk.

    Returns:
        Dict mapping profile name to profile dict.
    """
    profiles_dir = _get_profiles_dir()
    profiles: Dict[str, Dict[str, Any]] = {}
    if not profiles_dir.exists():
        return profiles
    for profile_file in sorted(profiles_dir.glob("*.json")):
        name = profile_file.stem
        try:
            with open(profile_file) as f:
                profiles[name] = json.load(f)
        except Exception as exc:
            LOG.warning(f"Skipping malformed profile '{name}': {exc}")
    return profiles


def _ensure_profiles_initialized() -> None:
    """Bootstrap a ``"default"`` profile from ``server.json`` if none exist.

    On first run (or when the profiles directory is empty), reads the current
    ``database`` key from ``server.json`` and writes it as
    ``database_profiles/default.json``.  Does nothing if any profile files
    already exist.
    """
    if _list_profiles():
        return
    cfg = get_server_config()
    current_db = cfg.get("database", {})
    module = current_db.get("module", "hivemind-json-db-plugin")
    module_cfg = current_db.get(module, {})
    _save_profile("default", {"module": module, "config": module_cfg})
    LOG.info("Bootstrapped default database profile from server.json")


def _build_db_config_key(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a profile dict to the nested ``database`` key format.

    ``ClientDatabase`` expects ``{"module": "...", "<module>": {...kwargs}}``.
    Profiles store config flat as ``{"module": "...", "config": {...}}``.
    This function converts between the two.

    Args:
        profile: Profile dict with ``module`` and ``config`` keys.

    Returns:
        Dict suitable for ``cfg["database"]``.
    """
    module = profile["module"]
    return {
        "module": module,
        module: profile.get("config", {}),
    }


def _get_active_profile_name() -> Optional[str]:
    """Return the name of the profile that matches the current server.json database config.

    Compares ``server.json["database"]`` against every profile file.  Returns
    the first matching profile name, or ``None`` if no profile matches.

    Returns:
        Profile name string, or ``None``.
    """
    cfg = get_server_config()
    db_cfg = cfg.get("database", {})
    active_module = db_cfg.get("module", "")
    active_config = db_cfg.get(active_module, {})
    for name, profile in _list_profiles().items():
        if profile.get("module") == active_module and profile.get("config", {}) == active_config:
            return name
    return None


def _normalize_db_kwargs(module: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Translate profile config keys to the kwargs expected by the DB plugin class.

    Some plugins use different parameter names than what the UI/profile stores.
    For example, ``hivemind-redis-db-plugin`` (RedisDB dataclass) uses
    ``database_id`` while the profile config stores it as ``db``.

    Args:
        module: Database plugin entry-point string.
        config: Raw config dict from the profile.

    Returns:
        A copy of *config* with keys renamed to match the plugin's ``__init__``.
    """
    cfg = dict(config)
    if "redis" in module.lower():
        if "db" in cfg and "database_id" not in cfg:
            cfg["database_id"] = cfg.pop("db")
    return cfg


def _migrate_clients(
    src_module: str,
    src_kwargs: Dict[str, Any],
    tgt_module: str,
    tgt_kwargs: Dict[str, Any],
) -> int:
    """Copy all clients from the source DB to the target DB.

    Skips the internal client (``client_id == -1``) and skips any client
    whose ``api_key`` already exists in the target to avoid duplicates.

    Args:
        src_module: Source database plugin entry-point.
        src_kwargs: Constructor kwargs for the source plugin.
        tgt_module: Target database plugin entry-point.
        tgt_kwargs: Constructor kwargs for the target plugin.

    Returns:
        Number of clients copied.
    """
    src_class = DatabaseFactory.get_class(src_module)
    tgt_class = DatabaseFactory.get_class(tgt_module)
    src_db = src_class(**_normalize_db_kwargs(src_module, src_kwargs))
    tgt_db = tgt_class(**_normalize_db_kwargs(tgt_module, tgt_kwargs))

    # Collect existing api_keys in target to skip duplicates
    existing_keys = {c.api_key for c in tgt_db if c.client_id != -1}

    copied = 0
    for client in src_db:
        if client.client_id == -1:
            continue
        if client.api_key in existing_keys:
            LOG.debug(f"Skipping duplicate client '{client.name}' (already in target)")
            continue
        tgt_db.add_client(
            name=client.name,
            key=client.api_key,
            admin=client.is_admin,
            intent_blacklist=client.intent_blacklist,
            skill_blacklist=client.skill_blacklist,
            message_blacklist=client.message_blacklist,
            allowed_types=client.allowed_types,
            crypto_key=client.crypto_key,
            password=client.password,
        )
        copied += 1

    LOG.info(f"Migrated {copied} clients from {src_module} to {tgt_module}")
    return copied


def _test_db_connectivity(module: str, config: Dict[str, Any]) -> DatabaseTestResult:
    """Test database connectivity for a given module + config.

    For Redis modules: attempts a TCP connect + PING.
    For file-based modules (SQLite / JSON): verifies the parent directory
    is writable (or uses the plugin default path if none given).
    For all other modules: verifies the plugin class is loadable.

    Args:
        module: Database plugin entry-point string.
        config: Constructor kwargs for the plugin.

    Returns:
        DatabaseTestResult with success flag and human-readable message.
    """
    if not module:
        return DatabaseTestResult(success=False, message="No module specified", module=module)

    try:
        DatabaseFactory.get_class(module)
    except Exception as exc:
        return DatabaseTestResult(
            success=False,
            message=f"Plugin '{module}' could not be loaded: {exc}",
            module=module,
        )

    module_lower = module.lower()

    if "redis" in module_lower:
        host = config.get("host", "localhost")
        port = int(config.get("port", 6379))
        try:
            import socket as _socket
            conn = _socket.create_connection((host, port), timeout=5)
            conn.close()
        except OSError as exc:
            return DatabaseTestResult(
                success=False,
                message=f"Cannot reach Redis at {host}:{port} — {exc}",
                module=module,
            )
        # Attempt PING if redis package is available
        try:
            import redis as _redis
            r = _redis.Redis(
                host=host,
                port=port,
                db=int(config.get("db", 0)),
                password=config.get("password") or None,
                socket_connect_timeout=5,
                decode_responses=True,
            )
            r.ping()
        except ImportError:
            pass  # TCP connect succeeded — that's enough
        except Exception as exc:
            return DatabaseTestResult(
                success=False,
                message=f"Redis PING failed at {host}:{port} — {exc}",
                module=module,
            )
        return DatabaseTestResult(
            success=True,
            message=f"Redis reachable at {host}:{port}",
            module=module,
        )

    # File-based databases — check path writability
    path_str = config.get("path") or config.get("db_path")
    if path_str:
        test_path = Path(str(path_str)).expanduser()
        parent = test_path.parent
    elif "sqlite" in module_lower:
        from ovos_utils.xdg_utils import xdg_data_home as _xdg
        parent = Path(_xdg()) / "hivemind"
    elif "json" in module_lower:
        from ovos_utils.xdg_utils import xdg_data_home as _xdg
        parent = Path(_xdg()) / "hivemind"
    else:
        return DatabaseTestResult(
            success=True,
            message=f"Plugin '{module}' loaded successfully",
            module=module,
        )

    try:
        parent.mkdir(parents=True, exist_ok=True)
        probe = parent / ".hivemind_write_test"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        return DatabaseTestResult(
            success=False,
            message=f"Path '{parent}' is not writable: {exc}",
            module=module,
        )

    return DatabaseTestResult(
        success=True,
        message=f"Path '{parent}' is writable and plugin '{module}' is available",
        module=module,
    )


# ============================================================================
# Database profile CRUD endpoints
# ============================================================================


@app.get("/database/profiles", dependencies=[Depends(verify_credentials)])
def list_database_profiles() -> Dict[str, Any]:
    """List all saved database profiles and which one is active.

    Profiles are individual JSON files in
    ``~/.config/hivemind-core/database_profiles/``. On the first call, if
    none exist, a ``"default"`` profile is bootstrapped from the current
    ``database`` config in ``server.json``.

    Returns:
        Dict with ``profiles`` mapping (name → profile) and ``active`` name
        (the profile whose module+config matches the current server.json
        ``database`` section, or ``null`` if none match).
    """
    _ensure_profiles_initialized()
    profiles = _list_profiles()
    active = _get_active_profile_name()
    return {"profiles": profiles, "active": active}


@app.post("/database/profiles", dependencies=[Depends(verify_credentials)])
def create_database_profile(data: DatabaseProfileCreate) -> Dict[str, Any]:
    """Create a new named database profile.

    Saves the profile to disk but does NOT activate it. Use
    ``POST /database/profiles/{name}/activate`` to switch the active DB.

    Args:
        data: DatabaseProfileCreate with name, module, and config.

    Returns:
        Created profile dict.

    Raises:
        HTTPException: 422 if name is invalid, 409 if name already exists.
    """
    if not _PROFILE_NAME_RE.match(data.name):
        raise HTTPException(
            status_code=422,
            detail="Profile name must contain only letters, numbers, hyphens, and underscores",
        )

    _ensure_profiles_initialized()
    existing = _load_profile(data.name)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Profile '{data.name}' already exists")

    profile = {"module": data.module, "config": data.config}
    _save_profile(data.name, profile)

    LOG.info(f"Created database profile '{data.name}' ({data.module})")
    return {"name": data.name, "module": data.module, "config": data.config}


@app.get("/database/profiles/{name}", dependencies=[Depends(verify_credentials)])
def get_database_profile(name: str) -> Dict[str, Any]:
    """Get a single database profile by name.

    Args:
        name: Profile name.

    Returns:
        Profile dict with name, module, config.

    Raises:
        HTTPException: 404 if not found.
    """
    _ensure_profiles_initialized()
    p = _load_profile(name)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    return {"name": name, "module": p.get("module"), "config": p.get("config", {})}


@app.put("/database/profiles/{name}", dependencies=[Depends(verify_credentials)])
def update_database_profile(name: str, data: DatabaseProfileUpdate) -> Dict[str, Any]:
    """Update an existing database profile.

    Changing the ``module`` of the currently active profile is forbidden —
    activate a different profile first, then edit.

    Args:
        name: Profile name.
        data: DatabaseProfileUpdate with optional ``module`` and ``config``.

    Returns:
        Updated profile dict.

    Raises:
        HTTPException: 404 if not found, 409 if changing the module of the
            active profile.
    """
    _ensure_profiles_initialized()
    profile = _load_profile(name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    active = _get_active_profile_name()
    if data.module is not None and data.module != profile.get("module") and name == active:
        raise HTTPException(
            status_code=409,
            detail="Cannot change the module of the active profile. "
                   "Activate a different profile first, then edit.",
        )

    if data.module is not None:
        profile["module"] = data.module
    if data.config is not None:
        profile["config"] = data.config

    _save_profile(name, profile)
    LOG.info(f"Updated database profile '{name}'")
    return {"name": name, "module": profile["module"], "config": profile.get("config", {})}


@app.delete("/database/profiles/{name}", dependencies=[Depends(verify_credentials)])
def delete_database_profile(name: str) -> Dict[str, Any]:
    """Delete a database profile file.

    The currently active profile cannot be deleted.

    Args:
        name: Profile name.

    Returns:
        ``{"status": "ok"}``

    Raises:
        HTTPException: 404 if not found, 409 if trying to delete the active
            profile.
    """
    _ensure_profiles_initialized()
    if _load_profile(name) is None:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    active = _get_active_profile_name()
    if name == active:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete the active profile. Activate a different profile first.",
        )

    profile_file = _get_profiles_dir() / f"{name}.json"
    profile_file.unlink(missing_ok=True)

    LOG.info(f"Deleted database profile '{name}'")
    return {"status": "ok"}


@app.post("/database/profiles/{name}/test", dependencies=[Depends(verify_credentials)])
def test_database_profile(name: str) -> DatabaseTestResult:
    """Test connectivity for a saved database profile.

    Args:
        name: Profile name.

    Returns:
        DatabaseTestResult.

    Raises:
        HTTPException: 404 if profile not found.
    """
    _ensure_profiles_initialized()
    p = _load_profile(name)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    return _test_db_connectivity(p.get("module", ""), p.get("config", {}))


@app.post("/database/profiles/{name}/activate", dependencies=[Depends(verify_credentials)])
def activate_database_profile(name: str, data: ActivateProfileRequest) -> ActivateProfileResult:
    """Activate a database profile.

    Optionally migrates all clients from the current active database into the
    new one before switching. Copies the profile's module and config directly
    into ``server.json["database"]`` — no extra tracking key is written.
    A service restart is required to take effect.

    Args:
        name: Profile name to activate.
        data: ActivateProfileRequest with ``migrate_data`` flag.

    Returns:
        ActivateProfileResult.

    Raises:
        HTTPException: 404 if profile not found, 400 if the plugin cannot
            be loaded, 500 if migration fails.
    """
    _ensure_profiles_initialized()
    target = _load_profile(name)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    tgt_module = target.get("module", "")
    tgt_kwargs = target.get("config", {})

    # Validate plugin is loadable before touching anything
    try:
        DatabaseFactory.get_class(tgt_module)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot load plugin '{tgt_module}': {exc}")

    clients_migrated = 0
    if data.migrate_data:
        cfg = get_server_config()
        src_db_cfg = cfg.get("database", {})
        src_module = src_db_cfg.get("module", "")
        src_kwargs = src_db_cfg.get(src_module, {})

        if src_module and (src_module != tgt_module or src_kwargs != tgt_kwargs):
            try:
                clients_migrated = _migrate_clients(src_module, src_kwargs, tgt_module, tgt_kwargs)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Migration failed: {exc}")

    # Copy profile data into server.json["database"] exactly as if it were
    # configured directly — no extra tracking key needed.
    cfg = get_server_config()
    cfg["database"] = _build_db_config_key(target)
    cfg.store()

    LOG.info(f"Activated database profile '{name}' ({tgt_module}), migrated {clients_migrated} clients")
    return ActivateProfileResult(
        success=True,
        message=f"Activated profile '{name}'. Restart hivemind-core to apply.",
        profile_name=name,
        clients_migrated=clients_migrated,
    )


# ============================================================================
# Database management endpoints
# ============================================================================


@app.post("/database/test", dependencies=[Depends(verify_credentials)])
def test_database_connection(data: Dict[str, Any]) -> DatabaseTestResult:
    """Test database connectivity without saving configuration.

    Use this to validate a module + config before creating a profile.
    For saved profiles use ``POST /database/profiles/{name}/test`` instead.

    Args:
        data: Dictionary with ``module`` (entry-point string) and optional
            ``config`` dict (plugin constructor kwargs).

    Returns:
        DatabaseTestResult with success flag and human-readable message.
    """
    module = data.get("module", "")
    config = data.get("config", {})
    return _test_db_connectivity(module, config)


@app.post("/database/migrate", dependencies=[Depends(require_admin)])
def migrate_database(data: DatabaseMigrationRequest, response: Response) -> DatabaseMigrationResult:
    """Migrate clients from the current active database to a target module.

    .. deprecated::
        Prefer ``POST /database/profiles/{name}/activate`` with
        ``migrate_data=true``. That endpoint works with named profiles and
        preserves full connection config.

    Args:
        data: DatabaseMigrationRequest with target_module and preserve_data.
        response: FastAPI Response (used to set the deprecation header).

    Returns:
        DatabaseMigrationResult with migration status and stats.
    """
    response.headers["X-Deprecated"] = (
        "Use POST /database/profiles/{name}/activate with migrate_data=true instead"
    )

    cfg = get_server_config()
    source_db_cfg = cfg.get("database", {})
    source_module = source_db_cfg.get("module", "unknown")
    src_kwargs = source_db_cfg.get(source_module, {})
    target_module = data.target_module

    LOG.info(f"Database migration (legacy): {source_module} -> {target_module}")

    if source_module == target_module:
        return DatabaseMigrationResult(
            success=False,
            message="Source and target database modules are the same",
            source_module=source_module,
            target_module=target_module,
            clients_migrated=0,
        )

    try:
        clients_migrated = 0
        if data.preserve_data:
            clients_migrated = _migrate_clients(source_module, src_kwargs, target_module, {})

        cfg["database"] = {"module": target_module}
        cfg.store()

        return DatabaseMigrationResult(
            success=True,
            message=f"Migrated {clients_migrated} clients from {source_module} to {target_module}",
            source_module=source_module,
            target_module=target_module,
            clients_migrated=clients_migrated,
        )

    except Exception as exc:
        LOG.error(f"Database migration failed: {exc}", exc_info=True)
        return DatabaseMigrationResult(
            success=False,
            message=f"Migration failed: {exc}",
            source_module=source_module,
            target_module=target_module,
            clients_migrated=0,
        )


@app.get("/database/backends", dependencies=[Depends(verify_credentials)])
def list_database_backends() -> List[Dict[str, Any]]:
    """List available database backends with their status.

    Returns:
        List of database backend info including package, entry_point, and installation status.
    """
    config = _load_plugins_config()
    backends = []

    for db in config.get("databases", []):
        backends.append({
            "package": db.get("package", ""),
            "entry_point": db.get("entry_point", db.get("package", "")),
            "module": db.get("entry_point", db.get("package", "")),  # Keep module for backwards compat
            "name": db.get("name", db.get("package", "")),
            "type": db.get("type", "unknown"),
            "description": db.get("description", ""),
            "installed": _check_plugin_installed(db.get("package", ""))
        })

    return backends


# ACL Management endpoints


class ACLUpdateRequest(BaseModel):
    """Request to update ACL for a client."""

    client_id: int
    is_admin: Optional[bool] = None
    can_escalate: Optional[bool] = None
    can_propagate: Optional[bool] = None
    allowed_types: Optional[List[str]] = None
    skill_blacklist: Optional[List[str]] = None
    intent_blacklist: Optional[List[str]] = None


@app.get("/database/{module}/clients", dependencies=[Depends(verify_credentials)])
def list_db_clients(module: str) -> List[Dict[str, Any]]:
    """List clients from a specific database module.
    
    Args:
        module: The database module entry point.
        
    Returns:
        List of client dictionaries.
    """
    try:
        db_class = DatabaseFactory.get_class(module)
        db = db_class()
        # Ensure we close if it's a context manager
        if hasattr(db, "__enter__"):
            with db:
                return [_client_to_dict(c, include_secrets=True) for c in db if c.client_id != -1]
        return [_client_to_dict(c, include_secrets=True) for c in db if c.client_id != -1]
    except Exception as e:
        LOG.error(f"Failed to list clients for {module}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CopyClientRequest(BaseModel):
    source_module: str
    target_module: str
    api_key: str


@app.post("/database/copy-client", dependencies=[Depends(verify_credentials)])
def copy_client(data: CopyClientRequest) -> Dict[str, Any]:
    """Copy a single client from one database to another.
    
    Args:
        data: CopyClientRequest with source, target, and client API key.
        
    Returns:
        Dict with success status.
    """
    try:

        # Load source
        source_class = DatabaseFactory.get_class(data.source_module)
        source_db = source_class()

        # Load target
        target_class = DatabaseFactory.get_class(data.target_module)
        target_db = target_class()

        # Find client in source
        client = None
        for c in source_db:
            if c.api_key == data.api_key:
                client = c
                break

        if not client:
            raise HTTPException(status_code=404, detail="Client not found in source database")

        # Add to target
        target_db.add_client(
            name=client.name,
            access_key=client.api_key,
            crypto_key=client.crypto_key,
            password=client.password,
            admin=client.is_admin
        )

        # Update extra fields if supported
        target_client = target_db.get_client_by_api_key(client.api_key)
        if target_client:
            target_client.allowed_types = client.allowed_types
            target_client.message_blacklist = client.message_blacklist
            target_client.skill_blacklist = client.skill_blacklist
            target_client.intent_blacklist = client.intent_blacklist
            target_client.can_escalate = client.can_escalate
            target_client.can_propagate = client.can_propagate
            target_db.update_item(target_client)

        return {"status": "ok", "message": f"Client {client.name} copied to {data.target_module}"}
    except Exception as e:
        LOG.error(f"Failed to copy client: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/database/{module}/clear", dependencies=[Depends(require_admin)])
def clear_db(module: str) -> Dict[str, Any]:
    """Delete all clients from a specific database.
    
    Args:
        module: The database module entry point.
        
    Returns:
        Dict with success status.
    """
    try:
        db_class = DatabaseFactory.get_class(module)
        db = db_class()

        count = 0
        # Iterate and delete (skipping internal)
        # Note: some DBs might need a better 'clear' method, but this is generic
        for client in list(db):
            if client.client_id != -1:
                db.delete_client(client.api_key)
                count += 1

        return {"status": "ok", "message": f"Cleared {count} clients from {module}"}
    except Exception as e:
        LOG.error(f"Failed to clear database {module}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _load_acl_config() -> Dict[str, Any]:
    """Load ACL configuration from JSON file.

    Returns:
        Dict with ACL configuration including messages, skills, intents, and templates.
    """
    config_path = Path(__file__).parent / "acl_config.json"
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        LOG.warning(f"Failed to load ACL config: {e}")
        return {
            "common_messages": [],
            "common_skills": [],
            "common_intents": [],
            "templates": []
        }


def _load_persona_config() -> Dict[str, Any]:
    """Load persona configuration from JSON file.

    Returns:
        Dict with persona configuration including llm, persona, memory, and solvers.
    """
    config_path = Path(__file__).parent / "persona.json"
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        LOG.warning(f"Failed to load persona config: {e}")
        return {}


@app.get("/acl/config", dependencies=[Depends(verify_credentials)])
def get_acl_config() -> Dict[str, Any]:
    """Get full ACL configuration from JSON file.

    Returns:
        Dict with common_messages, common_skills, common_intents, and templates.
    """
    return _load_acl_config()


@app.get("/persona/config", dependencies=[Depends(verify_credentials)])
def get_persona_config() -> Dict[str, Any]:
    """Get persona configuration from JSON file.

    Returns:
        Dict with persona configuration including llm, persona, memory, and solvers.
    """
    return _load_persona_config()


@app.put("/persona/config", dependencies=[Depends(verify_credentials)])
def save_persona_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """Save persona configuration to JSON file.

    Args:
        data: Persona configuration dict.

    Returns:
        Dict with saved configuration.
    """
    personas_path = Path(xdg_config_home()) / "ovos_persona"
    personas_path.mkdir(parents=True, exist_ok=True)
    config_path = personas_path / "persona.json"
    try:
        with open(config_path, "w") as f:
            json.dump(data, f, indent=4)
        return {"status": "success", "config": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save persona config: {e}")


@app.get("/acl/templates", dependencies=[Depends(verify_credentials)])
def list_acl_templates() -> List[Dict[str, Any]]:
    """List predefined ACL templates from config file.

    Returns:
        List of ACL templates that can be applied to clients.
    """
    config = _load_acl_config()
    return config.get("templates", [])


@app.get("/acl/messages", dependencies=[Depends(verify_credentials)])
def list_common_messages() -> List[Dict[str, str]]:
    """List common HiveMind message types for ACL configuration.

    Returns:
        List of common message types with descriptions (from config file).
    """
    config = _load_acl_config()
    return config.get("common_messages", [])


@app.get("/acl/skills", dependencies=[Depends(verify_credentials)])
def list_common_skills() -> List[Dict[str, str]]:
    """List common skill IDs for ACL configuration.

    Returns:
        List of common skill IDs with descriptions (from config file).
    """
    config = _load_acl_config()
    return config.get("common_skills", [])


@app.get("/acl/intents", dependencies=[Depends(verify_credentials)])
def list_common_intents() -> List[Dict[str, str]]:
    """List common intent IDs for ACL configuration.

    Returns:
        List of common intent IDs with descriptions (from config file).
    """
    config = _load_acl_config()
    return config.get("common_intents", [])


def _discover_chat_engines() -> Dict[str, Any]:
    """Discover installed persona handler plugins (modern + legacy).

    Prefers the modern OVOS agent stack (``ovos_plugin_manager.agents`` chat
    engines / AbstractAgentEngine). Legacy ``solver`` plugins are still loaded as
    persona handlers by ovos-persona, so they are included via a guarded,
    lazy import of the deprecated finders for back-compat — without emitting
    deprecation warnings at module import time.
    """
    engines: Dict[str, Any] = {}
    try:
        engines.update(find_chat_plugins())
    except Exception as e:
        LOG.debug(f"chat-engine discovery failed: {e}")
    # Legacy solver plugins (deprecated, removed in ovos-plugin-manager 3.0)
    try:
        from ovos_plugin_manager.solvers import (
            find_question_solver_plugins,
            find_chat_solver_plugins,
        )
        engines.update(find_question_solver_plugins())
        engines.update(find_chat_solver_plugins())
    except Exception as e:
        LOG.debug(f"legacy solver discovery skipped: {e}")
    return engines


@app.get("/plugins/memory", dependencies=[Depends(verify_credentials)])
def list_memory_plugins() -> List[str]:
    """List installed conversational-memory plugins for personas.

    Returns the entry points discoverable via the modern agent stack
    (``ovos_plugin_manager.agents.find_memory_plugins``); the persona default is
    ``ovos-agents-short-term-memory-plugin``.
    """
    try:
        return sorted(find_memory_plugins().keys())
    except Exception as e:
        LOG.error(f"Failed to load memory plugins: {e}")
        return []


@app.get("/plugins/solvers", dependencies=[Depends(verify_credentials)])
def list_solver_plugins() -> List[Dict[str, Any]]:
    """List available persona handler plugins with installation status.

    "Handlers" are the persona's response engines: modern OVOS chat/agent
    engines plus legacy solver plugins (deprecated). The endpoint path is kept
    for backwards compatibility with existing clients.

    Returns:
        List of plugins with name, package, entry_point, description, and install_status.
    """
    config = _load_plugins_config()
    solvers = []

    # Get all installed handler entry points (modern chat engines + legacy solvers)
    try:
        installed_solvers = _discover_chat_engines()
    except Exception as e:
        LOG.error(f"Failed to load solver plugins: {e}")
        installed_solvers = {}
    
    for item in config.get("solver_plugins", []):
        entry_point = item.get("entry_point") or item.get("package", "")
        
        # Check if entry point is in installed solvers
        is_installed = entry_point in installed_solvers
        
        # Determine status
        if is_installed:
            status = "installed"
            error = None
        else:
            # Check if package is installed but entry point failed to register
            import importlib.metadata
            package_installed = False
            try:
                for dist in importlib.metadata.distributions():
                    pkg_name = dist.metadata.get('Name', '').lower()
                    item_pkg = item.get("package", "").lower()
                    if pkg_name and item_pkg and (pkg_name == item_pkg or pkg_name.replace('-', '_') == item_pkg.replace('-', '_')):
                        package_installed = True
                        break
            except Exception:
                pass
            
            if package_installed:
                status = "failed"
                error = "Package installed but entry point not registered"
            else:
                status = "missing"
                error = None
        
        solvers.append({
            "name": item.get("name", ""),
            "package": item.get("package", ""),
            "entry_point": entry_point,
            "description": item.get("description", ""),
            "install_status": status,
            "install_package": item.get("package", ""),
            "version": _pkg_version(item.get("package", "")),
            "error": error
        })
    
    return solvers


@app.get("/clients/{client_id}/acl", dependencies=[Depends(verify_credentials)])
def get_client_acl(client_id: int) -> Dict[str, Any]:
    """Get ACL configuration for a specific client.

    Args:
        client_id: The client ID.

    Returns:
        Dict with client ACL configuration including core permissions.

    Raises:
        HTTPException: 404 if client not found.
    """
    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                return {
                    "client_id": client.client_id,
                    "name": client.name,
                    "is_admin": bool(client.is_admin),
                    "can_escalate": bool(client.can_escalate),
                    "can_propagate": bool(client.can_propagate),
                    "allowed_types": client.allowed_types or [],
                    "skill_blacklist": client.skill_blacklist or [],
                    "intent_blacklist": client.intent_blacklist or [],
                }
    raise HTTPException(status_code=404, detail=f"Client {client_id} not found")


@app.put("/clients/{client_id}/acl", dependencies=[Depends(verify_credentials)])
def update_client_acl(client_id: int, data: ACLUpdateRequest) -> Dict[str, Any]:
    """Update ACL configuration for a specific client.

    Args:
        client_id: The client ID.
        data: ACLUpdateRequest with new ACL values.

    Returns:
        Dict with updated client ACL configuration.

    Raises:
        HTTPException: 404 if client not found.
    """
    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                # Core permissions
                if data.is_admin is not None:
                    client.is_admin = data.is_admin
                if data.can_escalate is not None:
                    client.can_escalate = data.can_escalate
                if data.can_propagate is not None:
                    client.can_propagate = data.can_propagate
                # Message whitelist
                if data.allowed_types is not None:
                    client.allowed_types = data.allowed_types
                # Skill blacklist
                if data.skill_blacklist is not None:
                    client.skill_blacklist = data.skill_blacklist
                # Intent blacklist
                if data.intent_blacklist is not None:
                    client.intent_blacklist = data.intent_blacklist
                db.update_item(client)
                return {
                    "client_id": client.client_id,
                    "name": client.name,
                    "is_admin": bool(client.is_admin),
                    "can_escalate": bool(client.can_escalate),
                    "can_propagate": bool(client.can_propagate),
                    "allowed_types": client.allowed_types or [],
                    "skill_blacklist": client.skill_blacklist or [],
                    "intent_blacklist": client.intent_blacklist or [],
                }
    raise HTTPException(status_code=404, detail="Client not found")


@app.post("/clients/{client_id}/acl/apply-template", dependencies=[Depends(verify_credentials)])
def apply_acl_template(client_id: int, template_name: str) -> Dict[str, Any]:
    """Apply an ACL template to a client.

    Args:
        client_id: The client ID.
        template_name: Name of the ACL template to apply.

    Returns:
        Dict with updated client ACL configuration.

    Raises:
        HTTPException: 404 if client or template not found.
    """
    # Load templates from config file
    config = _load_acl_config()
    templates = config.get("templates", [])

    # Find template
    template = None
    for t in templates:
        if t.get("name") == template_name:
            template = t
            break

    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")

    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                client.allowed_types = template.get("allowed_types", [])
                client.message_blacklist = template.get("message_blacklist", [])
                client.skill_blacklist = template.get("skill_blacklist", [])
                client.intent_blacklist = template.get("intent_blacklist", [])
                db.update_item(client)
                return {
                    "client_id": client.client_id,
                    "name": client.name,
                    "template_applied": template_name,
                    "allowed_types": client.allowed_types or [],
                    "message_blacklist": client.message_blacklist or [],
                    "skill_blacklist": client.skill_blacklist or [],
                    "intent_blacklist": client.intent_blacklist or [],
                }
    raise HTTPException(status_code=404, detail="Client not found")


@app.get("/ovos/test-bus", dependencies=[Depends(verify_credentials)])
def test_ovos_bus(host: str = "127.0.0.1", port: int = 8181) -> Dict[str, Any]:
    """Test connection to OVOS message bus from the server side.
    
    Args:
        host: The bus host.
        port: The bus port.
        
    Returns:
        Dict with success status and message.
    """
    url = f"ws://{host}:{port}/core"
    try:
        # First check if port is open
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            if s.connect_ex((host, port)) != 0:
                return {"success": False, "message": f"Port {port} is closed or unreachable on {host}"}

        # Try websocket handshake
        ws = create_connection(url, timeout=2.0)
        ws.close()
        return {"success": True, "message": f"Successfully connected to OVOS bus at {url}"}
    except Exception as e:
        return {"success": False, "message": f"Connection failed: {str(e)}"}


@app.get("/plugins/installed/ovos/{plugin_type}", dependencies=[Depends(verify_credentials)])
def list_installed_ovos_plugins(plugin_type: str) -> List[Dict[str, Any]]:
    """List actually installed OVOS plugins using ovos-plugin-manager.

    Args:
        plugin_type: 'stt', 'tts', 'ww', or 'vad'

    Returns:
        List of plugin info with entry_point, install_status, and error message.
    """
    try:
        mapping = {
            "stt": find_stt_plugins,
            "tts": find_tts_plugins,
            "ww": find_wake_word_plugins,
            "vad": find_vad_plugins,
        }

        if plugin_type not in mapping:
            raise HTTPException(status_code=400, detail=f"Invalid plugin type: {plugin_type}")

        # Get all plugins from ovos-plugin-manager (these are already installed)
        plugins_dict = mapping[plugin_type]()

        # Build maps from entry point name to its distribution package + version
        ep_to_package: Dict[str, str] = {}
        ep_to_version: Dict[str, str] = {}
        for dist in importlib.metadata.distributions():
            for ep in dist.entry_points:
                ep_to_package[ep.name] = dist.metadata["Name"]
                ep_to_version[ep.name] = dist.version

        # Return entry points with installed status
        result = []
        for entry_point in plugins_dict.keys():
            result.append({
                "entry_point": entry_point,
                "install_status": "installed",
                "package": ep_to_package.get(entry_point, entry_point),
                "version": ep_to_version.get(entry_point),
                "error": None
            })

        return result
    except ImportError:
        LOG.warning("ovos-plugin-manager not installed, falling back to empty list")
        return []
    except Exception as e:
        LOG.error(f"Error finding {plugin_type} plugins: {e}")
        return []


# ============================================================================
# Persona Management Endpoints
# ============================================================================

def _get_personas_path() -> Path:
    """Get the path to the personas directory.
    
    Returns:
        Path to ~/.config/ovos_persona/ directory.
    """
    return Path(xdg_config_home()) / "ovos_persona"


def _load_persona_files() -> List[Dict[str, Any]]:
    """Load all persona JSON files from the personas directory.
    
    Returns:
        List of persona configurations.
    """
    personas_path = _get_personas_path()
    personas = []

    if not personas_path.exists():
        return personas

    for persona_file in personas_path.glob("*.json"):
        try:
            with open(persona_file, "r") as f:
                persona = json.load(f)
                persona["_file"] = persona_file.name
                personas.append(persona)
        except Exception as e:
            LOG.warning(f"Failed to load persona file {persona_file}: {e}")

    return personas


def _get_persona_file_path(name: str) -> Path:
    """Get the file path for a persona by name.
    
    Args:
        name: Persona name (will be sanitized for filename).
        
    Returns:
        Path to the persona JSON file.
    """
    # Sanitize name for filename
    safe_name = "".join(c for c in name if c.isalnum() or c in " -_").strip().replace(" ", "_").lower()
    return _get_personas_path() / f"{safe_name}.json"


def _validate_persona_config(config: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate a persona configuration.
    
    Args:
        config: Persona configuration dictionary.
        
    Returns:
        Tuple of (is_valid, list of error messages).
    """
    errors = []

    # Required fields
    if "name" not in config or not config["name"]:
        errors.append("Persona must have a 'name' field")

    # Response engines: modern `handlers` (preferred) or legacy `solvers`
    handlers = config.get("handlers") or config.get("solvers")
    if not handlers or not isinstance(handlers, list) or len(handlers) == 0:
        errors.append("Persona must have a 'handlers' list with at least one response engine")

    return len(errors) == 0, errors


def _check_persona_models(config: Dict[str, Any]) -> Dict[str, Any]:
    """Check if persona requires model downloads.

    Args:
        config: Persona configuration dictionary.

    Returns:
        Dict with download_required flag and warnings.
    """
    warnings = []
    download_required = False

    solvers = config.get("solvers") or config.get("handlers") or []

    for solver in solvers:
        solver_config = config.get(solver, {})

        # Check for GGUF/LLama models (these are large custom downloads)
        if "gguf" in solver.lower():
            model_path = solver_config.get("model_path") or solver_config.get("model")
            if model_path:
                if not Path(model_path).exists():
                    warnings.append(f"GGUF model not found: {model_path}")
                    download_required = True

        # Check for custom/unknown solvers (manually installed by user)
        # We don't know if these need downloads, so warn user
        else:
            # Known OVOS solver ENTRY POINTS that don't need extra downloads
            # These are OVOS plugins used by personas (NOT HiveMind agent plugins)
            known_solvers = [
                # LLM Solvers
                "ovos-solver-openai-plugin",
                "ovos-solver-claude-plugin",
                "ovos-solver-gemini-plugin",
                # Fallback/Scripting
                "ovos-solver-failure-plugin",
                "ovos-solver-plugin-rivescript",
                "ovos-solver-plugin-aiml",
                # Knowledge/Tools
                "ovos-wolfram-alpha-solver",
                # OVOS Bus (provides OVOS skill execution)
                "ovos-solver-bus-plugin",
                # HiveMind OVOS Agent (provides OVOS skill execution via HiveMind)
                "hivemind-ovos-agent-plugin"
            ]
            if solver not in known_solvers:
                warnings.append(f"Custom plugin may require additional setup or download large model files on launch: {solver}")

        # TODO - check for solvers needing auth keys

    return {
        "download_required": download_required,
        "warnings": warnings
    }


class PersonaCreate(BaseModel):
    """Request model for creating a persona.

    Per-handler and per-memory-module config arrive as **extra** fields keyed by
    entry point (e.g. ``{"ovos-solver-openai-plugin": {...}, "memory_module":
    "ovos-agents-short-term-memory-plugin", "ovos-agents-short-term-memory-plugin":
    {...}}``) — ``extra="allow"`` keeps them so they're persisted on create, the
    same way ``ovos_persona.Persona`` reads ``config.get(<entry_point>)``.
    """
    model_config = ConfigDict(extra="allow")

    name: str
    description: Optional[str] = None
    handlers: Optional[List[str]] = None  # modern: persona response engines (chat/agent plugins)
    solvers: List[str] = []  # deprecated alias for handlers (legacy solver plugins)
    memory_module: Optional[str] = "ovos-agents-short-term-memory-plugin"


@app.get("/personas", dependencies=[Depends(verify_credentials)])
def list_personas() -> List[Dict[str, Any]]:
    """List all available personas.

    Returns:
        List of persona configurations.
    """
    return _load_persona_files()


@app.get("/personas/active", dependencies=[Depends(verify_credentials)])
def get_active_persona() -> Dict[str, Any]:
    """Get the currently active persona.

    Returns:
        Active persona path/name or null.
    """
    try:
        config = get_server_config()
        agent_config = config.get("agent_protocol", {})

        # Get persona path from agent protocol config
        persona_agent_config = agent_config.get("hivemind-persona-agent-plugin", {})
        persona_path = persona_agent_config.get("persona")

        if persona_path:
            # Extract persona name from path
            persona_name = Path(persona_path).stem
            return {"active": persona_name, "path": persona_path}

        return {"active": None}
    except Exception as e:
        LOG.warning(f"Failed to get active persona: {e}")
        return {"active": None}


@app.get("/personas/{name}", dependencies=[Depends(verify_credentials)])
def get_persona(name: str) -> Dict[str, Any]:
    """Get a specific persona configuration.

    Args:
        name: Persona name.

    Returns:
        Persona configuration.

    Raises:
        HTTPException: 404 if persona not found.
    """
    personas = _load_persona_files()
    for persona in personas:
        if persona.get("name") == name or persona.get("_file") == f"{name}.json":
            # Remove internal _file field
            result = {k: v for k, v in persona.items() if not k.startswith("_")}
            return result

    raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")


@app.post("/personas", dependencies=[Depends(verify_credentials)])
def create_persona(data: PersonaCreate) -> Dict[str, Any]:
    """Create a new persona.
    
    Args:
        data: Persona creation data.
        
    Returns:
        Created persona configuration.
    """
    # Build persona config
    config = {
        "name": data.name,
        "description": data.description or "",
    }

    # Always persist the modern persona schema: `handlers` (ovos-persona reads
    # `handlers`, falling back to the deprecated `solvers`). Accept either field
    # on input for back-compat, but store `handlers`.
    config["handlers"] = data.handlers if data.handlers else data.solvers

    # Memory module
    if data.memory_module:
        config["memory_module"] = data.memory_module

    # Per-entry-point config (handler config + memory-module config) arrives as
    # extra fields; persist them so create matches edit (and ovos-persona reads
    # config under each entry-point key).
    reserved = {"name", "description", "handlers", "solvers", "memory_module", "status", "path"}
    for key, value in (data.__pydantic_extra__ or {}).items():
        if key not in reserved:
            config[key] = value

    # Validate
    is_valid, errors = _validate_persona_config(config)
    if not is_valid:
        raise HTTPException(status_code=400, detail=", ".join(errors))

    # Save to file
    persona_path = _get_persona_file_path(data.name)
    persona_path.parent.mkdir(parents=True, exist_ok=True)

    with open(persona_path, "w") as f:
        json.dump(config, f, indent=2)

    LOG.info(f"Created persona '{data.name}' at {persona_path}")

    return {**config, "status": "ok", "path": str(persona_path)}


@app.put("/personas/{name}", dependencies=[Depends(verify_credentials)])
def update_persona(name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing persona.
    
    Args:
        name: Persona name.
        data: Updated persona configuration.
        
    Returns:
        Updated persona configuration.
        
    Raises:
        HTTPException: 404 if persona not found, 400 if invalid.
    """
    personas = _load_persona_files()
    existing = None
    for persona in personas:
        if persona.get("name") == name or persona.get("_file") == f"{name}.json":
            existing = persona
            break

    if not existing:
        raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")

    # Validate updated config
    is_valid, errors = _validate_persona_config(data)
    if not is_valid:
        raise HTTPException(status_code=400, detail=", ".join(errors))

    # Save to file
    persona_path = _get_persona_file_path(name)

    with open(persona_path, "w") as f:
        json.dump(data, f, indent=2)

    LOG.info(f"Updated persona '{name}' at {persona_path}")

    return data


@app.delete("/personas/{name}", dependencies=[Depends(verify_credentials)])
def delete_persona(name: str) -> Dict[str, Any]:
    """Delete a persona.
    
    Args:
        name: Persona name.
        
    Returns:
        Status message.
        
    Raises:
        HTTPException: 404 if persona not found.
    """
    personas = _load_persona_files()
    existing = None
    for persona in personas:
        if persona.get("name") == name or persona.get("_file") == f"{name}.json":
            existing = persona
            break

    if not existing:
        raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")

    persona_path = _get_persona_file_path(name)

    if persona_path.exists():
        persona_path.unlink()
        LOG.info(f"Deleted persona '{name}' from {persona_path}")

    return {"status": "ok", "message": f"Persona '{name}' deleted"}


@app.post("/personas/{name}/test", dependencies=[Depends(verify_credentials)])
def test_persona(name: str) -> Dict[str, Any]:
    """Test and validate a persona configuration.
    
    Args:
        name: Persona name.
        
    Returns:
        Test results with validation status, warnings, and download requirements.
        
    Raises:
        HTTPException: 404 if persona not found.
    """
    personas = _load_persona_files()
    persona = None
    for p in personas:
        if p.get("name") == name or p.get("_file") == f"{name}.json":
            persona = p
            break

    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")

    # Validate config
    is_valid, errors = _validate_persona_config(persona)

    # Check for model downloads
    model_check = _check_persona_models(persona)

    # Check if solvers are installed
    solver_warnings = []
    solvers = persona.get("handlers") or persona.get("solvers") or []

    try:
        # Available handler entry points (modern chat engines + legacy solvers)
        all_solvers = _discover_chat_engines()

        # Check if each handler in the persona is available (by entry point)
        for solver in solvers:
            # Check if solver entry point exists in available plugins
            if solver not in all_solvers:
                # Not found - this is a warning, not an error
                solver_warnings.append(f"Solver plugin not installed: {solver}")
    except ImportError:
        solver_warnings.append("ovos-plugin-manager not installed, cannot verify solver installation")

    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": model_check["warnings"] + solver_warnings,
        "download_required": model_check["download_required"],
        "solvers": solvers,
        "name": persona.get("name"),
        "description": persona.get("description", "")
    }


@app.get("/personas/{name}/export", dependencies=[Depends(verify_credentials)])
def export_persona(name: str) -> Dict[str, Any]:
    """Export a persona configuration as JSON.
    
    Args:
        name: Persona name.
        
    Returns:
        Persona configuration for download.
        
    Raises:
        HTTPException: 404 if persona not found.
    """
    personas = _load_persona_files()
    for persona in personas:
        if persona.get("name") == name or persona.get("_file") == f"{name}.json":
            # Remove internal fields
            result = {k: v for k, v in persona.items() if not k.startswith("_")}
            return result

    raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")


@app.post("/personas/{name}/activate", dependencies=[Depends(verify_credentials)])
def activate_persona(name: str, force: bool = False) -> Dict[str, Any]:
    """Activate a persona as the agent backend.

    Validates the persona before activating: a persona with config errors or
    handler plugins that aren't installed is rejected with 409 unless
    ``?force=true`` is passed (so you don't activate a hub that can't answer).

    Args:
        name: Persona name.
        force: Activate even if validation fails.

    Returns:
        Activation status.

    Raises:
        HTTPException: 404 if not found, 409 if not ready (and not forced).
    """
    # Verify persona exists
    personas = _load_persona_files()
    persona_data = None
    persona_path = None

    for p in personas:
        if p.get("name") == name or p.get("_file") == f"{name}.json":
            persona_data = p
            persona_path = p.get("_file")
            break

    if not persona_data:
        raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")

    if not persona_path:
        raise HTTPException(status_code=500, detail=f"Persona '{name}' has no associated file path")

    # Pre-activation validation — don't activate a persona that can't answer.
    if not force:
        is_valid, errors = _validate_persona_config(persona_data)
        missing: List[str] = []
        try:
            available = _discover_chat_engines()
            for handler in (persona_data.get("handlers") or persona_data.get("solvers") or []):
                if handler not in available:
                    missing.append(handler)
        except ImportError:
            pass
        if not is_valid or missing:
            raise HTTPException(status_code=409, detail={
                "message": f"Persona '{name}' is not ready to activate",
                "errors": errors,
                "missing_handlers": missing,
                "hint": "Install the missing handler plugins, or retry with ?force=true.",
            })

    # Get full path to persona file
    full_path = str(Path(xdg_config_home()) / "ovos_persona" / persona_path)

    # Update hivemind config to set active persona
    _snapshot_config()
    config = get_server_config()

    if "agent_protocol" not in config:
        config["agent_protocol"] = {}

    if "hivemind-persona-agent-plugin" not in config["agent_protocol"]:
        config["agent_protocol"]["hivemind-persona-agent-plugin"] = {}

    config["agent_protocol"]["hivemind-persona-agent-plugin"]["persona"] = full_path

    # Also set the module if not already set
    config["agent_protocol"]["module"] = "hivemind-persona-agent-plugin"

    config.store()

    LOG.info(f"Activated persona '{name}' at {full_path}")
    return {"status": "ok", "active_persona": name, "path": full_path}


@app.get("/plugins/installed/hivemind/{plugin_type}", dependencies=[Depends(verify_credentials)])
def list_installed_hivemind_plugins(plugin_type: str) -> List[str]:
    """List actually installed hivemind plugins using hivemind-plugin-manager.

    Args:
        plugin_type: 'network', 'agent', 'database' or 'binary'

    Returns:
        List of plugin entry points.
    """
    try:

        mapping = {
            "agent": HiveMindPluginTypes.AGENT_PROTOCOL,
            "database": HiveMindPluginTypes.DATABASE,
            "network": HiveMindPluginTypes.NETWORK_PROTOCOL,
            "binary": HiveMindPluginTypes.BINARY_PROTOCOL,
        }

        if plugin_type not in mapping:
            raise HTTPException(status_code=400, detail=f"Invalid plugin type: {plugin_type}")

        return list(find_plugins(mapping[plugin_type]).keys())
    except Exception as e:
        LOG.error(f"Error finding {plugin_type} plugins: {e}")
        return []


# ===================== Observability: metrics / events / logs =====================
import asyncio as _asyncio
import json as _json
from fastapi.responses import StreamingResponse
from hivemind_admin_panel._metrics import METRICS


def _live_snapshot() -> Dict[str, Any]:
    """Combine process metrics with live counts from the injected hivemind-core objects."""
    snap = METRICS.snapshot()
    active = None
    if _protocol is not None and hasattr(_protocol, "clients"):
        try:
            active = len(_protocol.clients)
        except Exception:
            active = None
    snap["active_connections"] = active
    total = None
    try:
        db = _db or ClientDatabase()
        total = len([c for c in db if getattr(c, "client_id", -1) != -1])
    except Exception:
        total = None
    snap["total_clients"] = total
    snap["service_status"] = (
        _service._status.state.name
        if _service and getattr(_service, "_status", None) else None
    )
    return snap


@app.get("/metrics", dependencies=[Depends(verify_credentials)])
def get_metrics() -> Dict[str, Any]:
    """Process + hivemind-core metrics: uptime, counters, gauges, live connection/client counts."""
    return _live_snapshot()


@app.get("/events/recent", dependencies=[Depends(verify_credentials)])
def get_recent_events(limit: int = 100, since: Optional[float] = None) -> List[Dict[str, Any]]:
    """Recent admin/hivemind-core events from the in-process ring buffer."""
    return METRICS.recent_events(limit=limit, since=since)


@app.get("/events", dependencies=[Depends(verify_credentials)])
async def stream_events(interval: float = 2.0, limit: int = 0) -> StreamingResponse:
    """Server-Sent Events: a live snapshot every `interval`s plus new events.

    `limit` bounds the number of SSE messages (0 = unbounded); clients/tests pass
    a small limit to terminate the stream.
    """
    interval = max(0.25, min(interval, 30.0))

    async def gen():
        last_ts = 0.0
        count = 0
        yield f"event: snapshot\ndata: {_json.dumps(_live_snapshot())}\n\n"
        count += 1
        while not limit or count < limit:
            await _asyncio.sleep(interval)
            for evt in METRICS.recent_events(limit=50, since=last_ts):
                last_ts = max(last_ts, evt["ts"])
                yield f"event: event\ndata: {_json.dumps(evt)}\n\n"
                count += 1
            yield f"event: snapshot\ndata: {_json.dumps(_live_snapshot())}\n\n"
            count += 1

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/logs", dependencies=[Depends(verify_credentials)])
def get_logs(lines: int = 200, level: Optional[str] = None) -> Dict[str, Any]:
    """Tail hivemind-core log file (core.log), optionally filtered by level substring."""
    base = getattr(LOG, "base_path", None)
    path = None
    if base and base != "stdout":
        candidate = os.path.join(base, "core.log")
        if os.path.isfile(candidate):
            path = candidate
    if not path:
        return {"path": None, "lines": [],
                "note": "no log file (logging to stdout or not yet created)"}
    lines = max(1, min(lines, 5000))
    try:
        with open(path, "r", errors="replace") as f:
            tail = f.readlines()[-lines:]
    except Exception as e:
        return {"path": path, "lines": [], "error": str(e)}
    if level:
        lvl = level.upper()
        tail = [ln for ln in tail if lvl in ln]
    return {"path": path, "lines": [ln.rstrip("\n") for ln in tail]}


# ===================== Auth: sessions, roles, audit =====================

class LoginRequest(BaseModel):
    """Request model for token login."""
    username: str
    password: str


@app.post("/auth/login")
def login(data: LoginRequest) -> Dict[str, Any]:
    """Exchange username/password for a signed bearer token (no auth required)."""
    cfg = get_server_config()
    role = authenticate(cfg, data.username, data.password)
    if not role:
        audit(data.username, "login.failed")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(cfg, data.username, role)
    audit(data.username, "login.ok", role=role)
    from hivemind_admin_panel._metrics import METRICS
    METRICS.event("auth.login", f"{data.username} logged in", role=role)
    return token


@app.post("/auth/logout", dependencies=[Depends(verify_credentials)])
def logout(request: Request) -> Dict[str, str]:
    """Stateless logout — the client discards its token."""
    audit(_current_user(request), "logout")
    return {"status": "ok"}


@app.get("/auth/me", dependencies=[Depends(verify_credentials)])
def whoami(request: Request) -> Dict[str, Any]:
    """Return the authenticated user and role."""
    ident = _identify(request)
    return {"username": ident[0], "role": ident[1]}


@app.get("/audit", dependencies=[Depends(verify_credentials)])
def get_audit(limit: int = 200) -> List[Dict[str, Any]]:
    """Recent admin audit-log entries (most recent last)."""
    return read_audit(limit=limit)


@app.middleware("http")
async def _audit_mutations(request: Request, call_next):
    """Record mutating requests (POST/PUT/DELETE) to the audit log + event feed."""
    response = await call_next(request)
    if request.method in ("POST", "PUT", "DELETE"):
        path = request.url.path
        # /auth/login records its own outcome; skip to avoid duplicate noise
        if path not in ("/auth/login",) and response.status_code < 400:
            user = _current_user(request)
            audit(user, f"{request.method} {path}", status=response.status_code)
            from hivemind_admin_panel._metrics import METRICS
            METRICS.event("admin.action", f"{user}: {request.method} {path}",
                          status=response.status_code)
    return response


# ===================== Onboarding: pairing + bulk client ops =====================

def _ws_endpoint() -> Dict[str, Any]:
    """Resolve hivemind-core's websocket transport host/port/ssl from server config."""
    net = get_server_config().get("network_protocol", {}) or {}
    for key in ("hivemind-websocket-plugin", "hivemind-websocket-protocol"):
        c = net.get(key)
        if isinstance(c, dict):
            return {"host": c.get("host", "0.0.0.0"), "port": c.get("port", 5678),
                    "ssl": bool(c.get("ssl", False))}
    for c in net.values():
        if isinstance(c, dict) and "port" in c:
            return {"host": c.get("host", "0.0.0.0"), "port": c.get("port", 5678),
                    "ssl": bool(c.get("ssl", False))}
    return {"host": "0.0.0.0", "port": 5678, "ssl": False}


@app.get("/clients/{client_id}/pairing", dependencies=[Depends(verify_credentials)])
def get_client_pairing(client_id: int, host: Optional[str] = None) -> Dict[str, Any]:
    """Return a satellite pairing bundle (credentials + hivemind-core endpoint + QR payload).

    `host` overrides the advertised hivemind-core address (use hivemind-core's LAN IP when it binds
    0.0.0.0). The `qr` field is a self-contained JSON payload to render as a QR code.
    """
    with ClientDatabase() as db:
        for c in db:
            if c.client_id == client_id:
                ep = _ws_endpoint()
                advertise = host or (ep["host"] if ep["host"] not in ("0.0.0.0", "") else None)
                hoststr = advertise or "<CORE-IP>"
                scheme = "wss" if ep["ssl"] else "ws"
                bundle = {
                    "client_id": c.client_id,
                    "name": c.name,
                    "key": c.api_key,
                    "password": c.password,
                    "crypto_key": c.crypto_key,
                    "host": advertise,
                    "port": ep["port"],
                    "ssl": ep["ssl"],
                    "connect_url": f"{scheme}://{hoststr}:{ep['port']}",
                }
                bundle["qr"] = _json.dumps({
                    "key": c.api_key, "password": c.password, "crypto_key": c.crypto_key,
                    "host": hoststr, "port": ep["port"], "ssl": ep["ssl"],
                })
                if not advertise:
                    bundle["note"] = ("hivemind-core bound to 0.0.0.0; pass ?host=<LAN-IP> "
                                      "before sharing the bundle.")
                return bundle
    raise HTTPException(status_code=404, detail="Client not found")


class BulkClientRequest(BaseModel):
    """Batch operation over multiple clients."""
    action: str  # delete | make_admin | revoke_admin | apply_template
    client_ids: List[int]
    template_name: Optional[str] = None


@app.post("/clients/bulk", dependencies=[Depends(verify_credentials)])
def bulk_clients(data: BulkClientRequest) -> Dict[str, Any]:
    """Apply one action to many clients; returns a per-client result list."""
    results = []
    for cid in data.client_ids:
        try:
            if data.action == "delete":
                delete_client(cid)
            elif data.action == "make_admin":
                _modify_flag(cid, "is_admin", True)
            elif data.action == "revoke_admin":
                _modify_flag(cid, "is_admin", False)
            elif data.action == "apply_template":
                if not data.template_name:
                    raise HTTPException(status_code=400, detail="template_name required")
                apply_acl_template(cid, data.template_name)
            else:
                raise HTTPException(status_code=400, detail=f"unknown action: {data.action}")
            results.append({"client_id": cid, "ok": True})
        except HTTPException as e:
            results.append({"client_id": cid, "ok": False, "error": e.detail})
        except Exception as e:  # pragma: no cover - defensive
            results.append({"client_id": cid, "ok": False, "error": str(e)})
    return {"action": data.action, "results": results}


# ===================== Agent depth: persona chat + engine taxonomy =====================

class PersonaChatRequest(BaseModel):
    """A single user turn to test a persona."""
    message: str
    lang: Optional[str] = "en-US"


@app.post("/personas/{name}/chat", dependencies=[Depends(verify_credentials)])
def chat_with_persona(name: str, data: PersonaChatRequest) -> Dict[str, Any]:
    """Run one chat turn against a persona (a live "try this persona" probe).

    Loads the persona JSON, instantiates ``ovos_persona.Persona`` and calls its
    handler chain. Returns ``{reply, error}`` — errors are returned (not raised)
    so the UI can show them.
    """
    path = _get_persona_file_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")
    try:
        with open(path) as f:
            config = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid persona file: {e}")

    try:
        from ovos_persona import Persona
        from ovos_plugin_manager.templates.agents import AgentMessage, MessageRole
        from ovos_bus_client.session import Session

        persona = Persona(name, config)
        sess = Session(lang=data.lang or "en-US")
        messages = [AgentMessage(role=MessageRole.USER, content=data.message)]
        reply = persona.chat(messages, sess)
        return {"persona": name, "reply": reply, "error": None}
    except Exception as e:
        LOG.error(f"persona chat failed for {name}: {e}")
        return {"persona": name, "reply": None, "error": str(e)}


# ----- Multi-turn persona chat (persistent Persona, memory accumulates) -----

class PersonaChatSay(BaseModel):
    """One turn in a multi-turn persona chat session."""
    message: str
    lang: Optional[str] = "en-US"


@app.post("/personas/{name}/chat/sessions", dependencies=[Depends(require_admin)])
def persona_chat_start(name: str, request: Request) -> Dict[str, Any]:
    """Open a multi-turn chat session against a persona (keeps memory across turns)."""
    path = _get_persona_file_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")
    try:
        config = json.loads(path.read_text())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid persona file: {e}")
    from hivemind_admin_panel._persona_chat import PERSONA_CHAT
    sess = PERSONA_CHAT.create(name, config)
    if sess.error:
        PERSONA_CHAT.close(sess.id)
        raise HTTPException(status_code=502, detail=f"Could not load persona '{name}': {sess.error}")
    audit(_current_user(request), "persona.chat.start", persona=name)
    return {"session_id": sess.id, "name": name}


@app.post("/personas/chat/sessions/{sid}/say", dependencies=[Depends(require_admin)])
def persona_chat_say(sid: str, data: PersonaChatSay) -> Dict[str, str]:
    """Send a turn; the reply is appended to the transcript synchronously."""
    from hivemind_admin_panel._persona_chat import PERSONA_CHAT
    sess = PERSONA_CHAT.get(sid)
    if sess is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if not (data.message or "").strip():
        raise HTTPException(status_code=400, detail="Empty message")
    sess.say(data.message.strip(), data.lang or "en-US")
    return {"status": "ok"}


@app.get("/personas/chat/sessions/{sid}/messages", dependencies=[Depends(verify_credentials)])
def persona_chat_messages(sid: str, since: int = 0) -> Dict[str, Any]:
    """Poll the transcript (``since`` = count already seen)."""
    from hivemind_admin_panel._persona_chat import PERSONA_CHAT
    sess = PERSONA_CHAT.get(sid)
    if sess is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    msgs, total = sess.messages(since)
    return {"messages": msgs, "total": total}


@app.delete("/personas/chat/sessions/{sid}", dependencies=[Depends(require_admin)])
def persona_chat_end(sid: str, request: Request) -> Dict[str, str]:
    """End a persona chat session (drops the Persona instance / its memory)."""
    from hivemind_admin_panel._persona_chat import PERSONA_CHAT
    PERSONA_CHAT.close(sid)
    audit(_current_user(request), "persona.chat.end", session=sid)
    return {"status": "ok"}


@app.get("/plugins/agents", dependencies=[Depends(verify_credentials)])
def list_agent_engines() -> Dict[str, List[str]]:
    """Installed plugins for each modern OVOS agent engine type.

    The agent stack (``ovos_plugin_manager.agents``) is the modern replacement for
    solver plugins and spans many engine types beyond chat (memory, reranker,
    retrieval, QA, summarizer, yes/no, multimodal).
    """
    from ovos_plugin_manager import agents as _agents
    finders = {
        "chat": "find_chat_plugins",
        "memory": "find_memory_plugins",
        "summarizer": "find_summarizer_plugins",
        "reranker": "find_reranker_plugins",
        "retrieval": "find_retrieval_plugins",
        "qa": "find_extractive_qa_plugins",
        "yesno": "find_yesno_plugins",
        "multimodal_chat": "find_multimodal_chat_plugins",
        "coreference": "find_coreference_plugins",
    }
    out: Dict[str, List[str]] = {}
    for kind, fn in finders.items():
        try:
            out[kind] = sorted(getattr(_agents, fn)().keys())
        except Exception as e:
            LOG.debug(f"agent discovery '{kind}' failed: {e}")
            out[kind] = []
    return out


# ===================== OVOS server registry (persona/stt/tts/translate) =====================

def _servers_path() -> Path:
    base = Path(xdg_config_home()) / "hivemind-admin"
    base.mkdir(parents=True, exist_ok=True)
    return base / "servers.json"


def _load_servers() -> List[Dict[str, Any]]:
    p = _servers_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except Exception:
        return []


def _save_servers(servers: List[Dict[str, Any]]) -> None:
    _servers_path().write_text(json.dumps(servers, indent=2))


class ServerCreate(BaseModel):
    """Register an external OVOS network server."""
    name: str
    type: str  # persona | stt | tts | translate | other
    url: str


@app.get("/servers", dependencies=[Depends(verify_credentials)])
def list_servers() -> List[Dict[str, Any]]:
    """List registered external OVOS servers (persona/stt/tts/translate)."""
    return _load_servers()


@app.post("/servers", dependencies=[Depends(verify_credentials)])
def add_server(data: ServerCreate) -> Dict[str, Any]:
    """Register an external OVOS server endpoint."""
    import uuid
    servers = _load_servers()
    entry = {"id": uuid.uuid4().hex[:8], "name": data.name,
             "type": data.type, "url": data.url.rstrip("/")}
    servers.append(entry)
    _save_servers(servers)
    return entry


@app.delete("/servers/{server_id}", dependencies=[Depends(verify_credentials)])
def delete_server(server_id: str) -> Dict[str, str]:
    """Remove a registered server."""
    servers = _load_servers()
    kept = [s for s in servers if s.get("id") != server_id]
    if len(kept) == len(servers):
        raise HTTPException(status_code=404, detail="Server not found")
    _save_servers(kept)
    return {"status": "ok"}


@app.get("/servers/{server_id}/health", dependencies=[Depends(verify_credentials)])
def server_health(server_id: str) -> Dict[str, Any]:
    """Probe a registered server for reachability + latency."""
    server = next((s for s in _load_servers() if s.get("id") == server_id), None)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    # type-aware health path; fall back to the base URL
    probe = {
        "persona": "/v1/models",
        "stt": "/status",
        "tts": "/status",
        "translate": "/status",
    }.get(server.get("type"), "")
    url = server["url"] + probe
    import requests
    started = time.time()
    try:
        resp = requests.get(url, timeout=3)
        return {"id": server_id, "url": url, "reachable": True,
                "status_code": resp.status_code,
                "latency_ms": round((time.time() - started) * 1000, 1)}
    except Exception as e:
        # retry base url once (probe path may not exist)
        try:
            resp = requests.get(server["url"], timeout=3)
            return {"id": server_id, "url": server["url"], "reachable": True,
                    "status_code": resp.status_code,
                    "latency_ms": round((time.time() - started) * 1000, 1)}
        except Exception:
            return {"id": server_id, "url": url, "reachable": False, "error": str(e)}


# ===================== Ops: backup/restore, policy chain, TLS certs =====================

@app.get("/backup", dependencies=[Depends(verify_credentials)])
def export_backup() -> Dict[str, Any]:
    """Export a portable bundle: server config + all clients (with secrets) + servers."""
    clients = []
    try:
        with ClientDatabase() as db:
            for c in db:
                if getattr(c, "client_id", -1) != -1:
                    clients.append(_client_to_dict(c, include_secrets=True))
    except Exception as e:
        LOG.error(f"backup: client export failed: {e}")
    return {
        "version": 1,
        "created_at": time.time(),
        "config": dict(get_server_config()),
        "clients": clients,
        "servers": _load_servers(),
    }


class RestoreRequest(BaseModel):
    """A backup bundle to restore."""
    config: Optional[Dict[str, Any]] = None
    clients: Optional[List[Dict[str, Any]]] = None
    servers: Optional[List[Dict[str, Any]]] = None
    restore_config: bool = False  # opt-in: overwriting server.json is destructive


@app.post("/restore", dependencies=[Depends(require_admin)])
def import_backup(data: RestoreRequest) -> Dict[str, Any]:
    """Restore clients (and optionally config/servers) from a backup bundle. Admin only."""
    added, skipped = 0, 0
    if data.clients:
        with ClientDatabase() as db:
            for c in data.clients:
                key = c.get("api_key")
                if not key or db.get_client_by_api_key(key):
                    skipped += 1
                    continue
                db.add_client(
                    c.get("name", "restored"), key,
                    admin=bool(c.get("is_admin")),
                    allowed_types=c.get("allowed_types"),
                    crypto_key=c.get("crypto_key"),
                    password=c.get("password"),
                )
                added += 1
    if data.servers is not None:
        _save_servers(data.servers)
    if data.restore_config and data.config:
        _snapshot_config()
        cfg = get_server_config()
        for k, v in data.config.items():
            cfg[k] = v
        cfg.store()
    return {"status": "ok", "clients_added": added, "clients_skipped": skipped,
            "config_restored": bool(data.restore_config and data.config)}


class PolicyUpdate(BaseModel):
    """The admission policy chain (evaluated for every client message)."""
    chain: List[Dict[str, Any]]


@app.get("/policy", dependencies=[Depends(verify_credentials)])
def get_policy() -> Dict[str, Any]:
    """Get the message admission policy chain from server config."""
    return get_server_config().get("policy", {"chain": []})


@app.put("/policy", dependencies=[Depends(require_admin)])
def set_policy(data: PolicyUpdate) -> Dict[str, Any]:
    """Replace the admission policy chain. Admin only."""
    _snapshot_config()
    cfg = get_server_config()
    policy = cfg.get("policy", {}) or {}
    policy["chain"] = data.chain
    cfg["policy"] = policy
    cfg.store()
    return {"status": "ok", "chain": data.chain}


def _cert_info() -> Dict[str, Any]:
    from ovos_utils.xdg_utils import xdg_data_home
    net = get_server_config().get("network_protocol", {}) or {}
    cfg = {}
    for key in ("hivemind-websocket-plugin", "hivemind-websocket-protocol"):
        if isinstance(net.get(key), dict):
            cfg = net[key]
            break
    cert_dir = cfg.get("cert_dir") or os.path.join(xdg_data_home(), "hivemind")
    cert_name = cfg.get("cert_name", "hivemind")
    return {"cert_dir": cert_dir, "cert_name": cert_name, "ssl_enabled": bool(cfg.get("ssl"))}


@app.get("/certs", dependencies=[Depends(verify_credentials)])
def get_certs() -> Dict[str, Any]:
    """Report TLS certificate status for the websocket transport."""
    info = _cert_info()
    crt = os.path.join(info["cert_dir"], f"{info['cert_name']}.crt")
    key = os.path.join(info["cert_dir"], f"{info['cert_name']}.key")
    info.update({
        "cert_path": crt, "key_path": key,
        "cert_exists": os.path.isfile(crt), "key_exists": os.path.isfile(key),
    })
    return info


@app.post("/certs/generate", dependencies=[Depends(require_admin)])
def generate_certs() -> Dict[str, Any]:
    """Generate a self-signed certificate for the websocket transport. Admin only."""
    info = _cert_info()
    os.makedirs(info["cert_dir"], exist_ok=True)
    crt = os.path.join(info["cert_dir"], f"{info['cert_name']}.crt")
    key = os.path.join(info["cert_dir"], f"{info['cert_name']}.key")
    try:
        import datetime
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        raise HTTPException(status_code=501, detail="cryptography not installed")

    pkey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hivemind")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(pkey.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=3650))
            .sign(pkey, hashes.SHA256()))
    with open(key, "wb") as f:
        f.write(pkey.private_bytes(serialization.Encoding.PEM,
                                   serialization.PrivateFormat.TraditionalOpenSSL,
                                   serialization.NoEncryption()))
    with open(crt, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return {"status": "ok", "cert_path": crt, "key_path": key}


# ===================== Pairing QR + topology =====================

@app.get("/clients/{client_id}/pairing/qr.svg", dependencies=[Depends(verify_credentials)])
def get_pairing_qr(client_id: int, host: Optional[str] = None) -> Response:
    """Render the client's pairing bundle as a scannable QR code (SVG)."""
    bundle = get_client_pairing(client_id, host=host)
    try:
        import qrcode
        import qrcode.image.svg
        img = qrcode.make(bundle["qr"], image_factory=qrcode.image.svg.SvgImage)
        import io
        buf = io.BytesIO()
        img.save(buf)
        return Response(content=buf.getvalue(), media_type="image/svg+xml")
    except ImportError:
        raise HTTPException(status_code=501, detail="qrcode not installed")


@app.get("/topology", dependencies=[Depends(verify_credentials)])
def get_topology() -> Dict[str, Any]:
    """Graph data for hivemind-core mesh: hivemind-core node plus each client, with live status.

    Nodes carry an ``online`` flag derived from the live protocol's connected
    sessions when available (best-effort in --no-core mode).
    """
    online_keys = set()
    if _protocol is not None and hasattr(_protocol, "clients"):
        try:
            online_keys = {str(k) for k in _protocol.clients.keys()}
        except Exception:
            online_keys = set()

    nodes = [{"id": "core", "label": "hivemind-core", "type": "core", "online": True}]
    edges = []
    try:
        with ClientDatabase() as db:
            for c in db:
                if getattr(c, "client_id", -1) == -1:
                    continue
                revoked = str(getattr(c, "api_key", "")).upper() == "REVOKED"
                if revoked:
                    continue
                nid = f"client-{c.client_id}"
                tags = (getattr(c, "metadata", None) or {}).get("tags", [])
                bridge = _match_bridge(c.name, tags)
                nodes.append({
                    "id": nid,
                    "label": c.name,
                    "type": "bridge" if bridge else ("admin" if c.is_admin else "satellite"),
                    "bridge": bridge,
                    "online": str(c.api_key) in online_keys,
                })
                edges.append({"from": "core", "to": nid})
    except Exception as e:
        LOG.error(f"topology: {e}")
    return {"nodes": nodes, "edges": edges,
            "online_count": sum(1 for n in nodes if n.get("online") and n["type"] != "core")}


# ===================== Client tags + first-run hint =====================

class TagsRequest(BaseModel):
    """Replace a client's tags."""
    tags: List[str]


@app.put("/clients/{client_id}/tags", dependencies=[Depends(verify_credentials)])
def set_client_tags(client_id: int, data: TagsRequest) -> Dict[str, Any]:
    """Set the tag list for a client (stored in client metadata)."""
    with ClientDatabase() as db:
        for client in db:
            if client.client_id == client_id:
                meta = dict(getattr(client, "metadata", None) or {})
                meta["tags"] = sorted(set(data.tags))
                client.metadata = meta
                db.update_item(client)
                return _client_to_dict(client)
    raise HTTPException(status_code=404, detail="Client not found")


# ===================== Bridges (chat-platform satellites) =====================
#
# A HiveMind bridge (Matrix, Twitch, ...) is an ordinary client/satellite whose
# input/output is a chat room instead of a microphone. The panel therefore
# *provisions* a bridge as a client (key + utterance ACL + a bridge tag) and
# *recognizes* it in the live views — it does NOT host or run the bridge process
# (those are independently deployed, with their own platform deps and secrets).

# The message type every bridge sends upstream (whitelist-only core).
BRIDGE_ALLOW = ["recognizer_loop:utterance"]

# Known bridges. ``match`` holds lowercase substrings tested against a live
# connection's peer/useragent so bridges provisioned outside the panel are still
# recognized; provisioned-here bridges also carry a ``bridge:<id>`` client tag.
_BRIDGES = [
    {"id": "matrix", "label": "Matrix", "icon": "💬",
     "repo": "https://github.com/JarbasHiveMind/HiveMind-matrix-bridge",
     "pip": "git+https://github.com/JarbasHiveMind/HiveMind-matrix-bridge",
     "match": ["matrixbridge", "hivemindmatrix"],
     "needs": ["Matrix homeserver URL", "bot access token", "room alias"]},
    {"id": "twitch", "label": "Twitch", "icon": "🟣",
     "repo": "https://github.com/JarbasHiveMind/HiveMind-twitch-bridge",
     "pip": "git+https://github.com/JarbasHiveMind/HiveMind-twitch-bridge",
     "match": ["twitchbridge", "hivemindtwitch"],
     "needs": ["Twitch bot account + OAuth token", "channel name"]},
    {"id": "mattermost", "label": "Mattermost", "icon": "🟦",
     "repo": "https://github.com/JarbasHiveMind/HiveMind_mattermost_bridge",
     "pip": "git+https://github.com/JarbasHiveMind/HiveMind_mattermost_bridge",
     "match": ["mattermostbridge", "hivemindmattermost"],
     "needs": ["Mattermost server URL", "bot token", "channel/team"]},
    {"id": "deltachat", "label": "DeltaChat", "icon": "📧",
     "repo": "https://github.com/JarbasHiveMind/HiveMind-deltachat-bridge",
     "pip": "git+https://github.com/JarbasHiveMind/HiveMind-deltachat-bridge",
     "match": ["deltachatbridge", "hiveminddeltachat"],
     "needs": ["bot e-mail address", "e-mail password"]},
    {"id": "hackchat", "label": "HackChat", "icon": "💻",
     "repo": "https://github.com/JarbasHiveMind/HiveMind-HackChatBridge",
     "pip": "git+https://github.com/JarbasHiveMind/HiveMind-HackChatBridge",
     "match": ["hackchat"],
     "needs": ["HackChat channel name", "bot nick"]},
]


def _bridge_meta(bridge_id: str) -> Optional[Dict[str, Any]]:
    return next((b for b in _BRIDGES if b["id"] == str(bridge_id).lower()), None)


def _bridge_public(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {k: meta[k] for k in ("id", "label", "icon", "repo", "pip", "needs")}


def _match_bridge(peer: Optional[str], tags: Optional[List[str]] = None
                  ) -> Optional[Dict[str, str]]:
    """Identify a connection as a bridge — by a ``bridge:<id>`` tag first
    (deterministic, set on provision), else by its peer/useragent (best effort)."""
    for t in (tags or []):
        if str(t).lower().startswith("bridge:"):
            m = _bridge_meta(str(t).split(":", 1)[1])
            if m:
                return {"id": m["id"], "label": m["label"], "icon": m["icon"]}
    p = str(peer or "").lower()
    for b in _BRIDGES:
        if any(tok in p for tok in b["match"]):
            return {"id": b["id"], "label": b["label"], "icon": b["icon"]}
    return None


@app.get("/bridges/catalog", dependencies=[Depends(verify_credentials)])
def bridges_catalog() -> List[Dict[str, Any]]:
    """The known HiveMind chat bridges the panel can provision a client for."""
    return [_bridge_public(b) for b in _BRIDGES]


class BridgeProvision(BaseModel):
    """Provision a client preset for a chat bridge."""
    type: str
    name: Optional[str] = None
    host: Optional[str] = None   # advertised core IP when bound to 0.0.0.0


@app.post("/bridges/provision", dependencies=[Depends(require_admin)])
def provision_bridge(data: BridgeProvision, request: Request) -> Dict[str, Any]:
    """Create a ready-to-use client for a bridge: mint credentials, grant the
    utterance ACL, tag it ``bridge:<id>``, and return the connection bundle.

    This is pure convenience over existing primitives (add client + allow-msg +
    pairing bundle) — the bridge itself is still deployed separately.
    """
    meta = _bridge_meta(data.type)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Unknown bridge type '{data.type}'")
    name = data.name or f"{meta['label']}-bridge"
    access_key = os.urandom(16).hex()
    password = os.urandom(16).hex()
    crypto_key = os.urandom(16).hex()   # 32 chars
    with ClientDatabase() as db:
        db.add_client(name, access_key, crypto_key=crypto_key, password=password, admin=False)
        client = db.get_client_by_api_key(access_key)
        client.allowed_types = list(BRIDGE_ALLOW)
        meta_d = dict(getattr(client, "metadata", None) or {})
        meta_d["tags"] = sorted(set((meta_d.get("tags") or []) + [f"bridge:{meta['id']}"]))
        client.metadata = meta_d
        db.update_item(client)
        cid = client.client_id
    from hivemind_admin_panel._metrics import METRICS
    METRICS.event("bridge.provisioned", f"{meta['label']} bridge client '{name}' created",
                  client_id=cid)
    audit(_current_user(request), "bridge.provisioned", type=meta["id"], client_id=cid)
    return {
        "client_id": cid,
        "bridge": _bridge_public(meta),
        "allow": list(BRIDGE_ALLOW),
        "bundle": get_client_pairing(cid, host=data.host),
    }


# ===================== Client impersonation chat =====================
#
# Chat through the hub *as* any registered client. The panel opens a real bus
# client with that client's credentials (server-side), so this exercises the
# genuine path — ACLs, routing, the agent backend — like a built-in webchat that
# can wear any client's identity. Requires a reachable hub (in-process by default).

class ChatStart(BaseModel):
    """Begin impersonating a client."""
    client_id: int


class ChatSay(BaseModel):
    """Send one utterance on the impersonated client's behalf."""
    utterance: str
    lang: Optional[str] = "en-us"


def _impersonation_endpoint() -> Dict[str, Any]:
    """Where to reach the hub for impersonation — loopback to the in-process core."""
    ep = _ws_endpoint()
    host = ep["host"]
    if host in ("0.0.0.0", "", None):
        host = "127.0.0.1"
    return {"host": host, "port": ep["port"]}


@app.post("/chat/sessions", dependencies=[Depends(require_admin)])
def chat_start(data: ChatStart, request: Request) -> Dict[str, Any]:
    """Open an impersonation chat session for a client (admin only)."""
    from hivemind_admin_panel._chat import CHAT
    with ClientDatabase() as db:
        client = next((c for c in db if getattr(c, "client_id", -1) == data.client_id), None)
        if client is None:
            raise HTTPException(status_code=404, detail="Client not found")
        key, password = client.api_key, client.password
        crypto_key, name = client.crypto_key, client.name
    if str(key).upper() == "REVOKED":
        raise HTTPException(status_code=400, detail="Client is revoked")
    ep = _impersonation_endpoint()
    sess = CHAT.create(data.client_id, name, key, password, crypto_key, ep["host"], ep["port"])
    if sess.error:
        CHAT.close(sess.id)
        raise HTTPException(status_code=502,
                            detail=f"Could not impersonate '{name}': {sess.error}")
    audit(_current_user(request), "chat.impersonate.start", client_id=data.client_id)
    return {"session_id": sess.id, "client_id": data.client_id, "name": name,
            "endpoint": f"{ep['host']}:{ep['port']}"}


@app.post("/chat/sessions/{sid}/say", dependencies=[Depends(require_admin)])
def chat_say(sid: str, data: ChatSay) -> Dict[str, str]:
    """Send an utterance as the impersonated client; replies arrive asynchronously."""
    from hivemind_admin_panel._chat import CHAT
    sess = CHAT.get(sid)
    if sess is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if not (data.utterance or "").strip():
        raise HTTPException(status_code=400, detail="Empty utterance")
    sess.say(data.utterance.strip(), data.lang or "en-us")
    return {"status": "ok"}


@app.get("/chat/sessions/{sid}/messages", dependencies=[Depends(verify_credentials)])
def chat_messages(sid: str, since: int = 0) -> Dict[str, Any]:
    """Poll the transcript; ``since`` is the count already seen by the client."""
    from hivemind_admin_panel._chat import CHAT
    sess = CHAT.get(sid)
    if sess is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    msgs, total = sess.messages(since)
    return {"messages": msgs, "total": total}


@app.get("/chat/sessions", dependencies=[Depends(verify_credentials)])
def chat_list() -> List[Dict[str, Any]]:
    """Active impersonation sessions."""
    from hivemind_admin_panel._chat import CHAT
    return CHAT.list_active()


@app.delete("/chat/sessions/{sid}", dependencies=[Depends(require_admin)])
def chat_end(sid: str, request: Request) -> Dict[str, str]:
    """End an impersonation session (disconnects the bus client)."""
    from hivemind_admin_panel._chat import CHAT
    CHAT.close(sid)
    audit(_current_user(request), "chat.impersonate.end", session=sid)
    return {"status": "ok"}


def _security_checks(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build the security self-check list shown on the dashboard.

    Each check is ``{id, label, ok, severity, hint, acknowledged}``. ``severity``
    is ``"critical"`` | ``"warning"`` | ``"info"``; ``ok`` False with a critical
    severity is what blocks the "secure" verdict and drives the first-run gate.
    A *warning* the operator has acknowledged (``POST /setup/ack``) is marked
    ``acknowledged`` and no longer counts against the verdict; criticals can
    never be acknowledged away.
    """
    acked = set(cfg.get("setup_acked", []) or [])
    admin_user = cfg.get("admin_user", "admin")
    default_creds = (admin_user == "admin"
                     and cfg.get("admin_pass", "admin") == "admin")
    host = _bound_host or "127.0.0.1"
    loopback = host in ("127.0.0.1", "localhost", "::1", "")
    # hivemind-core's satellite-facing websocket TLS (independent of the panel's HTTP).
    core_tls = bool(cfg.get("ssl") or (cfg.get("cert_file") and cfg.get("key_file")))

    checks: List[Dict[str, Any]] = [
        {
            "id": "admin_password",
            "label": "Admin password changed from default",
            "ok": not default_creds,
            "severity": "critical",
            "hint": ("The panel can install packages and migrate databases. "
                     "Change the default admin password before doing anything else."),
        },
        {
            "id": "bind_host",
            "label": "Panel bound to loopback (127.0.0.1)",
            "ok": loopback,
            "severity": "warning",
            "hint": (f"The panel is bound to {host} and reachable from the network. "
                     "Keep it on 127.0.0.1, or put it behind a TLS-terminating, "
                     "authenticating reverse proxy."),
        },
        {
            "id": "core_tls",
            "label": "hivemind-core websocket TLS configured",
            "ok": core_tls,
            "severity": "info",
            "hint": ("Satellites connect over plain ws://. For untrusted networks, "
                     "enable TLS (ssl/cert_file/key_file) in server.json."),
        },
    ]
    for c in checks:
        # only warnings are dismissable; criticals/info are never "acknowledged"
        c["acknowledged"] = (c["severity"] == "warning" and c["id"] in acked)
    return checks


@app.get("/setup/status", dependencies=[Depends(verify_credentials)])
def setup_status() -> Dict[str, Any]:
    """First-run + security self-check.

    Drives the dashboard "Security" card and the blocking first-run password
    gate. ``secure`` is False whenever any *critical* check fails.
    """
    cfg = get_server_config()
    checks = _security_checks(cfg)
    default_creds = not next(c["ok"] for c in checks if c["id"] == "admin_password")
    host = _bound_host or "127.0.0.1"
    exposed = host not in ("127.0.0.1", "localhost", "::1", "")
    clients = 0
    try:
        with ClientDatabase() as db:
            clients = sum(1 for c in db if getattr(c, "client_id", -1) != -1)
    except Exception:
        pass
    warnings = [c["hint"] for c in checks
                if not c["ok"] and not c.get("acknowledged")
                and c["severity"] in ("critical", "warning")]
    # criticals must pass; acknowledged warnings no longer count against "secure"
    secure = all(c["ok"] for c in checks if c["severity"] == "critical")
    clean = all(c["ok"] or c.get("acknowledged") or c["severity"] == "info"
                for c in checks)
    return {
        "default_credentials": default_creds,
        "has_clients": clients > 0,
        "client_count": clients,
        "bound_host": host,
        "exposed": exposed,
        "run_mode": _run_mode,
        "checks": checks,
        "secure": secure,
        "clean": clean,
        "warnings": warnings,
    }


class SetupAck(BaseModel):
    """Acknowledge (or un-acknowledge) a non-critical security warning."""
    id: str


@app.post("/setup/ack", dependencies=[Depends(require_admin)])
def setup_ack(data: SetupAck, request: Request) -> Dict[str, Any]:
    """Acknowledge a *warning* check so it stops nagging the dashboard.

    Only ``warning``-severity checks can be acknowledged; trying to ack a
    critical (e.g. default credentials) is rejected — fix it instead.
    """
    cfg = get_server_config()
    check = next((c for c in _security_checks(cfg) if c["id"] == data.id), None)
    if check is None:
        raise HTTPException(status_code=404, detail=f"Unknown check '{data.id}'")
    if check["severity"] != "warning":
        raise HTTPException(status_code=400,
                            detail="Only warnings can be acknowledged")
    acked = list(cfg.get("setup_acked", []) or [])
    if data.id not in acked:
        acked.append(data.id)
        cfg["setup_acked"] = acked
        cfg.store()
        audit(_current_user(request), "setup.ack", id=data.id)
    return setup_status()


@app.delete("/setup/ack/{check_id}", dependencies=[Depends(require_admin)])
def setup_unack(check_id: str, request: Request) -> Dict[str, Any]:
    """Re-enable a previously acknowledged warning."""
    cfg = get_server_config()
    acked = [a for a in (cfg.get("setup_acked", []) or []) if a != check_id]
    cfg["setup_acked"] = acked
    cfg.store()
    audit(_current_user(request), "setup.unack", id=check_id)
    return setup_status()


@app.get("/messages/recent", dependencies=[Depends(verify_credentials)])
def get_recent_messages(limit: int = 100, msg_type: Optional[str] = None,
                        peer: Optional[str] = None) -> List[Dict[str, Any]]:
    """Recent tapped HiveMessages (the live message inspector).

    Populated when hivemind-core runs in-process (the panel taps the listener
    protocol's ``handle_message``). Filter by ``msg_type`` or ``peer``.
    """
    from hivemind_admin_panel._metrics import METRICS
    return METRICS.recent_messages(limit=limit, msg_type=msg_type, peer=peer)


# ===================== Password change + config diff =====================

class PasswordChange(BaseModel):
    """Change the current user's password."""
    old_password: str
    new_password: str


@app.post("/auth/password", dependencies=[Depends(verify_credentials)])
def change_password(data: PasswordChange, request: Request) -> Dict[str, str]:
    """Change the current user's password (stored hashed with PBKDF2)."""
    from hivemind_admin_panel._auth import hash_password
    cfg = get_server_config()
    user = _current_user(request)
    if not authenticate(cfg, user, data.old_password):
        raise HTTPException(status_code=401, detail="Old password is incorrect")
    hashed = hash_password(data.new_password)
    if cfg.get("admin_user", "admin") == user:
        cfg["admin_pass"] = hashed
    else:
        users = cfg.get("users", []) or []
        for u in users:
            if u.get("username") == user:
                u["password"] = hashed
        cfg["users"] = users
    cfg.store()
    audit(user, "password.changed")
    return {"status": "ok"}


@app.post("/config/diff", dependencies=[Depends(verify_credentials)])
def config_diff(data: ConfigUpdate) -> Dict[str, Any]:
    """Diff a proposed config against the current server.json (dry-run preview)."""
    current = dict(get_server_config())
    proposed = data.config or {}
    added = {k: proposed[k] for k in proposed if k not in current}
    removed = {k: current[k] for k in current if k not in proposed}
    changed = {k: {"from": current[k], "to": proposed[k]}
               for k in proposed if k in current and current[k] != proposed[k]}
    return {"added": added, "removed": removed, "changed": changed,
            "has_changes": bool(added or removed or changed)}

