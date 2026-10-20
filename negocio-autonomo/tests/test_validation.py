"""Evaluación de oportunidades y veredictos de experimentos."""
from app import approvals, memory, validation
from app.actors import agent
from app.agents import director, evaluator, researcher
from app.db import now_iso

from .fixtures import research_fixture


def _setup_running_experiment(conn, owner, settings):
    researcher.import_research(conn, agent("investigador"), research_fixture())
    director.cycle(conn, agent("director"))
    exp = conn.execute("SELECT * FROM experiments").fetchone()
    ap = approvals.pending(conn)[0]
    approvals.decide(conn, owner, ap["id"], True)
    pid = conn.execute("INSERT INTO products (experiment_id, name, slug, status, created_by, created_at)"
                       " VALUES (?,?,?,?,?,?)", (exp["id"], "p", "p", "tested", "t", now_iso())).lastrowid
    conn.execute("UPDATE products SET status='published' WHERE id=?", (pid,))
    validation.start(conn, exp["id"])
    return exp["id"], pid


def _visits(conn, pid, n, kind, signups=0):
    for i in range(n):
        conn.execute("INSERT INTO events (product_id, ts, type, visitor_hash, data_kind) VALUES (?,?,?,?,?)",
                     (pid, now_iso(), "visit", f"v{kind}{i}", kind))
    for i in range(signups):
        conn.execute("INSERT INTO events (product_id, ts, type, visitor_hash, data_kind) VALUES (?,?,?,?,?)",
                     (pid, now_iso(), "signup", f"v{kind}{i}", kind))


def test_score_penalizes_thin_evidence(conn):
    researcher.import_research(conn, agent("investigador"), research_fixture())
    res = evaluator.evaluate_all_new(conn, agent("evaluador"))
    by_title = {conn.execute("SELECT title FROM opportunities WHERE id=?", (r["id"],)).fetchone()["title"]: r for r in res}
    strong, weak = by_title["Kit de plantillas de presupuestos para reformas"], by_title["Curso de cerámica online"]
    assert strong["score"] > weak["score"]
    assert any("fuentes independientes" in n for n in weak["notes"])


def test_criteria_locked_after_approval(conn, owner, settings):
    eid, _ = _setup_running_experiment(conn, owner, settings)
    import sqlite3

    import pytest
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE experiments SET success_threshold=0.1 WHERE id=?", (eid,))


def test_simulated_traffic_never_validates(conn, owner, settings):
    eid, pid = _setup_running_experiment(conn, owner, settings)
    _visits(conn, pid, 500, "simulation", signups=200)
    r = validation.evaluate(conn, agent("director"), eid, force=True)
    assert r["verdict"] == "datos_insuficientes"
    assert r["simulation"]["signups"] == 200


def test_signups_give_interest_but_not_validation(conn, owner, settings):
    eid, pid = _setup_running_experiment(conn, owner, settings)
    _visits(conn, pid, 120, "real", signups=15)
    r = validation.evaluate(conn, agent("director"), eid, force=True)
    assert r["verdict"] == "interes_sin_validar" and r["decision"] == "modify"


def test_low_interest_is_abandoned_and_remembered(conn, owner, settings):
    eid, pid = _setup_running_experiment(conn, owner, settings)
    _visits(conn, pid, 150, "real", signups=2)
    r = validation.evaluate(conn, agent("director"), eid, force=True)
    assert r["verdict"] == "no_validada" and r["decision"] == "abandon"
    opp_id, title = conn.execute("SELECT o.id, o.title FROM opportunities o JOIN experiments e ON e.opportunity_id=o.id"
                                 " WHERE e.id=?", (eid,)).fetchone()
    assert memory.similar_failed(conn, title) is not None
    director.cycle(conn, agent("director"))  # no debe repetir la oportunidad abandonada
    assert conn.execute("SELECT COUNT(*) c FROM experiments WHERE opportunity_id=?", (opp_id,)).fetchone()["c"] == 1


def test_only_real_purchases_validate(conn):
    from app import finance
    from app.actors import PUBLIC

    researcher.import_research(conn, agent("investigador"), research_fixture())
    eid = conn.execute(
        "INSERT INTO experiments (opportunity_id, hypothesis, design, max_budget_cents, success_metric, success_threshold,"
        " min_visits, duration_days, status, created_by, created_at) VALUES (1,'h','d',0,'purchases',3,100,14,'approved','t',?)",
        (now_iso(),)).lastrowid
    pid = conn.execute("INSERT INTO products (experiment_id, name, slug, status, created_by, created_at)"
                       " VALUES (?,?,?,?,?,?)", (eid, "p", "p", "published", "t", now_iso())).lastrowid
    validation.start(conn, eid)
    for i in range(5):
        finance.record_order(conn, PUBLIC, "stripe", f"sim{i}", 1900, "simulation", pid)
    assert validation.evaluate(conn, agent("director"), eid, force=True)["verdict"] == "datos_insuficientes"
    conn.execute("UPDATE experiments SET status='running', verdict=NULL WHERE id=?", (eid,))
    for i in range(3):
        finance.record_order(conn, PUBLIC, "stripe", f"real{i}", 1900, "real", pid)
    assert validation.evaluate(conn, agent("director"), eid)["verdict"] == "validada"
