"""Pedidos, ingresos y resumen financiero. Separa siempre real / estimación / simulación."""
from __future__ import annotations

import sqlite3

from . import audit, budget
from .actors import Actor
from .db import now_iso, one, rows, transaction


def record_order(conn: sqlite3.Connection, actor: Actor, provider: str, external_id: str, amount_cents: int,
                 data_kind: str, product_id: int | None = None, currency: str = "eur") -> tuple[dict, bool]:
    """Idempotente por (provider, external_id): reintentar no duplica. Devuelve (pedido, creado)."""
    if data_kind not in ("real", "simulation"):
        raise ValueError("data_kind de pedido no válido")
    if amount_cents <= 0:
        raise ValueError("importe no válido")
    with transaction(conn):
        existing = one(conn, "SELECT * FROM orders WHERE provider=? AND external_id=?", (provider, external_id))
        if existing:
            return existing, False
        cur = conn.execute(
            "INSERT INTO orders (product_id, provider, external_id, amount_cents, currency, status, data_kind, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (product_id, provider, external_id, amount_cents, currency, "paid", data_kind, now_iso()),
        )
        oid = cur.lastrowid
        conn.execute(
            "INSERT INTO ledger (ts, kind, amount_cents, data_kind, category, source, order_id, notes)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (now_iso(), "revenue", amount_cents, data_kind, "venta", provider, oid, f"pedido {external_id}"),
        )
        if product_id:
            conn.execute("INSERT INTO events (product_id, ts, type, source, data_kind) VALUES (?,?,?,?,?)",
                         (product_id, now_iso(), "purchase", provider, data_kind))
        audit.log(conn, actor, "order.record", f"order:{oid}",
                  {"provider": provider, "amount_cents": amount_cents, "data_kind": data_kind})
        return one(conn, "SELECT * FROM orders WHERE id=?", (oid,)), True


def record_refund(conn: sqlite3.Connection, actor: Actor, provider: str, external_id: str) -> bool:
    with transaction(conn):
        o = one(conn, "SELECT * FROM orders WHERE provider=? AND external_id=?", (provider, external_id))
        if o is None or o["status"] == "refunded":
            return False
        conn.execute("UPDATE orders SET status='refunded' WHERE id=?", (o["id"],))
        conn.execute(
            "INSERT INTO ledger (ts, kind, amount_cents, data_kind, category, source, order_id, notes)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (now_iso(), "refund", -o["amount_cents"], o["data_kind"], "reembolso", provider, o["id"], external_id),
        )
        audit.log(conn, actor, "order.refund", f"order:{o['id']}")
        return True


def _ledger_sum(conn, kind: str, data_kind: str, date_from: str | None, date_to: str | None) -> int:
    q = "SELECT COALESCE(SUM(amount_cents),0) s FROM ledger WHERE kind=? AND data_kind=?"
    p: list = [kind, data_kind]
    if date_from:
        q += " AND ts >= ?"
        p.append(date_from)
    if date_to:
        q += " AND ts < ?"
        p.append(date_to + "T23:59:59~")
    return int(conn.execute(q, p).fetchone()["s"])


def summary(conn: sqlite3.Connection, date_from: str | None = None, date_to: str | None = None) -> dict:
    out: dict = {"budget": budget.balance(conn)}
    for dk in ("real", "estimate", "simulation"):
        rev = _ledger_sum(conn, "revenue", dk, date_from, date_to)
        ref = _ledger_sum(conn, "refund", dk, date_from, date_to)
        exp = _ledger_sum(conn, "expense", dk, date_from, date_to)
        out[dk] = {"revenue_cents": rev, "refunds_cents": ref, "expenses_cents": exp,
                   "net_cents": rev + ref + exp}
    q = "SELECT COALESCE(SUM(-amount_cents),0) s FROM ledger WHERE kind='expense' AND category=?"
    out["ads_spend_cents"] = int(conn.execute(q, ("ads",)).fetchone()["s"])
    out["api_spend_cents"] = int(conn.execute(q, ("api",)).fetchone()["s"])
    out["tools_spend_cents"] = int(conn.execute(
        "SELECT COALESCE(SUM(-amount_cents),0) s FROM ledger WHERE kind='expense' AND category IN ('tool','service','other')"
    ).fetchone()["s"])
    out["orders_real"] = conn.execute("SELECT COUNT(*) c FROM orders WHERE data_kind='real' AND status='paid'").fetchone()["c"]
    out["orders_simulation"] = conn.execute("SELECT COUNT(*) c FROM orders WHERE data_kind='simulation'").fetchone()["c"]
    out["refunds_count"] = conn.execute("SELECT COUNT(*) c FROM orders WHERE status='refunded'").fetchone()["c"]
    # Beneficio operativo: ingresos REALES - reembolsos reales - gastos (reales + estimados de API).
    out["operating_profit_cents"] = (out["real"]["revenue_cents"] + out["real"]["refunds_cents"]
                                     + out["real"]["expenses_cents"] + out["estimate"]["expenses_cents"])
    return out


def ledger(conn: sqlite3.Connection, date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    q, p = "SELECT * FROM ledger WHERE 1=1", []
    if date_from:
        q += " AND ts >= ?"
        p.append(date_from)
    if date_to:
        q += " AND ts < ?"
        p.append(date_to + "T23:59:59~")
    return rows(conn, q + " ORDER BY id DESC", tuple(p))
