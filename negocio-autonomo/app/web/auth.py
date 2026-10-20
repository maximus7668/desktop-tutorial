"""Autenticación del panel: contraseñas con scrypt, sesión firmada con HMAC y token CSRF,
y límite de intentos de acceso."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import time

from .. import audit
from ..actors import SYSTEM
from ..db import now_iso, transaction

SESSION_TTL = 8 * 3600
COOKIE = "na_session"


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("la contraseña debe tener al menos 12 caracteres")
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, h_hex = stored.split("$")
    except ValueError:
        return False
    h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(h.hex(), h_hex)


def create_user(conn: sqlite3.Connection, username: str, password: str) -> None:
    with transaction(conn):
        conn.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)"
                     " ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash",
                     (username, hash_password(password), now_iso()))
        audit.log(conn, SYSTEM, "user.create_or_reset", username)


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> bool:
    r = conn.execute("SELECT password_hash FROM users WHERE username=?", (username,)).fetchone()
    if r is None:
        hashlib.scrypt(b"x", salt=b"0" * 16, n=2**14, r=8, p=1)  # tiempo similar exista o no el usuario
        return False
    return verify_password(password, r["password_hash"])


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_session(username: str, secret: str) -> str:
    body = _b64(json.dumps({"u": username, "exp": int(time.time()) + SESSION_TTL,
                            "csrf": secrets.token_urlsafe(24)}).encode())
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_session(token: str | None, secret: str) -> dict | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data


class RateLimiter:
    """Límite en memoria por clave (IP). Suficiente para una sola instancia."""

    def __init__(self, max_events: int, window_seconds: int):
        self.max, self.window = max_events, window_seconds
        self.events: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def hit(self, key: str) -> bool:
        now = time.time()
        with self.lock:
            ev = [t for t in self.events.get(key, []) if now - t < self.window]
            if len(ev) >= self.max:
                self.events[key] = ev
                return False
            ev.append(now)
            self.events[key] = ev
            return True
