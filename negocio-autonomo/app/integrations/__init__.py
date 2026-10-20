"""Integraciones externas. Cada una declara si está configurada, si se ha probado y qué permisos tiene.
Ninguna simula éxito: si no hay conexión real, lanza IntegrationNotConfigured o IntegrationError."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..db import now_iso, rows, transaction


class IntegrationNotConfigured(Exception):
    pass


class IntegrationError(Exception):
    pass


@dataclass
class IntegrationInfo:
    name: str
    configured: bool
    permissions: str
    setup: str  # instrucciones si falta configurar


def record_status(conn: sqlite3.Connection, info: IntegrationInfo, tested: bool | None = None, message: str = "") -> None:
    with transaction(conn):
        conn.execute(
            "INSERT INTO integration_status (name, configured, tested_at, test_ok, message, permissions)"
            " VALUES (?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET configured=excluded.configured,"
            " tested_at=COALESCE(excluded.tested_at, integration_status.tested_at),"
            " test_ok=COALESCE(excluded.test_ok, integration_status.test_ok),"
            " message=excluded.message, permissions=excluded.permissions",
            (info.name, int(info.configured), now_iso() if tested is not None else None,
             None if tested is None else int(tested), message or info.setup, info.permissions),
        )


def list_status(conn: sqlite3.Connection) -> list[dict]:
    return rows(conn, "SELECT * FROM integration_status ORDER BY name")
