# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Authentication, roles and audit log for the admin panel.

Auth model
----------
Credentials live in ``server.json``. The legacy ``admin_user`` / ``admin_pass``
remain the primary full-admin account; an optional ``users`` list adds extra
accounts with roles:

    "users": [{"username": "ops", "password": "...", "role": "operator"}]

Roles: ``admin`` (full) and ``operator`` (read + non-destructive writes; barred
from destructive actions guarded by :func:`require_admin` at the API layer).

Sessions are stateless HMAC-signed bearer tokens, so the API accepts either HTTP
Basic (username/password) or ``Authorization: Bearer <token>``.

Passwords are compared in plaintext for parity with hivemind-core's existing
``server.json`` model; hashing them is tracked as a hardening follow-up.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from ovos_utils.log import LOG
from ovos_utils.xdg_utils import xdg_data_home

ADMIN = "admin"
OPERATOR = "operator"
TOKEN_TTL = 12 * 3600  # 12h


# --------------------------------------------------------------------------- users

def _users(config: Dict[str, Any]) -> List[Dict[str, str]]:
    """All admin accounts: the primary admin_user plus any extra `users`."""
    users = [{
        "username": config.get("admin_user", "admin"),
        "password": config.get("admin_pass", "admin"),
        "role": ADMIN,
    }]
    for u in config.get("users", []) or []:
        if u.get("username"):
            users.append({
                "username": u["username"],
                "password": u.get("password", ""),
                "role": u.get("role", OPERATOR),
            })
    return users


def authenticate(config: Dict[str, Any], username: str, password: str) -> Optional[str]:
    """Return the user's role if credentials match, else None (timing-safe)."""
    role = None
    for u in _users(config):
        user_ok = hmac.compare_digest(u["username"], username)
        pass_ok = hmac.compare_digest(u["password"], password)
        if user_ok and pass_ok:
            role = u["role"]
    return role


# --------------------------------------------------------------------------- tokens

def _secret(config: Dict[str, Any]) -> bytes:
    """Persistent signing secret, generated into server.json on first use."""
    secret = config.get("admin_token_secret")
    if not secret:
        secret = os.urandom(32).hex()
        try:
            config["admin_token_secret"] = secret
            config.store()
        except Exception as e:  # config may be a plain dict in tests
            LOG.debug(f"could not persist token secret: {e}")
    return secret.encode()


def create_token(config: Dict[str, Any], username: str, role: str, ttl: int = TOKEN_TTL) -> Dict[str, Any]:
    payload = {"sub": username, "role": role, "exp": int(time.time()) + ttl}
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(config), raw.encode(), hashlib.sha256).hexdigest()
    return {"token": f"{raw}.{sig}", "role": role, "expires": payload["exp"]}


def verify_token(config: Dict[str, Any], token: str) -> Optional[Dict[str, Any]]:
    try:
        raw, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(_secret(config), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        pad = "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(raw + pad))
    except Exception:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


# --------------------------------------------------------------------------- audit

def _audit_path() -> str:
    base = os.path.join(xdg_data_home(), "hivemind-admin")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "audit.log")


def audit(user: str, action: str, **data: Any) -> None:
    entry = {"ts": time.time(), "user": user, "action": action, **data}
    try:
        with open(_audit_path(), "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        LOG.debug(f"audit write failed: {e}")


def read_audit(limit: int = 200) -> List[Dict[str, Any]]:
    path = _audit_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()[-limit:]
    except Exception:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out
