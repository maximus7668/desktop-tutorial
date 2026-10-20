"""Ajustes de operación guardados en BD (modo, parada de emergencia, límites).
Solo una persona puede cambiarlos; cualquier actor puede ACTIVAR la parada, nadie salvo una persona la quita."""
from __future__ import annotations

import sqlite3

from . import audit
from .actors import SYSTEM, Actor, require_human
from .db import now_iso, transaction

DEFAULTS: dict[str, str] = {
    "mode": "2",                          # 1 investigación | 2 validación controlada | 3 operación supervisada
    "kill_switch": "off",
    "queue_paused": "off",
    "commerce_authorized": "off",         # cobros reales: solo tras checklist legal/fiscal y decisión humana
    "capital_cents": "50000",             # 500 € iniciales
    "reserve_floor_cents": "10000",       # 100 € intocables: el sistema nunca gasta por debajo
    "max_daily_spend_cents": "2000",
    "max_single_spend_cents": "5000",
    "api_envelope_month_cents": "0",      # gasto de API preautorizado al mes (lo fija el propietario)
    "llm_max_calls_per_agent_day": "40",
    "low_balance_alert_cents": "20000",
    "publish_daily_limit": "3",
}

VALID_MODES = ("1", "2", "3")


def get(conn: sqlite3.Connection, key: str) -> str:
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else DEFAULTS[key]


def get_int(conn: sqlite3.Connection, key: str) -> int:
    return int(get(conn, key))


def is_on(conn: sqlite3.Connection, key: str) -> bool:
    return get(conn, key) == "on"


def _write(conn: sqlite3.Connection, key: str, value: str, actor: Actor) -> None:
    conn.execute(
        "INSERT INTO settings (key, value, updated_at, updated_by) VALUES (?,?,?,?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at,"
        " updated_by=excluded.updated_by",
        (key, value, now_iso(), actor.label),
    )


def initialize(conn: sqlite3.Connection, overrides: dict[str, str] | None = None) -> None:
    """Primer arranque: escribe valores por defecto que aún no existan (nunca sobrescribe)."""
    vals = {**DEFAULTS, **(overrides or {})}
    with transaction(conn):
        for k, v in vals.items():
            if conn.execute("SELECT 1 FROM settings WHERE key=?", (k,)).fetchone() is None:
                _write(conn, k, v, SYSTEM)


def set_value(conn: sqlite3.Connection, actor: Actor, key: str, value: str) -> None:
    require_human(actor, f"cambiar ajuste {key}")
    if key not in DEFAULTS:
        raise KeyError(key)
    if key == "mode" and value not in VALID_MODES:
        raise ValueError("modo no válido")
    if key == "commerce_authorized" and value == "on":
        from .compliance import missing_for
        missing = missing_for(conn, "commerce")
        if missing:
            raise PermissionError("Faltan requisitos legales/fiscales: " + ", ".join(missing))
    if key.endswith("_cents") or key.endswith("_limit") or key.endswith("_day"):
        if int(value) < 0:
            raise ValueError("valor negativo")
    old = get(conn, key)
    with transaction(conn):
        _write(conn, key, value, actor)
        audit.log(conn, actor, "setting.change", key, {"old": old, "new": value})


def activate_kill_switch(conn: sqlite3.Connection, actor: Actor, reason: str) -> None:
    with transaction(conn):
        _write(conn, "kill_switch", "on", actor)
        audit.log(conn, actor, "kill_switch.on", "", {"reason": reason})
        conn.execute(
            "INSERT INTO alerts (ts, level, message) VALUES (?,?,?)",
            (now_iso(), "critical", f"Parada de emergencia activada por {actor.label}: {reason}"),
        )


def release_kill_switch(conn: sqlite3.Connection, actor: Actor) -> None:
    require_human(actor, "desactivar la parada de emergencia")
    with transaction(conn):
        _write(conn, "kill_switch", "off", actor)
        audit.log(conn, actor, "kill_switch.off")
