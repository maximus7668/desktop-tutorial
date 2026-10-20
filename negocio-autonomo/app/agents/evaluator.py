"""Agente evaluador: puntuación determinista y explicable (0-100). No usa el modelo, así es
reproducible, gratis y no manipulable por texto externo."""
from __future__ import annotations

import json
import sqlite3
from urllib.parse import urlparse

from .. import audit, permissions
from ..actors import Actor
from ..db import one, rows, transaction

AGENT = "evaluador"

WEIGHTS = {
    "demanda": 0.25,
    "disposicion_a_pagar": 0.25,
    "competencia": 0.10,
    "coste_construccion": 0.15,
    "tiempo_primera_venta": 0.10,
    "riesgo_legal": 0.05,
    "encaje": 0.10,
}
MIN_INDEPENDENT_SOURCES = 2


def _cost_points(eur: float) -> float:
    return 5 if eur <= 50 else 3 if eur <= 150 else 1 if eur <= 300 else 0


def _time_points(days: int) -> float:
    return 5 if days <= 14 else 3 if days <= 30 else 1 if days <= 60 else 0


def score(opportunity: dict, evidence: list[dict]) -> dict:
    est = json.loads(opportunity["inputs"])
    kinds = {e["kind"] for e in evidence if e["reliability"] != "low"}
    domains = {(urlparse(e["url"]).hostname or "").removeprefix("www.") for e in evidence if e["reliability"] != "low"}
    notes = []

    demand = est["demand"]
    if not kinds & {"demand", "pain"}:
        demand = min(demand, 2)
        notes.append("sin evidencia de demanda: demanda limitada a 2/5")
    wtp = est["willingness_to_pay"]
    if not kinds & {"willingness_to_pay", "price"}:
        wtp = min(wtp, 2)
        notes.append("sin evidencia de precio/pago: disposición a pagar limitada a 2/5")

    pts = {
        "demanda": demand,
        "disposicion_a_pagar": wtp,
        "competencia": 5 - est["competition_intensity"],
        "coste_construccion": _cost_points(est["build_cost_eur"]),
        "tiempo_primera_venta": _time_points(est["time_to_first_sale_days"]),
        "riesgo_legal": 5 - est["legal_risk"],
        "encaje": est["fit"],
    }
    total = sum(WEIGHTS[k] * v for k, v in pts.items()) / 5 * 100
    factor = 1.0
    if len(domains) < MIN_INDEPENDENT_SOURCES:
        factor = 0.6
        notes.append(f"menos de {MIN_INDEPENDENT_SOURCES} fuentes independientes fiables: puntuación x0,6")
    verified = sum(1 for e in evidence if e["verified"])
    return {
        "score": round(total * factor, 1),
        "points": pts,
        "weights": WEIGHTS,
        "independent_sources": len(domains),
        "verified_sources": verified,
        "notes": notes,
        "data_kind": "estimate",
    }


def evaluate(conn: sqlite3.Connection, actor: Actor, opportunity_id: int) -> dict:
    permissions.authorize(conn, actor, "opportunity", "evaluate", f"opportunity:{opportunity_id}")
    opp = one(conn, "SELECT * FROM opportunities WHERE id=?", (opportunity_id,))
    if opp is None:
        raise KeyError(opportunity_id)
    ev = rows(conn, "SELECT * FROM evidence WHERE opportunity_id=?", (opportunity_id,))
    result = score(opp, ev)
    with transaction(conn):
        conn.execute("UPDATE opportunities SET score=?, score_breakdown=?, status=CASE WHEN status='new'"
                     " THEN 'evaluated' ELSE status END WHERE id=?",
                     (result["score"], json.dumps(result, ensure_ascii=False), opportunity_id))
        audit.log(conn, actor, "opportunity.evaluate", f"opportunity:{opportunity_id}",
                  {"score": result["score"], "notes": result["notes"]})
    return result


def evaluate_all_new(conn: sqlite3.Connection, actor: Actor) -> list[dict]:
    out = []
    for o in rows(conn, "SELECT id FROM opportunities WHERE status='new'"):
        out.append({"id": o["id"], **evaluate(conn, actor, o["id"])})
    return out
