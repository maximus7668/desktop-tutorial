"""Cola de tareas persistente: idempotencia, reintentos limitados con espera, arrendamiento (lease)
para recuperarse tras un reinicio, y pausa/reanudación sin perder estado."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from . import audit, settings_store
from .actors import Actor, require_human
from .db import now_iso, one, rows, transaction


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(conn: sqlite3.Connection, task_type: str, agent: str, payload: dict | None, idempotency_key: str,
            max_attempts: int = 3, delay_seconds: int = 0) -> tuple[int, bool]:
    """Devuelve (id, creada). Con la misma clave de idempotencia no se crea otra tarea."""
    with transaction(conn):
        ex = conn.execute("SELECT id FROM tasks WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if ex:
            return ex["id"], False
        ts = now_iso()
        cur = conn.execute(
            "INSERT INTO tasks (type, agent, payload, max_attempts, idempotency_key, run_after, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (task_type, agent, json.dumps(payload or {}, ensure_ascii=False), max_attempts, idempotency_key,
             _iso(_now() + timedelta(seconds=delay_seconds)), ts, ts),
        )
        return cur.lastrowid, True


def claim(conn: sqlite3.Connection, lease_seconds: int = 300) -> dict | None:
    """Toma la siguiente tarea lista. Las tareas 'running' con lease caducado (proceso caído) se recuperan."""
    if settings_store.is_on(conn, "queue_paused") or settings_store.is_on(conn, "kill_switch"):
        return None
    now = _iso(_now())
    with transaction(conn):
        t = one(conn,
                "SELECT * FROM tasks WHERE (status='pending' AND run_after <= ?)"
                " OR (status='running' AND lease_until < ?) ORDER BY run_after, id LIMIT 1", (now, now))
        if t is None:
            return None
        if t["status"] == "running" and t["attempts"] >= t["max_attempts"]:
            conn.execute("UPDATE tasks SET status='failed', last_error=?, updated_at=? WHERE id=?",
                         ("abandonada tras caída sin completar", now, t["id"]))
            return None
        conn.execute(
            "UPDATE tasks SET status='running', attempts=attempts+1, lease_until=?, updated_at=? WHERE id=?",
            (_iso(_now() + timedelta(seconds=lease_seconds)), now, t["id"]),
        )
        t["attempts"] += 1
        t["payload"] = json.loads(t["payload"])
        return t


def complete(conn: sqlite3.Connection, task_id: int, result: dict | None = None) -> None:
    with transaction(conn):
        conn.execute("UPDATE tasks SET status='done', result=?, lease_until=NULL, updated_at=? WHERE id=?",
                     (json.dumps(result or {}, ensure_ascii=False, default=str), now_iso(), task_id))


def fail(conn: sqlite3.Connection, task_id: int, error: str, retryable: bool = True) -> str:
    with transaction(conn):
        t = one(conn, "SELECT attempts, max_attempts FROM tasks WHERE id=?", (task_id,))
        if retryable and t["attempts"] < t["max_attempts"]:
            backoff = 30 * (2 ** (t["attempts"] - 1))
            conn.execute("UPDATE tasks SET status='pending', last_error=?, run_after=?, lease_until=NULL, updated_at=?"
                         " WHERE id=?", (error[:500], _iso(_now() + timedelta(seconds=backoff)), now_iso(), task_id))
            return "pending"
        conn.execute("UPDATE tasks SET status='failed', last_error=?, lease_until=NULL, updated_at=? WHERE id=?",
                     (error[:500], now_iso(), task_id))
        conn.execute("INSERT INTO alerts (ts, level, message) VALUES (?,?,?)",
                     (now_iso(), "warning", f"Tarea {task_id} fallida: {error[:200]}"))
        return "failed"


def set_paused(conn: sqlite3.Connection, actor: Actor, paused: bool) -> None:
    settings_store.set_value(conn, actor, "queue_paused", "on" if paused else "off")


def cancel(conn: sqlite3.Connection, actor: Actor, task_id: int) -> None:
    require_human(actor, "cancelar tareas")
    with transaction(conn):
        conn.execute("UPDATE tasks SET status='cancelled', updated_at=? WHERE id=? AND status IN ('pending','failed')",
                     (now_iso(), task_id))
        audit.log(conn, actor, "task.cancel", f"task:{task_id}")


# --- Programación periódica ---------------------------------------------------------------

DEFAULT_SCHEDULES = [
    ("ciclo-director", "director.cycle", "director", 6 * 3600),
    ("informe-diario", "ops.report", "operaciones", 24 * 3600),
    ("copia-seguridad", "ops.backup", "operaciones", 24 * 3600),
    ("vigilancia-presupuesto", "ops.watch", "operaciones", 3600),
]


def seed_schedules(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        for name, ttype, agent, interval in DEFAULT_SCHEDULES:
            conn.execute("INSERT OR IGNORE INTO schedules (name, task_type, agent, interval_seconds, next_run_at)"
                         " VALUES (?,?,?,?,?)", (name, ttype, agent, interval, now_iso()))


def tick_schedules(conn: sqlite3.Connection) -> list[int]:
    """Encola las tareas programadas vencidas. La clave incluye el hueco temporal: sin duplicados."""
    created = []
    now = _now()
    for s in rows(conn, "SELECT * FROM schedules WHERE enabled=1 AND next_run_at <= ?", (_iso(now),)):
        slot = s["next_run_at"]
        tid, new = enqueue(conn, s["task_type"], s["agent"], json.loads(s["payload"]), f"sched:{s['name']}:{slot}")
        if new:
            created.append(tid)
        with transaction(conn):
            conn.execute("UPDATE schedules SET next_run_at=? WHERE name=?",
                         (_iso(now + timedelta(seconds=s["interval_seconds"])), s["name"]))
    return created


def set_schedule_enabled(conn: sqlite3.Connection, actor: Actor, name: str, enabled: bool) -> None:
    require_human(actor, "pausar/reanudar programación")
    with transaction(conn):
        conn.execute("UPDATE schedules SET enabled=? WHERE name=?", (1 if enabled else 0, name))
        audit.log(conn, actor, "schedule." + ("resume" if enabled else "pause"), name)


def stats(conn: sqlite3.Connection) -> dict:
    return {r["status"]: r["c"] for r in conn.execute("SELECT status, COUNT(*) c FROM tasks GROUP BY status")}

