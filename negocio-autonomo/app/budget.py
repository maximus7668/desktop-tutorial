"""Control de presupuesto aplicado en el servidor.

Reglas:
- Todo gasto se pide primero (reserva). La reserva cuenta contra el saldo desde ese momento.
- La comprobación y la reserva ocurren dentro de BEGIN IMMEDIATE: dos agentes no pueden gastar a la vez
  por encima del límite.
- Nunca se compromete por debajo del suelo de reserva (por defecto 100 € de los 500 €).
- Un gasto solo se ejecuta si está 'approved'. Lo aprueba una persona o, para API, un sobre mensual
  que el propietario fijó de antemano. Un agente no puede aprobar su propio gasto.
- Los ingresos NO amplían automáticamente el presupuesto: subir el capital es una decisión humana."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable

from . import approvals, audit, settings_store
from .actors import Actor, require_human
from .db import now_iso, one, rows, transaction

CATEGORIES = ("api", "tool", "ads", "service", "other")
_COMMITTED = "('pending','approved','executing')"


class BudgetError(Exception):
    pass


def _sum(conn: sqlite3.Connection, where: str, params: tuple = ()) -> int:
    r = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN status IN ('executed','failed') THEN COALESCE(actual_cents,0)"
        " ELSE amount_cents END),0) s FROM spend_requests WHERE " + where, params
    ).fetchone()
    return int(r["s"])


def committed_cents(conn: sqlite3.Connection) -> int:
    return _sum(conn, f"status IN {_COMMITTED} OR status IN ('executed','failed')")


def balance(conn: sqlite3.Connection) -> dict:
    capital = settings_store.get_int(conn, "capital_cents")
    floor = settings_store.get_int(conn, "reserve_floor_cents")
    spent = _sum(conn, "status IN ('executed','failed')")
    reserved = _sum(conn, f"status IN {_COMMITTED}")
    return {
        "capital_cents": capital,
        "reserve_floor_cents": floor,
        "spent_cents": spent,
        "reserved_cents": reserved,
        "available_cents": capital - floor - spent - reserved,
        "cash_balance_cents": capital - spent,
    }


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def request_spend(conn: sqlite3.Connection, actor: Actor, category: str, amount_cents: int, description: str,
                  idempotency_key: str, experiment_id: int | None = None) -> dict:
    """Crea (o devuelve, si ya existe con esa clave) una solicitud de gasto.
    El resultado tiene status: approved | pending | rejected."""
    if category not in CATEGORIES:
        raise ValueError("categoría no válida")
    if not isinstance(amount_cents, int) or amount_cents <= 0:
        raise ValueError("importe no válido")
    with transaction(conn):
        existing = one(conn, "SELECT * FROM spend_requests WHERE idempotency_key=?", (idempotency_key,))
        if existing:
            return existing
        if settings_store.is_on(conn, "kill_switch"):
            raise BudgetError("parada de emergencia activa: no se aceptan gastos")

        reason = None
        capital = settings_store.get_int(conn, "capital_cents")
        floor = settings_store.get_int(conn, "reserve_floor_cents")
        if amount_cents > settings_store.get_int(conn, "max_single_spend_cents"):
            reason = "supera el máximo por gasto"
        elif committed_cents(conn) + amount_cents > capital - floor:
            reason = "supera el presupuesto disponible (respetando el suelo de reserva)"
        elif _sum(conn, f"(status IN {_COMMITTED} OR status IN ('executed','failed')) AND created_at >= ?",
                  (_today(),)) + amount_cents > settings_store.get_int(conn, "max_daily_spend_cents"):
            reason = "supera el límite diario de gasto"
        elif experiment_id is not None:
            exp = one(conn, "SELECT max_budget_cents FROM experiments WHERE id=?", (experiment_id,))
            if exp is None:
                reason = "experimento inexistente"
            elif _sum(conn, f"experiment_id=? AND (status IN {_COMMITTED} OR status IN ('executed','failed'))",
                      (experiment_id,)) + amount_cents > exp["max_budget_cents"]:
                reason = "supera el presupuesto máximo del experimento"

        status, authorized_by, approval_id = "pending", None, None
        if reason:
            status = "rejected"
        elif category == "api":
            envelope = settings_store.get_int(conn, "api_envelope_month_cents")
            used = _sum(conn, f"category='api' AND (status IN {_COMMITTED} OR status IN ('executed','failed'))"
                              " AND created_at >= ?", (_month(),))
            if used + amount_cents <= envelope:
                status, authorized_by = "approved", "sobre-api-preautorizado"

        cur = conn.execute(
            "INSERT INTO spend_requests (agent, category, amount_cents, description, experiment_id, status, reason,"
            " idempotency_key, authorized_by, created_at, decided_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (actor.name, category, amount_cents, description, experiment_id, status, reason, idempotency_key,
             authorized_by, now_iso(), now_iso() if status != "pending" else None),
        )
        sid = cur.lastrowid
        if status == "pending":
            approval_id = approvals.request(
                conn, actor, "spend", f"Gasto {category}: {amount_cents / 100:.2f} € — {description}",
                "spend_requests", sid, {"amount_cents": amount_cents, "category": category})
            conn.execute("UPDATE spend_requests SET approval_id=? WHERE id=?", (approval_id, sid))
        audit.log(conn, actor, "spend.request", f"spend:{sid}",
                  {"category": category, "amount_cents": amount_cents, "status": status, "reason": reason})
        if status == "rejected":
            conn.execute("INSERT INTO alerts (ts, level, message) VALUES (?,?,?)",
                         (now_iso(), "warning", f"Gasto rechazado ({actor.label}): {reason}"))
        return one(conn, "SELECT * FROM spend_requests WHERE id=?", (sid,))


def _on_spend_decision(conn: sqlite3.Connection, actor: Actor, ap: dict, approve: bool) -> None:
    sr = one(conn, "SELECT * FROM spend_requests WHERE id=?", (ap["ref_id"],))
    if sr is None or sr["status"] != "pending":
        raise ValueError("la solicitud de gasto ya no está pendiente")
    if sr["agent"] == actor.name:
        raise PermissionError("nadie puede autorizar su propio gasto")
    if approve:
        bal = balance(conn)
        if bal["available_cents"] < 0:  # los límites pudieron bajar tras la solicitud
            conn.execute("UPDATE spend_requests SET status='rejected', reason=?, decided_at=? WHERE id=?",
                         ("presupuesto insuficiente en el momento de aprobar", now_iso(), sr["id"]))
            return
        conn.execute("UPDATE spend_requests SET status='approved', authorized_by=?, decided_at=? WHERE id=?",
                     (actor.label, now_iso(), sr["id"]))
    else:
        conn.execute("UPDATE spend_requests SET status='rejected', reason='rechazado por el propietario',"
                     " authorized_by=?, decided_at=? WHERE id=?", (actor.label, now_iso(), sr["id"]))


approvals.ON_DECIDE["spend"] = _on_spend_decision


def execute(conn: sqlite3.Connection, actor: Actor, spend_id: int,
            fn: Callable[[int], tuple[int, str]]) -> dict:
    """Ejecuta un gasto aprobado. fn(max_cents) realiza la acción externa y devuelve
    (coste_real_cents, data_kind). Si fn falla, el gasto queda 'failed' y se relanza el error."""
    with transaction(conn):
        sr = one(conn, "SELECT * FROM spend_requests WHERE id=?", (spend_id,))
        if sr is None:
            raise KeyError(spend_id)
        if settings_store.is_on(conn, "kill_switch"):
            raise BudgetError("parada de emergencia activa")
        if sr["status"] != "approved":
            audit.log(conn, actor, "spend.blocked", f"spend:{spend_id}", {"status": sr["status"]})
            raise BudgetError(f"gasto no ejecutable en estado '{sr['status']}'")
        conn.execute("UPDATE spend_requests SET status='executing' WHERE id=?", (spend_id,))
    try:
        actual, data_kind = fn(sr["amount_cents"])
    except Exception as e:
        with transaction(conn):
            conn.execute("UPDATE spend_requests SET status='failed', actual_cents=0, executed_at=?, reason=? WHERE id=?",
                         (now_iso(), f"error: {type(e).__name__}", spend_id))
            audit.log(conn, actor, "spend.failed", f"spend:{spend_id}", {"error": str(e)[:300]})
        raise
    with transaction(conn):
        conn.execute("UPDATE spend_requests SET status='executed', actual_cents=?, executed_at=? WHERE id=?",
                     (actual, now_iso(), spend_id))
        if actual > 0:
            conn.execute(
                "INSERT INTO ledger (ts, kind, amount_cents, data_kind, category, source, spend_request_id, notes)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (now_iso(), "expense", -actual, data_kind, sr["category"], actor.label, spend_id, sr["description"]),
            )
        if actual > sr["amount_cents"]:
            conn.execute("INSERT INTO alerts (ts, level, message) VALUES (?,?,?)",
                         (now_iso(), "critical", f"Gasto {spend_id} superó lo autorizado: {actual} > {sr['amount_cents']} céntimos"))
        audit.log(conn, actor, "spend.executed", f"spend:{spend_id}", {"actual_cents": actual, "data_kind": data_kind})
    return one(conn, "SELECT * FROM spend_requests WHERE id=?", (spend_id,))


def cancel(conn: sqlite3.Connection, actor: Actor, spend_id: int) -> None:
    require_human(actor, "cancelar gastos")
    with transaction(conn):
        conn.execute("UPDATE spend_requests SET status='cancelled' WHERE id=? AND status IN ('pending','approved')",
                     (spend_id,))
        conn.execute("UPDATE approvals SET status='expired' WHERE ref_table='spend_requests' AND ref_id=? AND status='pending'",
                     (spend_id,))
        audit.log(conn, actor, "spend.cancel", f"spend:{spend_id}")


def list_requests(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    return rows(conn, "SELECT * FROM spend_requests ORDER BY id DESC LIMIT ?", (limit,))
