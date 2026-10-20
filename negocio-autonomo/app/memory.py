"""Memoria persistente y revisable: lecciones, decisiones, errores y notas.
No se guardan contraseñas ni datos personales: el texto pasa por redacción y por un filtro de emails."""
from __future__ import annotations

import re
import sqlite3

from .actors import Actor
from .db import now_iso, rows, transaction
from .redact import redact

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _clean(text: str) -> str:
    return _EMAIL.sub("[email]", redact(text))


def remember(conn: sqlite3.Connection, actor: Actor, kind: str, title: str, content: str, ref: str = "") -> int:
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO memory (kind, title, content, ref, created_by, created_at) VALUES (?,?,?,?,?,?)",
            (kind, _clean(title)[:200], _clean(content)[:4000], ref, actor.label, now_iso()),
        )
        return cur.lastrowid


def recall(conn: sqlite3.Connection, kind: str | None = None, limit: int = 100) -> list[dict]:
    if kind:
        return rows(conn, "SELECT * FROM memory WHERE kind=? ORDER BY id DESC LIMIT ?", (kind, limit))
    return rows(conn, "SELECT * FROM memory ORDER BY id DESC LIMIT ?", (limit,))


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-záéíóúñü0-9]{4,}", s.lower())}


def similar_failed(conn: sqlite3.Connection, title: str, threshold: float = 0.5) -> dict | None:
    """Busca una lección de experimento abandonado parecida (Jaccard de palabras) para no repetirlo."""
    t = _tokens(title)
    if not t:
        return None
    for m in recall(conn, "lesson", 500):
        if "abandon" not in (m["ref"] or ""):
            continue
        o = _tokens(m["title"])
        if o and len(t & o) / len(t | o) >= threshold:
            return m
    return None
