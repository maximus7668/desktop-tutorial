"""Presupuesto: nunca se supera, la concurrencia no lo rompe, lo rechazado no se ejecuta."""
import threading

import pytest

from app import approvals, budget, settings_store
from app.actors import PermissionDenied, agent
from app.core import bootstrap
from app.db import connect


def test_never_exceeds_available_budget(conn, owner):
    settings_store.set_value(conn, owner, "max_daily_spend_cents", "100000")
    a = agent("director")
    approved_total = 0
    for i in range(20):  # 20 x 50 € = 1000 €, muy por encima de los 400 € disponibles
        sr = budget.request_spend(conn, a, "ads", 5000, f"campaña {i}", f"k{i}")
        if sr["status"] == "pending":
            approvals.decide(conn, owner, sr["approval_id"], True)
            approved_total += 5000
    bal = budget.balance(conn)
    assert approved_total == 40000  # 500 € - 100 € de suelo
    assert bal["available_cents"] == 0
    assert bal["capital_cents"] - bal["reserve_floor_cents"] >= budget.committed_cents(conn)


def test_single_and_daily_limits(conn, owner):
    a = agent("director")
    assert budget.request_spend(conn, a, "ads", 6000, "demasiado", "big")["status"] == "rejected"
    assert budget.request_spend(conn, a, "ads", 1500, "ok", "d1")["status"] == "pending"
    r = budget.request_spend(conn, a, "ads", 1000, "pasa del límite diario de 20 €", "d2")
    assert r["status"] == "rejected" and "diario" in r["reason"]


def test_concurrent_agents_cannot_overspend(settings, conn, owner):
    settings_store.set_value(conn, owner, "api_envelope_month_cents", "40000")
    settings_store.set_value(conn, owner, "max_daily_spend_cents", "100000")
    results, errors = [], []

    def worker(n):
        c = connect(settings.database_path)
        try:
            for i in range(10):
                sr = budget.request_spend(c, agent(f"agente{n}"), "api", 1000, "llamada", f"t{n}-{i}")
                results.append(sr["status"])
        except Exception as e:  # pragma: no cover
            errors.append(e)
        finally:
            c.close()

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]  # 80 x 10 € = 800 € pedidos
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert results.count("approved") == 40  # exactamente 400 €
    assert budget.committed_cents(conn) == 40000


def test_rejected_spend_is_never_executed(conn, owner):
    a = agent("director")
    sr = budget.request_spend(conn, a, "ads", 1000, "anuncio", "rej")
    approvals.decide(conn, owner, sr["approval_id"], False)
    called = []
    with pytest.raises(budget.BudgetError):
        budget.execute(conn, a, sr["id"], lambda m: called.append(1) or (m, "real"))
    assert not called
    assert conn.execute("SELECT COUNT(*) c FROM ledger WHERE kind='expense'").fetchone()["c"] == 0


def test_pending_spend_cannot_execute_and_agent_cannot_approve(conn):
    a = agent("director")
    sr = budget.request_spend(conn, a, "ads", 1000, "anuncio", "pend")
    with pytest.raises(budget.BudgetError):
        budget.execute(conn, a, sr["id"], lambda m: (m, "real"))
    with pytest.raises(PermissionDenied):
        approvals.decide(conn, a, sr["approval_id"], True)
    with pytest.raises(PermissionDenied):
        approvals.decide(conn, agent("operaciones"), sr["approval_id"], True)


def test_failed_execution_is_recorded_as_failure(conn, owner):
    a = agent("director")
    sr = budget.request_spend(conn, a, "ads", 1000, "anuncio", "fail")
    approvals.decide(conn, owner, sr["approval_id"], True)

    def boom(_):
        raise RuntimeError("API de anuncios caída")

    with pytest.raises(RuntimeError):
        budget.execute(conn, a, sr["id"], boom)
    row = conn.execute("SELECT status FROM spend_requests WHERE id=?", (sr["id"],)).fetchone()
    assert row["status"] == "failed"
    with pytest.raises(budget.BudgetError):  # no se puede reintentar el mismo gasto a escondidas
        budget.execute(conn, a, sr["id"], lambda m: (m, "real"))


def test_spend_request_is_idempotent(conn):
    a = agent("director")
    s1 = budget.request_spend(conn, a, "ads", 1000, "x", "same-key")
    s2 = budget.request_spend(conn, a, "ads", 1000, "x", "same-key")
    assert s1["id"] == s2["id"]
    assert conn.execute("SELECT COUNT(*) c FROM spend_requests").fetchone()["c"] == 1


def test_budget_survives_restart(settings, conn, owner):
    a = agent("director")
    sr = budget.request_spend(conn, a, "ads", 2000, "x", "persist")
    approvals.decide(conn, owner, sr["approval_id"], True)
    budget.execute(conn, a, sr["id"], lambda m: (1800, "real"))
    conn.close()
    c2 = bootstrap(settings)
    bal = budget.balance(c2)
    assert bal["spent_cents"] == 1800 and bal["available_cents"] == 40000 - 1800
    c2.close()
