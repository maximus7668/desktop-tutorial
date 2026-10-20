"""Cola de aprobaciones humanas. Un agente puede pedir; solo una persona puede decidir."""
from __future__ import annotations

import json
import sqlite3
from typing import Callable

from . import audit
from .actors import Actor, require_human
from .db import now_iso, one, rows, transaction

# kind -> función(conn, actor_humano, approval_dict, aprobado: bool) que aplica el efecto.
ON_DECIDE: dict[str, Callable[[sqlite3.Connection, Actor, dict, bool], None]] = {}


def request(conn: sqlite3.Connection, actor: Actor, kind: str, summary: str,
            ref_table: str | None = None, ref_id: int | None = None, payload: dict | None = None) -> int:
    with transaction(conn):
        existing = conn.execute(
            "SELECT id FROM approvals WHERE kind=? AND ref_table IS ? AND ref_id IS ? AND status='pending'",
            (kind, ref_table, ref_id),
        ).fetchone()
        if existing:
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO approvals (kind, ref_table, ref_id, requested_by, summary, payload, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (kind, ref_table, ref_id, actor.label, summary, json.dumps(payload or {}, ensure_ascii=False), now_iso()),
        )
        audit.log(conn, actor, "approval.request", f"approval:{cur.lastrowid}", {"kind": kind, "summary": summary})
        return cur.lastrowid


def decide(conn: sqlite3.Connection, actor: Actor, approval_id: int, approve: bool, note: str = "") -> dict:
    require_human(actor, "decidir aprobaciones")
    with transaction(conn):
        ap = one(conn, "SELECT * FROM approvals WHERE id=?", (approval_id,))
        if ap is None:
            raise KeyError(approval_id)
        if ap["status"] != "pending":
            raise ValueError(f"la aprobación ya está {ap['status']}")
        if ap["requested_by"] == actor.label:
            raise PermissionError("nadie puede aprobar su propia solicitud")
        status = "approved" if approve else "rejected"
        conn.execute(
            "UPDATE approvals SET status=?, decided_by=?, decided_at=?, note=? WHERE id=?",
            (status, actor.label, now_iso(), note, approval_id),
        )
        ap["status"] = status
        handler = ON_DECIDE.get(ap["kind"])
        if handler:
            handler(conn, actor, ap, approve)
        audit.log(conn, actor, f"approval.{status}", f"approval:{approval_id}", {"kind": ap["kind"], "note": note})
    return ap


def pending(conn: sqlite3.Connection) -> list[dict]:
    return rows(conn, "SELECT * FROM approvals WHERE status='pending' ORDER BY id")


def list_recent(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    return rows(conn, "SELECT * FROM approvals ORDER BY id DESC LIMIT ?", (limit,))
