"""Motor de validación comercial: experimentos con presupuesto y criterio de éxito fijados ANTES
de empezar, medición y veredicto. Solo las compras reales validan una oportunidad; visitas o
registros como mucho son 'interés sin validar'. Los datos simulados nunca cuentan."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from . import approvals, audit, budget, memory, permissions, settings_store, tasks
from .actors import Actor
from .db import now_iso, one, rows, transaction

DEFAULT_MIN_VISITS = 100
DEFAULT_DAYS = 14
DEFAULT_SIGNUP_RATE = 8.0      # % de visitantes únicos que dejan su email
DEFAULT_PURCHASES = 3          # compras reales mínimas


def propose(conn: sqlite3.Connection, actor: Actor, opportunity_id: int) -> int:
    permissions.authorize(conn, actor, "experiment", "propose", f"opportunity:{opportunity_id}")
    opp = one(conn, "SELECT * FROM opportunities WHERE id=?", (opportunity_id,))
    if opp is None:
        raise KeyError(opportunity_id)
    prev = one(conn, "SELECT * FROM experiments WHERE opportunity_id=? ORDER BY id DESC LIMIT 1", (opportunity_id,))
    if prev and prev["status"] in ("draft", "approved", "running"):
        return prev["id"]
    commerce = settings_store.is_on(conn, "commerce_authorized")
    price = (opp["price_hint_cents"] or 1900) / 100
    step_up = prev is not None and prev["verdict"] == "interes_sin_validar"
    if commerce and step_up:
        metric, threshold = "purchases", float(DEFAULT_PURCHASES)
        design = (f"Preventa con pago real a {price:.2f} € (IVA incl.) mediante Payment Link. Tráfico orgánico "
                  "(comunidades y contactos del propietario). Sin anuncios salvo aprobación expresa.")
        hypothesis = f"Al menos {DEFAULT_PURCHASES} personas de '{opp['segment']}' pagarán {price:.2f} € por '{opp['product_idea']}' en {DEFAULT_DAYS} días."
    else:
        metric, threshold = "signup_rate", DEFAULT_SIGNUP_RATE
        design = (f"Smoke test: página de presentación con precio previsto {price:.2f} € y lista de espera "
                  "(sin cobro). Tráfico orgánico. Resultado máximo posible: 'interés sin validar'; para validar "
                  "hará falta una segunda prueba con pago real.")
        hypothesis = (f"Al menos un {DEFAULT_SIGNUP_RATE:.0f}% de los visitantes de '{opp['segment']}' dejará su email "
                      f"para '{opp['product_idea']}' sabiendo que costará {price:.2f} €.")
    available = budget.balance(conn)["available_cents"]
    max_budget = max(0, min(3000, available // 10))  # como mucho 30 € o el 10 % de lo disponible
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO experiments (opportunity_id, hypothesis, design, max_budget_cents, success_metric,"
            " success_threshold, min_visits, duration_days, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (opportunity_id, hypothesis, design, max_budget, metric, threshold, DEFAULT_MIN_VISITS, DEFAULT_DAYS,
             actor.label, now_iso()),
        )
        eid = cur.lastrowid
        conn.execute("UPDATE opportunities SET status='selected' WHERE id=?", (opportunity_id,))
        approvals.request(conn, actor, "experiment.start",
                          f"Experimento #{eid} sobre «{opp['title']}»: {metric} ≥ {threshold}, "
                          f"mín. {DEFAULT_MIN_VISITS} visitas, {DEFAULT_DAYS} días, presupuesto máx. {max_budget / 100:.2f} €",
                          "experiments", eid, {"hypothesis": hypothesis})
        audit.log(conn, actor, "experiment.propose", f"experiment:{eid}", {"metric": metric, "threshold": threshold})
    return eid


def _on_start_decision(conn: sqlite3.Connection, actor: Actor, ap: dict, approve: bool) -> None:
    eid = ap["ref_id"]
    if approve:
        conn.execute("UPDATE experiments SET status='approved', criteria_locked_at=? WHERE id=? AND status='draft'",
                     (now_iso(), eid))
        tasks.enqueue(conn, "product.build", "constructor", {"experiment_id": eid}, f"build:experiment:{eid}")
    else:
        exp = one(conn, "SELECT opportunity_id FROM experiments WHERE id=?", (eid,))
        conn.execute("UPDATE experiments SET status='abandoned', decision='abandon', conclusion=? WHERE id=?",
                     ("rechazado por el propietario antes de empezar", eid))
        conn.execute("UPDATE opportunities SET status='evaluated' WHERE id=?", (exp["opportunity_id"],))


approvals.ON_DECIDE["experiment.start"] = _on_start_decision


def start(conn: sqlite3.Connection, experiment_id: int) -> None:
    exp = one(conn, "SELECT * FROM experiments WHERE id=?", (experiment_id,))
    if exp and exp["status"] == "approved":
        ends = datetime.now(timezone.utc) + timedelta(days=exp["duration_days"])
        conn.execute("UPDATE experiments SET status='running', started_at=?, ends_at=? WHERE id=?",
                     (now_iso(), ends.isoformat(timespec="seconds"), experiment_id))
        conn.execute("UPDATE opportunities SET status='testing' WHERE id=?", (exp["opportunity_id"],))


def metrics(conn: sqlite3.Connection, experiment_id: int, data_kind: str = "real") -> dict:
    pids = [r["id"] for r in rows(conn, "SELECT id FROM products WHERE experiment_id=?", (experiment_id,))]
    out = {"visits": 0, "unique_visitors": 0, "signups": 0, "checkout_clicks": 0, "purchases": 0, "inquiries": 0}
    if not pids:
        return out
    ph = ",".join("?" * len(pids))
    for r in conn.execute(f"SELECT type, COUNT(*) c, COUNT(DISTINCT visitor_hash) u FROM events WHERE product_id IN ({ph})"
                          " AND data_kind=? GROUP BY type", (*pids, data_kind)):
        key = {"visit": "visits", "signup": "signups", "checkout_click": "checkout_clicks",
               "purchase": "purchases", "inquiry": "inquiries"}[r["type"]]
        out[key] = r["c"]
        if r["type"] == "visit":
            out["unique_visitors"] = r["u"]
    # Compras: la fuente de verdad son los pedidos pagados (verificados por webhook), no los eventos.
    out["purchases"] = conn.execute(f"SELECT COUNT(*) c FROM orders WHERE product_id IN ({ph}) AND status='paid'"
                                    " AND data_kind=?", (*pids, data_kind)).fetchone()["c"]
    out["signup_rate"] = round(100 * out["signups"] / out["unique_visitors"], 2) if out["unique_visitors"] else 0.0
    return out


def evaluate(conn: sqlite3.Connection, actor: Actor, experiment_id: int, force: bool = False) -> dict:
    exp = one(conn, "SELECT * FROM experiments WHERE id=?", (experiment_id,))
    if exp is None or exp["status"] != "running":
        return {"verdict": "no_en_curso"}
    real = metrics(conn, experiment_id, "real")
    sim = metrics(conn, experiment_id, "simulation")
    ended = exp["ends_at"] and datetime.fromisoformat(exp["ends_at"]) <= datetime.now(timezone.utc)
    metric, thr = exp["success_metric"], exp["success_threshold"]

    if metric == "purchases" and real["purchases"] >= thr:
        verdict, decision = "validada", "continue"
    elif not ended and not force and real["unique_visitors"] < exp["min_visits"]:
        return {"verdict": "en_curso", "real": real, "simulation": sim}
    elif real["unique_visitors"] < exp["min_visits"]:
        verdict, decision = "datos_insuficientes", "modify"
    elif metric == "signup_rate" and real["signup_rate"] >= thr:
        verdict, decision = "interes_sin_validar", "modify"
    elif metric == "purchases" and real["purchases"] > 0:
        verdict, decision = "interes_sin_validar", "modify"
    else:
        verdict, decision = "no_validada", "abandon"

    texts = {
        "validada": "Compras reales por encima del umbral fijado de antemano: se puede invertir más, con cautela.",
        "interes_sin_validar": "Hay interés medible pero no compras suficientes. Siguiente paso: prueba con pago real.",
        "datos_insuficientes": "No se alcanzó el tráfico mínimo: el resultado no permite concluir. Cambiar canal o mensaje.",
        "no_validada": "El interés real quedó por debajo del umbral. Se abandona y se registra la lección.",
    }
    conclusion = texts[verdict]
    if sim["visits"] or sim["purchases"]:
        conclusion += " (Los datos simulados se muestran aparte y no cuentan para el veredicto.)"
    opp_status = {"continue": "validated", "modify": "evaluated", "abandon": "abandoned"}[decision]
    with transaction(conn):
        conn.execute("UPDATE experiments SET status='completed', result=?, verdict=?, decision=?, conclusion=? WHERE id=?",
                     (json.dumps({"real": real, "simulation": sim}), verdict, decision, conclusion, experiment_id))
        conn.execute("UPDATE opportunities SET status=? WHERE id=?", (opp_status, exp["opportunity_id"]))
        conn.execute("UPDATE products SET status='retired' WHERE experiment_id=? AND status='published'"
                     " AND ? = 'abandon'", (experiment_id, decision))
        audit.log(conn, actor, "experiment.evaluate", f"experiment:{experiment_id}",
                  {"verdict": verdict, "decision": decision, "real": real})
    opp = one(conn, "SELECT title FROM opportunities WHERE id=?", (exp["opportunity_id"],))
    memory.remember(conn, actor, "lesson", opp["title"],
                    f"Experimento #{experiment_id}: {exp['hypothesis']} Resultado real: {real}. "
                    f"Veredicto: {verdict}. {conclusion}",
                    f"{decision}:experiment:{experiment_id}")
    return {"verdict": verdict, "decision": decision, "real": real, "simulation": sim, "conclusion": conclusion}
