"""Registro de auditoría de solo inserción, encadenado por hash SHA-256."""
from __future__ import annotations

import hashlib
import json
import sqlite3

from .actors import Actor
from .db import now_iso, transaction
from .redact import redact

GENESIS = "0" * 64


def _digest(prev: str, ts: str, actor: str, kind: str, action: str, target: str, details: str) -> str:
    raw = "|".join([prev, ts, actor, kind, action, target, details])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def log(conn: sqlite3.Connection, actor: Actor, action: str, target: str = "", details: dict | None = None) -> int:
    payload = redact(json.dumps(details or {}, ensure_ascii=False, sort_keys=True, default=str))
    with transaction(conn):
        prev = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = prev["hash"] if prev else GENESIS
        ts = now_iso()
        h = _digest(prev_hash, ts, actor.name, actor.kind, action, target or "", payload)
        cur = conn.execute(
            "INSERT INTO audit_log (ts, actor, actor_kind, action, target, details, prev_hash, hash)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (ts, actor.name, actor.kind, action, target or "", payload, prev_hash, h),
        )
        return cur.lastrowid


def verify_chain(conn: sqlite3.Connection) -> tuple[bool, int | None]:
    """Devuelve (True, None) si la cadena es íntegra, o (False, id_del_primer_registro_roto)."""
    prev = GENESIS
    for r in conn.execute("SELECT * FROM audit_log ORDER BY id"):
        expected = _digest(prev, r["ts"], r["actor"], r["actor_kind"], r["action"], r["target"], r["details"])
        if r["prev_hash"] != prev or r["hash"] != expected:
            return False, r["id"]
        prev = r["hash"]
    return True, None
