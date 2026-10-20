"""Agente de operaciones: vigilancia de presupuesto e integridad, informes y copias de seguridad."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import audit, budget, finance, permissions, settings_store, tasks
from ..actors import Actor
from ..config import Settings
from ..db import now_iso, rows, transaction

AGENT = "operaciones"
KEEP_BACKUPS = 14


def _alert(conn: sqlite3.Connection, level: str, msg: str) -> None:
    with transaction(conn):
        recent = conn.execute("SELECT 1 FROM alerts WHERE message=? AND acknowledged=0", (msg,)).fetchone()
        if not recent:
            conn.execute("INSERT INTO alerts (ts, level, message) VALUES (?,?,?)", (now_iso(), level, msg))


def watch(conn: sqlite3.Connection, actor: Actor) -> dict:
    bal = budget.balance(conn)
    out = {"balance": bal, "actions": []}
    if bal["available_cents"] < 0 or bal["cash_balance_cents"] < bal["reserve_floor_cents"]:
        settings_store.activate_kill_switch(conn, actor, "el gasto comprometido supera el presupuesto")
        out["actions"].append("parada de emergencia")
    elif bal["cash_balance_cents"] < settings_store.get_int(conn, "low_balance_alert_cents"):
        _alert(conn, "warning", f"Saldo bajo: {bal['cash_balance_cents'] / 100:.2f} €")
    ok, broken = audit.verify_chain(conn)
    if not ok:
        settings_store.activate_kill_switch(conn, actor, f"registro de auditoría alterado (id {broken})")
        out["actions"].append("auditoría alterada")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(timespec="seconds")
    stale = conn.execute("SELECT COUNT(*) c FROM approvals WHERE status='pending' AND created_at < ?", (cutoff,)).fetchone()["c"]
    if stale:
        _alert(conn, "info", f"{stale} aprobaciones llevan más de 3 días pendientes")
    return out


def report(conn: sqlite3.Connection, actor: Actor, settings: Settings) -> Path:
    permissions.authorize(conn, actor, "report", "generate", "informe")
    fin = finance.summary(conn)
    data = {
        "generated_at": now_iso(),
        "environment": settings.app_env,
        "mode": settings_store.get(conn, "mode"),
        "kill_switch": settings_store.get(conn, "kill_switch"),
        "finance": fin,
        "tasks": tasks.stats(conn),
        "opportunities": rows(conn, "SELECT id, title, score, status FROM opportunities ORDER BY score DESC"),
        "experiments": rows(conn, "SELECT id, opportunity_id, status, verdict, decision FROM experiments"),
        "pending_approvals": rows(conn, "SELECT id, kind, summary FROM approvals WHERE status='pending'"),
        "open_alerts": rows(conn, "SELECT level, message FROM alerts WHERE acknowledged=0"),
    }
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = settings.reports_dir / f"informe-{settings.app_env}-{stamp}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    audit.log(conn, actor, "report.generate", path.name)
    return path


def backup(conn: sqlite3.Connection, actor: Actor, settings: Settings) -> Path:
    permissions.authorize(conn, actor, "backup", "run", "sqlite")
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = settings.backup_dir / f"{settings.app_env}-{stamp}.db"
    target = sqlite3.connect(dest)
    try:
        conn.backup(target)
    finally:
        target.close()
    olds = sorted(settings.backup_dir.glob(f"{settings.app_env}-*.db"))
    for old in olds[:-KEEP_BACKUPS]:
        old.unlink()
    audit.log(conn, actor, "backup.run", dest.name)
    return dest
