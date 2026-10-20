"""Agente director: decide el siguiente paso con reglas explícitas. No gasta: propone y pide aprobación.

Ciclo:
 1. Parada de emergencia → no hace nada.
 2. Evalúa oportunidades nuevas.
 3. Revisa experimentos en curso (veredicto al terminar el plazo o el tráfico mínimo).
 4. Si no hay experimento activo, elige la mejor oportunidad que supere el umbral y no repita un
    fracaso anterior, y propone el experimento más barato (requiere aprobación humana)."""
from __future__ import annotations

import sqlite3

from .. import audit, memory, settings_store, validation
from ..actors import Actor, agent
from ..db import rows
from . import evaluator

AGENT = "director"
MIN_SCORE = 55.0


def cycle(conn: sqlite3.Connection, actor: Actor) -> dict:
    out: dict = {"actions": []}
    if settings_store.is_on(conn, "kill_switch"):
        return {"actions": ["detenido: parada de emergencia"]}
    evaluated = evaluator.evaluate_all_new(conn, agent(evaluator.AGENT))
    if evaluated:
        out["actions"].append(f"evaluadas {len(evaluated)} oportunidades")

    for e in rows(conn, "SELECT id FROM experiments WHERE status='running'"):
        r = validation.evaluate(conn, actor, e["id"])
        if r["verdict"] != "en_curso":
            out["actions"].append(f"experimento {e['id']}: {r['verdict']} → {r['decision']}")

    active = rows(conn, "SELECT id, status FROM experiments WHERE status IN ('draft','approved','running')")
    if active:
        out["actions"].append(f"experimento activo #{active[0]['id']} ({active[0]['status']}); un experimento cada vez")
        return out

    candidates = rows(conn, "SELECT * FROM opportunities WHERE status='evaluated' AND score >= ? ORDER BY score DESC",
                      (MIN_SCORE,))
    for opp in candidates:
        failed = memory.similar_failed(conn, opp["title"])
        if failed:
            audit.log(conn, actor, "director.skip", f"opportunity:{opp['id']}",
                      {"reason": "parecida a un experimento abandonado", "lesson": failed["id"]})
            continue
        abandoned_same = rows(conn, "SELECT id FROM experiments WHERE opportunity_id=? AND decision='abandon'",
                              (opp["id"],))
        if abandoned_same:
            continue
        eid = validation.propose(conn, actor, opp["id"])
        memory.remember(conn, actor, "decision", f"Proponer experimento #{eid}",
                        f"Elegida «{opp['title']}» (puntuación {opp['score']}) por ser la mejor por encima de "
                        f"{MIN_SCORE} sin fracasos previos similares.", f"experiment:{eid}")
        out["actions"].append(f"propuesto experimento #{eid} para «{opp['title']}» (pendiente de aprobación)")
        return out
    out["actions"].append(f"ninguna oportunidad supera {MIN_SCORE} puntos: hace falta más investigación")
    return out
